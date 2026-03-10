"""
ScrapBot API — FastAPI REST Server
===================================
Tool cào data dạng API, test bằng Postman.

Chạy:
    cd d:\cào data\scraper-api
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000

Docs: http://localhost:8000/docs
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import sys

# Force UTF-8 encoding on Windows (tranh loi charmap khi print tieng Viet)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure core modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.auth import verify_api_key
from routes.scrape import router as scrape_router
from routes.multi_scrape import router as multi_scrape_router
from routes.pipeline import router as pipeline_router
from routes.content_write import router as content_write_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ScrapBot] API starting...")
    print("[ScrapBot] Docs: http://localhost:8000/docs")
    yield
    print("[ScrapBot] API shutting down")


app = FastAPI(
    title="ScrapBot API",
    description="""
## 🤖 ScrapBot REST API

Tool cào data và tạo bài viết tự động.

### Endpoints:
- **POST /api/scrape** — Cào 1 website
- **POST /api/classify** — Phân loại trang (product/category/other)
- **POST /api/analyze-product** — Phân tích 1 trang sản phẩm
- **POST /api/generate-article** — Tạo bài viết marketing
- **POST /api/pipeline** — Full pipeline (cào → classify → viết bài)
- **GET /api/pipeline/{job_id}** — Kiểm tra trạng thái pipeline
- **POST /api/content-write** — 4-factor pipeline (keyword + URL + backlink type + language → bài viết)
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS — cho phép Postman và mọi origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes — tất cả /api/* yêu cầu X-API-Key
_auth = [Depends(verify_api_key)]
app.include_router(scrape_router, prefix="/api", tags=["Scraping"], dependencies=_auth)
app.include_router(multi_scrape_router, prefix="/api", tags=["AI Processing"], dependencies=_auth)
app.include_router(pipeline_router, prefix="/api", tags=["Pipeline"], dependencies=_auth)
app.include_router(content_write_router, prefix="/api", tags=["Content Write"], dependencies=_auth)


@app.get("/")
async def root():
    return {
        "name": "ScrapBot API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "POST /api/scrape",
            "POST /api/classify",
            "POST /api/analyze-product",
            "POST /api/generate-article",
            "POST /api/pipeline",
            "GET /api/pipeline/{job_id}"
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
