# run.py — CLI entry point for the production Amazon scraper.
#
# Usage:
#   python run.py                          # Start or resume a crawl
#   python run.py --fresh                  # Ignore checkpoint, start from scratch
#   python run.py --ai-only               # Only run AI extraction on existing data
#   python run.py --config path/to/c.yaml  # Use a different config file
#
# The script loads config.yaml, adjusts Scrapy settings accordingly,
# then runs the production_spider using Scrapy's CrawlerProcess.

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Fix Windows Python 3.12 asyncio Proactor event loop assertion errors with Twisted/Playwright
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Production Amazon Product Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                   Start (or resume) scraping
  python run.py --fresh           Clear checkpoint and scrape from scratch
  python run.py --ai-only         Run AI extraction on existing products.jsonl
  python run.py --config prod.yaml  Use a different config file
        """
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore the ASIN checkpoint and re-scrape everything",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Skip scraping — only run AI extraction on existing products.jsonl",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    return parser.parse_args()


# ── Config loading ────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Load and return the YAML config. Exits with a message if missing."""
    path = Path(config_path)
    if not path.exists():
        print(f"[ERROR] Config file not found: {path.resolve()}")
        print("  Create one by copying config.yaml.example or editing config.yaml")
        sys.exit(1)
    try:
        import yaml
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[ERROR] Could not parse {path}: {e}")
        sys.exit(1)


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def clear_checkpoint() -> None:
    """Delete the ASIN checkpoint file so the run starts from scratch."""
    checkpoint = Path("amazon_scraper/storage/processed_asins.json")
    if checkpoint.exists():
        checkpoint.unlink()
        print("[INFO] Checkpoint cleared — starting fresh run")
    else:
        print("[INFO] No checkpoint found — will start fresh anyway")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Set up basic logging so run.py output is readable
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Silence verbose DEBUG/noise logs from third-party libraries
    logging.getLogger("scrapy-playwright").setLevel(logging.INFO)
    logging.getLogger("playwright").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    config = load_config(args.config)

    # ── AI-only mode ──────────────────────────────────────────────────────────
    if args.ai_only:
        ai_cfg = config.get("ai_extraction", {})
        if not ai_cfg.get("enabled", False) and not ai_cfg.get("api_key"):
            print("[WARN] AI extraction is disabled or missing api_key in config.yaml")
            print("       Set ai_extraction.enabled: true and provide api_key to use this mode")
            sys.exit(0)

        from amazon_scraper.utils.ai_extractor import run_ai_extraction
        output_dir = Path(config.get("output_dir", "output"))
        print(f"[INFO] Running AI extraction on {output_dir / 'products.jsonl'}")
        run_ai_extraction(config, output_dir)
        sys.exit(0)

    # ── Fresh run: clear checkpoint ───────────────────────────────────────────
    if args.fresh:
        clear_checkpoint()

    # ── Ensure storage and output directories exist ───────────────────────────
    Path("amazon_scraper/storage").mkdir(parents=True, exist_ok=True)
    Path(config.get("output_dir", "output")).mkdir(parents=True, exist_ok=True)

    # ── Build Scrapy custom_settings from config ──────────────────────────────
    # We override only the values that config.yaml controls.
    # All playwright stealth settings stay as defined in settings.py.
    custom_settings = {
        "LOG_LEVEL": "INFO",
        "CONCURRENT_REQUESTS": config.get("concurrency", 1),
        "CONCURRENT_REQUESTS_PER_DOMAIN": config.get("concurrency", 1),
        "DOWNLOAD_DELAY": config.get("download_delay", 3.0),
        "DOWNLOAD_TIMEOUT": config.get("timeout_seconds", 90),
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": config.get("timeout_seconds", 90) * 1000,
        "RETRY_TIMES": config.get("retry_count", 3),
        "CONFIG_FILE": args.config,
    }

    # ── Run the spider ────────────────────────────────────────────────────────
    # CrawlerProcess reads settings.py automatically (via scrapy.cfg / BOT_NAME)
    # then we layer custom_settings on top.
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    settings = get_project_settings()
    settings.update(custom_settings)

    # Adjust max contexts to fit the proxy pool
    num_proxies = len(config.get("proxies", []))
    if num_proxies > 0:
        # 1 default context + 1 per proxy
        settings["PLAYWRIGHT_MAX_CONTEXTS"] = num_proxies + 1
        print(f"[INFO] Proxy pool: {num_proxies} proxies → {num_proxies + 1} browser contexts")

    print("[INFO] Run started")
    print(f"[INFO] Target: {config.get('max_products', 1000)} products "
          f"across {len(config.get('search_urls', []))} search URL(s)")
    print(f"[INFO] Output directory: {Path(config.get('output_dir', 'output')).resolve()}")

    process = CrawlerProcess(settings)
    process.crawl("production_spider")
    process.start()   # Blocks until the spider finishes

    # ── Post-crawl AI extraction ──────────────────────────────────────────────
    ai_cfg = config.get("ai_extraction", {})
    if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
        print("\n[INFO] Starting AI extraction layer...")
        from amazon_scraper.utils.ai_extractor import run_ai_extraction
        output_dir = Path(config.get("output_dir", "output"))
        run_ai_extraction(config, output_dir)

    print("\n[INFO] Run completed")
    print(f"       Products: {Path(config.get('output_dir','output')) / 'products.jsonl'}")
    print(f"       Failed:   {Path(config.get('output_dir','output')) / 'failed_products.jsonl'}")
    print(f"       Stats:    {Path(config.get('output_dir','output')) / 'run_metadata.json'}")


if __name__ == "__main__":
    main()
