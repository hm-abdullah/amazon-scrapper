"""Quick validation script — checks all imports, config, and checkpoint."""
import sys
sys.path.insert(0, ".")

import amazon_scraper.items as items
import amazon_scraper.pipelines as pipelines
import amazon_scraper.middlewares as middlewares
import amazon_scraper.proxy_manager as pm
import amazon_scraper.utils.page_detector as pd
import amazon_scraper.utils.extractors as ex
import amazon_scraper.utils.ai_extractor as ai
from amazon_scraper.spiders.production_spider import ProductionSpider, _load_config, _load_checkpoint

# Check config loads
config = _load_config()
print("Config loaded:")
print(f"  search_urls:    {len(config['search_urls'])} URLs")
print(f"  max_products:   {config['max_products']}")
print(f"  max_pages:      {config['max_pages']}")
print(f"  concurrency:    {config['concurrency']}")
print(f"  download_delay: {config['download_delay']}")
print(f"  proxies:        {len(config.get('proxies', []))} proxies")

# Check checkpoint loads
asins = _load_checkpoint()
print(f"  checkpoint:     {len(asins)} ASINs already processed")

# Verify spider class
print(f"  spider name:    {ProductionSpider.name}")

# Check output files exist
from pathlib import Path
output_dir = Path(config.get("output_dir", "output"))
for fname in ["products.jsonl", "products.csv", "failed_products.jsonl"]:
    fpath = output_dir / fname
    if fpath.exists():
        size = fpath.stat().st_size
        lines = sum(1 for _ in open(fpath, "r", encoding="utf-8") if _.strip())
        print(f"  {fname}: {lines} lines ({size} bytes)")
    else:
        print(f"  {fname}: does not exist yet")

print()
print("ALL IMPORTS + CONFIG OK")
