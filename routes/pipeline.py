"""
Route: POST /api/pipeline — Full pipeline (cào → classify → viết bài)
"""

from fastapi import APIRouter, BackgroundTasks
from models.schemas import PipelineRequest, PipelineResponse, SiteResult

import sys
import os
import time
import json
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper import MultiLevelScraper, ScraperConfig
from core.content_extractor import AIContentExtractor

router = APIRouter()

# Store pipeline results (in-memory)
pipeline_jobs = {}


def _run_pipeline_sync(job_id: str, req_dict: dict):
    """Background task: chạy full pipeline"""
    urls = req_dict['urls']
    max_depth = req_dict.get('max_depth', 2)
    max_pages = req_dict.get('max_pages', 30)
    ai_base_url = req_dict.get('ai_base_url', 'https://content.scapbot.net/v1')
    ai_model = req_dict.get('ai_model', 'default')
    ai_api_key = req_dict.get('ai_api_key', 'd3f230c4fb86d327b79d18790e0d91df')
    website_workers = req_dict.get('website_workers', 3)
    analyze_workers = req_dict.get('analyze_workers', 5)
    
    output_dir = Path("output") / f"pipeline_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    extractor = AIContentExtractor(
        api_key=ai_api_key,
        base_url=ai_base_url,
        model=ai_model,
        max_workers=analyze_workers
    )
    
    results = []
    total_articles = 0
    
    def process_site(url: str, site_idx: int):
        """Xử lý 1 website"""
        domain = urlparse(url).netloc.replace("www.", "")
        domain_safe = domain.replace(".", "_")
        site_dir = output_dir / domain_safe
        site_dir.mkdir(exist_ok=True)
        
        site_result = SiteResult(url=url, domain=domain)
        
        try:
            # 1. CRAWL
            config = ScraperConfig(
                max_depth=max_depth,
                max_pages=max_pages,
                delay_between_requests=0.3
            )
            scraper = MultiLevelScraper(url, config)
            pages = scraper.crawl()
            
            if not pages:
                site_result.errors.append("No pages crawled")
                return site_result
            
            site_result.pages_crawled = len(pages)
            
            # 2. PREPARE DATA
            pages_metadata = []
            pages_full = {}
            for p in pages:
                sd = p.structured if hasattr(p, 'structured') else None
                meta = {
                    'url': p.url,
                    'title': p.title or '',
                    'meta_description': p.meta_description or '',
                    'structured': {
                        'jsonld_type': getattr(sd, 'jsonld_type', '') if sd else '',
                        'jsonld_name': getattr(sd, 'jsonld_name', '') if sd else '',
                        'jsonld_price': getattr(sd, 'jsonld_price', '') if sd else '',
                        'has_price': getattr(sd, 'has_price', False) if sd else False,
                        'breadcrumb': getattr(sd, 'breadcrumb', []) if sd else [],
                        'breadcrumb_depth': getattr(sd, 'breadcrumb_depth', 0) if sd else 0,
                        'og_type': getattr(sd, 'og_type', '') if sd else '',
                    }
                }
                pages_metadata.append(meta)
                pages_full[p.url] = p
            
            # 3. CLASSIFY
            classify_results = extractor.batch_classify_pages(pages_metadata)
            
            # 4. FILTER PRODUCTS
            products = []
            for r in classify_results:
                cat = r.get('category', '').upper()
                if cat == 'PRODUCT':
                    url_key = r.get('url', '')
                    if url_key in pages_full:
                        products.append({
                            'page': pages_full[url_key],
                            'classify': r
                        })
            
            site_result.products_found = len(products)
            
            # 5. WRITE ARTICLES
            articles_ok = 0
            for pi, prod in enumerate(products):
                p = prod['page']
                cr = prod['classify']
                p_name = cr.get('product_name', '') or (p.title or '')[:60]
                
                # Build raw content
                raw_parts = [f"URL: {p.url}", f"Title: {p.title or ''}"]
                if p.headings:
                    raw_parts.append("Headings: " + " | ".join(p.headings[:10]))
                if p.paragraphs:
                    raw_parts.append("Nội dung:")
                    for pp in p.paragraphs:
                        if len(pp) > 30:
                            raw_parts.append(pp)
                
                raw_content = "\n".join(raw_parts)
                
                try:
                    # AI: Analyze
                    product_info = extractor.analyze_product(raw_content)
                    if not product_info:
                        continue
                    
                    # AI: Write article
                    images = [img.url for img in p.images] if hasattr(p, 'images') and p.images else []
                    article = extractor.create_article(product_info, raw_content, images)
                    
                    if not article or article.startswith("Lỗi"):
                        continue
                    
                    # AI: Media prompts
                    media = {}
                    try:
                        media = extractor.generate_media_prompts(product_info)
                    except Exception:
                        pass
                    
                    # Save
                    import re
                    safe_name = "".join([c for c in p_name if c.isalnum() or c in ' _-']).strip()
                    safe_name = safe_name.replace(" ", "_").lower()[:60]
                    blog_file = site_dir / f"{safe_name}.md"
                    
                    with open(blog_file, 'w', encoding='utf-8') as f:
                        f.write(f"# {p_name}\n\n")
                        f.write(f"**URL gốc:** {p.url}\n\n")
                        f.write(article)
                        if media:
                            f.write("\n\n---\n## Media Prompts\n\n")
                            for k, v in media.items():
                                f.write(f"**{k}:** {v}\n\n")
                    
                    articles_ok += 1
                
                except Exception as e:
                    site_result.errors.append(f"Product {pi}: {str(e)[:80]}")
            
            site_result.articles_written = articles_ok
        
        except Exception as e:
            site_result.errors.append(str(e)[:200])
        
        return site_result
    
    # Process sites in parallel
    with ThreadPoolExecutor(max_workers=website_workers) as executor:
        futures = {executor.submit(process_site, url, i): url for i, url in enumerate(urls)}
        for future in as_completed(futures):
            try:
                site_result = future.result()
                results.append(site_result)
                total_articles += site_result.articles_written
            except Exception as e:
                url = futures[future]
                results.append(SiteResult(url=url, errors=[str(e)]))
    
    # Save results
    pipeline_jobs[job_id] = PipelineResponse(
        status="completed",
        total_sites=len(urls),
        total_articles=total_articles,
        sites=results,
        output_dir=str(output_dir)
    )


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    """
    Full pipeline: Cào → Classify → Viết bài cho nhiều websites.
    Chạy background, trả về job_id để theo dõi.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]
    
    pipeline_jobs[job_id] = PipelineResponse(
        status="processing",
        total_sites=len(req.urls)
    )
    
    background_tasks.add_task(_run_pipeline_sync, job_id, req.model_dump())
    
    return PipelineResponse(
        status="processing",
        total_sites=len(req.urls),
        output_dir=f"job:{job_id}"
    )


@router.get("/pipeline/{job_id}", response_model=PipelineResponse)
async def get_pipeline_status(job_id: str):
    """Kiểm tra trạng thái pipeline job"""
    if job_id not in pipeline_jobs:
        return PipelineResponse(status="not_found", error=f"Job {job_id} not found")
    return pipeline_jobs[job_id]
