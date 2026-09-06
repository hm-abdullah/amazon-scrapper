# Async SQLite database storage interface and CRUD operations.

import sqlite3
import aiosqlite
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "scrapers" / "storage" / "scraper.db"

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT UNIQUE NOT NULL,
                brand TEXT,
                title TEXT,
                seller TEXT,
                price REAL,
                currency TEXT,
                availability TEXT,
                description TEXT,
                bullet_points TEXT,
                specifications TEXT,
                images TEXT,
                rating REAL,
                review_count INTEGER,
                product_url TEXT,
                scraped_at TEXT,
                run_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS failed_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                asin TEXT,
                timestamp TEXT,
                failure_type TEXT,
                failure_message TEXT,
                retry_count INTEGER DEFAULT 0,
                run_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scrape_runs (
                id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                max_products INTEGER,
                target_urls TEXT,
                products_scraped INTEGER DEFAULT 0,
                products_failed INTEGER DEFAULT 0,
                products_discovered INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT UNIQUE NOT NULL,
                category TEXT,
                attributes TEXT,
                extracted_at TEXT,
                run_id TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_products_run_id ON products(run_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_products_asin ON products(asin)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ai_attr_run_id ON ai_attributes(run_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ai_attr_asin ON ai_attributes(asin)")

        await db.commit()
        await db.execute("""
            UPDATE scrape_runs 
            SET status = 'stopped', completed_at = DATETIME('now') 
            WHERE status IN ('running', 'pending')
        """)
        await db.commit()

@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

def _clean_string(val: Any) -> Optional[str]:
    if val is None:
        return None
    cleaned = str(val).strip()
    return cleaned if cleaned else None

def _clean_float(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(val)
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None

def _clean_int(val: Any) -> Optional[int]:
    try:
        if val is None:
            return None
        i = int(val)
        return i if i >= 0 else None
    except (ValueError, TypeError):
        return None

def _clean_json(val: Any) -> Optional[str]:
    if not val:
        return None
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val)
    except (TypeError, ValueError):
        return None

async def insert_product(product_dict: Dict[str, Any], run_id: str):
    asin = _clean_string(product_dict.get('asin'))
    if not asin:
        return
    
    brand = _clean_string(product_dict.get('brand'))
    title = _clean_string(product_dict.get('title'))
    seller = _clean_string(product_dict.get('seller'))
    price = _clean_float(product_dict.get('price'))
    currency = _clean_string(product_dict.get('currency'))
    availability = _clean_string(product_dict.get('availability'))
    description = _clean_string(product_dict.get('description'))
    
    bullet_points = _clean_json(product_dict.get('bullet_points'))
    specifications = _clean_json(product_dict.get('specifications'))
    images = _clean_json(product_dict.get('images'))
    
    rating = _clean_float(product_dict.get('rating'))
    if rating is not None and (rating < 0 or rating > 5):
        rating = None
        
    review_count = _clean_int(product_dict.get('review_count'))
    product_url = _clean_string(product_dict.get('product_url'))
    scraped_at = _clean_string(product_dict.get('scraped_at'))

    async with get_db() as db:
        await db.execute("""
            INSERT OR REPLACE INTO products (
                asin, brand, title, seller, price, currency, availability, 
                description, bullet_points, specifications, images, 
                rating, review_count, product_url, scraped_at, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asin, brand, title, seller, price, currency, availability,
            description, bullet_points, specifications, images,
            rating, review_count, product_url, scraped_at, run_id
        ))
        await db.commit()

async def insert_failed(failed_dict: Dict[str, Any], run_id: str):
    url = _clean_string(failed_dict.get('url'))
    asin = _clean_string(failed_dict.get('asin'))
    timestamp = _clean_string(failed_dict.get('timestamp'))
    failure_type = _clean_string(failed_dict.get('failure_type'))
    failure_message = _clean_string(failed_dict.get('failure_message'))
    retry_count = _clean_int(failed_dict.get('retry_count')) or 0

    async with get_db() as db:
        await db.execute("""
            INSERT INTO failed_products (
                url, asin, timestamp, failure_type, failure_message, retry_count, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            url, asin, timestamp, failure_type, failure_message, retry_count, run_id
        ))
        await db.commit()

async def create_run(run_id: str, max_products: int, urls: List[str]):
    import datetime
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    urls_json = json.dumps(urls)
    
    async with get_db() as db:
        await db.execute("""
            INSERT INTO scrape_runs (
                id, status, max_products, target_urls, started_at
            ) VALUES (?, 'pending', ?, ?, ?)
        """, (run_id, max_products, urls_json, started_at))
        await db.commit()

async def update_run_status(run_id: str, status: str, **kwargs):
    updates = ["status = ?"]
    params = [status]
    for k, v in kwargs.items():
        updates.append(f"{k} = ?")
        params.append(v)
    params.append(run_id)
    
    query = f"UPDATE scrape_runs SET {', '.join(updates)} WHERE id = ?"
    async with get_db() as db:
        await db.execute(query, params)
        await db.commit()

async def update_run_progress(run_id: str, scraped: int, failed: int, discovered: int):
    async with get_db() as db:
        await db.execute("""
            UPDATE scrape_runs 
            SET products_scraped = ?, products_failed = ?, products_discovered = ?
            WHERE id = ?
        """, (scraped, failed, discovered, run_id))
        await db.commit()

async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d['target_urls'] = json.loads(d['target_urls']) if d.get('target_urls') else []
                return d
            return None

async def get_latest_run() -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d['target_urls'] = json.loads(d['target_urls']) if d.get('target_urls') else []
                return d
            return None

async def get_products(page: int, per_page: int, search: str, sort_by: str, sort_dir: str, run_id: Optional[str] = None):
    offset = (page - 1) * per_page
    query = "SELECT * FROM products"
    where_clauses = []
    params = []
    
    if run_id and run_id != "all":
        where_clauses.append("run_id = ?")
        params.append(run_id)

    if search:
        where_clauses.append("(title LIKE ? OR asin LIKE ? OR brand LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
        
    valid_sort_cols = ['price', 'rating', 'review_count', 'scraped_at', 'title', 'brand']
    if sort_by in valid_sort_cols:
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        query += f" ORDER BY {sort_by} {direction}"
    
    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    async with get_db() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_product_count(search: str = "", run_id: Optional[str] = None) -> int:
    query = "SELECT COUNT(*) as count FROM products"
    where_clauses = []
    params = []
    
    if run_id and run_id != "all":
        where_clauses.append("run_id = ?")
        params.append(run_id)

    if search:
        where_clauses.append("(title LIKE ? OR asin LIKE ? OR brand LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    async with get_db() as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

async def get_all_products_for_export(run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM products"
    params = []
    if run_id and run_id != "all":
        query += " WHERE run_id = ?"
        params.append(run_id)
    query += " ORDER BY scraped_at DESC"
    
    async with get_db() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def clear_all_data():
    async with get_db() as db:
        await db.execute("DELETE FROM products")
        await db.execute("DELETE FROM failed_products")
        await db.execute("DELETE FROM scrape_runs")
        await db.execute("DELETE FROM ai_attributes")
        await db.commit()

async def get_all_ai_attributes_for_export(run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query = """
        SELECT a.asin, a.category, a.attributes, a.extracted_at, a.run_id,
               p.title, p.brand, p.price, p.rating
        FROM ai_attributes a
        LEFT JOIN products p ON a.asin = p.asin
    """
    params = []
    if run_id and run_id != "all":
        query += " WHERE a.run_id = ? OR p.run_id = ?"
        params.extend([run_id, run_id])
    query += " ORDER BY a.extracted_at DESC"
    
    async with get_db() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_ai_attributes_count(run_id: Optional[str] = None) -> int:
    query = "SELECT COUNT(*) as count FROM ai_attributes"
    params = []
    if run_id and run_id != "all":
        query += " WHERE run_id = ?"
        params.append(run_id)
    async with get_db() as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0

async def get_products_by_run(run_id: str) -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM products WHERE run_id = ?", (run_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_metrics() -> Dict[str, Any]:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as total FROM products") as cursor:
            total_row = await cursor.fetchone()
            total_products = total_row['total'] if total_row else 0

        async with db.execute("SELECT COUNT(*) as total FROM failed_products") as cursor:
            failed_row = await cursor.fetchone()
            total_failed = failed_row['total'] if failed_row else 0

        async with db.execute("SELECT AVG(price) as avg_p, MIN(price) as min_p, MAX(price) as max_p FROM products WHERE price IS NOT NULL") as cursor:
            price_row = await cursor.fetchone()

        async with db.execute("SELECT AVG(rating) as avg_r FROM products WHERE rating IS NOT NULL") as cursor:
            rating_row = await cursor.fetchone()

        async with db.execute("SELECT COALESCE(SUM(review_count), 0) as total_reviews FROM products WHERE review_count IS NOT NULL") as cursor:
            reviews_row = await cursor.fetchone()

        async with db.execute("SELECT brand, COUNT(*) as count FROM products WHERE brand IS NOT NULL GROUP BY brand ORDER BY count DESC LIMIT 5") as cursor:
            brand_rows = await cursor.fetchall()
            top_brands = [{"brand": r["brand"], "count": r["count"]} for r in brand_rows]

        rating_distribution = []
        async with db.execute("""
            SELECT CAST(ROUND(rating) AS INTEGER) as rating, COUNT(*) as count
            FROM products WHERE rating IS NOT NULL
            GROUP BY CAST(ROUND(rating) AS INTEGER)
            ORDER BY rating
        """) as cursor:
            rows = await cursor.fetchall()
            rating_distribution = [{"rating": r["rating"], "count": r["count"]} for r in rows]

        price_ranges = []
        ranges_sql = """
            SELECT
                CASE
                    WHEN price < 25 THEN '$0-25'
                    WHEN price < 50 THEN '$25-50'
                    WHEN price < 100 THEN '$50-100'
                    WHEN price < 200 THEN '$100-200'
                    WHEN price < 500 THEN '$200-500'
                    ELSE '$500+'
                END as range_label,
                COUNT(*) as count
            FROM products WHERE price IS NOT NULL
            GROUP BY range_label
            ORDER BY MIN(price)
        """
        async with db.execute(ranges_sql) as cursor:
            rows = await cursor.fetchall()
            price_ranges = [{"range": r["range_label"], "count": r["count"]} for r in rows]

        total_attempted = total_products + total_failed
        success_rate = round((total_products / total_attempted) * 100, 1) if total_attempted > 0 else 0

        return {
            "total_products": total_products,
            "avg_price": round(price_row["avg_p"], 2) if price_row and price_row["avg_p"] is not None else None,
            "min_price": round(price_row["min_p"], 2) if price_row and price_row["min_p"] is not None else None,
            "max_price": round(price_row["max_p"], 2) if price_row and price_row["max_p"] is not None else None,
            "avg_rating": round(rating_row["avg_r"], 1) if rating_row and rating_row["avg_r"] is not None else None,
            "total_reviews": reviews_row["total_reviews"] if reviews_row else 0,
            "success_rate": success_rate,
            "top_brands": top_brands,
            "rating_distribution": rating_distribution,
            "price_ranges": price_ranges,
        }

async def get_processed_asins() -> Set[str]:
    async with get_db() as db:
        async with db.execute("SELECT asin FROM products") as cursor:
            rows = await cursor.fetchall()
            return {r['asin'] for r in rows}
