# Scrapy dataclass item definitions for search, product detail, and failed products.

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class SearchResultItem:
    asin: Optional[str] = None
    title: Optional[str] = None
    product_url: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    availability: Optional[str] = None
    image_url: Optional[str] = None
    source_search_url: Optional[str] = None
    page_number: int = 1


@dataclass
class ProductDetailItem:
    asin: Optional[str] = None
    brand: Optional[str] = None
    title: Optional[str] = None
    seller: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    availability: Optional[str] = None
    description: Optional[str] = None
    bullet_points: List[str] = field(default_factory=list)
    specifications: Dict[str, str] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    product_url: Optional[str] = None
    scraped_at: Optional[str] = None


@dataclass
class FailedItem:
    url: Optional[str] = None
    asin: Optional[str] = None
    timestamp: Optional[str] = None
    failure_type: Optional[str] = None
    failure_message: Optional[str] = None
    retry_count: int = 0
