"""AppForge Local free-source opportunity radar and locally stored idea shortlist."""
from pathlib import Path
import sqlite3, time\nfrom urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
STATE.mkdir(exist_ok=True)
DB = STATE / "opportunities.db"

FIELDS = {
    "demand": (0, 25),
    "revenue": (0, 20),
    "gap": (0, 20),
    "build_ease": (0, 15),
    "monetization": (0, 10),
    "fit": (0, 10),
}
SOURCES = [
    {"name":"Product Hunt","url":"https://www.producthunt.com/","purpose":"New launches and launch traction"},
    {"name":"BetaList","url":"https://betalist.com/","purpose":"Early-stage launches"},
    {"name":"Indie Hackers","url":"https://www.indiehackers.com/","purpose":"Founder revenue stories and lessons"},
    {"name":"Reddit","url":"https://www.reddit.com/","purpose":"Pain points, complaints, and requests"},
    {"name":"Google Play","url":"https://play.google.com/store/apps","purpose":"Mobile competitors and reviews"},
    {"name":"AppMagic","url":"https://appmagic.rocks/","purpose":"Mobile app estimates (limited free access)"},
    {"name":"Appfigures","url":"https://appfigures.com/","purpose":"App market estimates (limited free access)"},
    {"name":"GitHub Trending","url":"https://github.com/trending","purpose":"Emerging open-source projects"},
    {"name":"Google Trends","url":"https://trends.google.com/trends/","purpose":"Demand trend validation"},
    {"name":"AlternativeTo","url":"https://alternativeto.net/","purpose":"Competitor and alternative discovery"},
    {"name":"Hacker News","url":"https://news.ycombinator.com/","purpose":"Technical problems and new products"},
    {"name":"YC Companies","url":"https://www.ycombinator.com/companies","purpose":"Startup product and market discovery"},
    {"name":"Exploding Topics","url":"https://explodingtopics.com/","purpose":"Emerging consumer/business trends"},
    {"name":"Similarweb","url":"https://www.similarweb.com/","purpose":"Website traffic estimates (limited free access)"},
]

def _connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS opportunities(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, problem TEXT NOT NULL DEFAULT '',
        audience TEXT NOT NULL DEFAULT '', source_name TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
        evidence TEXT NOT NULL DEFAULT '', revenue_note TEXT NOT NULL DEFAULT '', launch_age TEXT NOT NULL DEFAULT '',
        demand INTEGER NOT NULL DEFAULT 0, revenue INTEGER NOT NULL DEFAULT 0, gap INTEGER NOT NULL DEFAULT 0,
        build_ease INTEGER NOT NULL DEFAULT 0, monetization INTEGER NOT NULL DEFAULT 0, fit INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'research', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
    )""")
    return conn

def _score(row):
    return sum(int(row.get(k,0)) for k in FIELDS)

def _clean_text(value, max_len):
    return str(value or "").strip()[:max_len]

def list_opportunities():
    with _connect() as db:
        rows = db.execute("SELECT * FROM opportunities ORDER BY (demand+revenue+gap+build_ease+monetization+fit) DESC, updated_at DESC").fetchall()
        return {"opportunities":[dict(r, score=_score(dict(r))) for r in rows], "sources":SOURCES,
                "score_max":100, "note":"Scores are your structured judgment, not verified market data. Revenue/download estimates must be labelled and sourced."}

def save_opportunity(data):
    if not isinstance(data, dict): raise ValueError("Expected an idea object.")
    title=_clean_text(data.get("title"),160)
    if not title: raise ValueError("Idea title is required.")
    fields={}
    for key,(lo,hi) in FIELDS.items():
        try: value=int(data.get(key,0))
        except (ValueError,TypeError): raise ValueError(f"{key} must be an integer.")
        if not lo<=value<=hi: raise ValueError(f"{key} must be between {lo} and {hi}.")
        fields[key]=value
    status=data.get("status","research")
    if status not in ("research","validate","build","rejected","launched"): status="research"
    source_url=_clean_text(data.get("source_url"),1000)\n    if source_url and urlparse(source_url).scheme not in ("http","https"):\n        raise ValueError("Source URL must use http or https.")\n    now=int(time.time())
    values=(title,_clean_text(data.get("problem"),2000),_clean_text(data.get("audience"),500),
      _clean_text(data.get("source_name"),120),source_url,
      _clean_text(data.get("evidence"),4000),_clean_text(data.get("revenue_note"),1000),
      _clean_text(data.get("launch_age"),120),fields["demand"],fields["revenue"],fields["gap"],
      fields["build_ease"],fields["monetization"],fields["fit"],status,now,now)
    with _connect() as db:
        if data.get("id"):
            try: oid=int(data["id"])
            except (ValueError,TypeError): raise ValueError("Invalid opportunity id.")
            db.execute("""UPDATE opportunities SET title=?,problem=?,audience=?,source_name=?,source_url=?,
                evidence=?,revenue_note=?,launch_age=?,demand=?,revenue=?,gap=?,build_ease=?,monetization=?,fit=?,
                status=?,updated_at=? WHERE id=?""", values[:-2]+(now,oid))
            if db.execute("SELECT changes()").fetchone()[0]==0: raise ValueError("Opportunity not found.")
        else:
            db.execute("""INSERT INTO opportunities(title,problem,audience,source_name,source_url,evidence,revenue_note,
                launch_age,demand,revenue,gap,build_ease,monetization,fit,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            oid=db.execute("SELECT last_insert_rowid()").fetchone()[0]
        row=db.execute("SELECT * FROM opportunities WHERE id=?",(oid,)).fetchone()
    result=dict(row); result["score"]=_score(result)
    return {"ok":True,"opportunity":result}

def delete_opportunity(oid):
    try: oid=int(oid)
    except (ValueError,TypeError): raise ValueError("Invalid opportunity id.")
    with _connect() as db:
        cur=db.execute("DELETE FROM opportunities WHERE id=?",(oid,))
        if cur.rowcount==0: raise ValueError("Opportunity not found.")
    return {"ok":True,"deleted":oid}
