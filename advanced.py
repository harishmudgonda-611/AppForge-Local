"""AppForge advanced local-first capabilities (stdlib only)."""
from pathlib import Path
from urllib.parse import urlencode
import json, sqlite3, time, urllib.request, urllib.error, subprocess, shutil, re, os, tempfile

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state'
WORKSPACE = ROOT / 'workspace'
for _private_dir in (STATE, WORKSPACE):
    if _private_dir.is_symlink() or (_private_dir.exists() and not _private_dir.is_dir()):
        raise RuntimeError(f'AppForge data directory must be a real directory: {_private_dir.name}')
    _private_dir.mkdir(exist_ok=True)
DB = STATE / 'appforge.db'


def local_endpoint_allowed(value):
    """Allow only plain-HTTP loopback or private-network model endpoints."""
    import ipaddress
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(value))
        if parsed.scheme != "http" or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost":
            return True
        address = ipaddress.ip_address(host)
        return bool(address.is_loopback or address.is_private or address.is_link_local)
    except Exception:
        return False



# AppForge-native workflow adapter based on the publicly documented Replica Skill stages.
# The upstream skill pack is referenced, not vendored into this project.
REPLICA_UPSTREAM = 'https://github.com/Jakeschincariol/replica-skill'
REPLICA_STAGES = [
    {'id':'replica-recon','title':'1. Reconnaissance','purpose':'Map public features, screens, user journeys, customer and evidence-backed feature gaps.','artifact':'replica/01-recon.md','writes_code':False},
    {'id':'replica-architect','title':'2. Architecture','purpose':'Plan original system architecture, data model, APIs, privacy and implementation order.','artifact':'replica/02-architecture.md','writes_code':False},
    {'id':'replica-design','title':'3. Design system','purpose':'Create original design tokens, component rules, accessibility requirements and responsive states.','artifact':'replica/03-design-system.md','writes_code':False},
    {'id':'replica-build','title':'4. Build app','purpose':'Generate an original PWA app shell from approved requirements; not a source-code clone.','artifact':'workspace root app files','writes_code':True},
    {'id':'replica-backend','title':'5. Backend plan','purpose':'Specify authentication, data storage, APIs, payments and integrations with security notes.','artifact':'replica/05-backend-plan.md','writes_code':False},
    {'id':'replica-test','title':'6. Test plan','purpose':'Build test cases from user flows, edge cases, accessibility and failure conditions.','artifact':'replica/06-test-plan.md','writes_code':False},
    {'id':'replica-diff','title':'7. Feature-gap review','purpose':'Compare the planned feature matrix to implemented evidence; report missing features without fake parity scores.','artifact':'replica/07-gap-review.md','writes_code':False},
    {'id':'replica-entrepreneur','title':'8. Review-based differentiation','purpose':'Analyze user-provided, linked reviews and propose fixes/positioning without inventing reviews or counts.','artifact':'replica/08-differentiation.md','writes_code':False},
    {'id':'replica-brand','title':'9. New brand','purpose':'Create a distinctive name, positioning and visual direction; flag trademark/domain checks still needed.','artifact':'replica/09-brand.md','writes_code':False},
    {'id':'replica-launch','title':'10. Store listing','purpose':'Draft store description, title, short description, keywords, pricing hypotheses and launch checklist.','artifact':'replica/10-launch.md','writes_code':False},
    {'id':'replica-deploy','title':'11. Release preflight','purpose':'Produce a release readiness report; does not publish, sign or deploy without separate owner actions.','artifact':'replica/11-release-preflight.md','writes_code':False},
]

def replica_workflows():
    return {'name':'Replica Skill workflow adapter','upstream':REPLICA_UPSTREAM,'license':'MIT (upstream repository; preserve its notice if using upstream files)','integration':'AppForge-native workflow adapter. Upstream SKILL.md files/scripts are not bundled in this archive.','stages':REPLICA_STAGES,'safety':'Public information and user-supplied evidence only; clean-room implementation; no decompiling, private APIs, copied branding/content, credential access, or automatic publishing.'}


def replica_run(data, llm_fn):
    """Run one owner-approved local Replica workflow stage."""
    name = str(data.get("project", ""))
    stage_id = str(data.get("stage", ""))
    stage = next((x for x in REPLICA_STAGES if x["id"] == stage_id), None)
    if not stage:
        return {"status": 400, "body": {"error": "Unknown Replica workflow stage."}}
    if data.get("approved") is not True:
        return {"status": 400, "body": {"error": "Explicit approval is required to generate and save stage artifacts."}}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name or ""):
        return {"status": 400, "body": {"error": "Invalid project slug."}}
    if (WORKSPACE / name).is_symlink():
        return {"status": 409, "body": {"error": "Project workspace entries cannot be symlinks."}}
    project = (WORKSPACE / name).resolve()
    if project.parent != WORKSPACE.resolve():
        return {"status": 400, "body": {"error": "Invalid project path."}}
    if stage_id != "replica-recon" and not project.is_dir():
        return {"status": 404, "body": {"error": "Project not found. Run Reconnaissance first."}}
    if project.exists() and not project.is_dir():
        return {"status": 409, "body": {"error": "A non-directory file already uses this project name. Choose another slug."}}
    fields = {
        "project": name,
        "target_app": str(data.get("target_app", ""))[:200],
        "platform": str(data.get("platform", "Android"))[:80],
        "audience": str(data.get("audience", ""))[:500],
        "scope": str(data.get("scope", "MVP core workflow"))[:800],
        "evidence": str(data.get("context", ""))[:12000],
    }
    replica_dir = project / "replica"
    # Never follow project-controlled symlinks while reading or writing workflow artifacts.
    if replica_dir.is_symlink() or (replica_dir.exists() and not replica_dir.is_dir()):
        return {"status": 409, "body": {"error": "The replica artifact path must be a real directory, not a symlink or file."}}
    state_path = replica_dir / "workflow-state.json"
    if state_path.is_symlink() or (state_path.exists() and not state_path.is_file()):
        return {"status": 409, "body": {"error": "Refusing to overwrite an unsafe workflow state path.", "written": []}}
    if stage_id == "replica-build":
        summary_path = replica_dir / "04-build-summary.md"
        if summary_path.is_symlink() or (summary_path.exists() and not summary_path.is_file()):
            return {"status": 409, "body": {"error": "Refusing to overwrite an unsafe workflow summary path.", "written": []}}
    prior = []
    if replica_dir.is_dir():
        for f in sorted(replica_dir.glob("*.md"))[-8:]:
            try:
                if f.is_symlink():
                    continue
                resolved = f.resolve()
                if project not in resolved.parents or not resolved.is_file():
                    continue
                if resolved.stat().st_size <= 60000:
                    prior.append({"file": f.name, "content": resolved.read_text(errors="replace")[-9000:]})
            except OSError:
                pass
    files = []
    if project.is_dir():
        for f in project.rglob("*"):
            if f.is_file() and not f.is_symlink() and not any(x in {".git", "node_modules", "android", "dist", "build"} for x in f.parts):
                files.append(str(f.relative_to(project)))
                if len(files) >= 100:
                    break
    context = {**fields, "existing_files": files, "prior_artifacts": prior}
    prompts = {
        "replica-recon": "Write a thorough Markdown product-recon report: source table with URL and evidence status; target user; bounded scope; screen inventory including empty/loading/error states; user flows; component inventory; inferred data model with confidence; must/should/could feature matrix; out-of-scope items; size estimate and open questions. Distinguish facts from hypotheses. Include a CSV feature matrix in a fenced block.",
        "replica-architect": "Write a pragmatic architecture plan: PWA/Android approach, modules, schema and relationships, API contracts, storage/offline behavior, auth/permissions, security/privacy, dependencies, build order, tradeoffs and acceptance criteria.",
        "replica-design": "Create an original design-system spec: semantic color tokens, typography, spacing, components, accessibility/contrast, responsive mobile and desktop rules, plus loading/empty/error/permission states. Do not reuse competitor branding or assets.",
        "replica-build": "Return valid JSON. It must contain a files object with only these allowed filenames: index.html, app.js, styles.css, manifest.webmanifest, sw.js, README.md. Also include a summary string. Make a functional original local-first PWA using previous recon/architecture/design artifacts, validation, responsive layout, accessibility and error states. No hosted app builders or runtime CDN dependencies.",
        "replica-backend": "Write a backend/integration plan covering entities/schema, data flow, authentication and authorization, input validation, secret handling, payment boundaries, privacy threat model, backup/migration and abuse controls. Do not claim any integration is connected.",
        "replica-test": "Create a test plan mapped to user flows. Include happy paths, invalid/long inputs, double submit, refresh/back, offline/slow network, permissions, data isolation, accessibility, mobile widths and regressions. Include test IDs, steps, expected result, severity and release gates.",
        "replica-diff": "Compare feature matrix against current workspace files and supplied test reports. Mark each feature implemented, partial, missing, out of scope or not verified. Do not invent parity scores. List evidence, blockers and highest-priority fixes.",
        "replica-entrepreneur": "Analyze only review text/URLs or review data supplied by the user. State sample sizes and sources, group complaints and feature requests, flag weak samples and suggest differentiators. If evidence is missing, produce a collection plan instead of inventing reviews or sentiment.",
        "replica-brand": "Propose five distinctive app names, positioning, audience, tone, logo brief and visual direction. Avoid competitor marks or confusingly similar names. List trademark/domain/store checks as pending; do not claim legal clearance.",
        "replica-launch": "Draft store listing title, short/full description, feature bullets, screenshot plan, monetization options and pricing hypotheses, privacy/data-safety checklist, testing plan and claims needing evidence. Do not promise revenue.",
        "replica-deploy": "Create a release preflight only: reproducible build, tests, signing, privacy/data safety, permissions, content rating, store assets, policy review, staged rollout, monitoring, rollback and owner approvals. Do not publish, deploy or access credentials.",
    }
    rules = "\n\nRules: clean-room original implementation only; never copy source code, logos, protected content, exact wording or private APIs. Use supplied evidence; never invent data, reviews, rankings, test results or revenue. Do not bypass login, paywalls, limits or terms. Label hypotheses. Do not claim unverified builds or releases."
    system = "You are AppForge Local's Replica workflow adapter inspired by the publicly documented stages of " + REPLICA_UPSTREAM + ". This is an AppForge-native adapter, not the upstream skill pack. " + prompts[stage_id] + rules
    user = "Approved stage: " + stage["title"] + "\nContext (JSON):\n" + json.dumps(context, ensure_ascii=False)[:24000]
    result = llm_fn(system, user, stage_id == "replica-build")
    if not result or not result.get("ok"):
        return {"status": 502, "body": {"error": (result or {}).get("error", "Local model returned no result."), "hint": (result or {}).get("hint", "Check local AI settings."), "stage": stage_id}}
    build_obj = None
    if stage_id == "replica-build":
        build_obj = result.get("data")
        if not isinstance(build_obj, dict) or not isinstance(build_obj.get("files"), dict):
            return {"status": 502, "body": {"error": "Model did not return valid JSON containing a files object. No app files were written."}}
        allowed = {"index.html", "app.js", "styles.css", "manifest.webmanifest", "sw.js", "README.md"}
        if not build_obj["files"] or any(k not in allowed or not isinstance(v, str) or len(v) > 150000 for k, v in build_obj["files"].items()):
            return {"status": 400, "body": {"error": "Build response contained unsafe paths or oversized files. No app files were written."}}
        required = {"index.html", "app.js", "styles.css", "manifest.webmanifest", "sw.js"}
        missing = required - {k for k, v in build_obj["files"].items() if isinstance(v, str) and v.strip()}
        if missing:
            return {"status": 422, "body": {"error": "Build response is missing required PWA files: " + ", ".join(sorted(missing)), "written": []}}
        # Existing top-level symlinks must not redirect generated source writes outside the project.
        for rel in build_obj["files"]:
            target = project / rel
            if target.is_symlink() or target.resolve().parent != project:
                return {"status": 409, "body": {"error": "Refusing to overwrite a symlinked or redirected project file: " + rel, "written": []}}
        manifest_text = build_obj["files"].get("manifest.webmanifest")
        if manifest_text:
            try:
                json.loads(manifest_text)
            except Exception as exc:
                return {"status": 422, "body": {"error": "manifest.webmanifest is invalid JSON: " + str(exc), "written": []}}
        if shutil.which("node"):
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
                    tmp.write(build_obj["files"]["app.js"])
                    tmp_path = tmp.name
                proc = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=20)
                if proc.returncode:
                    return {"status": 422, "body": {"error": "Generated app.js failed Node syntax validation; no app files were written.", "stderr": proc.stderr[-3000:], "written": []}}
            finally:
                if tmp_path:
                    try: Path(tmp_path).unlink()
                    except OSError: pass
    if not project.exists():
        if stage_id != "replica-recon":
            return {"status": 404, "body": {"error": "Project not found."}}
        project.mkdir(parents=True)
        meta = {"slug": name, "created_at": int(time.time()), "app_name": name, "description": "AppForge Replica workflow project", "workflow": "replica-skill-adapter"}
        (project / "appforge-project.json").write_text(json.dumps(meta, indent=2))
    replica_dir.mkdir(exist_ok=True)
    if replica_dir.is_symlink() or replica_dir.resolve().parent != project:
        return {"status": 409, "body": {"error": "Refusing to write workflow artifacts outside the project directory."}}
    written, checkpoint = [], None
    if stage_id == "replica-build":
        existing = [f for f in build_obj["files"] if (project / f).is_file()]
        if existing:
            checkpoint = git_action(name, "checkpoint")
            if not checkpoint.get("ok"):
                return {"status": 409, "body": {"error": "Git checkpoint failed; refusing to overwrite existing app files.", "checkpoint": checkpoint}}
        for rel, content in build_obj["files"].items():
            (project / rel).write_text(content)
            written.append(rel)
        summary_path.write_text(str(build_obj.get("summary", "Original PWA files generated."))[:12000])
        written.append("replica/04-build-summary.md")
    else:
        filename = stage["artifact"].split("/")[-1]
        out = replica_dir / filename
        if out.is_symlink() or (out.exists() and not out.is_file()):
            return {"status": 409, "body": {"error": "Refusing to overwrite an unsafe workflow artifact path.", "written": []}}
        content = str(result.get("text", "")).strip()
        if not content:
            return {"status": 502, "body": {"error": "Local model returned an empty artifact."}}
        out.write_text(content[:100000])
        written.append(str(out.relative_to(project)))
    try:
        state = json.loads(state_path.read_text())
    except Exception:
        state = {"upstream": REPLICA_UPSTREAM, "adapter": "AppForge-native; upstream files not bundled", "stages": {}}
    state["stages"][stage_id] = {"title": stage["title"], "completed_at": int(time.time()), "artifacts": written, "approved": True}
    state["last_stage"] = stage_id
    state_path.write_text(json.dumps(state, indent=2))
    return {"status": 200, "body": {"ok": True, "project": name, "stage": stage_id, "title": stage["title"], "written": written, "completed_at": int(time.time()), "summary": str(result.get("summary", "Artifact saved locally."))[:2000], "checkpoint": checkpoint, "note": "AI-generated draft saved locally. Review it and run tests; no external deployment or store action occurred."}}

def db():
    for candidate in (DB, Path(str(DB) + '-wal'), Path(str(DB) + '-shm')):
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
            raise RuntimeError('AppForge SQLite database must be a regular file; database and journal paths cannot be symlinks or directories.')
    c=sqlite3.connect(DB, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')
    c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY, app_id TEXT, name TEXT, developer TEXT, category TEXT, store_url TEXT, icon TEXT, source TEXT, region TEXT, rank INTEGER, collected_at INTEGER, raw_json TEXT)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_apps_history ON apps(app_id, collected_at)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, app_id TEXT, review_id TEXT, title TEXT, body TEXT, rating INTEGER, author TEXT, source_url TEXT, collected_at INTEGER, UNIQUE(app_id, review_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, project TEXT, event TEXT, value REAL, metadata TEXT, created_at INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS launch_config (project TEXT PRIMARY KEY, config TEXT, updated_at INTEGER)''')
    c.commit(); return c

def region_code(value, default='in'):
    """Validate the two-letter storefront region used in public Apple URLs."""
    if value is None or value == '':
        value = default
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z]{2}', value):
        raise ValueError('Region must be a two-letter country code.')
    return value.lower()


def request_json(url, timeout=12, attempts=3):
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'AppForgeLocal/2.0 (+local app research)','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                raw = r.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise ValueError('Public research response exceeds the 5 MB safety limit.')
                return json.loads(raw.decode('utf-8'))
        except Exception as e:
            last=e
            if i<attempts-1: time.sleep(0.4*(2**i))
    raise RuntimeError(f'Failed after {attempts} attempts: {last}')

def research_search(term, country='in', limit=25):
    country=region_code(country)
    if not isinstance(term, str) or not term.strip():
        raise ValueError('Search term is required.')
    term=term.strip()[:200]
    q=urlencode({'term':term,'country':country,'entity':'software','limit':max(1,min(int(limit),50))})
    payload=request_json('https://itunes.apple.com/search?'+q)
    rows=[]; now=int(time.time()); c=db()
    for idx,x in enumerate(payload.get('results',[]),1):
        appid=str(x.get('trackId') or x.get('bundleId') or x.get('trackName',''))
        row={'app_id':appid,'name':x.get('trackName',''),'developer':x.get('artistName',''),'category':x.get('primaryGenreName',''),'store_url':x.get('trackViewUrl',''),'icon':x.get('artworkUrl512') or x.get('artworkUrl100',''),'source':'Apple iTunes Search API','region':country,'rank':idx,'collected_at':now,'raw_json':json.dumps(x,ensure_ascii=False)}
        rows.append(row)
        c.execute('INSERT INTO apps(app_id,name,developer,category,store_url,icon,source,region,rank,collected_at,raw_json) VALUES(:app_id,:name,:developer,:category,:store_url,:icon,:source,:region,:rank,:collected_at,:raw_json)',row)
    c.commit(); c.close()
    return {'query':term,'region':country,'source':'Apple iTunes Search API','collected_at':now,'apps':rows,'note':'Search results are relevance-ranked, not proof of downloads or virality.'}

def snapshot(region='in'):
    region=region_code(region)
    url=f'https://rss.applemarketingtools.com/api/v2/{region}/apps/top-free/50/apps.json'
    payload=request_json(url)
    now=int(time.time()); rows=[]; c=db()
    for idx,x in enumerate(payload.get('feed',{}).get('results',[]),1):
        genres=x.get('genres') or [{}]
        row={'app_id':str(x.get('id','')),'name':x.get('name',''),'developer':x.get('artistName',''),'category':genres[0].get('name',''),'store_url':x.get('url',''),'url':x.get('url',''),'icon':x.get('artworkUrl100',''),'source':'Apple top-free RSS','region':region,'rank':idx,'collected_at':now,'raw_json':json.dumps(x,ensure_ascii=False)}
        rows.append(row); c.execute('INSERT INTO apps(app_id,name,developer,category,store_url,icon,source,region,rank,collected_at,raw_json) VALUES(:app_id,:name,:developer,:category,:store_url,:icon,:source,:region,:rank,:collected_at,:raw_json)',row)
    c.commit(); c.close()
    return {'source':'Apple Marketing Tools RSS','region':region,'collected_at':now,'apps':rows,'note':'Timestamped chart snapshot; ranking changes require repeated snapshots.'}

def history(app_id, limit=30):
    c=db(); rows=[dict(x) for x in c.execute('SELECT name,source,region,rank,collected_at FROM apps WHERE app_id=? ORDER BY collected_at DESC LIMIT ?', (str(app_id),max(1,min(int(limit),100))))]; c.close()
    return {'app_id':app_id,'history':rows,'note':'History accumulates only after AppForge collects repeated snapshots/searches.'}

def reviews(app_id, country='us', limit=25):
    country=region_code(country, 'us')
    if not re.fullmatch(r'[0-9]{1,20}', str(app_id or '')):
        raise ValueError('App Store app ID must be a positive numeric identifier.')
    # Apple's public customer review RSS feed is best-effort and can be unavailable by app/region.
    url=f'https://itunes.apple.com/{country}/rss/customerreviews/id={int(app_id)}/sortBy=mostRecent/json'
    payload=request_json(url, attempts=2); feed=payload.get('feed',{}); entries=feed.get('entry',[])
    if isinstance(entries,dict): entries=[entries]
    out=[]; c=db(); now=int(time.time())
    for i,x in enumerate(entries[:max(1,min(int(limit),50))]):
        if not isinstance(x,dict): continue
        def val(k):
            z=x.get(k,{}); return z.get('label','') if isinstance(z,dict) else ''
        title=val('title'); body=val('content'); rating=val('im:rating'); rid=val('id') or f'{app_id}:{i}:{title}'
        try: rating=int(rating)
        except: rating=0
        author=val('author')
        c.execute('INSERT OR IGNORE INTO reviews(app_id,review_id,title,body,rating,author,source_url,collected_at) VALUES(?,?,?,?,?,?,?,?)',(str(app_id),rid,title,body,rating,author,url,now))
        out.append({'title':title,'body':body,'rating':rating,'author':author,'source_url':url,'collected_at':now})
    c.commit(); c.close()
    return {'app_id':str(app_id),'source_url':url,'collected_at':now,'reviews':out,'note':'Public RSS availability varies; no reviews does not mean no complaints.'}

def repo_catalog():
    # Aider selected as optional adapter: never auto-install into host Python.
    return {'repositories':[{'name':'Aider','url':'https://github.com/Aider-AI/aider','license_claim':'Apache-2.0 (verify upstream LICENSE before deployment)','role':'Git-aware coding assistant','integration':'Optional CLI adapter, restricted to one AppForge workspace project','status':'available' if shutil.which('aider') else 'not-installed','install_command':'python -m pip install aider-chat','safety':'Install in a dedicated virtual environment; configure local model provider; review every diff.'}], 'policy':'Repository license and dependency status must be verified against the current upstream checkout before redistribution. This adapter does not bundle Aider.'}

def create_capacitor(project_name, app_name=None):
    """Prepare a reproducible Capacitor project; does not install SDKs or claim an APK."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,48}', project_name or ''):
        raise ValueError('Invalid project slug')
    if (WORKSPACE / project_name).is_symlink():
        raise ValueError('Project workspace entries cannot be symlinks.')
    p = (WORKSPACE / project_name).resolve()
    if p.parent != WORKSPACE.resolve() or not p.is_dir():
        raise ValueError('Project not found')
    if not (p / 'index.html').is_file():
        raise ValueError('Project must contain index.html before preparing Android scaffold')
    # Generated scaffold paths must be ordinary project-owned files/directories.
    for rel in ('package.json', 'capacitor.config.json', 'tests'):
        target=p/rel
        if target.is_symlink():
            raise ValueError(f'Refusing to write through symlinked scaffold path: {rel}')
        if target.exists() and ((rel == 'tests' and not target.is_dir()) or (rel != 'tests' and not target.is_file())):
            raise ValueError(f'Unexpected scaffold path type: {rel}')
    tests_dir=p/'tests'
    if tests_dir.exists() and (tests_dir/'smoke.test.js').is_symlink():
        raise ValueError('Refusing to overwrite symlinked tests/smoke.test.js')
    label = (app_name or project_name).strip()[:80]
    if not label:
        raise ValueError('App name cannot be empty')
    package_suffix = re.sub(r'[^a-z0-9]', '', project_name.lower())[:40]
    package_id = 'com.appforge.' + package_suffix
    build_script = (
        "node -e \"const fs=require('node:fs');"
        "fs.rmSync('dist',{recursive:true,force:true});"
        "fs.mkdirSync('dist',{recursive:true});"
        "for(const f of ['index.html','app.js','styles.css','manifest.webmanifest','sw.js','assets'])"
        "if(fs.existsSync(f))fs.cpSync(f,'dist/'+f,{recursive:true});\""
    )
    package = {
        "name": re.sub(r'[^a-z0-9-]', '-', project_name.lower()),
        "version": "1.0.0",
        "private": True,
        "description": "Generated by AppForge Local",
        "scripts": {
            "build": build_script,
            "test": "node --test",
            "android:add": "cap add android",
            "android:sync": "npm run build && cap sync android",
            "android:debug": "npm run android:sync && cd android && ./gradlew assembleDebug"
        },
        "dependencies": {"@capacitor/core": "^8.6.0"},
        "devDependencies": {
            "@capacitor/cli": "^8.6.0",
            "@capacitor/android": "^8.6.0"
        }
    }
    (p / 'package.json').write_text(json.dumps(package, indent=2))
    (p / 'capacitor.config.json').write_text(json.dumps({
        'appId': package_id,
        'appName': label,
        'webDir': 'dist'
    }, indent=2))
    (p / 'tests').mkdir(exist_ok=True)
    (p / 'tests' / 'smoke.test.js').write_text(
        "const test=require('node:test');"
        "const assert=require('node:assert/strict');"
        "const fs=require('node:fs');"
        "test('web entry point exists',()=>assert.ok(fs.existsSync('index.html')));"
        "test('app metadata exists',()=>assert.ok(fs.existsSync('appforge-project.json')));\n"
    )
    return {
        'ok': True,
        'project': project_name,
        'files': ['package.json', 'capacitor.config.json', 'tests/smoke.test.js'],
        'package_id': package_id,
        'next_steps': [
            'npm install',
            'npm run build',
            'npm run android:add',
            'npm run android:debug'
        ],
        'apk_expected_path': 'android/app/build/outputs/apk/debug/app-debug.apk',
        'note': 'Only the Capacitor configuration is prepared. Android platform creation, SDK setup, dependency installation and APK generation must be completed and verified separately.'
    }

def test_project(project_name, repair=False, call_llm=None, run_npm_tests=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',project_name or ''): raise ValueError('Invalid project slug')
    if (WORKSPACE/project_name).is_symlink(): raise ValueError('Project workspace entries cannot be symlinks.')
    p=(WORKSPACE/project_name).resolve()
    if p.parent!=WORKSPACE.resolve() or not p.is_dir(): raise ValueError('Project not found')
    logs=[]; failures=[]
    required=['index.html']
    for f in required:
        if not (p/f).is_file(): failures.append(f'Missing required file: {f}')
    for f in p.rglob('*.json'):
        if f.is_symlink() or any(x in f.parts for x in ('node_modules','.git','android')): continue
        try: json.loads(f.read_text())
        except Exception as e: failures.append(f'Invalid JSON {f.relative_to(p)}: {e}')
    if run_npm_tests:
        if not (p/'package.json').is_file():
            failures.append('npm test was requested but package.json is missing')
            logs.append({'stage':'npm-test','skipped':True,'reason':'package.json is missing'})
        elif not shutil.which('npm'):
            failures.append('npm test was requested but npm is not installed')
            logs.append({'stage':'npm-test','skipped':True,'reason':'npm executable is unavailable'})
        else:
            try:
                proc=subprocess.run(['npm','test'],cwd=p,capture_output=True,text=True,timeout=120,
                                    stdin=subprocess.DEVNULL)
                logs.append({'stage':'npm-test','returncode':proc.returncode,'stdout':proc.stdout[-5000:],'stderr':proc.stderr[-5000:]})
                if proc.returncode: failures.append('npm test failed')
            except Exception as e: failures.append('npm test could not run: '+str(e))
    # Syntax-check JavaScript using Node when available.
    if shutil.which('node'):
        for f in list(p.rglob('*.js'))[:100]:
            if f.is_symlink() or any(x in f.parts for x in ('node_modules','.git','android','dist')): continue
            try:
                proc=subprocess.run(['node','--check',str(f)],capture_output=True,text=True,timeout=20)
                if proc.returncode: failures.append(f'JS syntax failed {f.relative_to(p)}: {proc.stderr[-1000:]}')
            except Exception as e: failures.append(f'JS syntax check error: {e}')
    report={'project':project_name,'created_at':int(time.time()),'ok':not failures,'failures':failures,'logs':logs,'checks':['required files','JSON syntax','JavaScript syntax when Node exists'] + (['owner-approved npm test'] if run_npm_tests else []),'repair_mode':'proposal-only' if repair else 'disabled'}
    out=p/'test-reports'
    if out.is_symlink() or (out.exists() and not out.is_dir()):
        raise ValueError('Refusing to write test report through a symlink or non-directory path.')
    out.mkdir(exist_ok=True)
    report_path=out/f'{report["created_at"]}.json'
    if report_path.is_symlink():
        raise ValueError('Refusing to overwrite a symlinked test report.')
    report_path.write_text(json.dumps(report,indent=2))
    return report

def checkpoint_secret_findings(project):
    """Return paths/content markers that must never enter an AppForge Git checkpoint."""
    import fnmatch
    blocked_names = ('.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx',
                     '*.keystore', '*.jks', '*.mobileprovision', '*.provisionprofile', 'google-services.json', 'id_rsa', 'id_ed25519',
                     '*credentials*', '*secret*', '*token*', '*service-account*.json')
    secret_patterns = [
        re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
        re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b'),
        re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
        re.compile(r'\bsk_live_[A-Za-z0-9]{16,}\b'),
        re.compile(r'\bAIza[0-9A-Za-z_-]{30,}\b'),
        re.compile(r'(?i)\b(?:aws_secret_access_key|npm_token)\s*[:=]\s*["\']?[A-Za-z0-9_./+=:-]{16,}'),
        re.compile(r'(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)["\']?\s*[:=]\s*["\'][A-Za-z0-9_./+=:-]{16,}["\']'),
    ]
    findings=[]
    # Scan build output and reports too: Git stages these unless the project ignores them.
    # Only repository metadata, dependencies and Gradle's disposable cache are skipped.
    excluded={'.git','node_modules','.gradle'}
    for root, dirs, files in os.walk(project, followlinks=False):
        dirs[:] = [d for d in dirs if d not in excluded and not (Path(root)/d).is_symlink()]
        for name in files:
            path=Path(root)/name
            rel=path.relative_to(project).as_posix()
            lower=name.lower()
            if any(fnmatch.fnmatch(lower, pattern) for pattern in blocked_names):
                findings.append(rel + ' (sensitive filename)')
                continue
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.stat().st_size > 5_000_000:
                    findings.append(rel + ' (too large to inspect safely)')
                    continue
                raw=path.read_bytes()
                if b'\x00' in raw[:4096]:
                    continue
                content=raw.decode('utf-8', errors='ignore')
                if any(pattern.search(content) for pattern in secret_patterns):
                    findings.append(rel + ' (possible credential content)')
            except OSError:
                findings.append(rel + ' (could not inspect)')
    return findings


def git_action(project_name, action):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',project_name or ''): raise ValueError('Invalid project slug')
    if (WORKSPACE/project_name).is_symlink(): raise ValueError('Project workspace entries cannot be symlinks.')
    p=(WORKSPACE/project_name).resolve()
    if p.parent!=WORKSPACE.resolve() or not p.is_dir(): raise ValueError('Project not found')
    if not shutil.which('git'): return {'ok':False,'error':'Git is not installed'}
    git_meta=p/'.git'
    if git_meta.is_symlink():
        raise ValueError('Project Git metadata cannot be a symlink.')
    if git_meta.exists() and not git_meta.is_dir():
        raise ValueError('Unsupported Git metadata path; expected a real .git directory.')
    if action=='checkpoint':
        secret_findings=checkpoint_secret_findings(p)
        if secret_findings:
            return {'ok':False,'action':action,'error':'Checkpoint blocked: possible secrets or sensitive files were found. Move them outside the project or add an appropriate .gitignore rule, then retry.','blocked_paths':secret_findings[:30],'blocked_count':len(secret_findings)}
    # Override repository and global hook configuration for every Git command. Project hooks
    # are untrusted code and must never execute during checkpoints or rollbacks.
    hooks_dir=STATE/'empty-git-hooks'
    hooks_dir.mkdir(parents=True,exist_ok=True)
    git_env=os.environ.copy()
    git_env.update({'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.hooksPath',
                    'GIT_CONFIG_VALUE_0':str(hooks_dir.resolve()),'GIT_TERMINAL_PROMPT':'0'})
    def run_git(args, **kwargs):
        return subprocess.run(['git']+args,cwd=p,env=git_env,**kwargs)
    if not git_meta.exists():
        run_git(['init'],capture_output=True,text=True,timeout=20,check=True)
        run_git(['config','user.email','appforge-local@localhost'],capture_output=True,text=True,timeout=10,check=True)
        run_git(['config','user.name','AppForge Local'],capture_output=True,text=True,timeout=10,check=True)
    if action=='checkpoint':
        run_git(['add','-A'],capture_output=True,timeout=30,check=True)
        proc=run_git(['commit','-m',f'AppForge checkpoint {int(time.time())}'],capture_output=True,text=True,timeout=30)
        if proc.returncode and 'nothing to commit' in (proc.stdout+' '+proc.stderr).lower():
            head=run_git(['rev-parse','--verify','HEAD'],capture_output=True,text=True,timeout=10)
            if head.returncode==0 and head.stdout.strip():
                return {'ok':True,'stdout':proc.stdout[-2000:],'stderr':proc.stderr[-2000:],'action':action,'checkpoint_sha':head.stdout.strip(),'note':'Working tree is clean; existing HEAD is the checkpoint.'}
        return {'ok':proc.returncode==0,'stdout':proc.stdout[-2000:],'stderr':proc.stderr[-2000:],'action':action}
    if action=='status':
        proc=run_git(['status','--short'],capture_output=True,text=True,timeout=20)
        return {'ok':proc.returncode==0,'status':proc.stdout,'action':action}
    if action=='rollback':
        proc=run_git(['log','-1','--format=%H'],capture_output=True,text=True,timeout=20)
        if proc.returncode or not proc.stdout.strip(): return {'ok':False,'error':'No checkpoint commit exists'}
        # Roll back only tracked working-tree edits to the last checkpoint; untracked files are not deleted.
        reset=run_git(['restore','--worktree','--staged','.'],capture_output=True,text=True,timeout=20)
        return {'ok':reset.returncode==0,'stdout':reset.stdout,'stderr':reset.stderr,'note':'Restored tracked files to the last commit. Untracked files are preserved.'}
    raise ValueError('Unknown Git action')

def run_aider(project_name, prompt, approved=False):
    if not approved: raise ValueError('Explicit approval is required before Aider can modify project files.')
    if not shutil.which('aider'): return {'ok':False,'installed':False,'error':'Aider CLI is not installed. Use a dedicated virtual environment and install aider-chat after reviewing upstream requirements.'}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',project_name or ''): raise ValueError('Invalid project slug')
    if (WORKSPACE/project_name).is_symlink(): raise ValueError('Project workspace entries cannot be symlinks.')
    p=(WORKSPACE/project_name).resolve()
    if p.parent!=WORKSPACE.resolve() or not p.is_dir(): raise ValueError('Project not found')
    if not isinstance(prompt,str) or len(prompt.strip())<10 or len(prompt)>4000: raise ValueError('Provide a focused change request between 10 and 4000 characters')
    cfg=json.loads((ROOT/'config.local.json').read_text())
    if not local_endpoint_allowed(cfg.get('llm_base_url', '')):
        return {'ok':False,'installed':True,'error':'Local-first policy: Aider can only use localhost or a private-LAN model endpoint.'}
    # A checkpoint must succeed before allowing a coding agent to edit anything.
    cp=git_action(project_name,'checkpoint')
    if not cp.get('ok'): return {'ok':False,'error':'Git checkpoint failed; refusing to run coding agent.','checkpoint':cp}
    cmd=['aider','--message',prompt,'--yes','--no-auto-commits','--model','openai/'+str(cfg.get('llm_model','qwen2.5-coder')),'--openai-api-base',str(cfg.get('llm_base_url','http://127.0.0.1:8080/v1'))]
    # Do not pass the AppForge process environment wholesale to a project-aware coding agent.
    env={}
    for key in ('PATH','HOME','USERPROFILE','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR'):
        if key in os.environ: env[key]=os.environ[key]
    env.update({'OPENAI_API_KEY':str(cfg.get('llm_api_key','ollama')),
                'GIT_TERMINAL_PROMPT':'0','CI':'true'})
    reports=p/'test-reports'
    if reports.is_symlink() or (reports.exists() and not reports.is_dir()):
        return {'ok':False,'installed':True,'error':'Refusing to write Aider output through a symlinked or invalid test-reports path.'}
    try:
        proc=subprocess.run(cmd,cwd=p,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=900)
        log={'created_at':int(time.time()),'command':'aider --message [redacted]','returncode':proc.returncode,'stdout':proc.stdout[-12000:],'stderr':proc.stderr[-12000:]}
        reports.mkdir(exist_ok=True)
        report=reports/f'aider-{log["created_at"]}.json'
        if report.is_symlink(): return {'ok':False,'installed':True,'error':'Refusing to overwrite a symlinked Aider report.'}
        report.write_text(json.dumps(log,indent=2))
        return {'ok':proc.returncode==0,'installed':True,'log':log,'note':'Review the Git diff and run tests before accepting the changes.'}
    except Exception as e: return {'ok':False,'installed':True,'error':str(e)}

def launch_config(project_name, config=None):
    c=db(); now=int(time.time())
    if config is not None:
        safe={'monetization':config.get('monetization','none'),'price':str(config.get('price',''))[:40],'currency':config.get('currency','INR'),'ads_provider':config.get('ads_provider','none'),'analytics':config.get('analytics','local-only'),'privacy_url':str(config.get('privacy_url',''))[:300],'support_email':str(config.get('support_email',''))[:200],'target_regions':config.get('target_regions',['IN'])}
        c.execute('INSERT INTO launch_config(project,config,updated_at) VALUES(?,?,?) ON CONFLICT(project) DO UPDATE SET config=excluded.config,updated_at=excluded.updated_at',(project_name,json.dumps(safe),now)); c.commit()
    row=c.execute('SELECT config,updated_at FROM launch_config WHERE project=?',(project_name,)).fetchone(); c.close()
    return {'project':project_name,'config':json.loads(row['config']) if row else {'monetization':'none','currency':'INR','analytics':'local-only'},'updated_at':row['updated_at'] if row else None,'checklist':[{'task':'Original app functionality tested on device','required':True},{'task':'Privacy policy and data disclosures reviewed','required':True},{'task':'Store listing, screenshots, icon and content rating prepared','required':True},{'task':'Release signing key backed up securely','required':True},{'task':'Billing/ads SDK policy and consent flows verified','required':True},{'task':'Crash/retention/conversion analytics validated','required':False},{'task':'Google Play developer account and target API requirements checked','required':True}],'note':'This is a launch checklist/configuration store, not live billing, ad serving, store submission, or revenue collection.'}

def track_event(project, event, value=None, metadata=None):
    c=db(); c.execute('INSERT INTO events(project,event,value,metadata,created_at) VALUES(?,?,?,?,?)',(str(project)[:64],str(event)[:80],float(value) if value is not None else None,json.dumps(metadata or {})[:4000],int(time.time()))); c.commit(); c.close(); return {'ok':True}

def analytics(project):
    c=db(); rows=[dict(r) for r in c.execute('SELECT event,COUNT(*) count,MAX(created_at) last_seen FROM events WHERE project=? GROUP BY event ORDER BY count DESC',(project,))]; total=c.execute('SELECT COUNT(*) FROM events WHERE project=?',(project,)).fetchone()[0]; c.close(); return {'project':project,'total_events':total,'events':rows,'note':'Only locally recorded events are included; no users or external analytics are tracked automatically.'}

def repair_project(project_name, approved=False):
    """One bounded, owner-approved local-model repair attempt with checkpoint and rollback."""
    if not approved: raise ValueError('Explicit approval is required before model-generated edits are applied.')
    first=test_project(project_name)
    if first['ok']: return {'ok':True,'message':'No repair needed; current checks passed.','before':first,'after':first}
    if (WORKSPACE/project_name).is_symlink(): raise ValueError('Project workspace entries cannot be symlinks.')
    p=(WORKSPACE/project_name).resolve()
    cfg=json.loads((ROOT/'config.local.json').read_text())
    if not local_endpoint_allowed(cfg.get('llm_base_url', '')):
        return {'ok':False,'error':'Local-first policy: repair requires a localhost or private-LAN model endpoint.','before':first}
    checkpoint=git_action(project_name,'checkpoint')
    if not checkpoint.get('ok'): return {'ok':False,'error':'Could not create Git checkpoint; no files changed.','checkpoint':checkpoint,'before':first}
    candidates=[]
    for rel in first.get('failures',[]):
        m=re.match(r'(?:Invalid JSON |JS syntax failed )([^:]+):',rel)
        if m: candidates.append(m.group(1))
    # Include relevant project entry points, but never send node_modules/build output.
    for rel in ['index.html','app.js','styles.css','package.json','capacitor.config.json']:
        if (p/rel).is_file() and not (p/rel).is_symlink() and rel not in candidates: candidates.append(rel)
    snippets={}
    for rel in candidates[:12]:
        source=p/rel
        if source.is_symlink(): continue
        f=source.resolve()
        if p not in f.parents or not f.is_file() or f.stat().st_size>100000: continue
        snippets[rel]=f.read_text(errors='replace')
    payload={'model':cfg['llm_model'],'messages':[{'role':'system','content':'You are a careful repair engineer. Return ONLY a JSON object {"files":{"existing/relative/path":"complete replacement content"},"explanation":"..."}. Fix only listed test failures. Do not add dependencies, network calls, credentials, obfuscation, or unrelated features. Only replace files included in the supplied files map. If unsure return an empty files object.'},{'role':'user','content':json.dumps({'failures':first['failures'],'files':snippets},ensure_ascii=False)[:24000]}],'temperature':0.1}
    url=cfg['llm_base_url'].rstrip('/')+'/chat/completions'
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+str(cfg.get('llm_api_key','ollama'))},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=max(5,min(int(cfg.get('timeout_seconds',120)),600))) as r:
            raw = r.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ValueError('Local repair response exceeds the 10 MB safety limit.')
            response = json.loads(raw.decode('utf-8'))
        text=response['choices'][0]['message']['content'].strip(); text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I)
        patch=json.loads(text)
        if not isinstance(patch.get('files'),dict) or not patch['files']: return {'ok':False,'error':'Model did not return a usable patch. No files changed.','before':first,'model_response':text[:4000]}
        applied=[]
        for rel,content in patch['files'].items():
            if rel not in snippets or not isinstance(content,str) or len(content)>200000: continue
            source=p/rel
            if source.is_symlink(): continue
            target=source.resolve()
            if p not in target.parents or not target.is_file(): continue
            target.write_text(content); applied.append(rel)
        if not applied: return {'ok':False,'error':'No safe existing-file changes were returned.','before':first,'explanation':patch.get('explanation','')}
        after=test_project(project_name)
        if not after['ok']:
            git_action(project_name,'rollback')
            return {'ok':False,'rolled_back':True,'before':first,'after':after,'changed_files':applied,'message':'Repair failed regression checks; tracked files were restored to the pre-repair checkpoint.'}
        return {'ok':True,'rolled_back':False,'before':first,'after':after,'changed_files':applied,'explanation':patch.get('explanation',''),'message':'One approved repair attempt passed the available checks. Review the Git diff before release.'}
    except Exception as e:
        return {'ok':False,'error':'Repair attempt failed: '+str(e),'before':first,'message':'No automatic claim of success. Inspect the project and test report.'}
