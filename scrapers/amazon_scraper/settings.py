# Scrapy framework settings and Playwright integration configuration.

import random

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None

PLAYWRIGHT_BROWSER_TYPE = "chromium"

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "channel": "chrome",
    "args": [
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
    ],
}

PLAYWRIGHT_CONTEXTS = {
    "default": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "viewport": {
            "width": random.randint(1280, 1440),
            "height": random.randint(820, 980),
        },
        "locale": random.choice(["en-US", "en-GB", "en-IN"]),
        "timezone_id": "Asia/Karachi",
        "screen": {
            "width": 1920,
            "height": 1080,
        },
        "device_scale_factor": 1,
        "extra_http_headers": {
            "accept-language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Google Chrome";v="151", "Chromium";v="151", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    },
}

PLAYWRIGHT_MAX_CONTEXTS = 1
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 1

PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 90_000
DOWNLOAD_TIMEOUT = 120

BOT_NAME = "amazon_scraper"

SPIDER_MODULES = ["amazon_scraper.spiders"]
NEWSPIDER_MODULE = "amazon_scraper.spiders"

ADDONS = {}

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware": None,
    "amazon_scraper.middlewares.PlaywrightProxyMiddleware": 350,
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)
ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS_PER_DOMAIN = 1

RETRY_HTTP_CODES = [500, 502, 503, 504, 429]
RETRY_TIMES = 2
RETRY_PRIORITY_ADJUST = -2

FEED_EXPORT_ENCODING = "utf-8"

ITEM_PIPELINES = {
    "amazon_scraper.pipelines.DeduplicationPipeline": 100,
    "amazon_scraper.pipelines.ValidationPipeline": 200,
    "amazon_scraper.pipelines.OutputPipeline": 300,
    "amazon_scraper.pipelines.SQLitePipeline": 350,
    "amazon_scraper.pipelines.RunMetadataPipeline": 400,
}

CONCURRENT_REQUESTS = 1

LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_LEVEL = "INFO"

CONFIG_FILE = "config.yaml"
