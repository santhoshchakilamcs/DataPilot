"""The ask pipeline: question -> schema -> SQL -> guardrails -> warehouse -> rows.

Nothing here knows whether the warehouse is Databricks or the demo SQLite —
schema_provider and the executors make that decision in exactly one place.
"""
from . import databricks_client, demo_db, guardrails, llm, schema_provider


def _execute(sql_text: str):
    if databricks_client.is_configured():
        return databricks_client.run_sql(sql_text), "databricks"
    return demo_db.run_sql(sql_text), "demo"


def ask(question: str) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Ask me something first.")
    schema = schema_provider.get_schema()
    sql, explanation = llm.generate_sql(question, schema_provider.compact_text(schema))

    if sql == "__SCHEMA__":
        tables = [{"table": t["name"],
                   "columns": ", ".join(c["name"] for c in t["columns"]),
                   "rows": t.get("rows")}
                  for t in schema["tables"]]
        return {"question": question, "sql": None, "explanation": explanation,
                "columns": ["table", "columns", "rows"],
                "rows": [[t["table"], t["columns"], t["rows"]] for t in tables],
                "row_count": len(tables), "source": schema["source"],
                "llm_mode": llm.MODE}

    if sql is None:
        return {"question": question, "sql": None, "explanation": explanation,
                "columns": [], "rows": [], "row_count": 0,
                "source": schema["source"], "llm_mode": llm.MODE}

    safe_sql = guardrails.validate(sql)
    (cols, rows), source = _execute(safe_sql)
    _log(question, safe_sql, len(rows))
    return {"question": question, "sql": safe_sql, "explanation": explanation,
            "columns": cols, "rows": rows, "row_count": len(rows),
            "source": source, "llm_mode": llm.MODE}


def run_saved(sql_text: str):
    """Re-run a dashboard's stored SQL (still goes through guardrails)."""
    safe_sql = guardrails.validate(sql_text)
    (cols, rows), source = _execute(safe_sql)
    return {"sql": safe_sql, "columns": cols, "rows": rows,
            "row_count": len(rows), "source": source}


def _log(question: str, sql: str, row_count: int):
    conn = demo_db.get_conn()
    conn.execute("INSERT INTO ask_history(question, sql, row_count) VALUES (?,?,?)",
                 (question, sql, row_count))
    conn.commit()
    conn.close()
