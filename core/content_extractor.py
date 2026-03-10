"""
AI-Powered Content Extractor
Sử dụng AI để trích xuất thông tin doanh nghiệp từ nội dung đã cào
Tích hợp Vivibe TTS API cho voice-over generation
"""

import json
import os
import time
import requests
import tempfile
from typing import List, Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class BusinessInfo:
    """Thông tin doanh nghiệp được trích xuất"""
    core_values: List[str]           # Giá trị cốt lõi
    differentiators: List[str]       # Sự khác biệt
    expertise: List[str]             # Chuyên môn
    mission: str                     # Sứ mệnh
    vision: str                      # Tầm nhìn
    summary: str                     # Tóm tắt tổng quan
    source_urls: List[str]           # URLs nguồn
    raw_evidence: Dict[str, str]     # Bằng chứng gốc từ website


class AIContentExtractor:

    
    PRODUCT_EXTRACTION_PROMPT = """
    Phân tích văn bản và XÁC ĐỊNH LOẠI TRANG.

    ⚠️ PHÂN BIỆT LOẠI TRANG:
    
    🔴 "CATEGORY_PAGE" - Trang DANH MỤC / LISTING / SERIES:
       - Liệt kê NHIỀU sản phẩm khác nhau (grid/list)
       - Có bộ lọc (Hãng, Giá, Kích thước...)
       - Nội dung chứa NHIỀU tên sản phẩm khác nhau liệt kê
       - KHÔNG có mô tả chi tiết của MỘT sản phẩm cụ thể
       - ĐẶC BIỆT CHÚ Ý các dấu hiệu SAU → chắc chắn là CATEGORY_PAGE:
         * Title chứa "Series" (ví dụ: "iPhone 14 Series", "MacBook Pro M4 Series")
         * Trang hiển thị danh sách nhiều phiên bản/màu sắc/dung lượng để chọn
         * Trang TAG hoặc nhóm bài viết (chứa danh sách link đến bài viết/sản phẩm con)
         * Nội dung chỉ có list giá + tên nhiều sản phẩm, KHÔNG có mô tả chi tiết nào
         * Trang chỉ có thumbnail + tên + giá của nhiều SP mà không đi sâu vào SP nào
    
    🟢 "PRODUCT" - Trang SẢN PHẨM (MỘT sản phẩm DUY NHẤT):
       - Nói về MỘT sản phẩm chính, CÓ THÔNG SỐ KỸ THUẬT chi tiết
       - Có mô tả chi tiết, tính năng, thông số CỦA ĐÚNG 1 SẢN PHẨM
       - Có giá hoặc thông tin mua hàng CỤ THỂ
       - TIÊU CHÍ BẮT BUỘC: Phải mô tả CHI TIẾT ít nhất 3-5 tính năng/đặc điểm của SẢN PHẨM ĐÓ
       - LƯU Ý: Không nhất thiết phải có mã model. Sản phẩm nhập khẩu, thủ công, mỹ phẩm... thường KHÔNG có model code
    
    🔵 "ARTICLE" - Bài viết review/so sánh:
       - Review, đánh giá, so sánh sản phẩm
       - Bài hướng dẫn sử dụng sản phẩm
       - Top/Best sản phẩm (nếu giới thiệu CHI TIẾT từng sản phẩm)
    
    🟡 "SERVICE" - Trang dịch vụ:
       - Mô tả dịch vụ BÁN (SEO, marketing, thiết kế web...)
       - Có bảng giá dịch vụ
       - LƯU Ý: phải là DỊCH VỤ BÁN cho khách hàng, KHÔNG phải trang hướng dẫn nội bộ
    
    🟣 "PROMOTION" - Trang ƯU ĐÃI / KHUYẾN MÃI CHUNG (KHÔNG viết review):
       - Trang giới thiệu chương trình giảm giá, voucher, flash sale
       - Trang tổng hợp ưu đãi tháng/quý (quảng cáo nhiều dịch vụ CHUNG, không phải 1 sản phẩm cụ thể)
       - DẤU HIỆU: chứa "ưu đãi", "khuyến mãi", "giảm giá", "sale", "coupon", "voucher"
       - KHÔNG phải trang sản phẩm CÓ giá giảm (đó vẫn là PRODUCT)

    🟠 "UTILITY" - Trang hỗ trợ/tiện ích (KHÔNG viết review):
       - Trang "hướng dẫn mua hàng", "hướng dẫn đặt hàng", "hướng dẫn thanh toán"
       - Trang "cảm ơn", "hoàn tất đăng ký", "xác nhận đơn hàng"
       - Trang "chính sách bảo hành/đổi trả/vận chuyển"
       - Trang "liên hệ", "về chúng tôi", "tuyển dụng"
       - Trang "tra cứu đơn hàng", "kiểm tra bảo hành"
       - Trang FAQ, câu hỏi thường gặp
       - DẤU HIỆU: không nói về sản phẩm/dịch vụ CỤ THỂ nào, chỉ hướng dẫn quy trình
    
    ⚪ "OTHER" - Tin tức chung, blog không liên quan sản phẩm...

    CHỈ trích xuất nếu là PRODUCT hoặc ARTICLE hoặc SERVICE:
    1. Product Name: Tên sản phẩm/dịch vụ CHÍNH XÁC như trên trang (KHÔNG bịa tên)
    2. Product Model: Mã model/SKU/phiên bản CỤ THỂ (ví dụ: "EN-D29B", "iPhone 16 Pro Max 256GB", "ML-203W"). Nếu KHÔNG CÓ model thì ghi ""
    3. Features: Tính năng/thông số chi tiết
    4. Core Values: Lợi ích chính

    Trả về JSON ONLY:
    {
        "category": "PRODUCT hoặc ARTICLE hoặc SERVICE hoặc SOFTWARE hoặc CATEGORY_PAGE hoặc PROMOTION hoặc UTILITY hoặc OTHER",
        "product_name": "Tên Sản Phẩm/Dịch Vụ",
        "product_model": "Mã model/SKU cụ thể hoặc rỗng",
        "features": ["Feature 1", "Feature 2"],
        "core_values": ["Value 1"]
    }
    """

    ARTICLE_GENERATION_PROMPT = """
    [LANGUAGE REQUIREMENT: Write ENTIRE response in VIETNAMESE ONLY. Do NOT use Chinese, English or any other language. Do NOT output special tokens like <|im_start|> or <|im_end|>.]

    Bạn là một chuyên gia Content Marketing Việt Nam. Hãy viết một bài PR/Review sâu sắc về sản phẩm: {product_name}

    Dựa trên thông tin cốt lõi:
    1. GIÁ TRỊ CỐT LÕI: {core_values}
    2. SỰ KHÁC BIỆT: {differentiators}
    3. TÍNH NĂNG/CHUYÊN MÔN: {expertise}
    
    NGUỒN DỮ LIỆU:
    =========================================
    {source_content}
    =========================================

    YÊU CẦU BẮT BUỘC:
    - VIẾT 100% TIẾNG VIỆT. TUYỆT ĐỐI KHÔNG dùng tiếng Trung, tiếng Anh hoặc ký tự đặc biệt.
    - Viết bài hấp dẫn, thuyết phục, tập trung vào lợi ích người dùng.
    - Dùng giọng văn chuyên gia nhưng gần gũi.
    - KHÔNG BỊA ĐẶT thông tin không có trong Nguồn dữ liệu.
    - Độ dài: 600-1000 từ.
    - Format Markdown chuẩn (H1 có emoji, H2, Bold keywords).
    - TUYỆT ĐỐI KHÔNG chèn bất kỳ ảnh nào vào bài viết. KHÔNG dùng cú pháp ![...](...). Ảnh sẽ được bổ sung riêng sau.
    - KHÔNG viết thêm prompt hoặc yêu cầu khác ở cuối bài.
    """
    
    EXTRACTION_PROMPT = """Bạn là chuyên gia phân tích nội dung doanh nghiệp. 
    Dựa vào nội dung website được cung cấp, hãy trích xuất các thông tin sau:

    1. **GIÁ TRỊ CỐT LÕI (Core Values)**: Những nguyên tắc, giá trị nền tảng mà doanh nghiệp theo đuổi
    2. **SỰ KHÁC BIỆT (Differentiators)**: Điểm độc đáo, lợi thế cạnh tranh so với đối thủ
    3. **CHUYÊN MÔN (Expertise)**: Lĩnh vực chuyên môn, năng lực cốt lõi, dịch vụ chính

    Quy tắc:
    - Chỉ trích xuất thông tin CÓ TRONG nội dung, KHÔNG suy đoán
    - Mỗi mục liệt kê từ 3-7 điểm chính
    - Trích dẫn câu/đoạn văn gốc làm bằng chứng
    - Nếu không tìm thấy thông tin, ghi "Không tìm thấy trong nội dung"

    Trả về JSON với format:
    {
        "core_values": ["giá trị 1", "giá trị 2", ...],
        "differentiators": ["điểm khác biệt 1", "điểm khác biệt 2", ...],
        "expertise": ["chuyên môn 1", "chuyên môn 2", ...],
        "mission": "sứ mệnh của doanh nghiệp",
        "vision": "tầm nhìn của doanh nghiệp",
        "summary": "tóm tắt 2-3 câu về doanh nghiệp",
        "evidence": {
            "core_values_source": "trích dẫn gốc về giá trị cốt lõi",
            "differentiators_source": "trích dẫn gốc về sự khác biệt",
            "expertise_source": "trích dẫn gốc về chuyên môn"
        }
    }
    
    NỘI DUNG WEBSITE:
    {content}
    """
    
    MEDIA_PROMPT_TEMPLATE = """
    [STRICT RULES]
    1. Write ALL text in ENGLISH ONLY. ABSOLUTELY NO Chinese characters, NO Vietnamese diacritics.
    2. The product name is: "{product_name}" — you MUST use THIS EXACT NAME in all prompts. Do NOT invent a different product.
    3. Base your description ONLY on the features provided. Do NOT hallucinate or make up features.

    Product info:
    - Name: {product_name}
    - Features: {features}
    - Core values: {core_values}

    You are an AI Art Director. Write 3 English prompts for advertising media of "{product_name}".

    Style requirements:
    - Cinematic Lighting, 8k, Photorealistic, High detail.
    - Subject MUST be "{product_name}" — NOT a random luxury item.

    Return VALID JSON ONLY. ALL values in ENGLISH:
    {{
        "image_prompt": "[{product_name}], [Environment matching the product category], [Cinematic Lighting with soft shadows and highlights], [Photorealistic, high detail], [Key feature from the list above]",
        "video_shot_1": "Video Shot 1 (0s-8s): Product showcase intro. Slow motion close-up of {product_name} showing [specific feature]. (Format: Cinematic close-up of {product_name}...)",
        "video_shot_2": "Video Shot 2 (8s-16s): User lifestyle scene. A user [action related to product] with {product_name}. (Format: Medium shot of a user [action]...)"
    }}
    """

    # ===================== TTS SCRIPT PROMPT =====================
    TTS_SCRIPT_PROMPT = """
    [LANGUAGE REQUIREMENT: Write ENTIRE response in VIETNAMESE ONLY. Do NOT use Chinese, English or any other language. Do NOT output special tokens like <|im_start|> or <|im_end|>.]

    Bạn là một biên tập viên kịch bản voice-over chuyên nghiệp tại Việt Nam.
    Hãy viết một đoạn kịch bản đọc cho giọng nói (voice-over) về sản phẩm: {product_name}

    Dựa trên thông tin:
    1. TÍNH NĂNG: {features}
    2. GIÁ TRỊ CỐT LÕI: {core_values}

    NGUỒN DỮ LIỆU:
    =========================================
    {source_content}
    =========================================

    YÊU CẦU BẮT BUỘC:
    - VIẾT 100% TIẾNG VIỆT tự nhiên, giọng kể chuyện gần gũi.
    - Độ dài: 200-280 từ (tương đương 1-2 phút đọc).
    - TUYỆT ĐỐI KHÔNG dùng emoji, ký hiệu đặc biệt, Markdown, heading.
    - KHÔNG dùng dấu #, *, **, !, [], ().
    - KHÔNG BỊA ĐẶT thông tin không có trong Nguồn dữ liệu.
    - Viết thành các câu ngắn, dễ đọc, dễ nghe.
    - Mở đầu bằng câu hook gây tò mò.
    - Kết thúc bằng lời kêu gọi hành động nhẹ nhàng.
    - Giọng văn như đang nói chuyện với bạn bè, không quá trang trọng.
    - Ngắt câu hợp lý để người đọc có thể nghỉ hơi.
    - CHỈ trả về đoạn text thuần, KHÔNG có tiêu đề hay ghi chú gì thêm.
    """

    # ===================== LIKEPION BIO PROMPT =====================
    LIKEPION_BIO_PROMPT = """
    [LANGUAGE REQUIREMENT: Write ENTIRE response in VIETNAMESE ONLY. Do NOT use Chinese, English or any other language.]

    Bạn là chuyên gia viết content cho profile doanh nghiệp trên các nền tảng web.
    Hãy viết một đoạn giới thiệu ngắn gọn (bio/about) cho sản phẩm hoặc thương hiệu: {product_name}

    Thông tin:
    - Tính năng: {features}
    - Giá trị cốt lõi: {core_values}
    - Website: {source_url}

    YÊU CẦU BẮT BUỘC:
    - VIẾT 100% TIẾNG VIỆT.
    - Độ dài: 80-150 từ (3-5 câu).
    - Giọng văn chuyên nghiệp, ngắn gọn, đi thẳng vào trọng tâm.
    - Nêu rõ sản phẩm/thương hiệu là gì, phục vụ ai, điểm mạnh chính.
    - KHÔNG emoji, KHÔNG Markdown, KHÔNG ký hiệu đặc biệt.
    - KHÔNG BỊA ĐẶT thông tin.
    - CHỈ trả về đoạn text thuần, KHÔNG tiêu đề.
    """

    # ScapBot Content Hub API defaults
    SCAPBOT_API_URL = "https://content.scapbot.net/v1"
    SCAPBOT_API_KEY = "d3f230c4fb86d327b79d18790e0d91df"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, 
                 model: str = "default", max_workers: int = 5):
        """
        Args:
            api_key: API key (mặc định: ScapBot Content Hub)
            base_url: URL API server (mặc định: ScapBot Content Hub)
            model: Model để sử dụng ("default" cho ScapBot)
            max_workers: Số thread song song cho batch classify
        """ 
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or self.SCAPBOT_API_KEY
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or self.SCAPBOT_API_URL
        self.model = model
        self.max_workers = max_workers
        
        self._use_ai = True
        import openai
        # Cấu hình client
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        if "scapbot" in self.base_url:
            print(f" AI: ScapBot Content Hub (workers={self.max_workers})")
        elif "localhost" in self.base_url:
            print(f" AI: Local LM Studio. Model: {self.model}, URL: {self.base_url}")
        else:
            print(f" AI: {self.base_url} (model={self.model})")

    def extract(self, pages_data: List[Dict]) -> BusinessInfo:
        """
        Main method: Quyết định dùng AI hay Rules
        """
        if self._use_ai:
            return self.extract_with_ai(pages_data)
        return self.extract_with_rules(pages_data)

    def extract_with_ai(self, pages_data: List[Dict]) -> BusinessInfo:
        """
        Trích xuất thông tin doanh nghiệp bằng AI (OpenAI/LM Studio)
        Gửi toàn bộ nội dung trang cho AI phân tích
        """
        print("\n Đang phân tích nội dung bằng AI...")
        
        # Ghép nội dung các trang thành 1 block text
        combined_content = ""
        for page in pages_data:
            combined_content += f"\n--- PAGE: {page.get('url', '')} ---\n"
            combined_content += f"Title: {page.get('title', '')}\n"
            combined_content += f"Description: {page.get('meta_description', '')}\n"
            combined_content += f"Headings: {', '.join(page.get('headings', []))}\n"
            combined_content += f"Content: {' '.join(page.get('paragraphs', [])[:20])}\n"
        
        # Cắt ngắn nếu quá dài (giữ trong context window)
        combined_content = combined_content[:25000]
        
        prompt = self.EXTRACTION_PROMPT.format(content=combined_content)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a business analyst. Answer in Valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            content = response.choices[0].message.content.strip()
            
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(content)
            
            return BusinessInfo(
                core_values=data.get('core_values', []),
                differentiators=data.get('differentiators', []),
                expertise=data.get('expertise', []),
                mission=data.get('mission', ''),
                vision=data.get('vision', ''),
                summary=data.get('summary', ''),
                source_urls=[p['url'] for p in pages_data],
                raw_evidence=data.get('evidence', {})
            )
        except Exception as e:
            print(f" AI extraction failed: {e}. Fallback sang Rule-based.")
            return self.extract_with_rules(pages_data)

    def extract_with_rules(self, pages_data: List[Dict]) -> BusinessInfo:
        """
        Trích xuất thông tin bằng rule-based (không cần AI)
        PHƯƠNG PHÁP MỚI: Tìm heading → lấy nội dung tiếp theo
        """
        print("\n Đang phân tích nội dung bằng Smart Rules...")
        
        # ========== ĐỊNH NGHĨA PATTERNS ==========
        HEADING_PATTERNS = {
            'core_values': [
                'giá trị cốt lõi', 'core value', 'giá trị của chúng tôi',
                'our values', 'nguyên tắc', 'principles', 'triết lý',
                'philosophy', 'giá trị nền tảng', 'tôn chỉ'
            ],
            'differentiators': [
                'khác biệt', 'sự khác biệt', 'difference', 'điểm khác biệt',
                'tại sao chọn', 'why choose', 'why us', 'lợi thế',
                'ưu điểm', 'điểm mạnh', 'lý do chọn', 'vì sao chọn'
            ],
            'expertise': [
                'dịch vụ', 'service', 'chuyên môn', 'expertise',
                'năng lực', 'capability', 'lĩnh vực', 'giải pháp',
                'solution', 'sản phẩm', 'product', 'chúng tôi làm gì'
            ],
            'mission': ['sứ mệnh', 'mission', 'mục tiêu', 'objective'],
            'vision': ['tầm nhìn', 'vision', 'định hướng', 'mục tiêu dài hạn']
        }
        
        def extract_content_after_heading(headings: List[str], paragraphs: List[str], keywords: List[str]) -> List[str]:
            """TÌM HEADING → LẤY NỘI DUNG SAU"""
            results = []
            for heading in headings:
                heading_lower = heading.lower()
                for keyword in keywords:
                    if keyword in heading_lower:
                        for para in paragraphs:
                            para_clean = para.strip()
                            if para_clean and 5 < len(para_clean) < 150:
                                if not any(noise in para_clean.lower() for noise in ['đọc tiếp', 'xem thêm', 'click']):
                                    results.append(para_clean)
                        break
            # Unique
            seen = set()
            return [x for x in results if not (x in seen or seen.add(x))][:7]
        
        def extract_from_structured_content(paragraphs: List[str], keywords: List[str]) -> List[str]:
            """Tìm nội dung có cấu trúc Label: Value"""
            results = []
            for para in paragraphs:
                para_lower = para.lower()
                for keyword in keywords:
                    if keyword in para_lower and ':' in para:
                        parts = para.split(':', 1)
                        if len(parts) > 1:
                            content = parts[1].strip()
                            if ' - ' in content: results.extend([i.strip() for i in content.split(' - ')])
                            elif ',' in content: results.extend([i.strip() for i in content.split(',')])
                            else: results.append(content)
                            break
            # Unique & Clean
            return list(set([r for r in results if len(r) > 3 and len(r) < 150]))[:7]
        
        # ========== TRÍCH XUẤT CHÍNH ==========
        core_values = []
        differentiators = []
        expertise = []
        mission = ""
        vision = ""
        
        for page in pages_data:
            headings = page.get('headings', [])
            paragraphs = page.get('paragraphs', [])
            
            if not core_values: core_values = extract_content_after_heading(headings, paragraphs, HEADING_PATTERNS['core_values']) or extract_from_structured_content(paragraphs, HEADING_PATTERNS['core_values'])
            if not differentiators: differentiators = extract_content_after_heading(headings, paragraphs, HEADING_PATTERNS['differentiators']) or extract_from_structured_content(paragraphs, HEADING_PATTERNS['differentiators'])
            if not expertise: expertise = extract_content_after_heading(headings, paragraphs, HEADING_PATTERNS['expertise']) or extract_from_structured_content(paragraphs, HEADING_PATTERNS['expertise'])
            
            if not mission:
                for para in paragraphs:
                    if any(kw in para.lower() for kw in HEADING_PATTERNS['mission']):
                         mission = para.split(':', 1)[1].strip() if ':' in para else para.strip()
                         break
            
            if not vision:
                 for para in paragraphs:
                    if any(kw in para.lower() for kw in HEADING_PATTERNS['vision']):
                         vision = para.split(':', 1)[1].strip() if ':' in para else para.strip()
                         break
        
        return BusinessInfo(
            core_values=core_values if core_values else ["Không tìm thấy section 'Giá trị cốt lõi'"],
            differentiators=differentiators if differentiators else ["Không tìm thấy section 'Sự khác biệt'"],
            expertise=expertise if expertise else ["Không tìm thấy section 'Chuyên môn'"],
            mission=mission if mission else "Không tìm thấy section 'Sứ mệnh'",
            vision=vision if vision else "Không tìm thấy section 'Tầm nhìn'",
            summary="Được trích xuất bằng Smart Rule-based",
            source_urls=[p['url'] for p in pages_data],
            raw_evidence={}
        )

    # ===================== BATCH CLASSIFY — MULTI-THREAD =====================
    BATCH_CLASSIFY_PROMPT = """Bạn là chuyên gia phân tích website. Phân loại TỪNG trang và NHÓM CÁC TRANG CÙNG SẢN PHẨM.

LOẠI TRANG:
- "PRODUCT" — Trang sản phẩm CỤ THỂ (1 sản phẩm, có thông số/giá)
- "SERVICE" — Trang dịch vụ BÁN (SEO, marketing, thiết kế web...)
- "SOFTWARE" — Trang phần mềm/tool bán cho khách hàng
- "ARTICLE" — Bài review/so sánh/hướng dẫn sử dụng sản phẩm
- "CATEGORY" — Trang danh mục/listing nhiều sản phẩm
- "PROMOTION" — Trang ưu đãi/khuyến mãi chung
- "UTILITY" — Trang hỗ trợ (liên hệ, bảo hành, FAQ, giới thiệu, tin tức, tuyển dụng...)
- "OTHER" — Không phân loại được

QUY TẮC PHÂN LOẠI (QUAN TRỌNG, tuân thủ nghiêm ngặt):
1. jsonld_type: Product + has_price + has_spec_table → PRODUCT (chắc chắn)
2. jsonld_type: Product + has_price (price cụ thể, VD: 5.890.000đ) → PRODUCT
3. jsonld_type: Product + has_price (price range, VD: 1.000.000~10.000.000) → CATEGORY (listing nhiều SP)
4. URL chứa /danh-muc/ hoặc /dtdd-*-series hoặc title chứa "Series" → CATEGORY
5. has_price KHÔNG có jsonld_type: Product + title chứa "khuyến mãi/ưu đãi" → PROMOTION
6. has_price KHÔNG có jsonld_type: Product + URL là danh mục → CATEGORY
7. og_type: product + has_price → khả năng PRODUCT (kết hợp title để xác nhận)
8. jsonld_type: Article → ARTICLE
9. Trang chính sách, bảo hành, liên hệ, giới thiệu, tuyển dụng → UTILITY

CÁCH NHÓM SẢN PHẨM:
- Các trang CÙNG 1 sản phẩm → cùng product_group (VD: "socialking", "may-tro-thinh-gm953")
- Trang CATEGORY/UTILITY/PROMOTION/OTHER → product_group = null

DANH SÁCH TRANG:
{pages_list}

Trả về JSON ARRAY. Mỗi phần tử:
{{"idx": <số>, "category": "<loại>", "product_name": "<tên SP hoặc null>", "product_group": "<ID nhóm hoặc null>"}}

CHỈ TRẢ VỀ JSON ARRAY, KHÔNG viết gì thêm.
"""

    def _build_batch_prompt(self, batch: List[Dict]) -> str:
        """Build prompt string cho 1 batch pages"""
        pages_list = ""
        for i, page in enumerate(batch):
            pages_list += f"\n[{i}] URL: {page.get('url', '')}"
            pages_list += f"\n    Title: {page.get('title', '')}"
            meta = page.get('meta_description', '')
            if meta:
                pages_list += f"\n    Meta: {meta[:150]}"
            
            # ===== STRUCTURED DATA SIGNALS =====
            sd = page.get('structured', {})
            if sd:
                signals = []
                jt = sd.get('jsonld_type', '')
                if jt:
                    signals.append(f"jsonld_type: {jt}")
                jn = sd.get('jsonld_name', '')
                if jn:
                    signals.append(f"jsonld_name: {jn[:80]}")
                if sd.get('has_price'):
                    price_txt = sd.get('price_text', '')
                    signals.append(f"has_price: true ({price_txt})")
                if sd.get('has_spec_table'):
                    signals.append(f"has_spec_table: true")
                bc = sd.get('breadcrumb', [])
                if bc:
                    signals.append(f"breadcrumb: {' > '.join(bc[:5])}")
                og = sd.get('og_type', '')
                if og:
                    signals.append(f"og_type: {og}")
                
                if signals:
                    pages_list += f"\n    Signals: {' | '.join(signals)}"
            
            pages_list += "\n"
        
        return self.BATCH_CLASSIFY_PROMPT.format(pages_list=pages_list)

    def _classify_one_batch(self, batch_start: int, batch: List[Dict], batch_num: int, total_batches: int) -> List[Dict]:
        """Classify 1 batch — chạy trong thread riêng"""
        import re
        print(f"     Batch {batch_num}/{total_batches}: Phân loại {len(batch)} trang...")
        
        prompt = self._build_batch_prompt(batch)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a website page classifier. Output valid JSON array only. No explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4000,
                timeout=120,
            )
            content = response.choices[0].message.content.strip()
            
            # Parse JSON array — hỗ trợ cả markdown code block
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                batch_results = json.loads(json_match.group(0))
            else:
                batch_results = json.loads(content)
            
            # REMAP: local idx → global idx
            results = []
            seen_global = set()
            for entry in batch_results:
                local_idx = entry.get('idx', -1)
                if local_idx < 0 or local_idx >= len(batch):
                    continue
                global_idx = batch_start + local_idx
                if global_idx in seen_global:
                    continue
                seen_global.add(global_idx)
                entry['idx'] = global_idx
                results.append(entry)
            
            print(f"     Batch {batch_num}: {len(results)} kết quả")
            return results
                
        except Exception as e:
            print(f"     Batch {batch_num} classify error: {e}")
            # Fallback: đánh dấu toàn bộ batch là OTHER
            return [{
                "idx": batch_start + i,
                "category": "OTHER",
                "product_name": batch[i].get('title', '').split('–')[0].split('|')[0].strip(),
                "product_group": None
            } for i in range(len(batch))]

    def batch_classify_pages(self, pages_metadata: List[Dict]) -> List[Dict]:
        """
        Phân loại + nhóm TẤT CẢ trang — MULTI-THREADED.
        Các batch chạy song song qua ThreadPoolExecutor.
        
        Input: [{url, title, meta_description, structured}, ...]
        Output: [{idx, category, product_name, product_group}, ...]
        """
        if not pages_metadata:
            return []
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        BATCH_SIZE = 15
        total_batches = (len(pages_metadata) + BATCH_SIZE - 1) // BATCH_SIZE
        
        # Chuẩn bị tất cả batches
        batches = []
        for batch_start in range(0, len(pages_metadata), BATCH_SIZE):
            batch = pages_metadata[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            batches.append((batch_start, batch, batch_num, total_batches))
        
        print(f"     {total_batches} batches x {BATCH_SIZE} trang, {self.max_workers} threads song song")
        start_time = time.time()
        
        all_results = []
        
        # Multi-thread: chạy N batches song song
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._classify_one_batch, *args): args[2]  # batch_num
                for args in batches
            }
            
            for future in as_completed(futures):
                batch_num = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    print(f"     Batch {batch_num} thread error: {e}")
        
        elapsed = time.time() - start_time
        print(f"    ⏱ Classify xong {len(all_results)}/{len(pages_metadata)} trang trong {elapsed:.1f}s")
        
        return all_results

    def analyze_product(self, page_content_text: str) -> Optional[Dict]:
        """
        Dùng AI để xác định xem nội dung này có phải là sản phẩm không
        Trả về None nếu không phải, hoặc Dict nếu là sản phẩm
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a product analyzer. Answer in Valid JSON."},
                    {"role": "user", "content": self.PRODUCT_EXTRACTION_PROMPT + f"\n\nCONTENT:\n{page_content_text}"}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            content = response.choices[0].message.content.strip()
            
            # Debug: Print raw response xem model trả gì
            # print(f"[DEBUG AI RESPONSE]: {content[:100]}...") 

            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_data = json.loads(json_match.group(0))
                return json_data
            else:
                 # Cố gắng parse toàn bộ content nếu regex fail (model trả về thuần json)
                try:
                    return json.loads(content)
                except:
                    # print(f" [JSON ERROR] Raw: {content[:50]}...") # In ra để debug
                    return None
            
        except Exception as e:
            # print(f" Lỗi phân tích sản phẩm (Debug): {e}") # Có thể bật để debug sâu
            return None

    def create_article(self, product_info: Dict, source_content: str = "", product_images: list = None) -> str:
        """
        Viết bài marketing dựa trên 3 yếu tố của SẢN PHẨM và NỘI DUNG THÔ tham khảo
        product_images: KHÔNG còn truyền vào prompt AI — ảnh sẽ được liệt kê riêng ở cuối bài
        """
        # Prepare inputs
        p_name = product_info.get('product_name', 'Sản phẩm')
        c_vals = product_info.get('core_values', [])
        diffs = product_info.get('differentiators', [])
        exps = product_info.get('features', []) # Giờ dùng features cụ thể
        aud = product_info.get('target_audience', 'Khách hàng mục tiêu')

        # Format lists to string
        c_vals_str = ", ".join(c_vals) if isinstance(c_vals, list) else str(c_vals)
        diffs_str = ", ".join(diffs) if isinstance(diffs, list) else str(diffs)
        exps_str = ", ".join(exps) if isinstance(exps, list) else str(exps)

        # Cắt ngắn source_content nếu quá dài
        # Context 32K: tận dụng tối đa với model 7B (không cần chừa chỗ cho ảnh nữa)
        scan_limit = 28000
        safe_content = source_content[:scan_limit] + "..." if len(source_content) > scan_limit else source_content

        prompt = self.ARTICLE_GENERATION_PROMPT.format(
            product_name=p_name,
            core_values=c_vals_str,
            differentiators=diffs_str,
            expertise=exps_str,
            target_audience=aud,
            source_content=safe_content
        )

        try:
            print(f"  Đang viết bài cho sản phẩm: {product_info.get('product_name')}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional Content Writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            article = response.choices[0].message.content
            
            # Post-process: cắt bài bị lặp (model 7B hay repeat)
            article = self._deduplicate_article(article)
            # Post-process: fix lẫn ngôn ngữ (model 7B hay chuyển ngữ)
            article = self._fix_language_artifacts(article)
            return article
        except Exception as e:
            return f"Lỗi tạo bài viết: {e}"
    
    def _deduplicate_article(self, text: str) -> str:
        """Cắt bài viết bị model 7B repeat. Detect heading/section lặp lại."""
        lines = text.split('\n')
        
        # Tìm heading đầu tiên (## hoặc #)
        first_h1 = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('# ') and not stripped.startswith('##'):
                if first_h1 is None:
                    first_h1 = stripped
                elif stripped == first_h1:
                    # Heading lặp lại → cắt từ đây
                    text = '\n'.join(lines[:i]).rstrip()
                    break
        
        # Cắt tại dấu "---" thứ 2 nếu nội dung phía sau giống phía trước
        parts = text.split('\n---\n')
        if len(parts) >= 3:
            # Giữ phần đầu + phần đầu tiên sau ---
            text = parts[0]
        
        return text.strip()

    def _fix_language_artifacts(self, text: str) -> str:
        """Fix lẫn ngôn ngữ do model 7B hay chuyển ngữ giữa chừng."""
        import re
        
        # Fix common typo patterns từ model 7B
        typo_map = {
            'của course': 'tất nhiên',
            'of course,': 'tất nhiên,',
            'tuy nhiên,': 'tuy nhiên,',  # giữ nguyên
        }
        for typo, fix in typo_map.items():
            text = text.replace(typo, fix)
        
        # Detect và xóa ký tự CJK (Trung văn) lẫn trong bài VN
        text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', '', text)
        
        # Detect câu English dài (≥6 từ ASCII liên tiếp) giữa bài VN → xóa
        # Nhưng giữ lại tên riêng, thuật ngữ kỹ thuật ngắn
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Bỏ qua heading và dòng trống
            if not stripped or stripped.startswith('#'):
                cleaned_lines.append(line)
                continue
            # Detect dòng TOÀN BỘ là tiếng Anh (≥6 từ, toàn ASCII)
            words = stripped.split()
            ascii_words = [w for w in words if w.isascii()]
            if len(words) >= 6 and len(ascii_words) / len(words) > 0.8:
                # Dòng này hầu như toàn English → xóa
                continue
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        
        # Clean khoảng trắng thừa sau khi xóa
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def _sanitize_media_prompts(self, prompts: dict, product_name: str) -> dict:
        """Validate và clean media prompts — loại hallucination + Vietnamese text."""
        import re
        import unicodedata
        
        # Regex bắt TẤT CẢ ký tự Vietnamese có dấu (diacritics)
        VN_DIACRITICS_RE = re.compile(
            r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ'
            r'ùúụủũưừứựửữỳýỵỷỹđ'
            r'ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ'
            r'ÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]'
        )
        
        def _has_vietnamese(text: str) -> bool:
            """Kiểm tra text có chứa Vietnamese diacritics không"""
            return bool(VN_DIACRITICS_RE.search(text))
        
        def _strip_vn_phrases(text: str) -> str:
            """Xóa các cụm từ tiếng Việt lẫn trong prompt English"""
            # Tìm các cụm liên tiếp chứa dấu tiếng Việt (2+ words)
            # Tách text thành tokens, xóa token nào có dấu VN
            words = text.split()
            cleaned = []
            for w in words:
                if VN_DIACRITICS_RE.search(w):
                    continue  # Bỏ word có dấu VN
                cleaned.append(w)
            return ' '.join(cleaned)
        
        clean = {}
        for key, value in prompts.items():
            if not isinstance(value, str):
                value = str(value)
            
            # 1. Xóa ký tự CJK (Trung văn)
            value = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', '', value)
            
            # 2. Xóa từ/cụm tiếng Việt có dấu
            if _has_vietnamese(value):
                value = _strip_vn_phrases(value)
            
            # 3. Clean khoảng trắng / dấu phẩy thừa sau xóa
            value = re.sub(r',\s*,', ',', value)
            value = re.sub(r'\s+', ' ', value).strip()
            value = value.strip(', ')
            
            clean[key] = value
        
        # 4. Nếu prompt không chứa tên sản phẩm → thay thế bằng fallback
        p_name_ascii = product_name.encode('ascii', 'ignore').decode().strip()
        if not p_name_ascii:
            p_name_ascii = product_name
        
        for key in ['image_prompt', 'video_shot_1', 'video_shot_2']:
            if key in clean and p_name_ascii.lower() not in clean[key].lower() and product_name.lower() not in clean[key].lower():
                if key == 'image_prompt':
                    clean[key] = f"[{product_name}], [Modern studio environment], [Cinematic Lighting with soft shadows and highlights], [Photorealistic, high detail], [8k resolution]"
                elif key == 'video_shot_1':
                    clean[key] = f"Video Shot 1 (0s-8s): Product showcase intro. Slow motion close-up of {product_name}, highlighting its design and key features."
                elif key == 'video_shot_2':
                    clean[key] = f"Video Shot 2 (8s-16s): User lifestyle scene. Medium shot of a user interacting with {product_name} in daily life."
        
        return clean


    def generate_media_prompts(self, product_info: Dict) -> Dict:
        """
        Tạo prompt cho Ảnh và Video (2 Shots) dựa trên thông tin sản phẩm
        Có sanitize output để tránh hallucination.
        """
        p_name = product_info.get('product_name', 'Sản phẩm')
        features = ", ".join(product_info.get('features', []))
        core_values = ", ".join(product_info.get('core_values', []))
        
        prompt = self.MEDIA_PROMPT_TEMPLATE.format(
            product_name=p_name,
            features=features,
            core_values=core_values
        )
        
        try:
            print(f" Đang tạo kịch bản Media cho: {p_name}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"You are an AI Art Director. The product is '{p_name}'. Output valid JSON only. ALL text MUST be in English. Do NOT use Chinese or Vietnamese."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,  # Giảm temperature để bớt hallucinate
                max_tokens=1000
            )
            content = response.choices[0].message.content.strip()
            
            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                raw_prompts = json.loads(json_match.group(0))
            else:
                raw_prompts = json.loads(content)
            
            # Sanitize: loại CJK, VN dấu, kiểm tra product name
            return self._sanitize_media_prompts(raw_prompts, p_name)
                
        except Exception as e:
            print(f" Lỗi tạo media prompts: {e}")
            return {
                "image_prompt": f"[{p_name}], [Modern studio environment], [Cinematic Lighting with soft shadows and highlights], [Photorealistic, high detail], [8k resolution]",
                "video_shot_1": f"Video Shot 1 (0s-8s): Product showcase intro. Slow motion close-up of {p_name}, highlighting its design and key features.",
                "video_shot_2": f"Video Shot 2 (8s-16s): User lifestyle scene. Medium shot of a user interacting with {p_name} in daily life."
            }

    # ===================== TTS SCRIPT GENERATION =====================

    def create_tts_script(self, product_info: Dict, source_content: str = "") -> str:
        """
        Tạo kịch bản voice-over ngắn gọn (200-280 từ) cho TTS.
        Output: plain text thuần, không markdown, không emoji.
        """
        p_name = product_info.get('product_name', 'Sản phẩm')
        features = ", ".join(product_info.get('features', [])) if isinstance(product_info.get('features'), list) else str(product_info.get('features', ''))
        core_values = ", ".join(product_info.get('core_values', [])) if isinstance(product_info.get('core_values'), list) else str(product_info.get('core_values', ''))

        safe_content = source_content[:15000] if len(source_content) > 15000 else source_content

        prompt = self.TTS_SCRIPT_PROMPT.format(
            product_name=p_name,
            features=features,
            core_values=core_values,
            source_content=safe_content
        )

        try:
            print(f"  Đang tạo TTS script cho: {p_name}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Bạn là biên tập viên kịch bản voice-over. Chỉ trả về đoạn text thuần tiếng Việt, không dùng bất kỳ ký hiệu đặc biệt nào."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            script = response.choices[0].message.content.strip()
            # Post-process: loại bỏ tất cả ký hiệu không mong muốn
            script = self._clean_tts_script(script)
            return script
        except Exception as e:
            return f"Lỗi tạo TTS script: {e}"

    def _clean_tts_script(self, text: str) -> str:
        """Loại bỏ tất cả ký hiệu markdown, emoji, heading khỏi TTS script."""
        import re
        # Xóa emoji
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
                      r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF'
                      r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF'
                      r'\U0000FE00-\U0000FE0F\U0000200D]+', '', text)
        # Xóa markdown heading
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Xóa bold/italic
        text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
        # Xóa markdown links
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Xóa dấu --- separator
        text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
        # Xóa CJK
        text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', '', text)
        # Xóa dòng trống thừa
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # ===================== LIKEPION BIO GENERATION =====================

    def create_likepion_bio(self, product_info: Dict, source_url: str = "") -> str:
        """
        Tạo bio/about ngắn gọn (80-150 từ) cho profile Likepion entity.
        Output: plain text thuần.
        """
        p_name = product_info.get('product_name', 'Sản phẩm')
        features = ", ".join(product_info.get('features', [])) if isinstance(product_info.get('features'), list) else str(product_info.get('features', ''))
        core_values = ", ".join(product_info.get('core_values', [])) if isinstance(product_info.get('core_values'), list) else str(product_info.get('core_values', ''))

        prompt = self.LIKEPION_BIO_PROMPT.format(
            product_name=p_name,
            features=features,
            core_values=core_values,
            source_url=source_url
        )

        try:
            print(f" Đang tạo Likepion bio cho: {p_name}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Bạn là chuyên gia viết content ngắn gọn cho profile doanh nghiệp. Chỉ trả về đoạn text thuần tiếng Việt."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=400
            )
            bio = response.choices[0].message.content.strip()
            # Clean
            bio = self._clean_tts_script(bio)  # Dùng chung hàm clean
            return bio
        except Exception as e:
            return f"Lỗi tạo Likepion bio: {e}"


    # ===================== BACKLINK CONTENT WRITE (4-FACTOR) =====================

    # Prompt template riêng cho từng loại backlink
    # [[AI_TOPIC]] = data cào được từ URL (đã được gộp và lọc sạch)
    # {keyword} = từ khóa người dùng nhập
    # {word_count} = số từ mục tiêu
    BACKLINK_PROMPTS = {
        # [[AI_TOPIC]]    = data cào từ URL đã lọc sạch
        # [[LANG_FOR_AI]] = tên ngôn ngữ đầy đủ (Vietnamese, English...)
        # {keyword}       = từ khóa người dùng nhập
        # {word_count}    = số từ mục tiêu

        # --- LIKEPION ---
        "likepion": """[CHUA CO PROMPT - can bo sung]""",
        "likepion_title": """[CHUA CO PROMPT TITLE - can bo sung]""",

        # --- SOCIAL ---
        # Title cho social post
        "social_title": """Write a title social post in a professional tone about: [[AI_TOPIC]]. You write in [[LANG_FOR_AI]] language. Please write only one title and do not include the expanded content of that title. Titles do not include numbers at the beginning.""",
        # Content cho social post
        "social": """Write a 500+ character social post in a professional tone about: [[AI_TOPIC]]. You write in [[LANG_FOR_AI]] language. You do not need to write any contact details or sample content. You can use up to 5 emojis. Do not include an introductory statement like 'Here is; Hello; Welcome to; Article about'. Focus just on providing the requested content.""",

        # --- BLOG 2.0 ---
        "blog20_title": """You are a specialized title-generation expert for the [[TOPIC]] industry, with a deep understanding of E-E-A-T and click-through rate optimization. Your sole function is to generate 1 [[LANGUAGE_AI]] title for an article to be published on [[URL_AI]], using the keywords in [[KEYWORD]]. The following mandatory directives must be followed without exception: 1. Creative Variation Mandate (CRITICAL): To ensure every generated title is unique in both form and substance, you must systematically vary the creative angle. For each execution, choose a different archetype from the list below. Do not reuse the same archetype or a similar phrasing style consecutively. This variation is non-negotiable. Benefit-Oriented: Focus on the value or positive outcome for the reader. Problem/Solution: Address a common pain point and present the content as the solution. Intrigue/Curiosity: Pose a compelling question or statement that sparks curiosity without being clickbait. Direct Guide/How-To: Clearly state that the content is an instructional or definitive guide. Authoritative Statement: Present a definitive or expert take. 2. Content Quality: The title must be 50-70 characters long (max 120 characters), naturally integrate the [[KEYWORD]], be highly engaging, and professional. Do not use punctuation like "!" or "?". 3. Forbidden Content: You must not generate generic placeholder titles. The use of terms like "Untitled", "No Title", or their equivalent translations is strictly forbidden. The title must always be meaningful. 4. Mandatory Output Directive: You MUST generate a meaningful title that fulfills all other directives. Failure to produce a valid output is not an option. 5. Final Output Format: Your entire response must be a single, valid JSON object and nothing else. There must be no text, explanations, or markdown fences. The JSON object must contain a single key: "title". Example of correct format: {"title": "This Is A Correctly Formatted Sample Title"}""",
        "blog20": """You are a world-class SEO article writing expert in the [[KEYWORD]] industry with a deep understanding of E-E-A-T. Your task is to write a unique and high-quality article to be published on the website [[URL_AI]], using the keywords from [[KEYWORD]]. The article MUST be informed by the following crawled and filtered website data of the client: [[TOPIC]]. Use this data to ensure the content reflects the client's actual products, services, and brand — do NOT write generic content. You must strictly adhere to the following instructions: Mandatory Uniqueness and Anti-Repetition Protocol (CRITICAL): This is the most important directive. Vary the Core Angle and Rhetorical Approach for every execution. Language: [[LANGUAGE_AI]]. Language Purity Protocol (CRITICAL): The entire article must be written exclusively in [[LANGUAGE_AI]]. Absolutely no words or phrases from other languages are permitted. Length (MANDATORY RANGE): The article MUST be between [[MIN_LENGTH]] and [[TEXT_LENGTH]] characters. This range is strict — writing less than [[MIN_LENGTH]] characters is a failure. You MUST write enough to reach the minimum. Structure: Begin with a compelling introductory paragraph. Develop content using AIDA, PAS, 4Ps, or FAB framework logic (do not label the framework). Tone: Professional, fluent, coherent. Forbidden Words: Never use: conclusion, summary, finally, in the end, overall, ultimately. HTML Formatting: Every paragraph must be enclosed in <p></p> tags. No bullet points, numbered lists, or <br> tags. Headings: Use <h2> and <h3> HTML tags in sentence case. No colon in headings. First heading must be <h2>. Last heading must be <h3>. Final paragraph has no heading. Links (STRICT): Exactly 2 hyperlinks total. First: <a href="[[URL_AI]]">[[TEXT_LINK_AI]]</a> naturally in first paragraph. Second: <a href="[[URL_AI]]">[[URL_AI]]</a> naturally in latter half, not in final paragraph. Images: Insert [[TOTAL_IMAGE_EN]] ([[TOTAL_IMAGE]]) [[TAG_IMAGE_AI]] tags at varied positions, NOT inside <p> tags and NOT in the final paragraph. Output: Wrap everything in a single <article> tag. No intro phrases like 'Here is...' or 'Certainly...'.""",
    }

    # Map language code → full name dùng cho [[LANG_FOR_AI]]
    LANGUAGE_NAMES = {
        "vi": "Vietnamese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "th": "Thai",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "id": "Indonesian",
    }

    LANGUAGE_INSTRUCTIONS = {
        "vi": "QUAN TRONG: Toan bo bai viet PHAI bang TIENG VIET chuan, khong lan tieng Anh hay ngon ngu khac.",
        "en": "IMPORTANT: Write the ENTIRE article in ENGLISH only. Professional and fluent.",
        "ja": "Write the entire article in Japanese only. Natural and fluent.",
        "ko": "Write the entire article in Korean only. Natural and fluent.",
        "zh": "Write the entire article in Chinese only. Natural and fluent.",
        "th": "Write the entire article in Thai only. Natural and fluent.",
    }

    def generate_title_only(
        self,
        keyword: str,
        ai_topic: str,
        backlink_type: str = "social",
        language: str = "vi",
        url: str = "",
    ) -> str:
        """
        Sinh title riêng — dùng để chạy song song với crawl.
        Returns: title string
        """
        bl_type = backlink_type.lower().strip()
        lang_code = language.lower().strip()
        lang_full_name = self.LANGUAGE_NAMES.get(lang_code, language.capitalize())
        title_key = f"{bl_type}_title"

        if title_key not in self.BACKLINK_PROMPTS:
            return ""

        p = self.BACKLINK_PROMPTS[title_key]
        p = p.replace("[[AI_TOPIC]]", ai_topic)
        p = p.replace("[[LANG_FOR_AI]]", lang_full_name)
        p = p.replace("[[TOPIC]]", ai_topic[:300])
        p = p.replace("[[LANGUAGE_AI]]", lang_full_name)
        p = p.replace("[[URL_AI]]", url)
        p = p.replace("[[KEYWORD]]", keyword)

        try:
            raw = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Output only the title as instructed."},
                    {"role": "user", "content": f"{p}\nKEYWORD: {keyword}\nOutput ONLY the title. One single line. No explanation."},
                ],
                temperature=0.7,
                max_tokens=150,
            ).choices[0].message.content.strip()

            # blog20 trả về JSON {"title": "..."}
            if bl_type == "blog20":
                import json as _json
                try:
                    return _json.loads(raw).get("title", raw)[:120]
                except Exception:
                    return raw.strip('"').strip()[:120]
            return raw
        except Exception as e:
            return ""

    def generate_content_only(
        self,
        keyword: str,
        ai_topic: str,
        backlink_type: str = "social",
        language: str = "vi",
        word_count: int = 800,
        url: str = "",
        text_link: str = "",
        total_image: int = 2,
        tag_image: str = "",
        text_length: int = 5000,
    ) -> str:
        """
        Sinh content riêng — nhận ai_topic đã có cấu trúc từ content_write.py.
        Có retry tự động nếu blog20 trả về bài quá ngắn.
        Returns: article string
        """
        bl_type = backlink_type.lower().strip()
        lang_code = language.lower().strip()
        lang_full_name = self.LANGUAGE_NAMES.get(lang_code, language.capitalize())

        NUM_TO_WORDS = {1:"one",2:"two",3:"three",4:"four",5:"five",
                        6:"six",7:"seven",8:"eight",9:"nine",10:"ten"}
        total_image_en = NUM_TO_WORDS.get(total_image, str(total_image))
        text_link_val = text_link or keyword
        min_length = int(text_length * 0.85)

        def build_prompt(key: str) -> str:
            p = self.BACKLINK_PROMPTS.get(key, "")
            p = p.replace("[[AI_TOPIC]]", ai_topic)      # legacy alias
            p = p.replace("[[TOPIC]]", ai_topic)          # full crawled + filtered data
            p = p.replace("[[LANG_FOR_AI]]", lang_full_name)
            p = p.replace("[[LANGUAGE_AI]]", lang_full_name)
            p = p.replace("[[URL_AI]]", url)
            p = p.replace("[[KEYWORD]]", keyword)
            p = p.replace("[[TEXT_LENGTH]]", str(text_length))
            p = p.replace("[[MIN_LENGTH]]", str(min_length))
            p = p.replace("[[TAG_IMAGE_AI]]", tag_image)
            p = p.replace("[[TOTAL_IMAGE]]", str(total_image))
            p = p.replace("[[TOTAL_IMAGE_EN]]", total_image_en)
            p = p.replace("[[TEXT_LINK_AI]]", text_link_val)
            try:
                p = p.format(keyword=keyword, word_count=word_count)
            except Exception:
                pass
            return p

        if bl_type not in self.BACKLINK_PROMPTS:
            return f"Loi viet bai: backlink_type '{bl_type}' chua co prompt."

        content_sys = build_prompt(bl_type)

        try:
            print(f"  Dang viet [{bl_type}] keyword='{keyword}' lang='{lang_full_name}'...")

            def call_ai(system: str, max_tok: int = 3000) -> str:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"KEYWORD: {keyword}\nWrite the content now."},
                    ],
                    temperature=0.7,
                    max_tokens=max_tok,
                ).choices[0].message.content.strip()

            article = call_ai(content_sys)
            article = self._deduplicate_article(article)
            if lang_code == "vi":
                article = self._fix_language_artifacts(article)

            # ── RETRY nếu blog20 quá ngắn ──────────────────────────────────
            if bl_type == "blog20":
                for retry in range(2):
                    if len(article) >= int(text_length * 0.80):
                        break
                    print(f"  [blog20] Bai qua ngan ({len(article)} chars < {int(text_length*0.80)}), retry {retry+1}...")
                    retry_sys = (
                        content_sys
                        + f"\n\nCRITICAL: The previous attempt was too short. "
                        f"You MUST write at least {min_length} characters this time. "
                        f"Expand all sections with more detail and depth."
                    )
                    article = call_ai(retry_sys)
                    article = self._deduplicate_article(article)
                    if lang_code == "vi":
                        article = self._fix_language_artifacts(article)

            return article

        except Exception as e:
            return f"Loi viet bai: {e}"

    def write_backlink_content(
        self,
        keyword: str,
        crawled_content: str,
        backlink_type: str = "likepion",
        language: str = "vi",
        word_count: int = 800,
        # Blog20 extra params
        url: str = "",
        text_link: str = "",
        total_image: int = 2,
        tag_image: str = "",
        text_length: int = 5000,
    ) -> tuple:
        """
        Viết bài backlink dựa trên 4 yếu tố:
        1. keyword    — từ khóa SEO KH muốn lên top
        2. crawled_content — nội dung cào từ website KH
        3. backlink_type  — loại dịch vụ backlink
        4. language       — ngôn ngữ bài viết

        Returns: tuple (title: str, article: str)
        """
        bl_type = backlink_type.lower().strip()
        lang_code = language.lower().strip()
        lang_full_name = self.LANGUAGE_NAMES.get(lang_code, language.capitalize())

        # Helper: build 1 prompt (replace tat ca bien)
        NUM_TO_WORDS = {1:"one",2:"two",3:"three",4:"four",5:"five",
                        6:"six",7:"seven",8:"eight",9:"nine",10:"ten"}
        total_image_en = NUM_TO_WORDS.get(total_image, str(total_image))
        text_link_val = text_link or keyword  # fallback to keyword neu khong co

        def build_prompt(key: str) -> str:
            p = self.BACKLINK_PROMPTS.get(key, "")
            # Common variables
            p = p.replace("[[AI_TOPIC]]", ai_topic)
            p = p.replace("[[LANG_FOR_AI]]", lang_full_name)
            # Blog20 specific variables
            p = p.replace("[[TOPIC]]", ai_topic)
            p = p.replace("[[LANGUAGE_AI]]", lang_full_name)
            p = p.replace("[[URL_AI]]", url)
            p = p.replace("[[KEYWORD]]", keyword)
            p = p.replace("[[TEXT_LENGTH]]", str(text_length))
            p = p.replace("[[TAG_IMAGE_AI]]", tag_image)
            p = p.replace("[[TOTAL_IMAGE]]", str(total_image))
            p = p.replace("[[TOTAL_IMAGE_EN]]", total_image_en)
            p = p.replace("[[TEXT_LINK_AI]]", text_link_val)
            # Python format placeholders (safe)
            try:
                p = p.format(keyword=keyword, word_count=word_count)
            except Exception:
                pass
            return p

        # Helper: gọi AI 1 lần
        def call_ai(system: str, user: str, max_tok: int = 3000) -> str:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
                max_tokens=max_tok,
            )
            return resp.choices[0].message.content.strip()

        # Giới hạn [[AI_TOPIC]] theo loại —
        # title-only types chỉ cần ~500 ký tự đầu
        TITLE_ONLY_TYPES = {"likepion"}
        SHORT_TOPIC_TYPES = {"likepion", "social", "blog20"}

        if bl_type in SHORT_TOPIC_TYPES:
            ai_topic = crawled_content[:800].strip()
        else:
            ai_topic = crawled_content[:20000] + "..." if len(crawled_content) > 20000 else crawled_content

        title_key = f"{bl_type}_title"
        has_title_prompt = title_key in self.BACKLINK_PROMPTS

        print(f"  Dang viet [{bl_type}] keyword='{keyword}' lang='{lang_full_name}'...")

        try:
            # ── TITLE ──────────────────────────────────────────────────────────
            title_str = ""
            if has_title_prompt:
                title_sys = build_prompt(title_key)
                raw_title = call_ai(
                    system=title_sys,
                    user=f"KEYWORD: {keyword}\nOutput ONLY the title. One single line. No explanation. No numbering.",
                    max_tok=150,
                )
                # blog20 title tra ve JSON {"title": "..."} → parse ra
                if bl_type == "blog20":
                    import json as _json
                    try:
                        parsed = _json.loads(raw_title)
                        title_str = parsed.get("title", raw_title)[:120]
                    except Exception:
                        # Neu khong parse duoc JSON, lay nguyen chuoi
                        title_str = raw_title.strip('"').strip()[:120]
                else:
                    title_str = raw_title

            # ── CONTENT ────────────────────────────────────────────────────────
            content_str = ""
            if bl_type not in TITLE_ONLY_TYPES:
                content_sys = build_prompt(bl_type)
                content_str = call_ai(
                    system=content_sys,
                    user=f"KEYWORD: {keyword}\nWrite the content now.",
                    max_tok=3000,
                )
                content_str = self._deduplicate_article(content_str)
                if lang_code == "vi":
                    content_str = self._fix_language_artifacts(content_str)
            else:
                # likepion: chỉ có title, không có content
                if not title_str:
                    content_sys = build_prompt(bl_type)
                    title_str = call_ai(
                        system=content_sys,
                        user=f"KEYWORD: {keyword}\nOutput ONLY the title. One single line.",
                        max_tok=80,
                    )

            return title_str, content_str

        except Exception as e:
            return "", f"Loi viet bai: {e}"


# ============================================================================
#  VIVIBE TTS CLIENT — Tích hợp trực tiếp
# ============================================================================

class VivibeTTSClient:
    """
    Client gọi Vivibe TTS API (api.lucylab.io/json-rpc).
    Tạo audio voice-over tiếng Việt từ text.
    """

    API_URL = "https://api.lucylab.io/json-rpc"
    MAX_RETRIES = 3

    # Danh sách giọng đọc sẵn có
    VOICES = {
        "duc_trung":   {"id": "7Tb4dvGZyJMPjnnfxVBgik", "name": "Đức Trung",  "gender": "nam", "region": "miền bắc", "use": "podcast"},
        "dang_khoi":   {"id": "dTqpG5DfoqexJzvb2DK1YE", "name": "Đăng Khôi",  "gender": "nam", "region": "miền bắc", "use": "review"},
        "chi_chi":     {"id": "nqak8C85bsAG5mihyunRkj", "name": "Chi Chi",    "gender": "nữ",  "region": "miền nam", "use": "review"},
        "quang_anh":   {"id": "24oEtXGic7NhDjXzmDbDvt", "name": "Quang Anh",  "gender": "nam", "region": "miền bắc", "use": "tự nhiên"},
        "vy_tin_tuc":  {"id": "8GNXzqzEk4AXq64rmSwqtW", "name": "Vy Tin Tức", "gender": "nữ",  "region": "miền bắc", "use": "tin tức"},
        "chi_mai":     {"id": "cLZiqtzLcKYqwYrWJemAJH", "name": "Chi Mai",    "gender": "nữ",  "region": "miền bắc", "use": "đọc truyện"},
        "bao_anh":     {"id": "cACFxDTEUiNBcCSpmJbgwj", "name": "Bảo Anh",    "gender": "nữ",  "region": "miền bắc", "use": "đọc truyện"},
        "duc_anh":     {"id": "2rECfs5gZFwLVmbGyfNDrE", "name": "Đức Anh",    "gender": "nam", "region": "miền bắc", "use": "review"},
        "my_review":   {"id": "vcXEe1p3FxPfpswf3BhwbG", "name": "My Review",  "gender": "nữ",  "region": "miền nam", "use": "review"},
    }

    DEFAULT_VOICE = "vy_tin_tuc"

    def __init__(self, auth_token: str):
        """
        Args:
            auth_token: Firebase Auth Bearer token (lấy từ vivibe.app DevTools)
        """
        self.auth_token = auth_token
        self.headers = {
            "Content-Type": "application/json",
            "Origin": "https://www.vivibe.app",
            "Referer": "https://www.vivibe.app/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Authorization": f"Bearer {auth_token}",
        }

    def _call_rpc(self, method: str, input_data: dict, mappings: dict = None) -> dict:
        """Gọi JSON-RPC endpoint với retry."""
        payload = {"method": method, "input": input_data}
        if mappings:
            payload["mappings"] = mappings

        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = requests.post(self.API_URL, headers=self.headers, json=payload, timeout=120)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}: {resp.text[:300]}")
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(1.5 * attempt)
        raise last_err

    def generate_tts(self, text: str, voice_key: str = None, speed: float = 1.0) -> str:
        """
        Tạo audio TTS từ text.

        Args:
            text: Văn bản cần chuyển giọng nói
            voice_key: Key giọng (ví dụ: 'vy_tin_tuc', 'duc_trung'). None = default.
            speed: Tốc độ đọc (0.5 - 2.0)

        Returns:
            str: URL file audio (.wav)
        """
        voice_key = voice_key or self.DEFAULT_VOICE
        voice_info = self.VOICES.get(voice_key, self.VOICES[self.DEFAULT_VOICE])
        voice_id = voice_info["id"]

        result = self._call_rpc("tts", {
            "text": text,
            "userVoiceId": voice_id,
            "speed": speed,
            "blockVersion": 0,
        })

        if "result" in result and "url" in result["result"]:
            credits = result["result"].get("creditsRemaining", "?")
            print(f"    Audio OK — Credits còn: {credits}")
            return result["result"]["url"]
        else:
            raise Exception(f"TTS Error: {result}")

    def generate_and_download(self, text: str, output_path: str,
                              voice_key: str = None, speed: float = 1.0) -> str:
        """
        Generate TTS + download file audio về local.

        Args:
            text: Văn bản
            output_path: Đường dẫn file output (.wav)
            voice_key: Key giọng đọc
            speed: Tốc độ

        Returns:
            str: Path file đã lưu
        """
        url = self.generate_tts(text, voice_key, speed)

        resp = requests.get(url, timeout=60)
        if resp.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"    Đã lưu: {output_path} ({size_kb:.0f} KB)")
            return output_path
        else:
            raise Exception(f"Download Error: {resp.status_code}")

    def generate_long_text(self, text: str, output_path: str,
                           voice_key: str = None, speed: float = 1.0,
                           pause_ms: int = 300) -> str:
        """
        Generate TTS cho đoạn text dài bằng cách chia câu, tạo audio từng block,
        rồi merge thành 1 file. Cần pydub + ffmpeg.

        Args:
            text: Văn bản dài
            output_path: Đường dẫn file output
            voice_key: Key giọng
            speed: Tốc độ
            pause_ms: Pause giữa các câu (ms)

        Returns:
            str: Path file đã merge
        """
        import re
        try:
            from pydub import AudioSegment
        except ImportError:
            print(" Cần cài pydub: pip install pydub (và ffmpeg)")
            # Fallback: gửi toàn bộ text 1 lần
            return self.generate_and_download(text, output_path, voice_key, speed)

        # Chia câu
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

        if not sentences:
            return self.generate_and_download(text, output_path, voice_key, speed)

        print(f"    Chia thành {len(sentences)} câu...")

        combined = AudioSegment.empty()
        temp_files = []

        for i, sentence in enumerate(sentences):
            print(f"     [{i+1}/{len(sentences)}] {sentence[:50]}...")
            try:
                url = self.generate_tts(sentence, voice_key, speed)
                resp = requests.get(url, timeout=60)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
                    temp_files.append(tmp_path)

                audio = AudioSegment.from_wav(tmp_path)
                combined += audio

                if i < len(sentences) - 1 and pause_ms > 0:
                    combined += AudioSegment.silent(duration=pause_ms)

            except Exception as e:
                print(f"    Block {i+1} lỗi: {e}")

        # Export
        fmt = "mp3" if output_path.lower().endswith(".mp3") else "wav"
        combined.export(output_path, format=fmt)

        dur = len(combined) / 1000
        m, s = int(dur // 60), int(dur % 60)
        print(f"    Merged → {output_path} ({m}:{s:02d})")

        # Cleanup temp
        for p in temp_files:
            try:
                os.unlink(p)
            except OSError:
                pass

        return output_path


def format_business_info(info: BusinessInfo) -> str:
    """Format kết quả để hiển thị đẹp"""
    output = []
    output.append("\n" + "="*70)
    output.append("📊 KẾT QUẢ TRÍCH XUẤT THÔNG TIN DOANH NGHIỆP")
    output.append("="*70)
    
    output.append("\n🎯 GIÁ TRỊ CỐT LÕI (Core Values):")
    output.append("-" * 40)
    for i, value in enumerate(info.core_values, 1):
        output.append(f"  {i}. {value}")
    
    output.append("\n⭐ SỰ KHÁC BIỆT (Differentiators):")
    output.append("-" * 40)
    for i, diff in enumerate(info.differentiators, 1):
        output.append(f"  {i}. {diff}")
    
    output.append("\n🔧 CHUYÊN MÔN (Expertise):")
    output.append("-" * 40)
    for i, exp in enumerate(info.expertise, 1):
        output.append(f"  {i}. {exp}")
    
    output.append("\n📌 SỨ MỆNH:")
    output.append(f"  {info.mission}")
    
    output.append("\n👁️ TẦM NHÌN:")
    output.append(f"  {info.vision}")
    
    output.append("\n📝 TÓM TẮT:")
    output.append(f"  {info.summary}")
    
    output.append("\n🔗 NGUỒN DỮ LIỆU:")
    for url in info.source_urls[:5]:
        output.append(f"  • {url}")
    if len(info.source_urls) > 5:
        output.append(f"  ... và {len(info.source_urls) - 5} trang khác")
    
    output.append("\n" + "="*70)
    
    return "\n".join(output)


def save_result_to_file(info: BusinessInfo, filepath: str):
    data = {
        "core_values": info.core_values,
        "differentiators": info.differentiators,
        "expertise": info.expertise,
        "mission": info.mission,
        "vision": info.vision,
        "summary": info.summary,
        "source_urls": info.source_urls,
        "raw_evidence": info.raw_evidence
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, ensure_ascii=False, indent=2, fp=f)
    
    print(f" Đã lưu kết quả vào: {filepath}")


if __name__ == "__main__":
    # Test với dữ liệu mẫu
    sample_data = [
        {
            "url": "https://example.com/about",
            "title": "Giới thiệu về công ty",
            "meta_description": "Chúng tôi là công ty hàng đầu trong lĩnh vực công nghệ",
            "headings": ["Giá trị cốt lõi", "Tại sao chọn chúng tôi", "Dịch vụ"],
            "paragraphs": [
                "Giá trị cốt lõi của chúng tôi là Chính trực - Sáng tạo - Đồng hành",
                "Sự khác biệt của chúng tôi nằm ở đội ngũ chuyên gia giàu kinh nghiệm",
                "Chuyên môn: Phát triển phần mềm, Tư vấn chuyển đổi số"
            ]
        }
    ]
    
    extractor = AIContentExtractor()
    result = extractor.extract(sample_data)
    print(format_business_info(result))
