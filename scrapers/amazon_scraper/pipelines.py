# Scrapy item processing pipelines for deduplication, validation, output, and SQLite storage.

import csv
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from itemadapter import ItemAdapter
from amazon_scraper.items import ProductDetailItem, FailedItem, SearchResultItem

logger = logging.getLogger(__name__)

class DeduplicationPipeline:
    CHECKPOINT_FILE = Path(__file__).parent / "storage" / "processed_asins.json"

    def open_spider(self, spider):
        self.seen_asins: set = self._load_checkpoint(spider)
        self._item_count = 0
        logger.info("[Dedup] Loaded %d processed ASINs from checkpoint", len(self.seen_asins))

    def close_spider(self, spider):
        self._save_checkpoint()

    def process_item(self, item, spider):
        if not isinstance(item, ProductDetailItem):
            return item

        asin = item.asin
        if not asin:
            return item

        if asin in self.seen_asins:
            logger.debug("[Dedup] Dropping duplicate ASIN: %s", asin)
            from scrapy.exceptions import DropItem
            raise DropItem(f"Duplicate ASIN: {asin}")

        self.seen_asins.add(asin)
        self._item_count += 1

        if self._item_count % 10 == 0:
            self._save_checkpoint()

        return item

    def _load_checkpoint(self, spider=None) -> set:
        seen = set()
        try:
            db_path = Path(__file__).resolve().parent.parent / "storage" / "scraper.db"
            if db_path.exists():
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT asin FROM products WHERE asin IS NOT NULL")
                rows = cursor.fetchall()
                seen.update(r[0] for r in rows if r[0])
                conn.close()
        except Exception as e:
            logger.warning("[Dedup] Could not load checkpoint from SQLite DB: %s", e)

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

class ValidationPipeline:
    def process_item(self, item, spider):
        if not isinstance(item, ProductDetailItem):
            return item

        adapter = ItemAdapter(item)

        if not item.asin:
            return self._to_failed(item, "missing_asin", "Product has no ASIN")

        if not item.title:
            return self._to_failed(item, "missing_title", f"ASIN {item.asin} has no title")

        if item.price is not None:
            try:
                item.price = float(item.price)
            except (TypeError, ValueError):
                item.price = None

        if item.rating is not None:
            try:
                r = float(item.rating)
                item.rating = round(r, 1) if 0 <= r <= 5 else None
            except (TypeError, ValueError):
                item.rating = None

        if item.review_count is not None:
            try:
                item.review_count = int(item.review_count)
            except (TypeError, ValueError):
                item.review_count = None

        if not item.scraped_at:
            item.scraped_at = datetime.now(timezone.utc).isoformat()

        return item

    @staticmethod
    def _to_failed(item: ProductDetailItem, failure_type: str, message: str) -> FailedItem:
        logger.warning("[Validation] %s → %s", failure_type, message)
        return FailedItem(
            url=item.product_url,
            asin=item.asin,
            timestamp=datetime.now(timezone.utc).isoformat(),
            failure_type=failure_type,
            failure_message=message,
            retry_count=0,
        )

class OutputPipeline:
    CSV_FIELDS = [
        "asin", "brand", "title", "seller", "price", "currency",
        "availability", "rating", "review_count", "product_url", "scraped_at",
    ]

    def open_spider(self, spider):
        output_dir = Path(getattr(spider, "output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        self._jsonl_file = open(output_dir / "products.jsonl", "a", encoding="utf-8")
        self._search_results_file = open(output_dir / "search_results.jsonl", "a", encoding="utf-8")
        self._failed_file = open(output_dir / "failed_products.jsonl", "a", encoding="utf-8")

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

class RunMetadataPipeline:
    def open_spider(self, spider):
        self._start_time = datetime.now(timezone.utc)
        self._pages_visited = 0
        self._products_discovered = 0
        self._products_scraped = 0
        self._products_failed = 0
        self._processing_times = []

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
        if isinstance(item, SearchResultItem):
            self._products_discovered += 1
        elif isinstance(item, ProductDetailItem):
            self._products_scraped += 1
            t = getattr(item, "_processing_time", None)
            if t:
                self._processing_times.append(t)
            logger.info("[INFO] Product scraped: %s", item.asin)
        elif isinstance(item, FailedItem):
            self._products_failed += 1
            logger.warning("[WARN] Product failed: %s — %s", item.asin, item.failure_type)

        return item

    def increment_pages(self) -> None:
        self._pages_visited += 1

class SQLitePipeline:
    def open_spider(self, spider):
        db_path = Path(__file__).resolve().parent.parent / 'storage' / 'scraper.db'
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT UNIQUE NOT NULL,
                brand TEXT,
                title TEXT,
                seller TEXT,
                price REAL,
                currency TEXT,
                availability TEXT,
                description TEXT,
                bullet_points TEXT,
                specifications TEXT,
                images TEXT,
                rating REAL,
                review_count INTEGER,
                product_url TEXT,
                scraped_at TEXT,
                run_id TEXT
            );

            CREATE TABLE IF NOT EXISTS failed_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                asin TEXT,
                timestamp TEXT,
                failure_type TEXT,
                failure_message TEXT,
                retry_count INTEGER DEFAULT 0,
                run_id TEXT
            );

            CREATE TABLE IF NOT EXISTS scrape_runs (
                id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                max_products INTEGER,
                target_urls TEXT,
                products_scraped INTEGER DEFAULT 0,
                products_failed INTEGER DEFAULT 0,
                products_discovered INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT
            );
        ''')
        self.conn.commit()
        
        self.run_id = getattr(spider, 'run_id', None) or spider.settings.get('RUN_ID') or str(uuid.uuid4())
        self._scraped_count = 0
        self._failed_count = 0
        
        max_products = getattr(spider, 'max_products', None)
        search_urls = getattr(spider, 'search_urls', [])
        
        try:
            self.cursor.execute("SELECT id FROM scrape_runs WHERE id = ?", (self.run_id,))
            if self.cursor.fetchone():
                self.cursor.execute('''
                    UPDATE scrape_runs
                    SET status = 'running', max_products = COALESCE(?, max_products), target_urls = COALESCE(?, target_urls)
                    WHERE id = ?
                ''', (max_products, json.dumps(search_urls) if search_urls else None, self.run_id))
            else:
                self.cursor.execute('''
                    INSERT INTO scrape_runs (id, status, max_products, target_urls, started_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    self.run_id, 
                    'running', 
                    max_products, 
                    json.dumps(search_urls), 
                    datetime.now(timezone.utc).isoformat()
                ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"[SQLite] Failed to insert/update scrape_run: {e}")

    def close_spider(self, spider):
        try:
            self.cursor.execute('''
                UPDATE scrape_runs
                SET status = 'completed', completed_at = ?, products_scraped = ?, products_failed = ?
                WHERE id = ?
            ''', (datetime.now(timezone.utc).isoformat(), self._scraped_count, self._failed_count, self.run_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"[SQLite] Failed to update scrape_run: {e}")
        finally:
            self.conn.close()

    def process_item(self, item, spider):
        try:
            if isinstance(item, ProductDetailItem):
                adapter = ItemAdapter(item)
                
                bullet_points = json.dumps(adapter.get('bullet_points', []))
                specifications = json.dumps(adapter.get('specifications', {}))
                images = json.dumps(adapter.get('images', []))
                
                self.cursor.execute('''
                    INSERT OR IGNORE INTO products (
                        asin, brand, title, seller, price, currency, availability, 
                        description, bullet_points, specifications, images, rating, 
                        review_count, product_url, scraped_at, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    adapter.get('asin'), adapter.get('brand'), adapter.get('title'),
                    adapter.get('seller'), adapter.get('price'), adapter.get('currency'),
                    adapter.get('availability'), adapter.get('description'), bullet_points,
                    specifications, images, adapter.get('rating'), adapter.get('review_count'),
                    adapter.get('product_url'), adapter.get('scraped_at'), self.run_id
                ))
                
                self._scraped_count += 1
                self.cursor.execute('''
                    UPDATE scrape_runs SET products_scraped = ? WHERE id = ?
                ''', (self._scraped_count, self.run_id))
                self.conn.commit()
                
            elif isinstance(item, FailedItem):
                adapter = ItemAdapter(item)
                self.cursor.execute('''
                    INSERT INTO failed_products (
                        url, asin, timestamp, failure_type, failure_message, retry_count, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    adapter.get('url'), adapter.get('asin'), adapter.get('timestamp'),
                    adapter.get('failure_type'), adapter.get('failure_message'),
                    adapter.get('retry_count', 0), self.run_id
                ))
                
                self._failed_count += 1
                self.cursor.execute('''
                    UPDATE scrape_runs SET products_failed = ? WHERE id = ?
                ''', (self._failed_count, self.run_id))
                self.conn.commit()
                
            elif isinstance(item, SearchResultItem):
                self.cursor.execute('''
                    UPDATE scrape_runs SET products_discovered = products_discovered + 1 WHERE id = ?
                ''', (self.run_id,))
                self.conn.commit()
                
        except Exception as e:
            logger.error(f"[SQLite] Failed to process item: {e}")
            
        return item
