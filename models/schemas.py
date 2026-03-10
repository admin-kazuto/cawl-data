"""
Pydantic models cho Scraper API
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any


# ============== SCRAPE ==============

class ScrapeRequest(BaseModel):
    url: str = Field(..., description="URL website cần cào")
    max_depth: int = Field(2, description="Độ sâu cào tối đa")
    max_pages: int = Field(30, description="Số trang tối đa")
    use_playwright: bool = Field(False, description="Dùng Playwright cho JS-rendered pages")


class ImageInfo(BaseModel):
    url: str
    alt: str = ""
    title: str = ""
    context: str = ""


class StructuredDataResponse(BaseModel):
    jsonld_type: str = ""
    jsonld_name: str = ""
    jsonld_description: str = ""
    jsonld_price: str = ""
    jsonld_brand: str = ""
    breadcrumb: List[str] = []
    has_price: bool = False
    price_text: str = ""
    og_type: str = ""
    og_title: str = ""


class PageResponse(BaseModel):
    url: str
    title: str = ""
    meta_description: str = ""
    headings: List[str] = []
    paragraphs: List[str] = []
    images: List[ImageInfo] = []
    depth: int = 0
    structured: StructuredDataResponse = StructuredDataResponse()


class ScrapeResponse(BaseModel):
    status: str = "success"
    domain: str = ""
    pages_crawled: int = 0
    pages: List[PageResponse] = []
    error: Optional[str] = None


# ============== CLASSIFY ==============

class ClassifyRequest(BaseModel):
    pages: List[Dict[str, Any]] = Field(..., description="Danh sách pages cần phân loại")
    ai_base_url: str = Field("https://content.scapbot.net/v1", description="AI API URL")
    ai_model: str = Field("default", description="AI model")
    ai_api_key: str = Field("d3f230c4fb86d327b79d18790e0d91df", description="API key")


class ClassifyResult(BaseModel):
    url: str = ""
    category: str = ""
    product_name: str = ""
    product_group: str = ""


class ClassifyResponse(BaseModel):
    status: str = "success"
    total_pages: int = 0
    results: List[ClassifyResult] = []
    error: Optional[str] = None


# ============== GENERATE ARTICLE ==============

class GenerateArticleRequest(BaseModel):
    product_info: Dict[str, Any] = Field(..., description="Thông tin sản phẩm (name, features, core_values)")
    source_content: str = Field("", description="Nội dung thô tham khảo")
    product_images: List[str] = Field([], description="URLs ảnh sản phẩm")
    ai_base_url: str = Field("https://content.scapbot.net/v1")
    ai_model: str = Field("default")
    ai_api_key: str = Field("d3f230c4fb86d327b79d18790e0d91df")


class GenerateArticleResponse(BaseModel):
    status: str = "success"
    article: str = ""
    media_prompts: Dict[str, str] = {}
    error: Optional[str] = None


# ============== PIPELINE ==============

class PipelineRequest(BaseModel):
    urls: List[str] = Field(..., description="Danh sách URLs cần xử lý")
    max_depth: int = Field(2, description="Độ sâu cào")
    max_pages: int = Field(30, description="Số trang tối đa per site")
    website_workers: int = Field(3, description="Số website xử lý song song")
    analyze_workers: int = Field(5, description="Số worker phân tích per site")
    ai_base_url: str = Field("https://content.scapbot.net/v1")
    ai_model: str = Field("default")
    ai_api_key: str = Field("d3f230c4fb86d327b79d18790e0d91df")
    use_playwright: bool = Field(False)


class SiteResult(BaseModel):
    url: str
    domain: str = ""
    pages_crawled: int = 0
    products_found: int = 0
    articles_written: int = 0
    errors: List[str] = []


class PipelineResponse(BaseModel):
    status: str = "success"
    total_sites: int = 0
    total_articles: int = 0
    sites: List[SiteResult] = []
    output_dir: str = ""
    error: Optional[str] = None


# ============== ANALYZE PRODUCT ==============

class AnalyzeProductRequest(BaseModel):
    page_content: str = Field(..., description="Nội dung thô của trang sản phẩm")
    ai_base_url: str = Field("https://content.scapbot.net/v1")
    ai_model: str = Field("default")
    ai_api_key: str = Field("d3f230c4fb86d327b79d18790e0d91df")


class AnalyzeProductResponse(BaseModel):
    status: str = "success"
    is_product: bool = False
    product_info: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============== CONTENT WRITE (4-FACTOR PIPELINE) ==============

class ContentWriteRequest(BaseModel):
    url: str = Field(..., description="URL website khach hang de cao noi dung")
    keyword: str = Field(..., description="Tu khoa SEO khach hang muon len top")
    backlink_type: str = Field(
        ...,
        description="Loai dich vu backlink: social | blog20"
    )
    language: str = Field(
        ...,
        description="Ngon ngu bai viet: vi | en | ja | ko | zh | th"
    )
    word_count: int = Field(..., description="So tu bai viet muc tieu")
    text_length: int = Field(..., description="[blog20] Gioi han ky tu noi dung")
    text_link: str = Field("", description="[blog20] Anchor text de chen link <a href>")
    total_image: int = Field(2, description="[blog20] So luong anh chen vao bai (default: 2)")
    tag_image: str = Field(
        "<img src='https://via.placeholder.com/800x400' alt='image'>",
        description="[blog20] HTML tag anh mau"
    )
    ai_base_url: str = Field("https://content.scapbot.net/v1")
    ai_model: str = Field("default")
    ai_api_key: str = Field("d3f230c4fb86d327b79d18790e0d91df")


class ContentWriteResponse(BaseModel):
    status: str = "success"
    keyword: str = ""
    language: str = ""
    backlink_type: str = ""
    domain: str = ""
    pages_crawled: int = 0
    word_count: int = 0
    processing_time_seconds: float = 0.0   # Thời gian xử lý từ lúc nhận request tới lúc trả response
    title: str = ""      # Title riêng (social, blog20, likepion)
    article: str = ""    # Nội dung chính
    error: Optional[str] = None
