# proxy_manager.py — Residential proxy pool manager.
#
# Tracks health metrics for each proxy and decides which one to use.
# State is persisted to storage/proxy_health.json so health data
# survives restarts. Thread-safe via a simple lock.

import json
import logging
import time
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Where proxy health state is saved between runs
HEALTH_FILE = Path(__file__).parent / "storage" / "proxy_health.json"


class ProxyManager:
    """
    Manages a pool of residential proxies.

    Usage:
        pm = ProxyManager(["http://user:pass@host:port"])
        proxy_url = pm.get_proxy()      # Returns best proxy or None
        pm.mark_success(proxy_url)
        pm.mark_failure(proxy_url)
        pm.mark_timeout(proxy_url)
    """

    def __init__(self, proxy_urls: list, max_consecutive_failures: int = 3,
                 cooldown_seconds: int = 300):
        self.max_consecutive_failures = max_consecutive_failures
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()

        # Initialize health record for each proxy
        self._health: dict = {}
        saved = self._load_state()

        for url in proxy_urls:
            if url in saved:
                # Restore saved health data from last run
                self._health[url] = saved[url]
            else:
                self._health[url] = self._fresh_record()

        logger.info("[ProxyManager] Loaded %d proxies", len(self._health))

    # ── Public API ────────────────────────────────────────────────────────────

    def get_proxy(self) -> Optional[str]:
        """
        Returns the URL of the healthiest available proxy,
        or None if no healthy proxies exist (scraper continues without proxy).
        """
        with self._lock:
            healthy = [
                url for url, rec in self._health.items()
                if self._is_healthy(rec)
            ]
            if not healthy:
                logger.warning("[ProxyManager] No healthy proxies available — scraping without proxy")
                return None

            # Pick the proxy with fewest total failures (simple round-robin would
            # work too, but failure-weighted selection gives better performance)
            best = min(healthy, key=lambda u: self._health[u]["fail_count"])
            self._health[best]["last_used"] = time.time()
            return best

    def mark_success(self, proxy_url: str) -> None:
        """Call after a request using this proxy succeeded."""
        with self._lock:
            if proxy_url not in self._health:
                return
            rec = self._health[proxy_url]
            rec["success_count"] += 1
            rec["consecutive_failures"] = 0   # Reset streak on success
        self._save_state()

    def mark_failure(self, proxy_url: str) -> None:
        """Call after a request using this proxy got an HTTP error (4xx/5xx)."""
        with self._lock:
            if proxy_url not in self._health:
                return
            rec = self._health[proxy_url]
            rec["fail_count"] += 1
            rec["consecutive_failures"] += 1
            if rec["consecutive_failures"] >= self.max_consecutive_failures:
                rec["unhealthy_since"] = time.time()
                logger.warning(
                    "[ProxyManager] Proxy marked unhealthy (too many consecutive failures): %s",
                    self._mask(proxy_url)
                )
        self._save_state()

    def mark_timeout(self, proxy_url: str) -> None:
        """Call after a request using this proxy timed out."""
        with self._lock:
            if proxy_url not in self._health:
                return
            rec = self._health[proxy_url]
            rec["timeout_count"] += 1
            rec["consecutive_failures"] += 1
            if rec["consecutive_failures"] >= self.max_consecutive_failures:
                rec["unhealthy_since"] = time.time()
                logger.warning(
                    "[ProxyManager] Proxy marked unhealthy (timeouts): %s",
                    self._mask(proxy_url)
                )
        self._save_state()

    def stats(self) -> dict:
        """Returns a summary dict for run_metadata.json."""
        with self._lock:
            return {
                url: {
                    "success": rec["success_count"],
                    "failures": rec["fail_count"],
                    "timeouts": rec["timeout_count"],
                    "healthy": self._is_healthy(rec),
                }
                for url, rec in self._health.items()
            }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_healthy(self, rec: dict) -> bool:
        """A proxy is healthy unless it has too many consecutive failures
        AND the cooldown period has not expired yet."""
        if rec["consecutive_failures"] < self.max_consecutive_failures:
            return True   # Still within failure budget

        # Check if cooldown has elapsed → auto-recover the proxy
        since = rec.get("unhealthy_since", 0)
        elapsed = time.time() - since
        if elapsed >= self.cooldown_seconds:
            rec["consecutive_failures"] = 0   # Recover
            rec["unhealthy_since"] = None
            logger.info("[ProxyManager] Proxy recovered after cooldown: %s",
                        self._mask(list(self._health.keys())[0]))
            return True
        return False

    @staticmethod
    def _fresh_record() -> dict:
        return {
            "success_count": 0,
            "fail_count": 0,
            "timeout_count": 0,
            "consecutive_failures": 0,
            "last_used": None,
            "unhealthy_since": None,
        }

    @staticmethod
    def _mask(proxy_url: str) -> str:
        """Hide password in logs: http://user:****@host:port"""
        try:
            p = urlparse(proxy_url)
            return f"{p.scheme}://{p.username}:****@{p.hostname}:{p.port}"
        except Exception:
            return "***"

    def _load_state(self) -> dict:
        """Load persisted health data from disk (returns {} on first run)."""
        try:
            if HEALTH_FILE.exists():
                with open(HEALTH_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning("[ProxyManager] Could not load proxy health file: %s", e)
        return {}

    def _save_state(self) -> None:
        """Persist current health data to disk."""
        try:
            HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(HEALTH_FILE, "w") as f:
                json.dump(self._health, f, indent=2)
        except Exception as e:
            logger.warning("[ProxyManager] Could not save proxy health: %s", e)


# ── Standalone helper ─────────────────────────────────────────────────────────

def parse_proxy_url(proxy_url: str) -> dict:
    """
    Convert a proxy URL string into the dict format Playwright expects.

    Input:  "http://user:pass@host:8080"
    Output: {"server": "http://host:8080", "username": "user", "password": "pass"}
    """
    p = urlparse(proxy_url)
    result = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        result["username"] = p.username
    if p.password:
        result["password"] = p.password
    return result
