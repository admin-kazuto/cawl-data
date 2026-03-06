"""
Route: POST /api/scrape — Cào 1 website
"""

from fastapi import APIRouter, HTTPException
from models.schemas import ScrapeRequest, ScrapeResponse, PageResponse, ImageInfo, StructuredDataResponse

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper import MultiLevelScraper, ScraperConfig

router = APIRouter()


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_website(req: ScrapeRequest):
    """
    Cào nội dung từ 1 website.
    
    - **url**: URL cần cào
    - **max_depth**: Độ sâu tối đa (default: 2)
    - **max_pages**: Số trang tối đa (default: 30)
    - **use_playwright**: Dùng Playwright cho JS pages
    """
    try:
        from urllib.parse import urlparse
        domain = urlparse(req.url).netloc
        
        config = ScraperConfig(
            max_depth=req.max_depth,
            max_pages=req.max_pages,
            delay_between_requests=0.3
        )
        
        scraper = MultiLevelScraper(req.url, config)
        pages = scraper.crawl()
        
        if not pages:
            return ScrapeResponse(
                status="success",
                domain=domain,
                pages_crawled=0,
                pages=[],
                error="Không cào được trang nào"
            )
        
        # Convert PageContent objects to response
        pages_response = []
        for p in pages:
            images = []
            if hasattr(p, 'images') and p.images:
                for img in p.images:
                    images.append(ImageInfo(
                        url=img.url if hasattr(img, 'url') else str(img),
                        alt=getattr(img, 'alt', ''),
                        title=getattr(img, 'title', ''),
                        context=getattr(img, 'context', '')
                    ))
            
            # Build structured data
            sd = StructuredDataResponse()
            if hasattr(p, 'structured') and p.structured:
                s = p.structured
                sd = StructuredDataResponse(
                    jsonld_type=getattr(s, 'jsonld_type', ''),
                    jsonld_name=getattr(s, 'jsonld_name', ''),
                    jsonld_description=getattr(s, 'jsonld_description', ''),
                    jsonld_price=getattr(s, 'jsonld_price', ''),
                    jsonld_brand=getattr(s, 'jsonld_brand', ''),
                    breadcrumb=getattr(s, 'breadcrumb', []),
                    has_price=getattr(s, 'has_price', False),
                    price_text=getattr(s, 'price_text', ''),
                    og_type=getattr(s, 'og_type', ''),
                    og_title=getattr(s, 'og_title', ''),
                )
            
            pages_response.append(PageResponse(
                url=p.url,
                title=p.title or "",
                meta_description=p.meta_description or "",
                headings=p.headings or [],
                paragraphs=p.paragraphs or [],
                images=images,
                depth=p.depth,
                structured=sd
            ))
        
        return ScrapeResponse(
            status="success",
            domain=domain,
            pages_crawled=len(pages_response),
            pages=pages_response
        )
    
    except Exception as e:
        return ScrapeResponse(
            status="error",
            error=str(e)
        )
