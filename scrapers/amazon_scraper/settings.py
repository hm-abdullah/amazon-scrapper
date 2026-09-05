# Scrapy settings for amazon_scraper project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# settings.py

import random

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# ── THE FIX ────────────────────────────────────────────────────────────────
# By default scrapy-playwright uses `use_scrapy_headers` which injects
# Scrapy's request headers (including `User-Agent: Scrapy/2.18.0`) into
# every Playwright navigation, overriding the stealth UA set in the context.
# Setting this to None tells scrapy-playwright: "let the browser decide all
# headers" — exactly what the standalone Playwright script does.
PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None

PLAYWRIGHT_BROWSER_TYPE = "chromium"

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    # 'channel: chrome' tells Playwright to use the REAL installed Google Chrome
    # binary instead of its bundled Chromium. This gives us the authentic Chrome
    # TLS stack (BoringSSL with Chrome's exact cipher suite order) → real JA3
    # fingerprint that Amazon's WAF accepts. Playwright's own Chromium has a
    # synthetic TLS fingerprint that is trivially detected.
    "channel": "chrome",
    "args": [
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        # NOTE: --disable-web-security and --disable-features removed.
        # They are unusual flags that real Chrome never uses and act as
        # secondary bot signals at the WAF layer.
    ],
}

# A single default context is fine for the basic version.
PLAYWRIGHT_CONTEXTS = {
    "default": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        # The random values are generated when the settings module loads.
        "viewport": {
            "width": random.randint(1280, 1440),
            "height": random.randint(820, 980),
        },

        # Locale/timezone must match your actual IP geolocation.
        # Mismatch is a first-class bot signal Amazon catches at the CDN layer.
        "locale": random.choice(["en-US", "en-GB", "en-IN"]),

        "timezone_id": "Asia/Karachi",

        "screen": {
            "width": 1920,
            "height": 1080,
        },

        "device_scale_factor": 1,

        "extra_http_headers": {
            "accept-language": "en-US,en;q=0.9",
            # Updated to match Chrome 151 (installed version on this machine)
            "sec-ch-ua": '"Google Chrome";v="151", "Chromium";v="151", "Not/A)Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },

        # ── PROXY CONFIGURATION ───────────────────────────────────────────
        # Uncomment and fill in when your IP is blocked.
        # Playwright routes ALL traffic (including TLS handshake) through the
        # proxy, giving you a fresh IP that Amazon hasn't flagged.
        #
        # Format: "http://user:pass@host:port"  or  "socks5://host:port"
        #
        # "proxy": {
        #     "server": "http://your-proxy-host:port",
        #     "username": "your-username",   # remove if no auth
        #     "password": "your-password",   # remove if no auth
        # },
    },
}

# Increased from 1 to support proxy contexts (one per proxy + 1 default).
# Does NOT change stealth settings — only controls resource allocation.
PLAYWRIGHT_MAX_CONTEXTS = 1
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 1

# Page methods (scrolls + wait_for_timeout) run AFTER domcontentloaded fires.
# Default 30s was timing out while the scroll/sleep sequence was still running.
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 90_000   # ms — 90 seconds
DOWNLOAD_TIMEOUT = 120                            # seconds — Scrapy-level safety net



BOT_NAME = "amazon_scraper"

SPIDER_MODULES = ["amazon_scraper.spiders"]
NEWSPIDER_MODULE = "amazon_scraper.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
# USER_AGENT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
# Properly disable Scrapy's header-injecting middlewares.
# These set `User-Agent: Scrapy/2.18.0` and `Accept-Language: en` on Scrapy
# Request objects. Even with PLAYWRIGHT_PROCESS_REQUEST_HEADERS=None they are
# harmless, but disabling them keeps the chain clean.
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware": None,
    # Proxy rotation — assigns residential proxies to Playwright requests
    "amazon_scraper.middlewares.PlaywrightProxyMiddleware": 350,
}

# Fallback UA — only used by Scrapy's own HTTP layer, not by Playwright.
# Matches what we set in the browser context.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)
# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Concurrency and throttling — keep low for Amazon
# CONCURRENT_REQUESTS = 5
CONCURRENT_REQUESTS_PER_DOMAIN = 1
# DOWNLOAD_DELAY = 1

# Retry 503s (Amazon bot-block) with exponential backoff
RETRY_HTTP_CODES = [500, 502, 503, 504, 429]
RETRY_TIMES = 2
RETRY_PRIORITY_ADJUST = -2

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "amazon_scraper.middlewares.AmazonScraperSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "amazon_scraper.middlewares.AmazonScraperDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "amazon_scraper.pipelines.AmazonScraperPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"


# ── PRODUCTION SETTINGS ────────────────────────────────────────────────────────
# Everything below is added for the production spider.
# The playwright stealth block above is untouched.

# Item pipelines — ordered by priority (lowest number runs first)
ITEM_PIPELINES = {
    "amazon_scraper.pipelines.DeduplicationPipeline": 100,
    "amazon_scraper.pipelines.ValidationPipeline": 200,
    "amazon_scraper.pipelines.OutputPipeline": 300,
    "amazon_scraper.pipelines.RunMetadataPipeline": 400,
}

# Concurrent requests — keep at 1 for Amazon; overridable from config.yaml
CONCURRENT_REQUESTS = 1

# Structured log format — shows level, logger name, and message clearly
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_LEVEL = "INFO"

# Path to the configuration file read by run.py and production_spider.py
CONFIG_FILE = "config.yaml"
