# Production Amazon Scrapy spider with Playwright anti-detection and pagination.

import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import scrapy
import yaml
from scrapy.exceptions import CloseSpider
from scrapy_playwright.page import PageMethod

from amazon_scraper.items import SearchResultItem, ProductDetailItem, FailedItem
from amazon_scraper.proxy_manager import ProxyManager
from amazon_scraper.utils.page_detector import detect_page_issue
from amazon_scraper.utils.extractors import (
    extract_price, extract_rating, extract_review_count,
    extract_bullet_points, extract_specifications, extract_images_from_html,
    extract_brand, extract_seller, extract_description, extract_asin_from_url,
)

logger = logging.getLogger(__name__)

INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: () => ({}) };
    Object.defineProperty(screen, 'availWidth',   { get: () => 1920 });
"""

CHECKPOINT_FILE = Path(__file__).parent.parent / "storage" / "processed_asins.json"
CONFIG_FILE = Path(__file__).parent.parent.parent / "config.yaml"


def _ms(lo: float, hi: float) -> int:
    return int(random.uniform(lo, hi) * 1000)


def _load_config() -> dict:
    defaults = {
        "search_urls": ["https://www.amazon.com/s?k=gaming+headset"],
        "max_pages": 1,
        "max_products": 10,
        "concurrency": 1,
        "download_delay": 3.0,
        "timeout_seconds": 90,
        "retry_count": 2,
        "output_dir": "output",
        "proxies": [],
        "proxy_max_consecutive_failures": 3,
        "proxy_cooldown_seconds": 300,
        "ai_extraction": {"enabled": False},
    }
    try:
        with open(CONFIG_FILE, "r") as f:
            loaded = yaml.safe_load(f)
            if loaded:
                defaults.update(loaded)
    except FileNotFoundError:
        logger.warning("config.yaml not found — using defaults")
    except Exception as e:
        logger.warning("Could not parse config.yaml: %s — using defaults", e)
    return defaults


def _load_checkpoint() -> set:
    asins = set()
    try:
        db_path = Path(__file__).resolve().parent.parent / "storage" / "scraper.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT asin FROM products WHERE asin IS NOT NULL")
            rows = cursor.fetchall()
            asins.update(r[0] for r in rows if r[0])
            conn.close()
    except Exception as e:
        logger.warning("Could not load checkpoint from SQLite DB: %s", e)

    return asins

def should_abort_req(request):
    ignored_types = ["image", "stylesheet", "font", "media", "beacon"]
    if request.resource_type in ignored_types:
        return True
    
    ignored_patterns = ["/g/", "/rb/", "doubleclick", "amazon-adsystem", "analytics"]
    if any(pattern in request.url for pattern in ignored_patterns):
        return True
        
    return False

class ProductionSpider(scrapy.Spider):
    name = "production_spider"
    allowed_domains = ["amazon.com"]
    custom_settings = {
        'PLAYWRIGHT_ABORT_REQUEST': should_abort_req
    }

    async def start(self):
        config = _load_config()
        self.config = config

        self.output_dir = config["output_dir"]
        self.search_urls = config["search_urls"]
        self.max_pages = config["max_pages"]
        self.max_products = config["max_products"]

        self._processed_asins: set = _load_checkpoint()
        prod_len = len(self._processed_asins)
        logger.info("[INFO] Run started — %d ASINs already in checkpoint",
                    prod_len)
        if(prod_len>=self.max_products):
            logger.info("[INFO] Max products reached")
            raise CloseSpider(f"Target max_products limit ({self.max_products}) reached")

        self._products_scraped = prod_len
        proxies = config.get("proxies", [])
        if proxies:
            self.proxy_manager = ProxyManager(
                proxy_urls=proxies,
                max_consecutive_failures=config.get("proxy_max_consecutive_failures", 3),
                cooldown_seconds=config.get("proxy_cooldown_seconds", 300),
            )
            logger.info("[INFO] Proxy pool initialized with %d proxies", len(proxies))
        else:
            self.proxy_manager = None
            logger.info("[INFO] No proxies configured — scraping directly")

        logger.info("[INFO] Navigating to Amazon homepage for warmup...")
        yield scrapy.Request(
            "https://www.amazon.com/",
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    PageMethod("add_init_script", INIT_SCRIPT),
                    PageMethod("wait_for_timeout", _ms(2.0, 4.0)),
                    PageMethod("evaluate", "window.scrollBy(0, 300)"),
                    PageMethod("wait_for_timeout", _ms(0.8, 1.5)),
                ],
                "playwright_include_page": True,
            },
            callback=self.after_homepage,
            errback=self.handle_error,
            dont_filter=True,
        )

    async def after_homepage(self, response):
        page = response.meta["playwright_page"]
        first_search_url = self.search_urls[0]

        logger.info("[INFO] Homepage loaded (%s). Navigating to first search...",
                    response.status)

        try:
            await page.goto(first_search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(_ms(1.5, 3.0))

            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(_ms(1.0, 2.0))
            await page.evaluate("window.scrollBy(0, 700)")
            await page.wait_for_timeout(_ms(0.8, 1.5))

            title = await page.title()
            logger.info("[INFO] Search page title: %s", title)

            content = await page.content()

        finally:
            await page.close()

        search_response = response.replace(body=content.encode(), url=first_search_url)
        search_response.meta["page_number"] = 1
        search_response.meta["source_search_url"] = first_search_url

        async for result in self.parse_search(search_response):
            yield result

        for url in self.search_urls[1:]:
            yield self._make_search_request(url, page_number=1)

    async def parse_search(self, response):
        source_url = response.meta.get("source_search_url", response.url)
        page_num = response.meta.get("page_number", 1)

        logger.info("[INFO] Search page %d — URL: %s", page_num, response.url)

        issue_type, issue_msg = detect_page_issue(response.text, response.url)
        if issue_type:
            logger.warning("[WARN] Access-restricted page detected: %s", issue_msg)
            return

        cards = response.css("div[data-component-type='s-search-result']")
        logger.info("[INFO] Products discovered: %d (page %d)", len(cards), page_num)

        for card in cards:
            if self._products_scraped >= self.max_products:
                logger.info("[INFO] Reached max_products limit (%d) — stopping",
                            self.max_products)
                return

            asin = card.attrib.get("data-asin", "").strip()
            if not asin:
                continue

            title = card.css("h2 span::text").get()
            product_url = card.css("h2 a::attr(href)").get()
            if product_url:
                product_url = response.urljoin(product_url)
            price_raw = card.css(".a-price .a-offscreen::text").get()
            rating_raw = card.css(".a-icon-star-small .a-icon-alt::text").get()
            review_raw = card.css("span.a-size-base.s-underline-text::text").get()
            image_url = card.css("img.s-image::attr(src)").get()

            yield SearchResultItem(
                asin=asin,
                title=title.strip() if title else None,
                product_url=product_url or f"https://www.amazon.com/dp/{asin}",
                price=price_raw.strip() if price_raw else None,
                rating=rating_raw.strip() if rating_raw else None,
                review_count=review_raw.strip() if review_raw else None,
                image_url=image_url,
                source_search_url=source_url,
                page_number=page_num,
            )

            if asin in self._processed_asins:
                logger.debug("[Dedup] Skipping already-processed ASIN: %s", asin)
                continue

            self._processed_asins.add(asin)

            prod_url = product_url or f"https://www.amazon.com/dp/{asin}"
            yield self._make_product_request(prod_url, asin)

        if page_num < self.max_pages and self._products_scraped < self.max_products:
            next_href = response.css(
                "a.s-pagination-next::attr(href), "
                ".s-pagination-item.s-pagination-next::attr(href)"
            ).get()
            if next_href:
                next_url = response.urljoin(next_href)
                logger.info("[INFO] Search page %d/%d — following to next page",
                            page_num, self.max_pages)
                yield self._make_search_request(
                    next_url,
                    page_number=page_num + 1,
                    source_search_url=source_url,
                )

    async def parse_product(self, response):
        asin = response.meta.get("asin")
        page = response.meta.get("playwright_page")
        start_time = time.monotonic()

        if self._products_scraped >= self.max_products:
            if page and not page.is_closed():
                await page.close()
            raise CloseSpider(f"Target max_products limit ({self.max_products}) reached")

        try:
            issue_type, issue_msg = detect_page_issue(response.text, response.url)
            if issue_type:
                logger.warning("[WARN] %s on product %s: %s", issue_type, asin, issue_msg)
                yield FailedItem(
                    url=response.url,
                    asin=asin,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    failure_type=issue_type,
                    failure_message=issue_msg,
                    retry_count=response.meta.get("retry_count", 0),
                )
                return

            images = []
            if page and not page.is_closed():
                try:
                    images = await page.evaluate("""
                        () => {
                            const mainImg = document.querySelector('#landingImage');
                            if (mainImg) {
                                const raw = mainImg.getAttribute('data-a-dynamic-image');
                                if (raw) return Object.keys(JSON.parse(raw));
                            }
                            const og = document.querySelector('meta[property="og:image"]');
                            return og ? [og.getAttribute('content')] : [];
                        }
                    """)
                except Exception as e:
                    logger.debug("Image JS extraction failed for %s: %s", asin, e)

            if not images:
                images = extract_images_from_html(response)

            price, currency = extract_price(response)

            item = ProductDetailItem(
                asin=asin,
                brand=extract_brand(response),
                title=(response.css("#productTitle::text").get() or "").strip() or None,
                seller=extract_seller(response),
                price=price,
                currency=currency,
                availability=(
                    response.css("#availability span::text").get() or ""
                ).strip() or None,
                description=extract_description(response),
                bullet_points=extract_bullet_points(response),
                specifications=extract_specifications(response),
                images=images,
                rating=extract_rating(response),
                review_count=extract_review_count(response),
                product_url=response.url,
                scraped_at=datetime.now(timezone.utc).isoformat(),
            )

            item._processing_time = time.monotonic() - start_time

            self._products_scraped += 1
            logger.info("[INFO] Product scraped (%d/%d): %s — %s",
                        self._products_scraped, self.max_products, asin, (item.title or "")[:60])
            yield item

            if self._products_scraped >= self.max_products:
                logger.info("[INFO] Target max_products limit (%d) reached — closing spider!",
                            self.max_products)
                raise CloseSpider(f"Reached target max_products limit ({self.max_products})")

        except CloseSpider:
            raise
        except Exception as e:
            logger.error("[ERROR] Unexpected error parsing %s: %s", asin, e, exc_info=True)
            yield FailedItem(
                url=response.url,
                asin=asin,
                timestamp=datetime.now(timezone.utc).isoformat(),
                failure_type="parse_error",
                failure_message=str(e),
                retry_count=response.meta.get("retry_count", 0),
            )

        finally:
            if page and not page.is_closed():
                await page.close()

    async def handle_error(self, failure):
        request = failure.request
        asin = request.meta.get("asin")
        url = request.url
        retry_count = request.meta.get("retry_times", 0)

        error_type = type(failure.value).__name__
        error_msg = str(failure.value)

        logger.warning("[WARN] Request failed (%s): %s — %s",
                       error_type, url, error_msg[:120])

        page = request.meta.get("playwright_page")
        if page and not page.is_closed():
            try:
                await page.close()
                logger.info("[INFO] Browser restarted (page closed after crash)")
            except Exception:
                pass

        if asin:
            yield FailedItem(
                url=url,
                asin=asin,
                timestamp=datetime.now(timezone.utc).isoformat(),
                failure_type=error_type,
                failure_message=error_msg,
                retry_count=retry_count,
            )

    def _make_search_request(self, url: str, page_number: int = 1,
                             source_search_url: str = None) -> scrapy.Request:
        return scrapy.Request(
            url,
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    PageMethod("add_init_script", INIT_SCRIPT),
                    PageMethod("wait_for_selector",
                               "div[data-component-type='s-search-result']",
                               timeout=15000, state="attached"),
                    PageMethod("wait_for_timeout", _ms(1.0, 2.5)),
                    PageMethod("evaluate", "window.scrollBy(0, 600)"),
                    PageMethod("wait_for_timeout", _ms(0.8, 1.5)),
                ],
                "page_number": page_number,
                "source_search_url": source_search_url or url,
            },
            callback=self.parse_search,
            errback=self.handle_error,
        )

    def _make_product_request(self, url: str, asin: str) -> scrapy.Request:
        return scrapy.Request(
            url,
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    PageMethod("add_init_script", INIT_SCRIPT),
                    PageMethod("wait_for_selector",
                               "#productTitle",
                               timeout=20000, state="visible"),
                    PageMethod("wait_for_timeout", _ms(1.0, 2.0)),
                    PageMethod("evaluate", "window.scrollBy(0, 600)"),
                    PageMethod("wait_for_timeout", _ms(0.5, 1.2)),
                ],
                "playwright_include_page": True,
                "asin": asin,
            },
            callback=self.parse_product,
            errback=self.handle_error,
        )
