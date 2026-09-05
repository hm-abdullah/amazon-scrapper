# items.py — Scrapy item definitions for the production scraper.
#
# Uses Python dataclasses (fully supported by Scrapy's ItemAdapter
# since Scrapy 2.2). Each field defaults to None / empty so missing
# data never causes a KeyError.

from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ── Search result ─────────────────────────────────────────────────────────────
# Populated when parsing a search results page (s?k=...).
# One item per product card found on the page.
@dataclass
class SearchResultItem:
    asin: Optional[str] = None          # Amazon Standard Identification Number
    title: Optional[str] = None         # Product title from card
    product_url: Optional[str] = None   # Full URL to product page
    price: Optional[str] = None         # Raw price string e.g. "$29.99"
    currency: Optional[str] = None      # Extracted currency symbol e.g. "$"
    rating: Optional[str] = None        # e.g. "4.5 out of 5 stars"
    review_count: Optional[str] = None  # e.g. "1,234"
    availability: Optional[str] = None  # e.g. "In Stock"
    image_url: Optional[str] = None     # Thumbnail URL from card
    source_search_url: Optional[str] = None  # The search URL that produced this
    page_number: int = 1                # Which pagination page this came from


# ── Full product detail ────────────────────────────────────────────────────────
# Populated when visiting an individual product page (amazon.com/dp/...).
# This is the primary output item written to products.jsonl / products.csv.
@dataclass
class ProductDetailItem:
    asin: Optional[str] = None
    brand: Optional[str] = None
    title: Optional[str] = None
    seller: Optional[str] = None
    price: Optional[float] = None         # Normalized to float (e.g. 29.99)
    currency: Optional[str] = None        # e.g. "USD"
    availability: Optional[str] = None
    description: Optional[str] = None     # Plain-text product description
    bullet_points: List[str] = field(default_factory=list)       # Feature bullets
    specifications: Dict[str, str] = field(default_factory=dict) # Tech spec table
    images: List[str] = field(default_factory=list)              # Image URLs
    rating: Optional[float] = None        # Normalized to float (e.g. 4.5)
    review_count: Optional[int] = None    # Normalized to int (e.g. 1234)
    product_url: Optional[str] = None
    scraped_at: Optional[str] = None      # ISO-8601 timestamp


# ── Failed product record ─────────────────────────────────────────────────────
# Written to failed_products.jsonl whenever a product cannot be scraped.
# Preserves enough context to investigate and re-run failures manually.
@dataclass
class FailedItem:
    url: Optional[str] = None
    asin: Optional[str] = None
    timestamp: Optional[str] = None       # ISO-8601 timestamp
    failure_type: Optional[str] = None    # e.g. "captcha", "timeout", "parse_error"
    failure_message: Optional[str] = None # Human-readable error description
    retry_count: int = 0                  # How many times this URL was retried
