# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class AmazonScraperSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # matching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class AmazonScraperDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass


    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


# ── Production Proxy Middleware ────────────────────────────────────────────────
# Appended to existing middlewares — existing classes above are NOT modified.

import logging as _logging
from amazon_scraper.proxy_manager import parse_proxy_url

_proxy_logger = _logging.getLogger(__name__)


class PlaywrightProxyMiddleware:
    """
    Assigns a residential proxy to each Playwright request.

    How it works:
    - On each request, asks ProxyManager for the healthiest proxy.
    - Sets request.meta["playwright_context"] to a name like "proxy_0"
      so scrapy-playwright creates a dedicated browser context for that proxy.
    - Adds proxy credentials to playwright_context_kwargs on first use.
    - On response: marks proxy success/failure based on HTTP status.
    - On exception: marks proxy as timed-out.
    """

    def __init__(self):
        self._proxy_manager = None
        # Maps proxy_url → context name e.g. "proxy_0"
        self._proxy_context_names: dict = {}

    def process_request(self, request, spider):
        # Only handle Playwright requests; let non-Playwright through unchanged
        if not request.meta.get("playwright"):
            return None

        # Grab the proxy manager from the spider (set in spider.start())
        if self._proxy_manager is None:
            self._proxy_manager = getattr(spider, "proxy_manager", None)

        if self._proxy_manager is None:
            return None   # No proxies configured — use default context

        proxy_url = self._proxy_manager.get_proxy()
        if not proxy_url:
            return None   # All proxies unhealthy — continue without proxy

        # Assign a stable context name for this proxy
        if proxy_url not in self._proxy_context_names:
            idx = len(self._proxy_context_names)
            self._proxy_context_names[proxy_url] = f"proxy_{idx}"
            _proxy_logger.info(
                "[Proxy] New context '%s' assigned for %s",
                self._proxy_context_names[proxy_url],
                self._mask(proxy_url)
            )

        context_name = self._proxy_context_names[proxy_url]

        # Store proxy url on the request so process_response can mark health
        request.meta["_proxy_url"] = proxy_url
        request.meta["playwright_context"] = context_name

        # Build Playwright-format proxy dict
        proxy_dict = parse_proxy_url(proxy_url)

        # Set context_kwargs only for new contexts (scrapy-playwright creates
        # the context on first use; existing contexts ignore these kwargs)
        request.meta.setdefault("playwright_context_kwargs", {})
        request.meta["playwright_context_kwargs"].setdefault("proxy", proxy_dict)

        return None

    def process_response(self, request, response, spider):
        proxy_url = request.meta.get("_proxy_url")
        if proxy_url and self._proxy_manager:
            if response.status in (200, 202, 301, 302):
                self._proxy_manager.mark_success(proxy_url)
            else:
                self._proxy_manager.mark_failure(proxy_url)
                _proxy_logger.warning(
                    "[WARN] Proxy returned %d — marking failure for %s",
                    response.status, self._mask(proxy_url)
                )
        return response

    def process_exception(self, request, exception, spider):
        proxy_url = request.meta.get("_proxy_url")
        if proxy_url and self._proxy_manager:
            self._proxy_manager.mark_timeout(proxy_url)
            _proxy_logger.warning(
                "[WARN] Proxy timeout — %s: %s", self._mask(proxy_url), exception
            )
        return None   # Let Scrapy's retry middleware handle the retry

    @staticmethod
    def _mask(proxy_url: str) -> str:
        """Hide password in logs."""
        try:
            from urllib.parse import urlparse
            p = urlparse(proxy_url)
            return f"{p.scheme}://{p.username}:****@{p.hostname}:{p.port}"
        except Exception:
            return "***"
