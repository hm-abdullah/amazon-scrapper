from fastapi import FastAPI

app = FastAPI(title="Amazon Scraper API")

@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Amazon Scraper API is running"}
