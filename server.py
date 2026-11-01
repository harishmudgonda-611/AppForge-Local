#!/usr/bin/env python3
"""AppForge Local: personal, locally hosted app discovery and build workbench."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, os, urllib.request, urllib.error, re, subprocess, threading, time, ipaddress, shutil, tempfile
import advanced

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
WORKSPACE = ROOT / 'workspace'
CONFIG = ROOT / 'config.local.json'
STATE = ROOT / 'state'
for _private_dir in (WORKSPACE, STATE):
    if _private_dir.is_symlink() or (_private_dir.exists() and not _private_dir.is_dir()):
        raise RuntimeError(f'AppForge data directory must be a real directory: {_private_dir.name}')
    _private_dir.mkdir(exist_ok=True)
if CONFIG.is_symlink() or (CONFIG.exists() and not CONFIG.is_file()):
    raise RuntimeError('AppForge config.local.json must be a regular file, not a symlink or directory.')
FEEDBACK = STATE / 'feedback.jsonl'
if FEEDBACK.is_symlink() or (FEEDBACK.exists() and not FEEDBACK.is_file()):
    raise RuntimeError('AppForge feedback.jsonl must be a regular file, not a symlink or directory.')
ROADMAP = STATE / 'improvement-roadmap.json'
DEFAULT_CONFIG = {'llm_base_url':'http://127.0.0.1:8080/v1','llm_model':'qwen2.5-coder','llm_api_key':'','timeout_seconds':120}

def local_endpoint_allowed(value):
    try:
        parsed=urlparse(str(value))
        if parsed.scheme!='http' or not parsed.hostname: return False
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment: return False
        host=parsed.hostname.lower().rstrip('.')
        if host=='localhost': return True
        addr=ipaddress.ip_address(host)
        return bool(addr.is_loopback or addr.is_private or addr.is_link_local)
    except Exception:
        return False

def read_limited_json(response, limit=10_000_000):
    """Read a bounded JSON response from the configured local model server."""
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f'Local model response exceeds the {limit}-byte limit.')
    return json.loads(raw.decode('utf-8'))


def validate_generated_files(files):
    """Validate a model-generated PWA file map before writing anything to disk."""
    if not isinstance(files, dict) or not files:
        return None, 'The model did not provide any project files.'
    if len(files) > 80:
        return None, 'The model returned too many files (maximum 80).'
    normalized = {}
    total = 0
    for rel, content in files.items():
        if not isinstance(rel, str) or not rel or len(rel) > 160 or "\\" in rel:
            return None, 'Generated file paths must be short, relative POSIX paths.'
        path = Path(rel)
        if path.is_absolute() or any(part in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', part) for part in path.parts):
            return None, 'Generated file paths contain an unsupported or unsafe path segment.'
        filename = path.name.lower()
        if (filename.startswith('.env') or filename in ('google-services.json', 'id_rsa', 'id_ed25519', 'appforge-project.json', 'config.local.json')
                or filename.endswith(('.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.mobileprovision', '.provisionprofile', '.p8', '.ppk'))
                or any(marker in filename for marker in ('credential', 'secret', 'token', 'service-account'))):
            return None, f'Generated file {rel} has a sensitive filename and is not allowed.'
        if not isinstance(content, str):
            return None, f'Generated file {rel} must contain text.'
        size = len(content.encode('utf-8'))
        if size > 512_000:
            return None, f'Generated file {rel} exceeds the 512 KB limit.'
        total += size
        if total > 2_000_000:
            return None, 'Generated project exceeds the 2 MB total source limit.'
        normalized[rel] = content
    required = ('index.html', 'app.js', 'styles.css', 'manifest.webmanifest', 'sw.js')
    missing = [name for name in required if name not in normalized or not normalized[name].strip()]
    if missing:
        return None, 'Generated PWA is incomplete; required non-empty files: ' + ', '.join(missing)
    try:
        manifest = json.loads(normalized['manifest.webmanifest'])
        if not isinstance(manifest, dict) or not isinstance(manifest.get('name'), str) or not manifest['name'].strip():
            return None, 'manifest.webmanifest must be a JSON object with a non-empty name.'
    except Exception as exc:
        return None, 'manifest.webmanifest is invalid JSON: ' + str(exc)
    if shutil.which('node'):
        for js_name in ('app.js', 'sw.js'):
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile('w', suffix='.js', encoding='utf-8', delete=False) as temp:
                    temp.write(normalized[js_name])
                    temp_path = temp.name
                checked = subprocess.run(['node', '--check', temp_path], capture_output=True, text=True, timeout=20)
                if checked.returncode:
                    return None, f'Generated {js_name} failed JavaScript syntax validation: ' + checked.stderr[-1500:]
            except Exception as exc:
                return None, f'Could not validate generated {js_name}: ' + str(exc)
            finally:
                if temp_path:
                    try:
                        Path(temp_path).unlink()
                    except OSError:
                        pass
    return normalized, None


def validate_config_update(current, updates):
    """Return a validated config copy; never persist partially invalid settings."""
    if not isinstance(updates, dict):
        return None, 'Settings must be a JSON object.'
    cfg=dict(current)
    allowed=('llm_base_url','llm_model','llm_api_key','timeout_seconds')
    for key in allowed:
        if key in updates:
            cfg[key]=updates[key]
    base=cfg.get('llm_base_url')
    if not isinstance(base,str) or len(base)>512 or not local_endpoint_allowed(base):
        return None, 'Use an HTTP localhost or private-LAN model URL (maximum 512 characters), without credentials, query strings or fragments.'
    model=cfg.get('llm_model')
    if not isinstance(model,str) or not model.strip() or len(model)>200:
        return None, 'Model name must be 1–200 characters.'
    key=cfg.get('llm_api_key')
    if not isinstance(key,str) or len(key)>1000:
        return None, 'API key must be text and no longer than 1000 characters.'
    timeout=cfg.get('timeout_seconds')
    if isinstance(timeout,bool) or not isinstance(timeout,int) or not 5 <= timeout <= 600:
        return None, 'Timeout must be a whole number between 5 and 600 seconds.'
    cfg['llm_base_url']=base.rstrip('/')
    cfg['llm_model']=model.strip()
    return cfg, None

if not CONFIG.exists(): CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(STATIC),**kwargs)
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        super().end_headers()

    def send_json(self, obj, status=200):
        data=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def body(self):
        raw_length = self.headers.get('Content-Length')
        if raw_length is None:
            raise ValueError('Content-Length header is required')
        try:
            n = int(raw_length)
        except (TypeError, ValueError):
            raise ValueError('Invalid Content-Length')
        if n < 0:
            raise ValueError('Invalid Content-Length')
        if n > 2_000_000:
            raise ValueError('Request too large')
        raw = self.rfile.read(n)
        if len(raw) != n:
            raise ValueError('Incomplete request body')
        try:
            data = json.loads(raw or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('Request body must be valid JSON')
        if not isinstance(data, dict):
            raise ValueError('Request body must be a JSON object')
        return data
    def local_host_request_allowed(self):
        """Reject unexpected Host headers, including DNS-rebinding hostnames."""
        try:
            parsed=urlparse('//'+self.headers.get('Host',''))
            hostname=(parsed.hostname or '').lower().rstrip('.')
            return hostname == 'localhost' or ipaddress.ip_address(hostname).is_loopback
        except (ValueError, TypeError):
            return False

    def do_GET(self):
        if not self.local_host_request_allowed():
            return self.send_json({'error':'Request rejected: AppForge is available only through a loopback Host header.'},403)
        p=urlparse(self.path)
        if p.path.startswith('/api/'):
            try:
                q=parse_qs(p.query)
                if p.path=='/api/research/search': return self.send_json(advanced.research_search(q.get('term',[''])[0],q.get('region',['in'])[0],q.get('limit',['25'])[0]))
                if p.path=='/api/research/history': return self.send_json(advanced.history(q.get('app_id',[''])[0],q.get('limit',['30'])[0]))
                if p.path=='/api/research/reviews':
                    result=advanced.reviews(q.get('app_id',[''])[0],q.get('region',['us'])[0],q.get('limit',['25'])[0]); ratings=[r['rating'] for r in result['reviews'] if r['rating']]; result['rating_summary']={'count':len(ratings),'average':round(sum(ratings)/len(ratings),2) if ratings else None,'positive_4_5':sum(1 for r in ratings if r>=4),'negative_1_2':sum(1 for r in ratings if r<=2)}; return self.send_json(result)
                if p.path=='/api/analytics': return self.send_json(advanced.analytics(q.get('project',[''])[0]))
                if p.path=='/api/launch': return self.send_json(advanced.launch_config(q.get('project',[''])[0]))
                if p.path=='/api/integrations/aider': return self.send_json(advanced.repo_catalog())
            except ValueError as e: return self.send_json({'error':str(e),'retryable':False},400)
            except Exception as e: return self.send_json({'error':str(e),'retryable':True},502)
            if p.path=='/api/health':
                cfg=json.loads(CONFIG.read_text()); self.send_json({'ok':True,'workspace':str(WORKSPACE),'llm_base_url':cfg['llm_base_url'],'llm_model':cfg['llm_model'],'timeout_seconds':cfg.get('timeout_seconds',120),'api_key_configured':bool(cfg.get('llm_api_key')),'time':int(time.time())}); return
            if p.path=='/api/replica/workflows':
                self.send_json(advanced.replica_workflows()); return
            if p.path=='/api/repos':
                self.send_json({'repositories':[
                  {'name':'AppStoreCat','url':'https://github.com/appstorecat/appstorecat','role':'App market intelligence','fit':'Potentially useful as a separate research service for App Store / Google Play collection and search. Larger dependency footprint; evaluate deployment and data-source rules first.','integration':'Optional adapter over its API/database; do not copy scraper internals blindly.'},
                  {'name':'Replica Skill','url':'https://github.com/Jakeschincariol/replica-skill','role':'Eleven-stage app research, build, test, rebrand and launch workflow','fit':'Best match for AppForge workflow orchestration. MIT-licensed upstream; the external skill pack is referenced, not bundled.','integration':'AppForge-native stage adapter saves research/build artifacts locally and gates generation with owner approval.'},
                  {'name':'OpenHands','url':'https://github.com/OpenHands/OpenHands','role':'Self-hosted coding agent and automation','fit':'Could power later isolated code-writing, test/fix loops, and scheduled maintenance. Heavier runtime; best on a computer/server with Docker, not a low-resource phone.','integration':'Optional external agent backend; keep AppForge as control plane.'},
                  {'name':'Aider','url':'https://github.com/Aider-AI/aider','role':'Git-aware AI coding assistant','fit':'Practical optional code-edit/test loop that supports local models. CLI-oriented and lighter than a full agent platform.','integration':'Run as a controlled subprocess only after sandboxing and explicit project approval.'},
                  {'name':'OpenCode','url':'https://github.com/anomalyco/opencode','role':'Open-source coding agent','fit':'Alternative coding-agent backend with provider flexibility; verify current install requirements and license before packaging.','integration':'Adapter/CLI bridge; not a required dependency.'}
                ],'policy':'Review each repository license, security posture, dependencies, and maintenance status before vendoring or redistributing. Prefer adapters over copying entire projects.'}); return
            if p.path=='/api/projects':
                projects=[]
                for d in sorted(WORKSPACE.iterdir(),key=lambda x:x.lstat().st_mtime,reverse=True):
                    if d.is_symlink() or not d.is_dir(): continue
                    projects.append({'name':d.name,'updated':int(d.stat().st_mtime),'files':[x.name for x in d.iterdir() if x.is_file() and not x.is_symlink()]})
                self.send_json({'projects':projects}); return
            if p.path=='/api/trends':
                region=parse_qs(p.query).get('region',['in'])[0]
                try:
                    result=advanced.snapshot(region)
                    self.send_json(result); return
                except Exception as e:
                    self.send_json({'source':'Apple RSS unavailable','region':region,'apps':[],'error':str(e),'note':'Retries were attempted. Check connectivity or use App Store search; no rankings are invented.'},502); return
            if p.path=='/api/apk':
                name=q.get('project',[''])[0]
                base=self.safe_path(name)
                if not base or not base.is_dir():
                    self.send_json({'error':'Project not found'},404); return
                apk=base/'android'/'app'/'build'/'outputs'/'apk'/'debug'/'app-debug.apk'
                current=base
                for part in ('android','app','build','outputs','apk','debug','app-debug.apk'):
                    current=current/part
                    if current.is_symlink():
                        self.send_json({'error':'APK artifact path contains a symlink.'},404); return
                if not apk.is_file() or apk.stat().st_size<=0 or not apk.resolve().is_relative_to(base.resolve()):
                    self.send_json({'error':'Verified debug APK not found. Run an approved build first.'},404); return
                self.send_response(200)
                self.send_header('Content-Type','application/vnd.android.package-archive')
                self.send_header('Content-Length',str(apk.stat().st_size))
                self.send_header('Content-Disposition','attachment; filename="app-debug.apk"')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                with apk.open('rb') as artifact:
                    while True:
                        chunk=artifact.read(1024*1024)
                        if not chunk: break
                        self.wfile.write(chunk)
                return
            if p.path=='/api/file':
                name=parse_qs(p.query).get('project',[''])[0]; file=parse_qs(p.query).get('file',[''])[0]
                target=self.safe_path(name,file)
                if not target or not target.is_file(): self.send_json({'error':'File not found'},404); return
                self.send_json({'project':name,'file':file,'content':target.read_text(errors='replace')}); return
            return self.send_json({'error':'Not found'},404)
        return super().do_GET()
    def safe_path(self, project, filename=''):
        if not isinstance(project, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', project): return None
        if not isinstance(filename, str): return None
        if filename and (Path(filename).name!=filename or filename in ('.','..')): return None
        workspace = WORKSPACE.resolve()
        candidate = workspace / project
        if candidate.is_symlink(): return None
        base = candidate.resolve()
        if base.parent != workspace: return None
        if not filename: return base
        target = (base / filename).resolve()
        # A filename can be a symlink; ensure its resolved target remains inside
        # the selected project before serving or modifying it.
        if target.parent != base and base not in target.parents: return None
        return target
    def same_origin_request_allowed(self):
        """Reject browser cross-origin writes and non-loopback Host headers.

        Origin-less requests remain available to local CLI clients. This is a
        defence-in-depth check, not authentication; keep the server on loopback.
        """
        host_header=self.headers.get('Host','')
        try:
            host=urlparse('//'+host_header)
            hostname=(host.hostname or '').lower().rstrip('.')
            if hostname!='localhost' and not ipaddress.ip_address(hostname).is_loopback:
                return False
            origin=self.headers.get('Origin')
            if origin:
                parsed=urlparse(origin)
                if parsed.scheme!='http' or not parsed.hostname:
                    return False
                origin_host=parsed.hostname.lower().rstrip('.')
                if origin_host!=hostname:
                    return False
                host_port=host.port or 80
                origin_port=parsed.port or (80 if parsed.scheme=='http' else 443)
                if origin_port!=host_port:
                    return False
            fetch_site=self.headers.get('Sec-Fetch-Site','').lower()
            if fetch_site and fetch_site not in ('same-origin','none'):
                return False
            return True
        except (ValueError, TypeError):
            return False

    def do_POST(self):
        if not self.same_origin_request_allowed():
            return self.send_json({'error':'Request rejected: AppForge accepts write requests only from its local same-origin interface.'},403)
        try: data=self.body()
        except Exception as e: return self.send_json({'error':str(e)},400)
        try:
            if self.path=='/api/replica/run':
                result=advanced.replica_run(data,self.call_llm_data)
                return self.send_json(result['body'],result.get('status',200))
            if self.path in ('/api/aider/run','/api/test-repair') and data.get('approved') is not True:
                return self.send_json({'error':'Explicit boolean approval is required for this operation.','requires_approval':True},403)
            if self.path=='/api/aider/run': return self.send_json(advanced.run_aider(str(data.get('project','')),str(data.get('prompt','')),True))
            if self.path=='/api/test-repair': return self.send_json(advanced.repair_project(str(data.get('project','')),True))
            if self.path=='/api/research/snapshot': return self.send_json(advanced.snapshot(str(data.get('region','in'))))
            if self.path=='/api/template/capacitor': return self.send_json(advanced.create_capacitor(str(data.get('project','')),data.get('app_name')))
            if self.path=='/api/test-run':
                run_npm_tests=data.get('run_npm_tests') is True
                if run_npm_tests and data.get('approved') is not True:
                    return self.send_json({'error':'Explicit boolean approval is required before executing project npm scripts.','requires_approval':True},403)
                return self.send_json(advanced.test_project(str(data.get('project','')),bool(data.get('repair',False)),run_npm_tests=run_npm_tests))
            if self.path=='/api/git': return self.send_json(advanced.git_action(str(data.get('project','')),str(data.get('action','status'))))
            if self.path=='/api/launch': return self.send_json(advanced.launch_config(str(data.get('project','')),data.get('config')))
            if self.path=='/api/track': return self.send_json(advanced.track_event(data.get('project',''),data.get('event','manual'),data.get('value'),data.get('metadata')))
        except Exception as e: return self.send_json({'error':str(e)},400)
        if self.path=='/api/config':
            current=json.loads(CONFIG.read_text())
            cfg,error=validate_config_update(current,data)
            if error: return self.send_json({'error':error},400)
            CONFIG.write_text(json.dumps(cfg,indent=2))
            return self.send_json({'ok':True,'config':{k:v for k,v in cfg.items() if k!='llm_api_key'}})
        if self.path=='/api/feedback':
            if not isinstance(data.get('feedback'),str) or not data['feedback'].strip(): return self.send_json({'error':'Feedback text is required.'},400)
            entry={'time':int(time.time()),'feedback':data['feedback'].strip()[:4000],'kind':str(data.get('kind','general'))[:40]}
            with FEEDBACK.open('a',encoding='utf-8') as f: f.write(json.dumps(entry,ensure_ascii=False)+'\n')
            return self.send_json({'ok':True,'message':'Feedback saved locally for future improvement reviews.'})
        if self.path=='/api/evolve':
            cfg=json.loads(CONFIG.read_text())
            projects=[]
            for d in WORKSPACE.iterdir():
                mf=d/'appforge-project.json'
                if d.is_dir() and mf.exists():
                    try: projects.append(json.loads(mf.read_text()))
                    except Exception: pass
            feedback=[]
            if FEEDBACK.exists():
                for line in FEEDBACK.read_text(encoding='utf-8').splitlines()[-40:]:
                    try: feedback.append(json.loads(line))
                    except Exception: pass
            context={'projects':projects[-20:],'feedback':feedback,'current_features':['Apple top-free chart snapshot','AI gap analysis','AI code generation','basic file checks','local project workspace']}
            system='You are the principal engineer for a locally hosted app research/build tool. Propose safe, incremental self-improvements based on evidence. Never claim a test passed unless data proves it. Never recommend copying proprietary app code. Return: (1) top 5 prioritized improvements with impact/effort/confidence, (2) tests and acceptance criteria, (3) risks, (4) what must be approved by the owner. Do not modify files; this is a proposal only.'
            user='Review this current local state and suggest the next version roadmap. Distinguish evidence from hypotheses.\n'+json.dumps(context,ensure_ascii=False)[:18000]
            return self.call_llm(system,user)
        if self.path=='/api/analyze':
            prompt=data.get('prompt','')
            if not isinstance(prompt,str) or not prompt.strip(): return self.send_json({'error':'Add an app idea or competitor to analyze as text.'},400)
            prompt=prompt.strip()[:12000]
            system='You are AppForge Local, an ethical app market researcher. Analyze only public-facing product positioning, features, reviews/complaints supplied by user, and opportunity hypotheses. Never claim live download/revenue data unless provided. Do not reproduce proprietary code, protected assets, or branding. Return practical sections: audience, problem, competitor comparison, likely gaps, differentiators, MVP, monetization, risks, validation experiments.'
            return self.call_llm(system,prompt)
        if self.path=='/api/generate':
            slug=data.get('slug','NewApp')
            brief=data.get('brief','')
            if not isinstance(slug,str) or not isinstance(brief,str):
                return self.send_json({'error':'Project slug and app brief must be text.'},400)
            name=re.sub(r'[^A-Za-z0-9_-]','',slug)[:48] or 'NewApp'
            brief=brief.strip()[:8000]
            if len(brief)<20: return self.send_json({'error':'Provide a detailed app brief (at least 20 characters).'},400)
            project=self.safe_path(name)
            if project is None:
                return self.send_json({'ok':False,'error':'The requested project path is unsafe or is already a symlink.'},409)
            if project.exists():
                base=name[:40]
                suffix=str(int(time.time()))[-6:]
                candidate=f'{base}_{suffix}'
                counter=1
                while (WORKSPACE/candidate).exists() or (WORKSPACE/candidate).is_symlink():
                    candidate=f'{base}_{suffix}_{counter}'
                    counter+=1
                name=candidate
                project=self.safe_path(name)
            if project is None:
                return self.send_json({'ok':False,'error':'Could not allocate a safe project directory.'},409)
            project.mkdir(parents=True,exist_ok=False)
            system='You are a senior software engineer. Produce a production-oriented, ORIGINAL Android/PWA app implementation. Do not copy any named competitor source or assets. Output a JSON object with keys: app_name, description, files (object mapping relative filenames to complete text content), build_notes, tests. Prefer a self-contained PWA (index.html, app.js, styles.css, manifest.webmanifest, sw.js) and include Android packaging instructions for Capacitor when relevant. Do not use markdown fences. Avoid secrets. Keep paths simple and safe.'
            result=self.call_llm(system,brief,raw=True)
            if not result.get('ok'):
                project.rmdir(); return self.send_json(result,502)
            obj=result.get('data')
            if not isinstance(obj,dict) or not isinstance(obj.get('files'),dict):
                (project/'generation-response.txt').write_text(result.get('text',''))
                return self.send_json({'ok':False,'error':'Model response was not valid structured JSON. Raw response saved. Try a stronger model or shorter brief.','project':name,'raw':result.get('text','')},502)
            files, file_error = validate_generated_files(obj.get('files'))
            if file_error:
                for child in project.iterdir():
                    if child.is_file() or child.is_symlink(): child.unlink()
                    elif child.is_dir(): import shutil; shutil.rmtree(child)
                project.rmdir()
                return self.send_json({'ok':False,'error':file_error,'project':name},422)
            written=[]
            for rel,content in files.items():
                target=project/rel
                # Check all existing parents before mkdir; then re-check after creation.
                current=project
                for part in Path(rel).parts[:-1]:
                    current=current/part
                    if current.is_symlink() or (current.exists() and not current.is_dir()):
                        return self.send_json({'ok':False,'error':'Refusing to write through an unsafe generated-file directory.','project':name},409)
                if target.is_symlink() or target.exists():
                    return self.send_json({'ok':False,'error':'Refusing to overwrite an unexpected generated-file path.','project':name},409)
                target.parent.mkdir(parents=True,exist_ok=True)
                current=project
                for part in Path(rel).parts[:-1]:
                    current=current/part
                    if current.is_symlink() or not current.is_dir():
                        return self.send_json({'ok':False,'error':'Refusing to write through an unsafe generated-file directory.','project':name},409)
                if target.is_symlink() or target.exists():
                    return self.send_json({'ok':False,'error':'Generated file path changed during creation.','project':name},409)
                target.write_text(content,encoding='utf-8')
                written.append(rel)
            meta={'slug':name,'brief':brief,'created_at':int(time.time()),'app_name':str(obj.get('app_name',name))[:120],'description':str(obj.get('description',''))[:2000],'build_notes':str(obj.get('build_notes',''))[:6000],'tests':str(obj.get('tests',''))[:6000],'files':written}
            (project/'appforge-project.json').write_text(json.dumps(meta,indent=2))
            return self.send_json({'ok':True,'project':name,'app_name':meta['app_name'],'description':meta['description'],'files':written,'build_notes':meta['build_notes'],'tests':meta['tests']})
        if self.path=='/api/build':
            name=data.get('project',''); project=self.safe_path(name)
            if not project or not project.is_dir(): return self.send_json({'error':'Project not found'},404)
            # Only run known build commands, never arbitrary user-provided shell strings.
            command=data.get('command','check')
            if command=='check':
                files=[p.name for p in project.iterdir() if p.is_file()]
                missing=[x for x in ('index.html','app.js','styles.css') if x not in files]
                return self.send_json({'ok':not missing,'project':name,'files':files,'missing_recommended_files':missing,'message':'Static file check complete. This is not a substitute for device testing.'})
            if command=='apk':
                # Building installs/runs project-controlled tools and Gradle scripts.
                # Require an explicit, deliberate approval on every build request.
                if data.get('approved') is not True:
                    return self.send_json({
                        'error':'APK build requires explicit approval. Review the project source and dependencies, then retry with approved=true.',
                        'requires_approval':True,
                    }, 403)
                package=project/'package.json'
                if package.is_symlink() or not package.is_file(): return self.send_json({'error':'A real project package.json file is required.'},400)
                package_lock=project/'package-lock.json'
                node_modules=project/'node_modules'
                if package_lock.is_symlink() or (package_lock.exists() and not package_lock.is_file()):
                    return self.send_json({'error':'Refusing to use a symlinked or invalid package-lock.json.'},400)
                if node_modules.is_symlink() or (node_modules.exists() and not node_modules.is_dir()):
                    return self.send_json({'error':'Refusing to install dependencies through a symlinked or invalid node_modules path.'},400)
                android_dir=project/'android'
                wrapper=android_dir/'gradlew'
                if android_dir.is_symlink() or (android_dir.exists() and not android_dir.is_dir()):
                    return self.send_json({'error':'Refusing to build through a symlinked or invalid android directory.'},400)
                if wrapper.is_symlink() or (wrapper.exists() and not wrapper.is_file()):
                    return self.send_json({'error':'Refusing to execute a symlinked or invalid Gradle wrapper.'},400)
                # Reduce inherited command-injection/configuration variables. This is not a
                # sandbox: approved project scripts and Gradle plugins still execute as this user.
                build_env={}
                for key in ('PATH','HOME','USERPROFILE','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR',
                            'JAVA_HOME','ANDROID_HOME','ANDROID_SDK_ROOT','ANDROID_USER_HOME'):
                    if key in os.environ: build_env[key]=os.environ[key]
                build_env.update({'CI':'true','npm_config_audit':'false','npm_config_fund':'false',
                                  'GIT_TERMINAL_PROMPT':'0'})
                try:
                    lockfile=project/'package-lock.json'
                    install_cmd=['npm','ci','--no-audit','--no-fund'] if lockfile.is_file() and not lockfile.is_symlink() else ['npm','install','--no-audit','--no-fund']
                    install=subprocess.run(install_cmd,cwd=project,env=build_env,stdin=subprocess.DEVNULL,
                                           capture_output=True,text=True,timeout=300)
                    if install.returncode:
                        return self.send_json({'ok':False,'stage':'npm-install','stdout':install.stdout[-6000:],'stderr':install.stderr[-6000:]},500)
                    tests=subprocess.run(['npm','test','--if-present'],cwd=project,env=build_env,
                                         stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=300)
                    if tests.returncode:
                        return self.send_json({'ok':False,'stage':'npm-test','stdout':tests.stdout[-6000:],'stderr':tests.stderr[-6000:]},500)
                    proc=subprocess.run(['npm','run','build'],cwd=project,env=build_env,
                                        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=300)
                    if proc.returncode: return self.send_json({'ok':False,'stage':'web-build','stdout':proc.stdout[-6000:],'stderr':proc.stderr[-6000:]},500)
                    if not android_dir.exists():
                        add=subprocess.run(['npx','--no-install','cap','add','android'],cwd=project,env=build_env,
                                            stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=300)
                        if add.returncode:
                            return self.send_json({'ok':False,'stage':'capacitor-add','stdout':add.stdout[-6000:],'stderr':add.stderr[-6000:]},500)
                    proc2=subprocess.run(['npx','--no-install','cap','sync','android'],cwd=project,env=build_env,
                                         stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=300)
                    if proc2.returncode: return self.send_json({'ok':False,'stage':'capacitor-sync','stdout':proc2.stdout[-6000:],'stderr':proc2.stderr[-6000:]},500)
                    if wrapper.is_symlink() or not wrapper.is_file() or wrapper.resolve().parent != android_dir.resolve():
                        return self.send_json({'ok':False,'stage':'gradle','error':'A real project-local Gradle wrapper is required.'},400)
                    proc3=subprocess.run(['./gradlew','--no-daemon','--no-watch-fs','assembleDebug'],
                                         cwd=android_dir,env=build_env,stdin=subprocess.DEVNULL,
                                         capture_output=True,text=True,timeout=600)
                    apk=android_dir/'app/build/outputs/apk/debug/app-debug.apk'
                    success=(proc3.returncode==0 and not apk.is_symlink() and apk.is_file()
                             and apk.stat().st_size>0 and apk.resolve().is_relative_to(project.resolve()))
                    return self.send_json({'ok':success,'stage':'gradle','stdout':proc3.stdout[-6000:],'stderr':proc3.stderr[-6000:],'apk':str(apk) if success else None,'download_url':('/api/apk?project='+name) if success else None,'artifact_verified':success},200 if success else 500)
                except Exception as e: return self.send_json({'error':str(e),'message':'Install Node.js, Java JDK, Android SDK, and Gradle prerequisites; see README.'},500)
            return self.send_json({'error':'Unknown build command'},400)
        return self.send_json({'error':'Not found'},404)
    def call_llm_data(self, system, user, raw=False):
        cfg=json.loads(CONFIG.read_text())
        base=str(cfg.get('llm_base_url','')).rstrip('/')
        if not local_endpoint_allowed(base):
            return {'ok':False,'error':'Local-first policy: Replica workflows only use localhost or a private LAN model endpoint.','hint':'Update Local AI settings to a local endpoint.'}
        url=base+'/chat/completions'
        payload={'model':cfg['llm_model'],'messages':[{'role':'system','content':system},{'role':'user','content':user}],'temperature':0.2}
        headers={'Content-Type':'application/json'}
        api_key=str(cfg.get('llm_api_key','')).strip()
        if api_key: headers['Authorization']='Bearer '+api_key
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers,method='POST')
        try:
            with urllib.request.urlopen(req,timeout=max(10,min(int(cfg.get('timeout_seconds',120)),600))) as r: response=read_limited_json(r)
            text=response['choices'][0]['message']['content']
            if raw:
                cleaned=text.strip()
                if cleaned.startswith('```'): cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I)
                try: parsed=json.loads(cleaned)
                except Exception: parsed=None
                return {'ok':True,'text':text,'data':parsed}
            return {'ok':True,'text':text}
        except urllib.error.HTTPError as e:
            return {'ok':False,'error':f'Local model returned HTTP {e.code}: {e.read(1000).decode(errors="replace")}','hint':'Check the local OpenAI-compatible server and model name.'}
        except Exception as e:
            return {'ok':False,'error':f'Could not reach local AI endpoint: {e}','hint':'Start the local model server and verify Local AI settings.'}

    def call_llm(self,system,user,raw=False):
        cfg=json.loads(CONFIG.read_text()); base=str(cfg.get('llm_base_url','')).rstrip('/')
        if not local_endpoint_allowed(base): return self.send_json({'error':'For local-first safety, configure a localhost or private-LAN model endpoint only.'},400)
        url=base+'/chat/completions'
        payload={'model':cfg['llm_model'],'messages':[{'role':'system','content':system},{'role':'user','content':user}], 'temperature':0.3}
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+cfg.get('llm_api_key','ollama')},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=max(5,min(int(cfg.get('timeout_seconds',120)),600))) as r: resp=read_limited_json(r)
            txt=resp['choices'][0]['message']['content']
            if raw:
                cleaned=txt.strip()
                if cleaned.startswith('```'): cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I)
                try: parsed=json.loads(cleaned)
                except Exception: parsed=None
                return {'ok':True,'data':parsed,'text':txt}
            return self.send_json({'ok':True,'result':txt})
        except urllib.error.HTTPError as e:
            return self.send_json({'error':f'Local model returned HTTP {e.code}: {e.read().decode(errors="replace")[:1000]}','hint':'Check that your local OpenAI-compatible model server is running and the model name is correct.'},502)
        except Exception as e:
            return self.send_json({'error':f'Could not reach local AI endpoint: {e}','hint':'Start Ollama or another OpenAI-compatible local server, then verify Settings.'},502)
    def log_message(self,*args): pass

if __name__=='__main__':
    host='127.0.0.1'; port=int(os.environ.get('APPFORGE_PORT','8787'))
    print(f'AppForge Local running at http://{host}:{port}'); ThreadingHTTPServer((host,port),Handler).serve_forever()
