# Scrapy spider and downloader middlewares including Playwright proxy handling.

from scrapy import signals
from itemadapter import ItemAdapter


class AmazonScraperSpiderMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        return None

    def process_spider_output(self, response, result, spider):
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        pass

    async def process_start(self, start):
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class AmazonScraperDownloaderMiddleware:

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


import logging as _logging
from amazon_scraper.proxy_manager import parse_proxy_url

_proxy_logger = _logging.getLogger(__name__)


class PlaywrightProxyMiddleware:

    def __init__(self):
        self._proxy_manager = None
        self._proxy_context_names: dict = {}

    def process_request(self, request, spider):
        if not request.meta.get("playwright"):
            return None

        if self._proxy_manager is None:
            self._proxy_manager = getattr(spider, "proxy_manager", None)

        if self._proxy_manager is None:
            return None

        proxy_url = self._proxy_manager.get_proxy()
        if not proxy_url:
            return None

        if proxy_url not in self._proxy_context_names:
            idx = len(self._proxy_context_names)
            self._proxy_context_names[proxy_url] = f"proxy_{idx}"
            _proxy_logger.info(
                "[Proxy] New context '%s' assigned for %s",
                self._proxy_context_names[proxy_url],
                self._mask(proxy_url)
            )

        context_name = self._proxy_context_names[proxy_url]

        request.meta["_proxy_url"] = proxy_url
        request.meta["playwright_context"] = context_name

        proxy_dict = parse_proxy_url(proxy_url)

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
        return None

    @staticmethod
    def _mask(proxy_url: str) -> str:
        try:
            from urllib.parse import urlparse
            p = urlparse(proxy_url)
            return f"{p.scheme}://{p.username}:****@{p.hostname}:{p.port}"
        except Exception:
            return "***"
