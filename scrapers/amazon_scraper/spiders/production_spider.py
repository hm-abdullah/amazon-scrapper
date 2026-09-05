# spiders/production_spider.py — Production Amazon scraper.
#
# Handles the full scraping lifecycle:
#   1. Homepage warmup   → establishes cookies, solves WAF challenge
#   2. Search pages      → discovers product ASINs, handles pagination
#   3. Product pages     → extracts full product details
#
# Design principles:
#   - One spider does both search AND product scraping (simpler than two)
#   - Resumable: skips ASINs already in storage/processed_asins.json
#   - Per-product error isolation: one failure never stops the whole run
#   - Uses element-based waiting (wait_for_selector) as primary sync
#   - Human-like interaction (random pauses, scrolls) as secondary sync

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

# ── Anti-detection JS ─────────────────────────────────────────────────────────
# Identical to amazon_spider.py — hides Playwright's automation markers.
# Injected before every page load via PageMethod("add_init_script", ...).
INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: () => ({}) };
    Object.defineProperty(screen, 'availWidth',   { get: () => 1920 });
"""

# Where the checkpoint file lives (loaded + saved by DeduplicationPipeline too)
CHECKPOINT_FILE = Path(__file__).parent.parent / "storage" / "processed_asins.json"
CONFIG_FILE = Path(__file__).parent.parent.parent / "config.yaml"


def _ms(lo: float, hi: float) -> int:
    """Convert a seconds range to milliseconds for page.wait_for_timeout()."""
    return int(random.uniform(lo, hi) * 1000)


def _load_config() -> dict:
    """Load config.yaml. Returns defaults if the file is missing."""
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
    """Load already-processed ASINs from checkpoint file & output/products.jsonl."""
    asins = set()
    # 1. Read storage/processed_asins.json
    try:
        if CHECKPOINT_FILE.exists():
            with open(CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
                asins.update(data.get("processed_asins", []))
    except Exception as e:
        logger.warning("Could not load checkpoint: %s", e)

    # 2. Read output/products.jsonl directly (live fallback)
    try:
        products_file = Path("output/products.jsonl")
        if products_file.exists():
            with open(products_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            obj = json.loads(line)
                            if obj.get("asin"):
                                asins.add(obj["asin"])
                        except Exception:
                            pass
    except Exception as e:
        logger.warning("Could not read products.jsonl for checkpoint: %s", e)

    return asins
def should_abort_req(request):
    """SPEED OPTIMIZATION: Block images, stylesheets, fonts, and tracking scripts."""
    ignored_types = ["image", "stylesheet", "font", "media", "beacon"]
    if request.resource_type in ignored_types:
        return True
    
    ignored_patterns = ["/g/", "/rb/", "doubleclick", "amazon-adsystem", "analytics"]
    if any(pattern in request.url for pattern in ignored_patterns):
        return True
        
    return False

class ProductionSpider(scrapy.Spider):
    """
    Production Amazon scraper.

    Run with:  python run.py
    Or:        scrapy crawl production_spider
    """

    name = "production_spider"
    allowed_domains = ["amazon.com"]
    custom_settings = {
        'PLAYWRIGHT_ABORT_REQUEST': should_abort_req
    }

    # ── Spider startup ────────────────────────────────────────────────────────

    async def start(self):
        """
        Entry point. Loads config and checkpoint, then fires the homepage
        warmup request. All subsequent requests flow from the callbacks below.
        """
        # Load configuration from config.yaml
        config = _load_config()
        self.config = config

        # Expose key config values as spider attributes for pipelines to read
        self.output_dir = config["output_dir"]
        self.search_urls = config["search_urls"]
        self.max_pages = config["max_pages"]
        self.max_products = config["max_products"]

       

        # Load the checkpoint so we skip already-processed ASINs
        self._processed_asins: set = _load_checkpoint()
        prod_len = len(self._processed_asins)
        logger.info("[INFO] Run started — %d ASINs already in checkpoint",
                    prod_len)
        if(prod_len>=self.max_products):
            logger.info("[INFO] Max products reached")
            raise CloseSpider(f"Target max_products limit ({self.max_products}) reached")

         # Track totals for early stopping
        self._products_scraped = prod_len
        # Set up the proxy manager (empty list = no proxies)
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

        # ── Step 1: Hit the Amazon homepage first ─────────────────────────────
        # Mimics a human opening their browser and going to amazon.com.
        # This sets session cookies, solves the AWS WAF challenge, and warms
        # up the browser context before we touch any search or product page.
        logger.info("[INFO] Navigating to Amazon homepage for warmup...")
        yield scrapy.Request(
            "https://www.amazon.com/",
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    # Inject anti-detection JS so webdriver is hidden from load
                    PageMethod("add_init_script", INIT_SCRIPT),
                    # Simulate a human reading the homepage for a moment
                    PageMethod("wait_for_timeout", _ms(2.0, 4.0)),
                    # Light scroll — a real user glances at the page
                    PageMethod("evaluate", "window.scrollBy(0, 300)"),
                    PageMethod("wait_for_timeout", _ms(0.8, 1.5)),
                ],
                # Keep the page open so we can reuse it for the first search
                "playwright_include_page": True,
            },
            callback=self.after_homepage,
            errback=self.handle_error,
            dont_filter=True,
        )

    # ── Step 2: Navigate to search from homepage ──────────────────────────────

    async def after_homepage(self, response):
        """
        Called after the homepage loads. Navigates the same browser page
        to the first search URL (sharing cookies and browser state).
        Then queues the remaining search URLs as separate requests.
        """
        page = response.meta["playwright_page"]
        first_search_url = self.search_urls[0]

        logger.info("[INFO] Homepage loaded (%s). Navigating to first search...",
                    response.status)

        try:
            # Navigate to first search using the same page (same cookies/session)
            await page.goto(first_search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(_ms(1.5, 3.0))

            # Simulate reading the search results page
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(_ms(1.0, 2.0))
            await page.evaluate("window.scrollBy(0, 700)")
            await page.wait_for_timeout(_ms(0.8, 1.5))

            title = await page.title()
            logger.info("[INFO] Search page title: %s", title)

            # Grab the fully rendered HTML
            content = await page.content()

        finally:
            # Always close the page — keeps memory usage flat
            await page.close()

        # Wrap the HTML in a Scrapy response so our CSS selectors work on it
        search_response = response.replace(body=content.encode(), url=first_search_url)
        search_response.meta["page_number"] = 1
        search_response.meta["source_search_url"] = first_search_url

        # Parse the first search page
        async for result in self.parse_search(search_response):
            yield result

        # Queue the remaining search URLs as independent requests
        # (they each get their own browser page in the same context)
        for url in self.search_urls[1:]:
            yield self._make_search_request(url, page_number=1)

    # ── Search results page ───────────────────────────────────────────────────

    async def parse_search(self, response):
        """
        Parses a search results page:
          - Detects CAPTCHA / access denial → logs warning, skips
          - Extracts product cards → yields SearchResultItem per card
          - Yields product page requests for unprocessed ASINs
          - Handles pagination up to max_pages
        """
        source_url = response.meta.get("source_search_url", response.url)
        page_num = response.meta.get("page_number", 1)

        logger.info("[INFO] Search page %d — URL: %s", page_num, response.url)

        # ── Page validation ───────────────────────────────────────────────────
        issue_type, issue_msg = detect_page_issue(response.text, response.url)
        if issue_type:
            logger.warning("[WARN] Access-restricted page detected: %s", issue_msg)
            return   # Skip this page — don't treat it as valid results

        # ── Extract product cards ─────────────────────────────────────────────
        cards = response.css("div[data-component-type='s-search-result']")
        logger.info("[INFO] Products discovered: %d (page %d)", len(cards), page_num)

        for card in cards:
            # Stop early if we've already hit the product target
            if self._products_scraped >= self.max_products:
                logger.info("[INFO] Reached max_products limit (%d) — stopping",
                            self.max_products)
                return

            asin = card.attrib.get("data-asin", "").strip()
            if not asin:
                continue   # Card has no ASIN — skip

            # Build the search-result item (intermediate data for tracking)
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

            # Skip if already processed in a previous run or earlier this run
            if asin in self._processed_asins:
                logger.debug("[Dedup] Skipping already-processed ASIN: %s", asin)
                continue

            # Mark as seen immediately so pagination doesn't re-queue it
            self._processed_asins.add(asin)

            # Yield a request to scrape the full product page
            prod_url = product_url or f"https://www.amazon.com/dp/{asin}"
            yield self._make_product_request(prod_url, asin)

        # ── Pagination ────────────────────────────────────────────────────────
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

    # ── Product detail page ───────────────────────────────────────────────────

    async def parse_product(self, response):
        """
        Parses a full Amazon product page and yields a ProductDetailItem.

        Uses playwright_include_page so we can run JavaScript to extract
        image URLs from dynamic data, then closes the page.
        """
        asin = response.meta.get("asin")
        page = response.meta.get("playwright_page")
        start_time = time.monotonic()

        # If we already reached target products while this request was queued, exit early
        if self._products_scraped >= self.max_products:
            if page and not page.is_closed():
                await page.close()
            raise CloseSpider(f"Target max_products limit ({self.max_products}) reached")

        try:
            # ── Page validation ───────────────────────────────────────────────
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

            # ── Extract images via JavaScript (they're loaded dynamically) ────
            images = []
            if page and not page.is_closed():
                try:
                    images = await page.evaluate("""
                        () => {
                            // Amazon stores image URLs as JSON in data-a-dynamic-image
                            const mainImg = document.querySelector('#landingImage');
                            if (mainImg) {
                                const raw = mainImg.getAttribute('data-a-dynamic-image');
                                if (raw) return Object.keys(JSON.parse(raw));
                            }
                            // Fallback: og:image meta tag
                            const og = document.querySelector('meta[property="og:image"]');
                            return og ? [og.getAttribute('content')] : [];
                        }
                    """)
                except Exception as e:
                    logger.debug("Image JS extraction failed for %s: %s", asin, e)

            # Fall back to HTML-based image extraction if JS gave nothing
            if not images:
                images = extract_images_from_html(response)

            # ── Extract all other fields from the HTML ────────────────────────
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

            # Store processing time so RunMetadataPipeline can compute averages
            item._processing_time = time.monotonic() - start_time

            self._products_scraped += 1
            logger.info("[INFO] Product scraped (%d/%d): %s — %s",
                        self._products_scraped, self.max_products, asin, (item.title or "")[:60])
            yield item

            # Immediately stop the crawler when target max_products is hit
            if self._products_scraped >= self.max_products:
                logger.info("[INFO] Target max_products limit (%d) reached — closing spider!",
                            self.max_products)
                raise CloseSpider(f"Reached target max_products limit ({self.max_products})")

        except CloseSpider:
            raise
        except Exception as e:
            # Catch-all: one broken product must NEVER kill the spider
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
            # Always close the page to free browser memory
            if page and not page.is_closed():
                await page.close()

    # ── Error handler ─────────────────────────────────────────────────────────

    async def handle_error(self, failure):
        """
        Errback for all requests. Catches network errors, timeouts, and
        browser crashes. Yields a FailedItem so the failure is recorded,
        then returns normally so the spider continues with other requests.
        """
        request = failure.request
        asin = request.meta.get("asin")
        url = request.url
        retry_count = request.meta.get("retry_times", 0)

        error_type = type(failure.value).__name__
        error_msg = str(failure.value)

        logger.warning("[WARN] Request failed (%s): %s — %s",
                       error_type, url, error_msg[:120])

        # Close the Playwright page if it's still open
        page = request.meta.get("playwright_page")
        if page and not page.is_closed():
            try:
                await page.close()
                logger.info("[INFO] Browser restarted (page closed after crash)")
            except Exception:
                pass

        # Yield a failure record (only for product pages — not for search pages)
        if asin:
            yield FailedItem(
                url=url,
                asin=asin,
                timestamp=datetime.now(timezone.utc).isoformat(),
                failure_type=error_type,
                failure_message=error_msg,
                retry_count=retry_count,
            )

    # ── Internal request builders ─────────────────────────────────────────────

    def _make_search_request(self, url: str, page_number: int = 1,
                             source_search_url: str = None) -> scrapy.Request:
        """
        Builds a Playwright request for a search results page.
        Uses domcontentloaded to avoid Amazon background ping timeouts.
        """
        return scrapy.Request(
            url,
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    PageMethod("add_init_script", INIT_SCRIPT),
                    # Wait for at least one product card to appear
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
        """
        Builds a Playwright request for a product detail page.
        Keeps the page open (playwright_include_page) so parse_product
        can run JavaScript to extract dynamic image data.
        """
        return scrapy.Request(
            url,
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
                "playwright_page_methods": [
                    PageMethod("add_init_script", INIT_SCRIPT),
                    # Wait for the product title — if it never appears we got a
                    # CAPTCHA or error page; the timeout triggers the errback.
                    PageMethod("wait_for_selector",
                               "#productTitle",
                               timeout=20000, state="visible"),
                    PageMethod("wait_for_timeout", _ms(1.0, 2.0)),
                    # Scroll to trigger lazy-loaded images
                    PageMethod("evaluate", "window.scrollBy(0, 600)"),
                    PageMethod("wait_for_timeout", _ms(0.5, 1.2)),
                ],
                # Keep page open for JS image extraction in parse_product
                "playwright_include_page": True,
                "asin": asin,
            },
            callback=self.parse_product,
            errback=self.handle_error,
        )
