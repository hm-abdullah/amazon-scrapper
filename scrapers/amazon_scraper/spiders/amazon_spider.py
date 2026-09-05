import random
import scrapy
from scrapy_playwright.page import PageMethod


# ---------------------------------------------------------------------------
# Anti-detection JS — mirrors context.add_init_script() from the reference
# script. Registered on each page before any page scripts run.
# ---------------------------------------------------------------------------
INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {}, loadTimes: () => ({}) };
    Object.defineProperty(screen, 'availWidth',   { get: () => 1920 });
"""


def _ms(lo: float, hi: float) -> int:
    """Convert a random seconds range to milliseconds — mirrors
    time.sleep(random.uniform(lo, hi)) from the reference script."""
    return int(random.uniform(lo, hi) * 1000)


class AmazonSpiderSpider(scrapy.Spider):
    name = "amazon_spider"
    allowed_domains = ["amazon.com"]

    # ── Step 1: Land on the Amazon homepage first (human-like warm-up) ────────
    async def start(self):
        yield scrapy.Request(
            "https://www.amazon.com/",
            meta={
                "playwright": True,
                "playwright_context": "default",
                "playwright_page_goto_kwargs": {
                    "wait_until": "domcontentloaded",
                },
                "playwright_page_methods": [
                    # Patch automation markers immediately after page creation
                    PageMethod("add_init_script", INIT_SCRIPT),
                    # Simulate reading the homepage for a moment
                    PageMethod("wait_for_timeout", _ms(2.0, 4.0)),
                    # Light scroll — a human glances at the page
                    PageMethod("evaluate", "window.scrollBy(0, 300)"),
                    PageMethod("wait_for_timeout", _ms(0.8, 1.5)),
                ],
                # Keep the page open so we can reuse the same context/cookies
                # for the follow-up search request
                "playwright_include_page": True,
            },
            callback=self.after_homepage,
            errback=self.errback,
            dont_filter=True,
        )

    # ── Step 2: Navigate to search from within the same browser page ──────────
    async def after_homepage(self, response):
        page = response.meta["playwright_page"]
        search_url = "https://www.amazon.com/s?k=gaming"

        self.logger.info("Homepage loaded (%s), navigating to search…", response.status)

        try:
            # Navigate the existing page (same cookies, same context)
            await page.goto(search_url, wait_until="domcontentloaded")

            # Mirrors: time.sleep(random.uniform(1.8, 3.5))
            await page.wait_for_timeout(_ms(1.8, 3.5))

            # Mirrors: page.evaluate("window.scrollBy(0, 400)")
            await page.evaluate("window.scrollBy(0, 400)")

            # Mirrors: time.sleep(random.uniform(0.8, 1.6))
            await page.wait_for_timeout(_ms(0.8, 1.6))

            # Mirrors: page.evaluate("window.scrollBy(0, 600)")
            await page.evaluate("window.scrollBy(0, 600)")

            # Mirrors: time.sleep(random.uniform(1.2, 2.1))
            await page.wait_for_timeout(_ms(1.2, 2.1))

            # Mirrors: print(page.title())
            title = await page.title()
            self.logger.info("PAGE TITLE: %s", title)

            content = await page.content()
        finally:
            await page.close()

        # Hand the rendered HTML to Scrapy's selector machinery
        fake_response = response.replace(body=content.encode(), url=search_url)
        for item in self.parse(fake_response):
            yield item

    def parse(self, response):

        self.logger.info(
            "STATUS: %s | URL: %s",
            response.status,
            response.url
        )

        cards = response.css(
            "div[data-component-type='s-search-result']"
        )

        self.logger.info(
            "FOUND PRODUCTS: %d",
            len(cards)
        )

        for card in cards:

            asin = card.attrib.get("data-asin")

            title = card.css(
                "h2 span::text"
            ).get()

            product_url = card.css(
                "h2 a::attr(href)"
            ).get()

            price = card.css(
                ".a-price .a-offscreen::text"
            ).get()

            rating = card.css(
                ".a-icon-star-small .a-icon-alt::text"
            ).get()

            review_count = card.css(
                "span.a-size-base.s-underline-text::text"
            ).get()

            image_url = card.css(
                "img.s-image::attr(src)"
            ).get()

            availability = card.css(
                ".a-color-base::text"
            ).get()

            yield {
                "asin": asin,
                "title": title.strip() if title else None,
                "product_url": (
                    response.urljoin(product_url)
                    if product_url
                    else None
                ),
                "price": price.strip()
                    if price else None,
                "rating": rating.strip()
                    if rating else None,
                "review_count": (
                review_count.strip()
                if review_count
                else None
                ),
                "availability": (
                    availability.strip()
                    if availability
                    else None
                ),
                "image_url": image_url,
            }
    async def errback(self, failure):
        self.logger.error("Request failed: %s", failure)
        page = failure.request.meta.get("playwright_page")
        if page and not page.is_closed():
            await page.close()