# utils/ai_extractor.py — Post-crawl AI enrichment using Google Gemini.
#
# This is a STANDALONE script — not part of the Scrapy pipeline.
# Run it via:  python run.py --ai-only
# Or called automatically at the end of a full run if ai_extraction.enabled=true.
#
# It reads output/products.jsonl, sends each product to Gemini, and saves
# structured attributes to output/ai_attributes.jsonl.

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Expected JSON structure that Gemini must return.
# We validate this before saving.
REQUIRED_KEYS = {"asin", "category", "attributes"}

# Prompt template — keep it tight to reduce token usage.
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


def run_ai_extraction(config: dict, output_dir: Path) -> None:
    """
    Main entry point. Reads products.jsonl and writes ai_attributes.jsonl.

    Args:
        config: The loaded config.yaml dict.
        output_dir: Path to the output directory.
    """
    products_file = output_dir / "products.jsonl"
    output_file = output_dir / "ai_attributes.jsonl"

    if not products_file.exists():
        logger.error("[AI] products.jsonl not found at %s", products_file)
        return

    ai_cfg = config.get("ai_extraction", {})
    provider = ai_cfg.get("provider", "gemini")
    api_key = ai_cfg.get("api_key", "")
    model_name = ai_cfg.get("model", "gemini-3.5-flash-lite")
    max_products = ai_cfg.get("max_products", 200)

    if not api_key:
        logger.error("[AI] No API key configured in config.yaml under ai_extraction.api_key")
        return

    # Load products
    products = _load_jsonl(products_file)
    if max_products:
        products = products[:max_products]

    # Load already-processed ASINs so we can resume
    already_done = _load_done_asins(output_file)

    logger.info("[AI] Starting AI extraction for %d products (provider: %s)", len(products), provider)

    # Set up the LLM client
    if provider == "gemini":
        client = _build_gemini_client(api_key, model_name)
    elif provider == "openai":
        client = _build_openai_client(api_key, model_name)
    else:
        logger.error("[AI] Unknown provider '%s'. Use 'gemini' or 'openai'.", provider)
        return

    if client is None:
        return  # Error already logged inside builder

    success = 0
    failed = 0

    with open(output_file, "a", encoding="utf-8") as out_f:
        for product in products:
            asin = product.get("asin")
            if not asin:
                continue
            if asin in already_done:
                logger.debug("[AI] Skipping already-processed ASIN: %s", asin)
                continue

            result = _extract_attributes(client, provider, product)

            if result is not None:
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                success += 1
                logger.info("[AI] Extracted attributes for ASIN: %s  category=%s",
                            asin, result.get("category", "?"))
            else:
                failed += 1
                logger.warning("[AI] Failed to extract attributes for ASIN: %s", asin)

            # Polite delay between API calls to avoid rate limits
            time.sleep(1.0)

    logger.info("[AI] Done — %d succeeded, %d failed. Output: %s", success, failed, output_file)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_attributes(client, provider: str, product: dict) -> Optional[dict]:
    """Calls the LLM and returns a validated dict, or None on failure."""
    asin = product.get("asin", "UNKNOWN")
    prompt = PROMPT_TEMPLATE.format(
        asin=asin,
        title=product.get("title", ""),
        brand=product.get("brand", "Unknown"),
        bullets="\n".join(f"- {b}" for b in product.get("bullet_points", [])),
        description=(product.get("description") or "")[:800],   # Cap length
    )

    # Try up to 3 times with exponential backoff
    for attempt in range(3):
        try:
            raw_text = _call_llm(client, provider, prompt)
            result = _parse_and_validate(raw_text, asin)
            if result:
                return result
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("[AI] LLM call failed (attempt %d/3): %s — retrying in %ds", attempt + 1, e, wait)
            time.sleep(wait)

    return None


def _call_llm(client, provider: str, prompt: str) -> str:
    """Calls the configured LLM and returns the raw text response."""
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
    """
    Strips markdown fences if present, parses JSON, validates structure.
    Returns the dict if valid, None otherwise.
    """
    # Strip ```json ... ``` markdown fences if the model added them
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[AI] Invalid JSON from LLM for %s: %s", asin, e)
        return None

    # Validate required keys exist
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        logger.warning("[AI] LLM response missing keys %s for %s", missing, asin)
        return None

    if not isinstance(data.get("attributes"), dict):
        logger.warning("[AI] 'attributes' is not a dict for %s", asin)
        return None

    return data


def _build_gemini_client(api_key: str, model_name: str):
    """Creates and returns a Gemini GenerativeModel client."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_name)
    except ImportError:
        logger.error("[AI] google-generativeai package not installed. Run: pip install google-generativeai")
        return None


def _build_openai_client(api_key: str, model_name: str):
    """Creates and returns an OpenAI client (with model name stored on it)."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        client._model = model_name   # Store model on the client for _call_llm
        return client
    except ImportError:
        logger.error("[AI] openai package not installed. Run: pip install openai")
        return None


def _load_jsonl(path: Path) -> list:
    """Reads a .jsonl file and returns a list of dicts."""
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        logger.error("[AI] Could not read %s: %s", path, e)
    return items


def _load_done_asins(output_file: Path) -> set:
    """Reads existing ai_attributes.jsonl to get already-processed ASINs."""
    done = set()
    if output_file.exists():
        for item in _load_jsonl(output_file):
            asin = item.get("asin")
            if asin:
                done.add(asin)
    return done
