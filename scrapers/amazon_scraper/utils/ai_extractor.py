# Post-crawl AI product attribute extraction using Gemini or OpenAI.

import json
import logging
import os
import sqlite3
import site
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.append(user_site)

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {"asin", "category", "attributes"}

PROMPT_TEMPLATE = """You are a product data analyst. Extract structured attributes from this Amazon product listing.

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "asin": "{asin}",
  "category": "<short_snake_case_category>",
  "attributes": {{
    "<key>": <value>
  }}
}}

Rules:
- category: short snake_case string describing the product type (e.g. wireless_headset, gaming_mouse, mechanical_keyboard)
- attributes: only include factual, clearly stated attributes from the listing
- Use boolean for yes/no attributes (wireless, noise_cancellation, backlit, etc.)
- Use numbers for measurable attributes (battery_hours, weight_grams, dpi, etc.)
- Use strings for everything else (color, connectivity, interface, etc.)
- Omit attributes that are not mentioned in the listing

Product Title: {title}
Brand: {brand}
Bullet Points:
{bullets}
Description:
{description}
"""

def load_env_vars():
    possible_paths = [
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in possible_paths:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ[k.strip()] = v.strip().strip("'\"")
            except Exception as e:
                logger.warning("[AI] Could not load env file %s: %s", env_path, e)

def get_db_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "storage" / "scraper.db"

def init_ai_table(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT UNIQUE NOT NULL,
            category TEXT,
            attributes TEXT,
            extracted_at TEXT,
            run_id TEXT
        )
    """)
    conn.commit()

def run_ai_extraction(config: dict, run_id: Optional[str] = None) -> None:
    load_env_vars()
    db_path = get_db_path()
    if not db_path.exists():
        logger.error("[AI] Database not found at %s", db_path)
        print(f"[AI_ERROR] Database not found at {db_path}", flush=True)
        sys.exit(1)

    ai_cfg = config.get("ai_extraction", {})
    provider = ai_cfg.get("provider", "gemini")
    
    api_key = ai_cfg.get("api_key") or ""
    if not api_key or api_key.startswith("${"):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""

    model_name = ai_cfg.get("model", "gemini-1.5-flash")
    max_products = ai_cfg.get("max_products", 50)

    if not api_key:
        error_msg = "No API key configured. Please set GEMINI_API_KEY in scrapers/.env or ai_extraction.api_key in config.yaml."
        logger.error("[AI] %s", error_msg)
        print(f"[AI_ERROR] {error_msg}", flush=True)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_ai_table(conn)

    cursor = conn.cursor()
    
    query = """
        SELECT p.* FROM products p
        LEFT JOIN ai_attributes a ON p.asin = a.asin
        WHERE a.asin IS NULL
    """
    params = []
    if run_id and run_id != "all":
        query += " AND p.run_id = ?"
        params.append(run_id)

    query += " ORDER BY p.scraped_at DESC"
    if max_products and max_products > 0:
        query += " LIMIT ?"
        params.append(max_products)

    cursor.execute(query, params)
    products = [dict(r) for r in cursor.fetchall()]

    if not products:
        print("[AI_COMPLETED] 0/0 (No unextracted products found)", flush=True)
        conn.close()
        return

    total = len(products)
    logger.info("[AI] Starting AI extraction for %d products (provider: %s)", total, provider)
    print(f"[AI_STARTED] total={total}", flush=True)

    client = None
    if provider == "gemini":
        client = _build_gemini_client(api_key, model_name)
    elif provider == "openai":
        client = _build_openai_client(api_key, model_name)
    else:
        logger.error("[AI] Unknown provider '%s'", provider)
        print(f"[AI_ERROR] Unknown provider '{provider}'", flush=True)
        conn.close()
        sys.exit(1)

    if client is None:
        print("[AI_ERROR] Failed to initialize LLM client", flush=True)
        conn.close()
        sys.exit(1)

    success = 0
    failed = 0

    for i, product in enumerate(products, start=1):
        asin = product.get("asin", "UNKNOWN")
        title = product.get("title", "")
        brand = product.get("brand", "")
        bullets_raw = product.get("bullet_points") or "[]"
        try:
            bullets_list = json.loads(bullets_raw) if isinstance(bullets_raw, str) else bullets_raw
        except Exception:
            bullets_list = []

        description = product.get("description", "")
        target_run_id = product.get("run_id") or run_id or ""

        print(f"[AI_PROGRESS] {i}/{total} ASIN:{asin} TITLE:{title[:30]}", flush=True)

        result = _extract_attributes(client, provider, {
            "asin": asin,
            "title": title,
            "brand": brand,
            "bullet_points": bullets_list,
            "description": description
        })

        if result is not None:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO ai_attributes (asin, category, attributes, extracted_at, run_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                asin,
                result.get("category", "general"),
                json.dumps(result.get("attributes", {})),
                now_iso,
                target_run_id
            ))
            conn.commit()
            success += 1
            logger.info("[AI] (%d/%d) Extracted ASIN: %s category: %s", i, total, asin, result.get("category"))
        else:
            failed += 1
            logger.warning("[AI] (%d/%d) Failed ASIN: %s", i, total, asin)

        time.sleep(0.5)

    conn.close()
    print(f"[AI_COMPLETED] success={success} failed={failed} total={total}", flush=True)

def _extract_attributes(client, provider: str, product: dict) -> Optional[dict]:
    asin = product.get("asin", "UNKNOWN")
    prompt = PROMPT_TEMPLATE.format(
        asin=asin,
        title=product.get("title", ""),
        brand=product.get("brand", "Unknown"),
        bullets="\n".join(f"- {b}" for b in product.get("bullet_points", [])),
        description=(product.get("description") or "")[:800],
    )

    for attempt in range(3):
        try:
            raw_text = _call_llm(client, provider, prompt)
            result = _parse_and_validate(raw_text, asin)
            if result:
                return result
        except Exception as e:
            wait = 1.5 ** attempt
            logger.warning("[AI] LLM call failed (attempt %d/3): %s — retrying in %.1fs", attempt + 1, e, wait)
            time.sleep(wait)

    return None

def _call_llm(client, provider: str, prompt: str) -> str:
    if provider == "gemini":
        response = client.generate_content(prompt)
        return response.text
    elif provider == "openai":
        response = client.chat.completions.create(
            model=client._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    raise ValueError(f"Unknown provider: {provider}")

def _parse_and_validate(raw_text: str, asin: str) -> Optional[dict]:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[AI] Invalid JSON from LLM for %s: %s", asin, e)
        return None

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        logger.warning("[AI] LLM response missing keys %s for %s", missing, asin)
        return None

    if not isinstance(data.get("attributes"), dict):
        logger.warning("[AI] 'attributes' is not a dict for %s", asin)
        return None

    return data

def _build_gemini_client(api_key: str, model_name: str):
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_name)
    except ImportError:
        logger.error("[AI] google-generativeai package not installed.")
        return None

def _build_openai_client(api_key: str, model_name: str):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        client._model = model_name
        return client
    except ImportError:
        logger.error("[AI] openai package not installed.")
        return None
