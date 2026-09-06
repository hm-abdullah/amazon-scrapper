# FastAPI application endpoints and WebSocket server for Amazon Scraper.

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
import sys
import logging
import uuid
import asyncio
from typing import List, Optional
import json
import csv
import io

if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from . import database
from .websocket_manager import manager
from .scraper_runner import runner

logger = logging.getLogger("backend.main")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:3000', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await database.init_db()

class ScrapeRequest(BaseModel):
    max_products: int
    urls: List[str]

    @field_validator('max_products')
    @classmethod
    def max_products_valid(cls, v):
        if not 1 <= v <= 1000:
            raise ValueError('max_products must be between 1 and 1000')
        return v
        
    @field_validator('urls')
    @classmethod
    def urls_valid(cls, v):
        if not v:
            raise ValueError('urls list cannot be empty')
        if len(v) > 10:
            raise ValueError('maximum 10 urls allowed')
        for url in v:
            if not url.startswith('https://www.amazon.com/s'):
                raise ValueError('each url must start with https://www.amazon.com/s')
        return v

@app.post("/api/scrape/start")
async def start_scrape(req: ScrapeRequest):
    if runner.is_running:
        raise HTTPException(status_code=409, detail="Scraper is already running")
    run_id = str(uuid.uuid4())
    try:
        await runner.start(run_id, req.max_products, req.urls)
        return {"message": "Scraper started", "run_id": run_id}
    except Exception as e:
        logger.error(f"Failed to start scrape: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape/stop")
async def stop_scrape():
    if not runner.is_running:
        raise HTTPException(status_code=404, detail="Scraper is not running")
    try:
        await runner.stop()
        return {"message": "Scraper stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scrape/status")
async def get_status():
    status = runner.get_status()
    latest_run = await database.get_latest_run()
    return {
        "scraper_status": status,
        "latest_run": latest_run
    }

@app.get("/api/products")
async def get_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str = "",
    sort_by: str = "scraped_at",
    sort_dir: str = "desc",
    run_id: Optional[str] = None
):
    try:
        products = await database.get_products(page, per_page, search, sort_by, sort_dir, run_id)
        total = await database.get_product_count(search, run_id)
        return {
            "products": products,
            "page": page,
            "per_page": per_page,
            "total": total
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/csv")
async def export_csv(run_id: Optional[str] = None):
    try:
        products = await database.get_all_products_for_export(run_id)
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "ASIN", "Title", "Brand", "Seller", "Price", "Currency", 
            "Availability", "Rating", "Review Count", "Description", 
            "Bullet Points", "Specifications", "Images", "Product URL", "Scraped At", "Run ID"
        ])
        
        for p in products:
            writer.writerow([
                p.get("asin", ""),
                p.get("title", ""),
                p.get("brand", ""),
                p.get("seller", ""),
                p.get("price", ""),
                p.get("currency", ""),
                p.get("availability", ""),
                p.get("rating", ""),
                p.get("review_count", ""),
                p.get("description", ""),
                p.get("bullet_points", ""),
                p.get("specifications", ""),
                p.get("images", ""),
                p.get("product_url", ""),
                p.get("scraped_at", ""),
                p.get("run_id", "")
            ])
            
        filename = f"amazon_products_{run_id}.csv" if (run_id and run_id != "all") else "amazon_products_all.csv"
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/ai-csv")
async def export_ai_csv(run_id: Optional[str] = None):
    try:
        ai_rows = await database.get_all_ai_attributes_for_export(run_id)
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            "ASIN", "Category", "Extracted Attributes (JSON)", 
            "Extracted At", "Run ID", "Product Title", "Brand", "Price", "Rating"
        ])
        
        for r in ai_rows:
            writer.writerow([
                r.get("asin", ""),
                r.get("category", ""),
                r.get("attributes", ""),
                r.get("extracted_at", ""),
                r.get("run_id", ""),
                r.get("title", ""),
                r.get("brand", ""),
                r.get("price", ""),
                r.get("rating", "")
            ])
            
        filename = f"ai_attributes_{run_id}.csv" if (run_id and run_id != "all") else "ai_attributes_all.csv"
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error exporting AI CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/products/clear")
async def clear_database():
    if runner.is_running:
        raise HTTPException(status_code=409, detail="Cannot clear database while scraper is running")
    try:
        await database.clear_all_data()
        return {"message": "All database history cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/count")
async def get_product_count():
    try:
        count = await database.get_product_count()
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics")
async def get_metrics():
    try:
        metrics = await database.get_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/runs")
async def get_runs():
    try:
        async with database.get_db() as db:
            async with db.execute("SELECT * FROM scrape_runs ORDER BY started_at DESC") as cursor:
                rows = await cursor.fetchall()
                runs = []
                for r in rows:
                    d = dict(r)
                    d['target_urls'] = json.loads(d['target_urls']) if d.get('target_urls') else []
                    runs.append(d)
                return runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    try:
        run = await database.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/extract")
async def extract_ai(run_id: Optional[str] = Query(None)):
    if runner.is_running:
        raise HTTPException(status_code=409, detail="Scraper or AI task is already running")
    target_run_id = run_id if (run_id and run_id != "all") else None
    try:
        await runner.start_ai_extraction(target_run_id)
        return {"message": "AI Extraction started", "run_id": target_run_id or "all"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/status")
async def ai_status():
    status = runner.get_status()
    return status

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
