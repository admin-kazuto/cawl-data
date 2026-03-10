"""
Route: POST /api/content-write
Full pipeline 4 yeu to: keyword + URL cao + backlink type + language → bai viet SEO

Improvements v2:
- Structured AI_TOPIC: truyền context có cấu trúc thay vì raw text
- Parallel: crawl + title chạy song song bằng asyncio
"""

from fastapi import APIRouter
from models.schemas import ContentWriteRequest, ContentWriteResponse

import sys
import os
import asyncio
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from urllib.parse import urlparse
from core.scraper import MultiLevelScraper, ScraperConfig
from core.content_extractor import AIContentExtractor

router = APIRouter()

SUPPORTED_BACKLINK_TYPES = ["social", "blog20"]  # likepion: coming soon


def _is_junk(text: str) -> bool:
    """Lọc rác: navigation, contact, legal, quảng cáo..."""
    if len(text) < 20:
        return True
    text_lower = text.lower()
    junk_keywords = [
        # Navigation / UI
        "đăng nhập", "đăng ký", "trang chủ", "giỏ hàng", "xem thêm",
        "home", "login", "register", "cart", "click here", "read more",
        "menu", "search", "tìm kiếm",
        # Contact
        "hotline", "zalo:", "tel:", "email:", "@gmail", "@yahoo",
        # Legal
        "bản quyền", "copyright ©", "all rights reserved", "privacy policy",
        "điều khoản", "terms of",
        # Social
        "follow us", "subscribe", "theo dõi chúng tôi",
        # Ads
        "khuyến mãi", "sale off", "giảm giá đến",
    ]
    return any(kw in text_lower for kw in junk_keywords)


def _build_structured_topic(pages: list, keyword: str, domain: str) -> str:
    """
    Xây dựng [[AI_TOPIC]] từ TẤT CẢ các trang đã cào.
    - Lấy thông tin thương hiệu từ trang chính
    - Gộp heading + paragraph từ toàn bộ trang, lọc rác
    - Giới hạn ~3000 ký tự để không quá dài cho prompt
    """
    if not pages:
        return keyword

    parts = []

    # ── Thông tin từ trang chủ (trang đầu tiên) ──────────────────────────────
    main = pages[0]
    parts.append(f"WEBSITE: {domain}")
    if main.title:
        parts.append(f"THUONG HIEU: {main.title}")
    if main.meta_description:
        parts.append(f"MO TA: {main.meta_description}")

    # ── Headings từ TẤT CẢ trang — lọc trùng và rác ─────────────────────────
    all_headings = []
    seen_h = set()
    for p in pages:
        for h in p.headings:
            h_clean = h.strip()
            if len(h_clean) > 5 and h_clean not in seen_h and not _is_junk(h_clean):
                seen_h.add(h_clean)
                all_headings.append(h_clean)

    if all_headings:
        parts.append("DICH VU / SAN PHAM / NOI DUNG:\n" + "\n".join(f"- {h}" for h in all_headings[:30]))

    # ── Paragraphs từ TẤT CẢ trang — lọc rác, giữ câu có giá trị ────────────
    all_paras = []
    seen_p = set()
    for p in pages:
        for para in p.paragraphs:
            para_clean = para.strip()
            if (
                len(para_clean) > 50
                and para_clean not in seen_p
                and not _is_junk(para_clean)
            ):
                seen_p.add(para_clean)
                all_paras.append(para_clean)

    if all_paras:
        parts.append("NOI DUNG WEBSITE:\n" + "\n\n".join(all_paras[:20]))

    parts.append(f"TU KHOA MUC TIEU: {keyword}")

    # Giới hạn tổng ~3500 ký tự để không làm prompt quá dài
    result = "\n\n".join(parts)
    if len(result) > 3500:
        result = result[:3500] + "\n...[truncated]"
    return result


@router.post("/content-write", response_model=ContentWriteResponse)
async def content_write(req: ContentWriteRequest):
    """
    ## 4-Factor Content Write Pipeline

    Tu dong cao website KH → ket hop voi keyword, loai backlink, ngon ngu → AI viet bai.

    ### 4 yeu to:
    - **url**: Website khach hang (chi cao dung URL do, khong follow link)
    - **keyword**: Tu khoa SEO muon len top
    - **backlink_type**: `social` | `blog20`
    - **language**: `vi` | `en` | `ja` | `ko` | `zh` | `th`
    """
    try:
        t_start = time.time()
        domain = urlparse(req.url).netloc

        # ── BUOC 1: CRAWL + TITLE — CHAY SONG SONG ───────────────────────────
        config = ScraperConfig(
            max_depth=0,
            max_pages=1,
            delay_between_requests=0.3,
        )

        extractor = AIContentExtractor(
            api_key=req.ai_api_key,
            base_url=req.ai_base_url,
            model=req.ai_model,
        )

        # Chạy crawl trong thread pool (blocking I/O)
        loop = asyncio.get_event_loop()

        async def crawl_async():
            scraper = MultiLevelScraper(req.url, config)
            return await loop.run_in_executor(None, scraper.crawl)

        async def title_async(ai_topic_placeholder: str):
            """Sinh title sớm với placeholder topic (keyword + domain)"""
            return await loop.run_in_executor(
                None,
                extractor.generate_title_only,
                req.keyword,
                ai_topic_placeholder,
                req.backlink_type,
                req.language,
                req.url,
            )

        # Placeholder topic để title request bắt đầu ngay, không cần chờ crawl
        placeholder_topic = f"WEBSITE: {domain}\nTỪ KHÓA MỤC TIÊU: {req.keyword}"

        # Chạy song song crawl và title
        crawl_task = asyncio.create_task(crawl_async())
        title_task = asyncio.create_task(title_async(placeholder_topic))

        pages, title_str = await asyncio.gather(crawl_task, title_task)

        if not pages:
            return ContentWriteResponse(
                status="error",
                keyword=req.keyword,
                language=req.language,
                backlink_type=req.backlink_type,
                domain=domain,
                pages_crawled=0,
                processing_time_seconds=round(time.time() - t_start, 2),
                error="Khong cao duoc noi dung tu URL nay.",
            )

        # ── BUOC 2: BUILD STRUCTURED AI_TOPIC ────────────────────────────────
        ai_topic = _build_structured_topic(pages, req.keyword, domain)

        # ── BUOC 3: AI VIET CONTENT ──────────────────────────────────────────
        article_str = await loop.run_in_executor(
            None,
            extractor.generate_content_only,
            req.keyword,
            ai_topic,
            req.backlink_type,
            req.language,
            req.word_count,
            req.url,
            req.text_link,
            req.total_image,
            req.tag_image,
            req.text_length,
        )

        has_error = article_str.startswith("Loi viet bai:") if article_str else False
        if has_error or (not title_str and not article_str):
            return ContentWriteResponse(
                status="error",
                keyword=req.keyword,
                language=req.language,
                backlink_type=req.backlink_type,
                domain=domain,
                pages_crawled=len(pages),
                processing_time_seconds=round(time.time() - t_start, 2),
                error=article_str or "AI khong tao duoc noi dung",
            )

        word_count_actual = len((title_str + " " + article_str).split())

        return ContentWriteResponse(
            status="success",
            keyword=req.keyword,
            language=req.language,
            backlink_type=req.backlink_type,
            domain=domain,
            pages_crawled=len(pages),
            word_count=word_count_actual,
            processing_time_seconds=round(time.time() - t_start, 2),
            title=title_str,
            article=article_str,
        )

    except Exception as e:
        return ContentWriteResponse(
            status="error",
            keyword=req.keyword,
            language=req.language,
            backlink_type=req.backlink_type,
            error=str(e),
        )
