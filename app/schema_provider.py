"""One schema interface, two backends.

Real Databricks -> Unity Catalog information_schema.
Demo mode        -> local SQLite PRAGMA inventory.
The rest of the app never knows which one answered.
"""
from . import databricks_client, demo_db


def get_schema() -> dict:
    if databricks_client.is_configured():
        tables = databricks_client.discover_schema()
        return {"source": "databricks", "tables": tables}
    return {"source": "demo", "tables": demo_db.describe_schema()}


def compact_text(schema: dict, max_tables: int = 40) -> str:
    """One-line-per-table context for the LLM prompt."""
    lines = []
    for t in schema["tables"][:max_tables]:
        cols = ", ".join(f'{c["name"]} {c["type"]}' for c in t["columns"])
        lines.append(f'- {t["name"]}({cols})')
    return "\n".join(lines)
