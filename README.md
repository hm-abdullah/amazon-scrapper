# 🛒 Amazon Product Scraper & AI Analytics Dashboard

A production-grade, full-stack Amazon product scraping and analytics system built with **Scrapy**, **Playwright**, **FastAPI**, **React (Vite + TailwindCSS)**, and **Google Gemini LLM**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?logo=fastapi)
![Scrapy](https://img.shields.io/badge/Scrapy-2.11%2B-orange?logo=scrapy)
![React](https://img.shields.io/badge/React-19.0-61DAFB?logo=react)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-v4-38B2AC?logo=tailwindcss)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-1.5%2F3.1_Flash-8E44AD?logo=google)

---

## ✨ Features

- 🛡️ **Anti-Bot Bypass & Stealth**: Browser fingerprint masking (JA3 TLS, Chromium automation flag removal, randomized viewports, human behavior emulation).
- 🔄 **Real-Time WebSockets**: Live progress streaming, live ASIN tracking, and real-time status metrics broadcast to the frontend.
- 🤖 **LLM Data Extraction**: Automated post-crawl attribute enrichment (category classification, tech specs, booleans) using **Gemini API** or **OpenAI**.
- 📊 **Analytics Dashboard**: Interactive Recharts metrics showing rating distributions, price ranges, and top brand statistics.
- 💾 **SQLite Storage & CSV Exports**: Instant export of raw scraped products and AI-enriched attributes into clean CSV files.
- 🗑️ **Dangerous Action Modal**: Safe database clearing backed by GitHub-style confirmation verification.

---

## 📁 Repository Structure

```text
amazon-scraper/
├── backend/                  # FastAPI Web Backend & WebSocket Server
│   ├── app/
│   │   ├── main.py           # REST API endpoints & WS handlers
│   │   ├── database.py       # Async SQLite CRUD interface
│   │   ├── scraper_runner.py # Subprocess runner for Scrapy & AI
│   │   └── websocket_manager.py # Broadcast manager
│   └── requirements.txt      # Backend Python dependencies
│
├── scrapers/                 # Scrapy + Playwright Crawler & AI Layer
│   ├── amazon_scraper/
│   │   ├── spiders/          # Production spider logic
│   │   ├── pipelines.py      # SQLite storage & validation pipeline
│   │   ├── middlewares.py    # Proxy rotation middleware
│   │   └── utils/
│   │       ├── ai_extractor.py # Gemini/OpenAI enrichment layer
│   │       └── extractors.py   # HTML parsing helpers
│   ├── config.yaml           # Crawler settings & target URLs
│   ├── run.py                # CLI runner script
│   └── .env                  # Environment variables (API Keys)
│
└── frontend/                 # React 19 + Vite Dashboard
    ├── src/
    │   ├── components/       # UI Components (Form, Table, Charts, AI)
    │   ├── lib/              # API Client & WebSockets hook
    │   └── App.tsx           # Main Dashboard Application
    └── package.json
```

---

## 📋 Prerequisites

Ensure you have the following installed on your system:

- **Python**: `3.10+`
- **Node.js**: `18.0+`
- **Package Manager**: `pnpm` (or `npm`)
- **Gemini API Key**: Get a free API key from [Google AI Studio](https://aistudio.google.com/)

---

## ⚡ Quick Start Guide

### 1. Configure Environment Variables

Create a `.env` file inside the `scrapers/` folder:

```bash
# In scrapers/.env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 2. Setup Backend & Scraper (Python)

Create and activate a virtual environment, then install dependencies:

```bash
# Create virtual environment
python -m venv backend/.venv

# Activate (Windows PowerShell)
.\backend\.venv\Scripts\Activate.ps1
# Activate (macOS/Linux)
source backend/.venv/bin/activate

# Install dependencies & Playwright browsers
pip install fastapi uvicorn[standard] websockets aiosqlite pydantic scrapy scrapy-playwright google-generativeai pyyaml
playwright install chromium
```

### 3. Setup Frontend (React)

Open a new terminal tab and install frontend dependencies:

```bash
cd frontend
pnpm install
```

---

## 🚀 Running the Application

### Option A: Run Full Stack (Backend + Frontend)

1. **Start the FastAPI Backend** (Terminal 1):
   ```bash
   # From root directory
   backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
   ```
   *Backend API runs at `http://localhost:8000`*

2. **Start the React Frontend** (Terminal 2):
   ```bash
   cd frontend
   pnpm dev
   ```
   *Dashboard runs at `http://localhost:5173`*

Open `http://localhost:5173` in your browser to access the dashboard!

---

### Option B: Run Scraper via CLI (Standalone)

You can also run the crawler directly from the command line without the web server:

```bash
# Scrape 50 products using config.yaml targets
python scrapers/run.py --max-products 50

# Run AI extraction on existing scraped database
python scrapers/run.py --ai-only
```

---

## ⚙️ Configuration (`scrapers/config.yaml`)

Customize target URLs, concurrency, download delays, and AI provider settings:

```yaml
search_urls:
  - "https://www.amazon.com/s?k=gaming+headset"
  - "https://www.amazon.com/s?k=gaming+mouse"

max_pages: 2
max_products: 50
concurrency: 2
download_delay: 3.0

ai_extraction:
  enabled: false
  provider: "gemini"
  model: "gemini-3.1-flash-lite"
  max_products: 50
```

---

## 📊 Exports & Data Output

- **SQLite Database**: Stored automatically at `scrapers/storage/scraper.db`.
- **Product CSV Export**: Downloadable via the frontend dashboard or API endpoint (`/api/export/csv`).
- **AI Enriched CSV Export**: Downloadable via the dashboard (`/api/export/ai-csv`).

---

## 🛡️ License

Distributed under the MIT License.
