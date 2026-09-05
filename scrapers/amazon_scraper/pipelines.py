# pipelines.py — Production Scrapy item pipelines.
#
# Pipeline execution order (set in settings.py):
#   100 → DeduplicationPipeline  (drop duplicates early)
#   200 → ValidationPipeline     (normalize + validate fields)
#   300 → OutputPipeline         (write to files)
#   400 → RunMetadataPipeline    (track stats, write run_metadata.json)
#
# Each pipeline is self-contained and fails gracefully.

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from itemadapter import ItemAdapter

from amazon_scraper.items import ProductDetailItem, FailedItem, SearchResultItem

logger = logging.getLogger(__name__)


# ── 1. Deduplication ──────────────────────────────────────────────────────────

class DeduplicationPipeline:
    """
    Drops duplicate ProductDetailItems based on ASIN.

    Maintains an in-memory set (fast) and also persists it to
    storage/processed_asins.json so that resuming a run skips
    already-scraped products.
    """

    CHECKPOINT_FILE = Path(__file__).parent / "storage" / "processed_asins.json"

    def open_spider(self, spider):
        # Load previously processed ASINs from disk & existing products.jsonl
        self.seen_asins: set = self._load_checkpoint(spider)
        self._item_count = 0
        logger.info("[Dedup] Loaded %d processed ASINs from checkpoint", len(self.seen_asins))

    def close_spider(self, spider):
        self._save_checkpoint()

    def process_item(self, item, spider):
        # Only deduplicate full product items; pass everything else through
        if not isinstance(item, ProductDetailItem):
            return item

        asin = item.asin
        if not asin:
            return item   # Can't deduplicate without ASIN

        if asin in self.seen_asins:
            logger.debug("[Dedup] Dropping duplicate ASIN: %s", asin)
            from scrapy.exceptions import DropItem
            raise DropItem(f"Duplicate ASIN: {asin}")

        self.seen_asins.add(asin)
        self._item_count += 1

        # Periodically save checkpoint to disk every 10 items for live visibility
        if self._item_count % 10 == 0:
            self._save_checkpoint()

        return item

    def _load_checkpoint(self, spider=None) -> set:
        seen = set()
        # 1. Read storage/processed_asins.json if it exists
        try:
            if self.CHECKPOINT_FILE.exists():
                with open(self.CHECKPOINT_FILE, "r") as f:
                    data = json.load(f)
                    seen.update(data.get("processed_asins", []))
        except Exception as e:
            logger.warning("[Dedup] Could not load checkpoint file: %s", e)

        # 2. Also read output/products.jsonl if it exists (live fallback)
        try:
            output_dir = Path(getattr(spider, "output_dir", "output")) if spider else Path("output")
            products_file = output_dir / "products.jsonl"
            if products_file.exists():
                with open(products_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                obj = json.loads(line)
                                if obj.get("asin"):
                                    seen.add(obj["asin"])
                            except Exception:
                                pass
        except Exception as e:
            logger.warning("[Dedup] Could not read products.jsonl for checkpoint fallback: %s", e)

        return seen

    def _save_checkpoint(self) -> None:
        try:
            self.CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CHECKPOINT_FILE, "w") as f:
                json.dump({
                    "processed_asins": list(self.seen_asins),
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
        except Exception as e:
            logger.warning("[Dedup] Could not save checkpoint: %s", e)


# ── 2. Validation & Normalization ─────────────────────────────────────────────

class ValidationPipeline:
    """
    Validates required fields and normalizes data types.

    On validation failure: converts the ProductDetailItem into a
    FailedItem so the failure is recorded — the item is NOT dropped,
    just converted. This lets the OutputPipeline write it to failed_products.jsonl.
    """

    def process_item(self, item, spider):
        # Only validate full product items
        if not isinstance(item, ProductDetailItem):
            return item

        adapter = ItemAdapter(item)

        # --- Required field check ---
        if not item.asin:
            return self._to_failed(item, "missing_asin", "Product has no ASIN")

        if not item.title:
            return self._to_failed(item, "missing_title", f"ASIN {item.asin} has no title")

        # --- Price normalization ---
        # Price is already a float from extractor, but double-check
        if item.price is not None:
            try:
                item.price = float(item.price)
            except (TypeError, ValueError):
                item.price = None

        # --- Rating normalization ---
        # Should be a float between 0–5
        if item.rating is not None:
            try:
                r = float(item.rating)
                item.rating = round(r, 1) if 0 <= r <= 5 else None
            except (TypeError, ValueError):
                item.rating = None

        # --- Review count normalization ---
        # Should be a non-negative integer
        if item.review_count is not None:
            try:
                item.review_count = int(item.review_count)
            except (TypeError, ValueError):
                item.review_count = None

        # --- Ensure scraped_at is set ---
        if not item.scraped_at:
            item.scraped_at = datetime.now(timezone.utc).isoformat()

        return item

    @staticmethod
    def _to_failed(item: ProductDetailItem, failure_type: str, message: str) -> FailedItem:
        """Convert a ProductDetailItem to a FailedItem for failure tracking."""
        logger.warning("[Validation] %s → %s", failure_type, message)
        return FailedItem(
            url=item.product_url,
            asin=item.asin,
            timestamp=datetime.now(timezone.utc).isoformat(),
            failure_type=failure_type,
            failure_message=message,
            retry_count=0,
        )


# ── 3. Output ─────────────────────────────────────────────────────────────────

class OutputPipeline:
    """
    Writes items to disk:
      - ProductDetailItem → output/products.jsonl  (append)
      - ProductDetailItem → output/products.csv    (append)
      - SearchResultItem  → output/search_results.jsonl (append)
      - FailedItem        → output/failed_products.jsonl (append)
    """

    # CSV column order — matches ProductDetailItem fields
    CSV_FIELDS = [
        "asin", "brand", "title", "seller", "price", "currency",
        "availability", "rating", "review_count", "product_url", "scraped_at",
    ]

    def open_spider(self, spider):
        # Resolve output directory from spider's config (set in settings.py)
        output_dir = Path(getattr(spider, "output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Open file handles (append mode so resume works)
        self._jsonl_file = open(output_dir / "products.jsonl", "a", encoding="utf-8")
        self._search_results_file = open(output_dir / "search_results.jsonl", "a", encoding="utf-8")
        self._failed_file = open(output_dir / "failed_products.jsonl", "a", encoding="utf-8")

        # CSV — write header only if file is new (empty)
        csv_path = output_dir / "products.csv"
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        self._csv_raw = open(csv_path, "a", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_raw, fieldnames=self.CSV_FIELDS, extrasaction="ignore"
        )
        if write_header:
            self._csv_writer.writeheader()

        logger.info("[Output] Writing to directory: %s", output_dir)

    def close_spider(self, spider):
        self._jsonl_file.close()
        self._search_results_file.close()
        self._failed_file.close()
        self._csv_raw.close()

    def process_item(self, item, spider):
        if isinstance(item, ProductDetailItem):
            self._write_product(item)

        elif isinstance(item, SearchResultItem):
            self._write_search_result(item)

        elif isinstance(item, FailedItem):
            self._write_failed(item)

        return item

    def _write_product(self, item: ProductDetailItem) -> None:
        row = ItemAdapter(item).asdict()
        self._jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._jsonl_file.flush()

        # CSV only gets the scalar fields (no lists/dicts)
        csv_row = {k: row.get(k) for k in self.CSV_FIELDS}
        self._csv_writer.writerow(csv_row)
        self._csv_raw.flush()

    def _write_search_result(self, item: SearchResultItem) -> None:
        row = ItemAdapter(item).asdict()
        self._search_results_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._search_results_file.flush()

    def _write_failed(self, item: FailedItem) -> None:
        row = ItemAdapter(item).asdict()
        self._failed_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._failed_file.flush()


# ── 4. Run Metadata ───────────────────────────────────────────────────────────

class RunMetadataPipeline:
    """
    Tracks statistics throughout the run and writes run_metadata.json
    when the spider closes.

    Stats tracked:
      - Start / end time
      - Search URLs
      - Pages visited
      - Products discovered (from search cards)
      - Products successfully scraped
      - Failed products
      - Retries performed
      - Average processing time per product
    """

    def open_spider(self, spider):
        self._start_time = datetime.now(timezone.utc)
        self._pages_visited = 0
        self._products_discovered = 0
        self._products_scraped = 0
        self._products_failed = 0
        self._processing_times = []   # List of seconds per product

        self._output_dir = Path(getattr(spider, "output_dir", "output"))
        self._search_urls = getattr(spider, "search_urls", [])

        logger.info("[INFO] Run started at %s", self._start_time.isoformat())

    def close_spider(self, spider):
        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - self._start_time).total_seconds()

        avg_time = (
            sum(self._processing_times) / len(self._processing_times)
            if self._processing_times else 0
        )

        metadata = {
            "run_start": self._start_time.isoformat(),
            "run_end": end_time.isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "search_urls": self._search_urls,
            "pages_visited": self._pages_visited,
            "products_discovered": self._products_discovered,
            "products_scraped": self._products_scraped,
            "products_failed": self._products_failed,
            "retries": spider.crawler.stats.get_value("retry/count", 0),
            "avg_processing_time_seconds": round(avg_time, 2),
            "proxy_stats": getattr(spider, "proxy_stats", {}),
        }

        self._output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self._output_dir / "run_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info("[INFO] Run completed — %d scraped, %d failed. Metadata: %s",
                    self._products_scraped, self._products_failed, metadata_path)

    def process_item(self, item, spider):
        import time

        if isinstance(item, SearchResultItem):
            self._products_discovered += 1

        elif isinstance(item, ProductDetailItem):
            self._products_scraped += 1
            # Track timing if spider set it on the item
            t = getattr(item, "_processing_time", None)
            if t:
                self._processing_times.append(t)
            logger.info("[INFO] Product scraped: %s", item.asin)

        elif isinstance(item, FailedItem):
            self._products_failed += 1
            logger.warning("[WARN] Product failed: %s — %s", item.asin, item.failure_type)

        return item

    def increment_pages(self) -> None:
        """Called by the spider after each search page is processed."""
        self._pages_visited += 1
