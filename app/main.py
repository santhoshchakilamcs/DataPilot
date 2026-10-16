"""DataPilot — ask your warehouse questions in plain English.

Flow:  UI -> POST /api/ask -> engine.ask() -> schema -> LLM -> SQL
       -> guardrails -> Databricks (or demo SQLite) -> rows -> UI/chart
Dashboards are saved ask-results that re-run on every view.
"""
import os
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import databricks_client, demo_db, engine, llm
from .auth import require_key
from .schema_provider import get_schema

app = FastAPI(title="DataPilot", version="1.0.0")


@app.on_event("startup")
def startup():
    demo_db.init()  # local state: dashboards, history, demo warehouse


class AskRequest(BaseModel):
    question: str


class QueryRequest(BaseModel):
    sql: str


class DashboardCreate(BaseModel):
    title: str
    question: str
    sql: str
    chart: str = "auto"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "datapilot",
            "warehouse": "databricks" if databricks_client.is_configured() else "demo",
            "llm_mode": llm.MODE}


@app.get("/api/schema", dependencies=[Depends(require_key)])
def schema():
    return get_schema()


@app.post("/api/ask", dependencies=[Depends(require_key)])
def ask(req: AskRequest):
    try:
        return engine.ask(req.question)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.post("/api/query", dependencies=[Depends(require_key)])
def query(req: QueryRequest):
    """Run raw SQL (dashboard re-runs). Still guardrailed."""
    try:
        return engine.run_saved(req.sql)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.get("/api/dashboards", dependencies=[Depends(require_key)])
def list_dashboards():
    conn = demo_db.get_conn()
    rows = conn.execute("SELECT * FROM dashboards ORDER BY id DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            res = engine.run_saved(d["sql"])
            d["result"] = res
        except Exception as e:  # a dead card shows its error, not a 500
            d["result"] = {"columns": [], "rows": [], "error": str(e)}
        out.append(d)
    return out


@app.post("/api/dashboards", dependencies=[Depends(require_key)])
def create_dashboard(req: DashboardCreate):
    try:
        engine.run_saved(req.sql)  # validate before saving
    except ValueError as e:
        raise HTTPException(400, str(e))
    conn = demo_db.get_conn()
    cur = conn.execute(
        "INSERT INTO dashboards(title, question, sql, chart) VALUES (?,?,?,?)",
        (req.title, req.question, req.sql, req.chart))
    did = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": did}


@app.delete("/api/dashboards/{did}", dependencies=[Depends(require_key)])
def delete_dashboard(did: int):
    conn = demo_db.get_conn()
    cur = conn.execute("DELETE FROM dashboards WHERE id=?", (did,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Dashboard card not found")
    return {"deleted": did}


STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
