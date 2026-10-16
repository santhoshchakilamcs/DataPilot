"""Question -> SQL, three modes.

LLM_MODE=demo   : built-in pattern translator. Zero credentials, runs on
                  Replit today. Handles common questions over the demo
                  schema; says so honestly when it can't.
LLM_MODE=azure  : Azure OpenAI chat completion. Production path.
LLM_MODE=openai : OpenAI API. Same prompt, different client.

Returns (sql | None, explanation). sql=None means "I can't translate this".
"""
import json
import os
import re

MODE = os.environ.get("LLM_MODE", "demo")

SYSTEM = """You translate business questions into Databricks SQL.
You are given table schemas as: table_name(col TYPE, col TYPE, ...)

Rules:
- Output ONE read-only SELECT statement (WITH ... SELECT is fine).
- Use the fully-qualified table names exactly as given.
- Join on obvious key relationships (e.g. quotes.product_id = products.id).
- Always include LIMIT 200 unless the question asks for an aggregate.
- Never invent table or column names — only use what is in the schema.
- Respond with ONLY a JSON object: {"sql": "...", "explanation": "..."}
  where explanation is one plain-English sentence a sales manager would understand."""


def generate_sql(question: str, schema_text: str):
    if MODE == "azure":
        return _via_azure(question, schema_text)
    if MODE == "openai":
        return _via_openai(question, schema_text)
    return _demo(question)


# ---------------- demo translator (honest toy, real loop) ----------------
def _demo(question: str):
    q = question.lower()
    if re.search(r"what (tables|data)|list tables|show .*tables|available data", q):
        return "__SCHEMA__", "Here is every table I can see. Ask me about any of them."
    if re.search(r"accept|reject|feedback|win rate", q):
        return ("""SELECT COALESCE(feedback, 'pending') AS outcome, COUNT(*) AS quotes
FROM quotes GROUP BY feedback ORDER BY quotes DESC""",
                "How quotes are landing: accepted, rejected, or still pending.")
    if re.search(r"how many quotes|number of quotes|count.*quotes|total quotes", q):
        return ("SELECT COUNT(*) AS total_quotes FROM quotes",
                "Counting every quote in the system.")
    if re.search(r"average.*price.*product|avg.*price.*product|price by product", q):
        return ("""SELECT p.name AS product, ROUND(AVG(q.unit_price), 2) AS avg_price_per_ton
FROM quotes q JOIN products p ON p.id = q.product_id
GROUP BY p.name ORDER BY avg_price_per_ton DESC""",
                "Average quoted price per ton, broken down by product.")
    if re.search(r"revenue", q):
        return ("""SELECT p.name AS product, ROUND(SUM(q.total_price), 2) AS total_revenue
FROM quotes q JOIN products p ON p.id = q.product_id
GROUP BY p.name ORDER BY total_revenue DESC""",
                "Total quoted revenue summed up by product.")
    if re.search(r"by plant", q):
        return ("""SELECT pl.name AS plant, COUNT(*) AS quotes,
       ROUND(AVG(q.unit_price), 2) AS avg_price_per_ton
FROM quotes q JOIN plants pl ON pl.id = q.plant_id
GROUP BY pl.name ORDER BY quotes DESC""",
                "Quote volume and average price for each plant.")
    if re.search(r"recent|latest", q):
        return ("""SELECT q.id, p.name AS product, pl.name AS plant,
       q.quantity_tons, q.unit_price, q.total_price
FROM quotes q JOIN products p ON p.id = q.product_id
JOIN plants pl ON pl.id = q.plant_id ORDER BY q.id DESC""",
                "The most recent quotes, newest first.")
    if re.search(r"confidence", q):
        return ("SELECT ROUND(AVG(confidence) * 100, 1) AS avg_confidence_pct FROM quotes",
                "Average model confidence across all quotes.")
    if re.search(r"highest|most expensive|top.*price", q):
        return ("""SELECT q.id, p.name AS product, pl.name AS plant,
       q.quantity_tons, q.unit_price
FROM quotes q JOIN products p ON p.id = q.product_id
JOIN plants pl ON pl.id = q.plant_id ORDER BY q.unit_price DESC""",
                "The priciest quotes by dollars per ton.")
    return (None,
            "Demo mode only handles simple questions so far — try 'average price by "
            "product', 'revenue by product', 'quotes by plant', or 'recent quotes'. "
            "Set LLM_MODE=azure with an Azure OpenAI key for full natural language.")


# ---------------- production LLM paths ----------------
def _via_azure(question: str, schema_text: str):
    from openai import AzureOpenAI
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"):
        if not os.environ.get(k):
            raise RuntimeError(f"LLM_MODE=azure needs {k} set.")
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
    )
    resp = client.chat.completions.create(
        model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"Schema:\n{schema_text}\n\nQuestion: {question}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(resp.choices[0].message.content)
    return data["sql"], data.get("explanation", "")


def _via_openai(question: str, schema_text: str):
    from openai import OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("LLM_MODE=openai needs OPENAI_API_KEY set.")
    client = OpenAI()
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"Schema:\n{schema_text}\n\nQuestion: {question}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(resp.choices[0].message.content)
    return data["sql"], data.get("explanation", "")
