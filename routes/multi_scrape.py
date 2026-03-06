"""
Routes: POST /api/classify, POST /api/analyze-product, POST /api/generate-article
"""

from fastapi import APIRouter
from models.schemas import (
    ClassifyRequest, ClassifyResponse, ClassifyResult,
    AnalyzeProductRequest, AnalyzeProductResponse,
    GenerateArticleRequest, GenerateArticleResponse
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.content_extractor import AIContentExtractor

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify_pages(req: ClassifyRequest):
    """
    Phân loại trang: PRODUCT / CATEGORY / OTHER.
    
    - **pages**: Danh sách pages cần classify
    - **ai_base_url**: AI API URL
    - **ai_model**: Model name
    """
    try:
        extractor = AIContentExtractor(
            api_key=req.ai_api_key,
            base_url=req.ai_base_url,
            model=req.ai_model
        )
        
        results = extractor.batch_classify_pages(req.pages)
        
        classify_results = []
        for r in results:
            classify_results.append(ClassifyResult(
                url=r.get('url', ''),
                category=r.get('category', ''),
                product_name=r.get('product_name', ''),
                product_group=r.get('product_group', '')
            ))
        
        return ClassifyResponse(
            status="success",
            total_pages=len(req.pages),
            results=classify_results
        )
    
    except Exception as e:
        return ClassifyResponse(status="error", error=str(e))


@router.post("/analyze-product", response_model=AnalyzeProductResponse)
async def analyze_product(req: AnalyzeProductRequest):
    """
    Phân tích 1 trang có phải sản phẩm không.
    
    - **page_content**: Nội dung thô
    """
    try:
        extractor = AIContentExtractor(
            api_key=req.ai_api_key,
            base_url=req.ai_base_url,
            model=req.ai_model
        )
        
        product_info = extractor.analyze_product(req.page_content)
        
        if product_info:
            return AnalyzeProductResponse(
                status="success",
                is_product=True,
                product_info=product_info
            )
        else:
            return AnalyzeProductResponse(
                status="success",
                is_product=False
            )
    
    except Exception as e:
        return AnalyzeProductResponse(status="error", error=str(e))


@router.post("/generate-article", response_model=GenerateArticleResponse)
async def generate_article(req: GenerateArticleRequest):
    """
    Tạo bài viết marketing cho 1 sản phẩm.
    
    - **product_info**: Dict chứa name, features, core_values
    - **source_content**: Nội dung thô tham khảo
    - **product_images**: URLs ảnh
    """
    try:
        extractor = AIContentExtractor(
            api_key=req.ai_api_key,
            base_url=req.ai_base_url,
            model=req.ai_model
        )
        
        # Generate article
        article = extractor.create_article(
            product_info=req.product_info,
            source_content=req.source_content,
            product_images=req.product_images
        )
        
        # Generate media prompts
        media_prompts = {}
        try:
            media_prompts = extractor.generate_media_prompts(req.product_info)
        except Exception:
            pass
        
        if article and not article.startswith("Lỗi"):
            return GenerateArticleResponse(
                status="success",
                article=article,
                media_prompts=media_prompts or {}
            )
        else:
            return GenerateArticleResponse(
                status="error",
                error=article or "Failed to generate article"
            )
    
    except Exception as e:
        return GenerateArticleResponse(status="error", error=str(e))
