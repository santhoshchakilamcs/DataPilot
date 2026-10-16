# DataPilot — Ask your warehouse anything

A natural-language data copilot for Databricks. Type a question, the app
finds the right tables, writes the SQL, runs it read-only, and shows you
the data with a chart. Save any answer as a live dashboard card for the team.

Built to learn the full enterprise loop end to end:
**Databricks (data) → LLM (language) → FastAPI (service) → UI → Azure (deploy).**

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  Browser UI │────▶│ FastAPI  /api/ask                        │
│  Ask · Dash │     │   1. schema_provider: what tables exist? │
│  boards ·   │     │   2. llm: question -> SQL (demo/azure)   │
│  Data       │     │   3. guardrails: SELECT-only, LIMIT      │
└─────────────┘     │   4. warehouse: Databricks | demo SQLite │
                    │   5. chart + table + "save to dashboard" │
                    └──────────────────────────────────────────┘
```

## Run it now (zero credentials)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

On Replit: **Import from GitHub** → the `.replit` file boots it. First load
seeds a demo warehouse (5 plants, 5 products, 80 quotes). Try:

- "What tables can I use?"
- "Average price by product"
- "Revenue by product"
- "Quotes by plant"
- "Recent quotes"

## Connect your real Databricks (the whole point)

Set three env vars — Replit Secrets locally, Key Vault on Azure:

| Var | Where to find it |
|---|---|
| `DATABRICKS_HOST` | your workspace URL host, e.g. `adb-123.adb...net` |
| `DATABRICKS_HTTP_PATH` | SQL Warehouses → your warehouse → Connection details |
| `DATABRICKS_TOKEN` | profile → Settings → Developer → Access tokens |

Optional: `DATABRICKS_CATALOG` (default `main`).

The moment those exist, the app switches sources automatically:
schema discovery walks Unity Catalog `information_schema`, questions run
against your real tables, and `/api/health` reports `"warehouse": "databricks"`.
The UI doesn't change at all.

## Full natural language (beyond demo patterns)

`LLM_MODE` controls the translator:

| Mode | Needs | Notes |
|---|---|---|
| `demo` (default) | nothing | pattern-based, honest about limits |
| `azure` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT` | production path |
| `openai` | `OPENAI_API_KEY` | same prompt, OpenAI client |

In `azure`/`openai` mode the LLM gets the live schema and returns
`{"sql", "explanation"}` — still forced through the guardrails.

## Guardrails (read-only by design)

`app/guardrails.py` — every SQL string passes through `validate()`:
must start with `SELECT`/`WITH`, blocked keywords (`DROP`, `DELETE`,
`INSERT`, …) rejected, `LIMIT 200` appended when missing. The copilot
can never write to your warehouse.

## Dashboards

Any answer → **Save to dashboard** → it becomes a card that re-runs its
SQL live on every view. That's the team's analytics layer: no BI tool,
no refresh schedules, just saved questions.

## Deploy to Azure

See [azure/deploy.md](azure/deploy.md) — full runbook: Azure OpenAI
resource, Key Vault secrets, App Service (recommended) or Container Apps,
managed identity, verification. ~15 minutes with the CLI.

## What's demo vs. real (honest inventory)

| Piece | Demo (today) | Production (Azure) |
|---|---|---|
| Warehouse | SQLite, 80 synthetic quotes | your Databricks SQL Warehouse |
| Schema discovery | PRAGMA inventory | Unity Catalog `information_schema` |
| NL → SQL | pattern translator | Azure OpenAI |
| Auth | demo API key | Entra ID (swap `app/auth.py`) |
| Dashboards/history | local SQLite | Azure Files or Postgres |
| Hosting | Replit | App Service + Key Vault |

## Interview talking points

- "I built a natural-language copilot over the warehouse: the app discovers
  the schema itself, an LLM writes the SQL, and guardrails enforce read-only."
- "The warehouse is a seam, not a rewrite — Databricks or demo SQLite, the
  UI and API don't change."
- "Every answer is explainable: you see the SQL before you trust the chart."
- "Dashboards are just saved questions that re-run — the analytics layer
  builds itself from usage."
- "Deployment is App Service + Key Vault + managed identity; the only
  secret the app ever sees comes from the vault."
