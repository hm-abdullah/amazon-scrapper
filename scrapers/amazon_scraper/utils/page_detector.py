# utils/page_detector.py — Classifies pages BEFORE parsing them.
#
# Amazon serves several types of "non-product" pages that we must
# detect and handle gracefully instead of blindly parsing them as data.
#
# Functions return True/False so the spider can decide what to do:
#   - CAPTCHA  → yield FailedItem, let scraper continue
#   - Blocked  → yield FailedItem, try another proxy next run
#   - Empty    → skip silently, move to next search page
#   - Valid    → proceed with data extraction

from typing import Tuple, Optional


# ── Signal word lists ─────────────────────────────────────────────────────────
# We search for these strings in the raw page HTML.
# Lower-cased comparison avoids case sensitivity issues.

_CAPTCHA_SIGNALS = [
    "type the characters you see",
    "enter the characters you see",
    "to discuss automated access to amazon data",
    "we need to verify",
    "robot check",
    "press & hold",
]

_ACCESS_DENIED_SIGNALS = [
    "access denied",
    "sorry, we just need to make sure you're not a robot",
    "enable javascript and cookies to continue",
    "503 service unavailable",
    "automated access to amazon",
    "request blocked",
]

_EMPTY_SEARCH_SIGNALS = [
    "did not match any products",
    "no results for",
    "0 results for",
    "we couldn't find",
]


# ── Public detection functions ────────────────────────────────────────────────

def is_captcha_page(html: str) -> bool:
    """True if the page is asking the user to solve a CAPTCHA."""
    lower = html.lower()
    return any(sig in lower for sig in _CAPTCHA_SIGNALS)


def is_access_denied(html: str) -> bool:
    """True if Amazon explicitly denied access (WAF block, rate limit)."""
    lower = html.lower()
    return any(sig in lower for sig in _ACCESS_DENIED_SIGNALS)


def is_empty_search(html: str) -> bool:
    """
    True if a search query returned zero results.

    IMPORTANT: Check only the specific <h1> and visible text markers Amazon uses
    for no-results pages. Do NOT scan raw HTML — it contains 'emptycart' in
    tracking pixel URLs and CSM tags, causing false positives on valid pages.
    """
    # Amazon's no-results page always has this specific phrase in visible text
    specific_signals = [
        "did not match any products",
        "no results for",
        "0 results for",
    ]
    # Only look for these inside the body text area, not in scripts/URLs
    # We check a limited substring to avoid URL/script noise
    body_start = html.find("<body")
    body_end = html.rfind("</body>")
    if body_start == -1:
        return False
    body_html = html[body_start:body_end] if body_end > body_start else html[body_start:]

    # Strip out <script> blocks and <a href> URLs before checking
    import re
    body_text = re.sub(r"<script[^>]*>.*?</script>", " ", body_html, flags=re.DOTALL)
    body_text = re.sub(r"<[^>]+>", " ", body_text)   # Strip remaining tags
    body_lower = body_text.lower()

    return any(sig in body_lower for sig in specific_signals)


def is_valid_search_page(html: str) -> bool:
    """
    True if the page looks like a real Amazon search results page.
    Checks for the presence of product cards in the HTML.
    """
    return (
        "data-component-type=\"s-search-result\"" in html
        or "data-asin" in html
    )


def is_valid_product_page(html: str) -> bool:
    """
    True if the page looks like a real Amazon product detail page.
    The element #productTitle is always present on genuine product pages.
    """
    return "id=\"productTitle\"" in html or "id='productTitle'" in html


def detect_page_issue(html: str, url: str) -> Tuple[Optional[str], str]:
    """
    Master check — call this once before parsing any page.

    Returns:
        (issue_type, message)  — issue_type is None if the page looks fine.

    Possible issue types:
        "captcha"       — CAPTCHA challenge page
        "access_denied" — Amazon blocked the request
        "empty_search"  — Search returned no results
        "invalid_page"  — Unexpected page structure
    """
    if is_captcha_page(html):
        return "captcha", "CAPTCHA challenge detected — page not parseable"

    if is_access_denied(html):
        return "access_denied", "Amazon returned an access-denied page"

    # If valid search cards exist, page is fine!
    if is_valid_search_page(html):
        return None, ""

    if is_empty_search(html):
        return "empty_search", f"Search returned no results for URL: {url}"

    return None, ""   # Page looks fine — safe to parse
