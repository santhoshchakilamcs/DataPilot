"""Demo warehouse: a local SQLite standing in for Databricks.

When DATABRICKS_HOST is set, the app talks to the real warehouse and this
module is bypassed entirely. Until then, this gives you the full loop —
ask questions, get SQL, see data — with zero credentials.
"""
import math
import random
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "datapilot.db"

PLANTS = [
    {"code": "AUS-01", "name": "Austin Plant", "lat": 30.2672, "lon": -97.7431},
    {"code": "SAT-02", "name": "San Antonio Plant", "lat": 29.4241, "lon": -98.4936},
    {"code": "DAL-03", "name": "Dallas Plant", "lat": 32.7767, "lon": -96.7970},
    {"code": "HOU-04", "name": "Houston Plant", "lat": 29.7604, "lon": -95.3698},
    {"code": "PHX-05", "name": "Phoenix Plant", "lat": 33.4484, "lon": -112.0740},
]

PRODUCTS = [
    {"sku": "AGG-34", "name": 'Concrete Aggregate 3/4"', "base_price": 18.50},
    {"sku": "HMA-12", "name": "Hot Mix Asphalt", "base_price": 72.00},
    {"sku": "BAS-01", "name": "Road Base Material", "base_price": 14.25},
    {"sku": "SND-02", "name": "Washed Sand", "base_price": 16.75},
    {"sku": "RIP-03", "name": "Rip Rap", "base_price": 22.00},
]

SEGMENTS = ["contractor", "government", "retail"]
SEG_MULT = {"contractor": 1.00, "government": 0.97, "retail": 1.08}


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _haversine(lat1, lon1, lat2, lon2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + \
        math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def init() -> None:
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS plants(
        id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, lat REAL, lon REAL);
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT, base_price REAL);
    CREATE TABLE IF NOT EXISTS quotes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT (datetime('now')),
        product_id INTEGER, plant_id INTEGER, quantity_tons REAL,
        dest_lat REAL, dest_lon REAL, distance_miles REAL,
        customer_segment TEXT, unit_price REAL, total_price REAL,
        confidence REAL, feedback TEXT DEFAULT NULL);
    CREATE TABLE IF NOT EXISTS dashboards(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        question TEXT NOT NULL, sql TEXT NOT NULL, chart TEXT DEFAULT 'auto',
        created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS ask_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, sql TEXT,
        row_count INTEGER, created_at TEXT DEFAULT (datetime('now')));
    """)
    for p in PLANTS:
        conn.execute("INSERT OR IGNORE INTO plants(code,name,lat,lon) VALUES (?,?,?,?)",
                     (p["code"], p["name"], p["lat"], p["lon"]))
    for p in PRODUCTS:
        conn.execute("INSERT OR IGNORE INTO products(sku,name,base_price) VALUES (?,?,?)",
                     (p["sku"], p["name"], p["base_price"]))

    n = conn.execute("SELECT COUNT(*) c FROM quotes").fetchone()["c"]
    if n == 0:
        rng = random.Random(7)
        plants = conn.execute("SELECT * FROM plants").fetchall()
        products = conn.execute("SELECT * FROM products").fetchall()
        for _ in range(80):
            pl = rng.choice(plants)
            pr = rng.choice(products)
            seg = rng.choice(SEGMENTS)
            qty = round(rng.uniform(20, 1500), 1)
            # random delivery point within ~150 miles of the plant
            ang, d = rng.uniform(0, 6.283), rng.uniform(5, 150)
            dlat = pl["lat"] + (d / 69.0) * math.cos(ang)
            dlon = pl["lon"] + (d / 54.6) * math.sin(ang)
            dist = _haversine(pl["lat"], pl["lon"], dlat, dlon)
            month = rng.randint(1, 12)
            price = pr["base_price"] * SEG_MULT[seg]
            if month in (5, 6, 7, 8, 9):
                price *= 1.03
            price += dist * 0.18
            if qty >= 500:
                price *= 0.93
            elif qty >= 200:
                price *= 0.96
            elif qty >= 100:
                price *= 0.98
            price = round(max(price, 5.0), 2)
            conn.execute(
                """INSERT INTO quotes(product_id, plant_id, quantity_tons, dest_lat,
                   dest_lon, distance_miles, customer_segment, unit_price,
                   total_price, confidence, feedback)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (pr["id"], pl["id"], qty, round(dlat, 4), round(dlon, 4),
                 round(dist, 1), seg, price, round(price * qty, 2),
                 round(rng.uniform(0.85, 0.98), 2),
                 rng.choice(["accepted", "rejected", None, None])))
    conn.commit()
    conn.close()


def describe_schema() -> list:
    """Table + column inventory for the schema explorer and the LLM context."""
    conn = get_conn()
    out = []
    for (t,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        cols = [{"name": r[1], "type": r[2]}
                for r in conn.execute(f"PRAGMA table_info({t})")]
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        out.append({"name": t, "columns": cols, "rows": n})
    conn.close()
    return out


def run_sql(sql_text: str):
    conn = get_conn()
    cur = conn.execute(sql_text)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [list(r) for r in cur.fetchall()]
    conn.close()
    return cols, rows
