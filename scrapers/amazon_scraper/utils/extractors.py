# utils/extractors.py — CSS/regex helpers for product page fields.
#
# All functions accept a Scrapy Response object (or Selector) and return
# cleaned Python values. Every function handles missing elements gracefully —
# it always returns None / [] / {} rather than raising an exception.

import re
from typing import Optional, List, Dict, Tuple


# ── Price ─────────────────────────────────────────────────────────────────────

def extract_price(response) -> Tuple[Optional[float], Optional[str]]:
    """
    Returns (amount_as_float, currency_symbol).
    Tries several CSS selectors in order of reliability.
    """
    # Selectors to try, from most to least specific
    selectors = [
        "span.a-price.a-text-price.a-size-medium span.a-offscreen::text",
        "#corePrice_feature_div span.a-offscreen::text",
        "#priceblock_ourprice::text",
        "#priceblock_dealprice::text",
        "span.a-price .a-offscreen::text",
        ".a-price .a-offscreen::text",
    ]

    raw = None
    for sel in selectors:
        raw = response.css(sel).get()
        if raw:
            raw = raw.strip()
            break

    if not raw:
        return None, None

    # Extract currency symbol (first non-digit, non-dot, non-comma char)
    currency_match = re.match(r"([^\d,\.]+)", raw)
    currency = currency_match.group(1).strip() if currency_match else None

    # Extract numeric amount
    amount_str = re.sub(r"[^\d.]", "", raw)
    try:
        amount = float(amount_str) if amount_str else None
    except ValueError:
        amount = None

    # Map common symbols to ISO currency codes
    symbol_map = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR"}
    if currency in symbol_map:
        currency = symbol_map[currency]

    return amount, currency


# ── Rating ────────────────────────────────────────────────────────────────────

def extract_rating(response) -> Optional[float]:
    """
    Returns rating as a float e.g. 4.5.
    Parses strings like '4.5 out of 5 stars'.
    """
    raw = (
        response.css("#acrPopover span.a-icon-alt::text").get()
        or response.css("span.a-icon-alt::text").get()
    )
    if not raw:
        return None

    match = re.search(r"([\d.]+)\s+out of", raw)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


# ── Review count ──────────────────────────────────────────────────────────────

def extract_review_count(response) -> Optional[int]:
    """
    Returns total review count as an integer e.g. 12345.
    Strips commas from strings like '12,345 ratings'.
    """
    raw = (
        response.css("#acrCustomerReviewText::text").get()
        or response.css("span#acrCustomerReviewText::text").get()
    )
    if not raw:
        return None

    # Remove commas and extract digits
    digits = re.sub(r"[^\d]", "", raw)
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


# ── Bullet points ─────────────────────────────────────────────────────────────

def extract_bullet_points(response) -> List[str]:
    """
    Returns the 'About this item' feature bullet points as a list of strings.
    Filters out empty strings and overly short entries.
    """
    bullets = response.css(
        "#feature-bullets li span.a-list-item::text"
    ).getall()

    cleaned = []
    for b in bullets:
        b = b.strip()
        if b and len(b) > 5:   # Skip short/empty bullets
            cleaned.append(b)
    return cleaned


# ── Specifications table ──────────────────────────────────────────────────────

def extract_specifications(response) -> Dict[str, str]:
    """
    Returns the product specifications table as {label: value}.
    Covers both the tech spec table and the product detail table.
    """
    specs = {}

    # Technical specs table (e.g. electronics)
    for row in response.css("#productDetails_techSpec_section_1 tr"):
        key = row.css("th::text").get("").strip()
        val = row.css("td::text").get("").strip()
        if key and val:
            specs[key] = val

    # Additional details table
    for row in response.css("#productDetails_detailBullets_sections1 tr"):
        key = row.css("th::text").get("").strip()
        val = row.css("td span::text").get("").strip()
        if key and val:
            specs[key] = val

    # Fallback: detail bullets list (appears on some product types)
    for item in response.css("#detailBullets_feature_div li"):
        parts = item.css("span::text").getall()
        parts = [p.strip().strip(":") for p in parts if p.strip()]
        if len(parts) >= 2:
            specs[parts[0]] = parts[1]

    return specs


# ── Images ────────────────────────────────────────────────────────────────────

def extract_images_from_html(response) -> List[str]:
    """
    Extracts product image URLs from the HTML.
    Amazon embeds high-res URLs in 'data-a-dynamic-image' attributes.
    Falls back to the main landing image src.
    """
    images = []

    # Primary method: data-a-dynamic-image contains JSON of {url: [w,h]}
    raw = response.css("#landingImage::attr(data-a-dynamic-image)").get()
    if raw:
        try:
            import json
            url_map = json.loads(raw)
            images = list(url_map.keys())
        except Exception:
            pass

    # Fallback: grab the src of the main image
    if not images:
        src = response.css("#landingImage::attr(src)").get()
        if src:
            images = [src]

    # Also grab thumbnails from the image strip
    thumbnails = response.css("li.imageThumbnail img::attr(src)").getall()
    for t in thumbnails:
        # Convert thumbnail URL to full-size by removing size suffix
        full = re.sub(r"\._[A-Z]{2}\d+_\.", ".", t)
        if full not in images:
            images.append(full)

    return images


# ── Brand ─────────────────────────────────────────────────────────────────────

def extract_brand(response) -> Optional[str]:
    """Extracts the brand/manufacturer from the byline or spec table."""
    brand = response.css("#bylineInfo span.a-color-secondary::text").get()
    if not brand:
        brand = response.css("#bylineInfo::text").get()
    if not brand:
        # Try the spec table
        for row in response.css("#productDetails_techSpec_section_1 tr"):
            key = row.css("th::text").get("").strip()
            if "brand" in key.lower() or "manufacturer" in key.lower():
                brand = row.css("td::text").get("").strip()
                break
    return brand.strip() if brand else None


# ── Seller ────────────────────────────────────────────────────────────────────

def extract_seller(response) -> Optional[str]:
    """Returns the name of the seller (Sold by...)."""
    seller = (
        response.css("#sellerProfileTriggerId::text").get()
        or response.css("#merchantInfoFeature_feature_div span.a-color-base::text").get()
        or response.css(".tabular-buybox-text span.a-color-base::text").get()
    )
    return seller.strip() if seller else None


# ── Description ───────────────────────────────────────────────────────────────

def extract_description(response) -> Optional[str]:
    """Returns the product description as a single string."""
    parts = response.css("#productDescription p::text, #productDescription span::text").getall()
    text = " ".join(p.strip() for p in parts if p.strip())
    return text if text else None


# ── ASIN from URL ─────────────────────────────────────────────────────────────

def extract_asin_from_url(url: str) -> Optional[str]:
    """
    Parses the ASIN from a product URL.
    Handles formats like:
      /dp/B0XXXXXXXX/
      /gp/product/B0XXXXXXXX
    """
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return match.group(1) if match else None
