"""Door #1 into Databricks: Databricks SQL.

Needs three env vars (never in code — Replit Secrets locally, Key Vault on Azure):
    DATABRICKS_HOST       e.g. adb-12345.azuredatabricks.net  (no https://)
    DATABRICKS_HTTP_PATH  from SQL Warehouses -> Connection details
    DATABRICKS_TOKEN      personal access token (dev) / service principal (prod)
Optional:
    DATABRICKS_CATALOG    Unity Catalog catalog to explore, default "main"
"""
import os

REQUIRED = ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")


def is_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED)


def missing() -> list:
    return [k for k in REQUIRED if not os.environ.get(k)]


def _connect():
    from databricks import sql
    if not is_configured():
        raise RuntimeError(
            "Databricks is not configured. Set: " + ", ".join(missing()))
    return sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )


def run_sql(sql_text: str, timeout: int = 60):
    """Execute read-only SQL against the warehouse. Returns (columns, rows)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql_text)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]
        return cols, rows
    finally:
        conn.close()


def discover_schema(catalog: str | None = None, max_tables: int = 100) -> list:
    """Walk Unity Catalog: every table + its columns. This is how the app
    answers 'I don't know what data to use' — it looks for itself."""
    catalog = catalog or os.environ.get("DATABRICKS_CATALOG", "main")
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT table_schema, table_name FROM {catalog}.information_schema.tables
            WHERE table_type = 'BASE TABLE' ORDER BY table_schema, table_name
            LIMIT {int(max_tables)}""")
        tables = cur.fetchall()
        out = []
        for schema, table in tables:
            cur.execute(f"""
                SELECT column_name, data_type
                FROM {catalog}.information_schema.columns
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position""")
            cols = [{"name": c, "type": t} for c, t in cur.fetchall()]
            out.append({"name": f"{catalog}.{schema}.{table}", "columns": cols})
        return out
    finally:
        conn.close()
