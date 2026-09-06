# CLI launcher for the production Amazon Scraper spider.

import argparse
import asyncio
import logging
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

def parse_args():
    parser = argparse.ArgumentParser(
        description="Production Amazon Product Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter
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
    parser.add_argument(
        "--max-products",
        type=int,
        default=None,
        help="Override config.yaml max_products",
    )
    parser.add_argument(
        "--urls",
        nargs='+',
        default=None,
        help="Override config.yaml search_urls",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID passed by backend runner",
    )
    return parser.parse_args()

def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"[ERROR] Config file not found: {path.resolve()}")
        sys.exit(1)
    try:
        import yaml
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[ERROR] Could not parse {path}: {e}")
        sys.exit(1)

def clear_checkpoint() -> None:
    checkpoint = Path(__file__).resolve().parent / "storage" / "processed_asins.json"
    if checkpoint.exists():
        checkpoint.unlink()
        print("[INFO] Checkpoint cleared — starting fresh run")
    else:
        print("[INFO] No checkpoint found — will start fresh anyway")

def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("scrapy-playwright").setLevel(logging.INFO)
    logging.getLogger("playwright").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    config = load_config(args.config)

    if args.max_products is not None:
        config['max_products'] = args.max_products
    if args.urls is not None:
        config['search_urls'] = args.urls

    if args.ai_only:
        from amazon_scraper.utils.ai_extractor import run_ai_extraction
        print("[INFO] Running AI extraction on products in SQLite database...")
        run_ai_extraction(config, run_id=args.run_id)
        sys.exit(0)

    if args.fresh:
        clear_checkpoint()

    storage_dir = Path(__file__).resolve().parent / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    Path(config.get("output_dir", "output")).mkdir(parents=True, exist_ok=True)

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
    if args.run_id:
        custom_settings["RUN_ID"] = args.run_id

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    settings = get_project_settings()
    settings.update(custom_settings)

    num_proxies = len(config.get("proxies", []))
    if num_proxies > 0:
        settings["PLAYWRIGHT_MAX_CONTEXTS"] = num_proxies + 1
        print(f"[INFO] Proxy pool: {num_proxies} proxies → {num_proxies + 1} browser contexts")

    print("[INFO] Run started")
    print(f"[INFO] Target: {config.get('max_products', 1000)} products "
          f"across {len(config.get('search_urls', []))} search URL(s)")
    print(f"[INFO] Output directory: {Path(config.get('output_dir', 'output')).resolve()}")

    process = CrawlerProcess(settings)
    process.crawl("production_spider", run_id=args.run_id)
    process.start()

    ai_cfg = config.get("ai_extraction", {})
    if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
        print("\n[INFO] Starting AI extraction layer...")
        from amazon_scraper.utils.ai_extractor import run_ai_extraction
        run_ai_extraction(config, run_id=args.run_id)

    print("\n[INFO] Run completed")

if __name__ == "__main__":
    main()
