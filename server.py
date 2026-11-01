#!/usr/bin/env python3
"""AppForge Local: personal, locally hosted app discovery and build workbench."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, os, urllib.request, urllib.error, re, subprocess, threading, time, ipaddress
import advanced

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
WORKSPACE = ROOT / 'workspace'
WORKSPACE.mkdir(exist_ok=True)
CONFIG = ROOT / 'config.local.json'
STATE = ROOT / 'state'
STATE.mkdir(exist_ok=True)
FEEDBACK = STATE / 'feedback.jsonl'
ROADMAP = STATE / 'improvement-roadmap.json'
DEFAULT_CONFIG = {'llm_base_url':'http://127.0.0.1:8080/v1','llm_model':'qwen2.5-coder','llm_api_key':'ollama','timeout_seconds':120}

def local_endpoint_allowed(value):
    try:
        parsed=urlparse(str(value))
        if parsed.scheme!='http' or not parsed.hostname: return False
        host=parsed.hostname.lower().rstrip('.')
        if host=='localhost': return True
        addr=ipaddress.ip_address(host)
        return bool(addr.is_loopback or addr.is_private or addr.is_link_local)
    except Exception:
        return False
if not CONFIG.exists(): CONFIG.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(STATIC),**kwargs)
    def send_json(self, obj, status=200):
        data=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>2_000_000: raise ValueError('Request too large')
        return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
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
            except Exception as e: return self.send_json({'error':str(e),'retryable':True},502)
            if p.path=='/api/health':
                cfg=json.loads(CONFIG.read_text()); self.send_json({'ok':True,'workspace':str(WORKSPACE),'llm_base_url':cfg['llm_base_url'],'llm_model':cfg['llm_model'],'time':int(time.time())}); return
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
                for d in sorted(WORKSPACE.iterdir(),key=lambda x:x.stat().st_mtime,reverse=True):
                    if d.is_dir(): projects.append({'name':d.name,'updated':int(d.stat().st_mtime),'files':[x.name for x in d.iterdir() if x.is_file()]})
                self.send_json({'projects':projects}); return
            if p.path=='/api/trends':
                region=parse_qs(p.query).get('region',['in'])[0]
                try:
                    result=advanced.snapshot(region)
                    self.send_json(result); return
                except Exception as e:
                    self.send_json({'source':'Apple RSS unavailable','region':region,'apps':[],'error':str(e),'note':'Retries were attempted. Check connectivity or use App Store search; no rankings are invented.'},502); return
            if p.path=='/api/file':
                name=parse_qs(p.query).get('project',[''])[0]; file=parse_qs(p.query).get('file',[''])[0]
                target=self.safe_path(name,file)
                if not target or not target.is_file(): self.send_json({'error':'File not found'},404); return
                self.send_json({'project':name,'file':file,'content':target.read_text(errors='replace')}); return
            return self.send_json({'error':'Not found'},404)
        return super().do_GET()
    def safe_path(self, project, filename=''):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',project or ''): return None
        if filename and (Path(filename).name!=filename or filename in ('.','..')): return None
        workspace = WORKSPACE.resolve()
        base = (workspace / project).resolve()
        if base.parent != workspace: return None
        if not filename: return base
        target = (base / filename).resolve()
        # A filename can be a symlink; ensure its resolved target remains inside
        # the selected project before serving or modifying it.
        if target.parent != base and base not in target.parents: return None
        return target
    def do_POST(self):
        try: data=self.body()
        except Exception as e: return self.send_json({'error':str(e)},400)
        try:
            if self.path=='/api/replica/run':
                result=advanced.replica_run(data,self.call_llm_data)
                return self.send_json(result['body'],result.get('status',200))
            if self.path=='/api/aider/run': return self.send_json(advanced.run_aider(str(data.get('project','')),str(data.get('prompt','')),bool(data.get('approved',False))))
            if self.path=='/api/test-repair': return self.send_json(advanced.repair_project(str(data.get('project','')),bool(data.get('approved',False))))
            if self.path=='/api/research/snapshot': return self.send_json(advanced.snapshot(str(data.get('region','in'))))
            if self.path=='/api/template/capacitor': return self.send_json(advanced.create_capacitor(str(data.get('project','')),data.get('app_name')))
            if self.path=='/api/test-run': return self.send_json(advanced.test_project(str(data.get('project','')),bool(data.get('repair',False))))
            if self.path=='/api/git': return self.send_json(advanced.git_action(str(data.get('project','')),str(data.get('action','status'))))
            if self.path=='/api/launch': return self.send_json(advanced.launch_config(str(data.get('project','')),data.get('config')))
            if self.path=='/api/track': return self.send_json(advanced.track_event(data.get('project',''),data.get('event','manual'),data.get('value'),data.get('metadata')))
        except Exception as e: return self.send_json({'error':str(e)},400)
        if self.path=='/api/config':
            cfg=json.loads(CONFIG.read_text())
            for k in ('llm_base_url','llm_model','llm_api_key','timeout_seconds'):
                if k in data: cfg[k]=data[k]
            if not local_endpoint_allowed(cfg['llm_base_url']):
                return self.send_json({'error':'For local-first safety, configure a local LAN/localhost LLM endpoint only.'},400)
            CONFIG.write_text(json.dumps(cfg,indent=2)); return self.send_json({'ok':True,'config':{k:v for k,v in cfg.items() if k!='llm_api_key'}})
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
            prompt=data.get('prompt','').strip()
            if not prompt: return self.send_json({'error':'Add an app idea or competitor to analyze.'},400)
            system='You are AppForge Local, an ethical app market researcher. Analyze only public-facing product positioning, features, reviews/complaints supplied by user, and opportunity hypotheses. Never claim live download/revenue data unless provided. Do not reproduce proprietary code, protected assets, or branding. Return practical sections: audience, problem, competitor comparison, likely gaps, differentiators, MVP, monetization, risks, validation experiments.'
            return self.call_llm(system,prompt)
        if self.path=='/api/generate':
            name=re.sub(r'[^A-Za-z0-9_-]','',data.get('slug','NewApp'))[:48] or 'NewApp'
            brief=data.get('brief','').strip()
            if len(brief)<20: return self.send_json({'error':'Provide a detailed app brief (at least 20 characters).'},400)
            project=self.safe_path(name)
            if project.exists(): name=name[:42]+'_'+str(int(time.time()))[-6:]; project=self.safe_path(name)
            project.mkdir(parents=True)
            system='You are a senior software engineer. Produce a production-oriented, ORIGINAL Android/PWA app implementation. Do not copy any named competitor source or assets. Output a JSON object with keys: app_name, description, files (object mapping relative filenames to complete text content), build_notes, tests. Prefer a self-contained PWA (index.html, app.js, styles.css, manifest.webmanifest, sw.js) and include Android packaging instructions for Capacitor when relevant. Do not use markdown fences. Avoid secrets. Keep paths simple and safe.'
            result=self.call_llm(system,brief,raw=True)
            if not result.get('ok'):
                project.rmdir(); return self.send_json(result,502)
            obj=result.get('data')
            if not isinstance(obj,dict) or not isinstance(obj.get('files'),dict):
                (project/'generation-response.txt').write_text(result.get('text',''))
                return self.send_json({'ok':False,'error':'Model response was not valid structured JSON. Raw response saved. Try a stronger model or shorter brief.','project':name,'raw':result.get('text','')},502)
            written=[]
            for rel,content in obj['files'].items():
                if not isinstance(rel,str) or Path(rel).is_absolute() or '..' in Path(rel).parts or len(rel)>120: continue
                target=(project/rel).resolve()
                if project.resolve() not in target.parents: continue
                target.parent.mkdir(parents=True,exist_ok=True); target.write_text(str(content)); written.append(rel)
            meta={'slug':name,'brief':brief,'created_at':int(time.time()),'app_name':obj.get('app_name',name),'description':obj.get('description',''),'build_notes':obj.get('build_notes',''),'tests':obj.get('tests',''),'files':written}
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
                package=project/'package.json'
                if not package.exists(): return self.send_json({'error':'No package.json found. Generate/prepare a Capacitor-compatible project first.'},400)
                try:
                    proc=subprocess.run(['npm','run','build'],cwd=project,capture_output=True,text=True,timeout=300)
                    if proc.returncode: return self.send_json({'ok':False,'stage':'web-build','stdout':proc.stdout[-6000:],'stderr':proc.stderr[-6000:]},500)
                    proc2=subprocess.run(['npx','cap','sync','android'],cwd=project,capture_output=True,text=True,timeout=300)
                    if proc2.returncode: return self.send_json({'ok':False,'stage':'capacitor-sync','stdout':proc2.stdout[-6000:],'stderr':proc2.stderr[-6000:]},500)
                    wrapper=project/'android'/'gradlew'
                    if not wrapper.exists(): return self.send_json({'ok':False,'stage':'gradle','error':'Gradle wrapper not found in Android project.'},400)
                    proc3=subprocess.run(['./gradlew','assembleDebug'],cwd=project/'android',capture_output=True,text=True,timeout=600)
                    apk=project/'android/app/build/outputs/apk/debug/app-debug.apk'
                    success=proc3.returncode==0 and apk.is_file() and apk.stat().st_size>0
                    return self.send_json({'ok':success,'stage':'gradle','stdout':proc3.stdout[-6000:],'stderr':proc3.stderr[-6000:],'apk':str(apk) if success else None,'artifact_verified':success},200 if success else 500)
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
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+str(cfg.get('llm_api_key','ollama'))},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=max(10,min(int(cfg.get('timeout_seconds',120)),600))) as r: response=json.loads(r.read())
            text=response['choices'][0]['message']['content']
            if raw:
                cleaned=text.strip()
                if cleaned.startswith('```'): cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I)
                try: parsed=json.loads(cleaned)
                except Exception: parsed=None
                return {'ok':True,'text':text,'data':parsed}
            return {'ok':True,'text':text}
        except urllib.error.HTTPError as e:
            return {'ok':False,'error':f'Local model returned HTTP {e.code}: {e.read().decode(errors="replace")[:1000]}','hint':'Check the local OpenAI-compatible server and model name.'}
        except Exception as e:
            return {'ok':False,'error':f'Could not reach local AI endpoint: {e}','hint':'Start the local model server and verify Local AI settings.'}

    def call_llm(self,system,user,raw=False):
        cfg=json.loads(CONFIG.read_text()); base=str(cfg.get('llm_base_url','')).rstrip('/')
        if not local_endpoint_allowed(base): return self.send_json({'error':'For local-first safety, configure a localhost or private-LAN model endpoint only.'},400)
        url=base+'/chat/completions'
        payload={'model':cfg['llm_model'],'messages':[{'role':'system','content':system},{'role':'user','content':user}], 'temperature':0.3}
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+cfg.get('llm_api_key','ollama')},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=int(cfg.get('timeout_seconds',120))) as r: resp=json.loads(r.read())
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
    host=os.environ.get('APPFORGE_HOST','127.0.0.1'); port=int(os.environ.get('APPFORGE_PORT','8787'))
    print(f'AppForge Local running at http://{host}:{port}'); ThreadingHTTPServer((host,port),Handler).serve_forever()
