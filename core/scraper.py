"""
Multi-Level Website Scraper
Cào đa tầng website doanh nghiệp để trích xuất nội dung
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Dict, List, Optional
from dataclasses import dataclass, field
from tqdm import tqdm
import time
import re
import json


@dataclass
class ImageInfo:
    """Thông tin về một ảnh"""
    url: str
    alt: str
    title: str
    context: str  # Text xung quanh ảnh


@dataclass
class StructuredData:
    """Dữ liệu cấu trúc trích xuất từ HTML (JSON-LD, breadcrumb, price...)"""
    # JSON-LD
    jsonld_type: str = ""             # @type chính (Product, Article, WebPage...)
    jsonld_name: str = ""             # Tên sản phẩm/bài viết từ JSON-LD
    jsonld_description: str = ""      # Mô tả từ JSON-LD
    jsonld_price: str = ""            # Giá từ JSON-LD (offers.price)
    jsonld_brand: str = ""            # Thương hiệu từ JSON-LD
    jsonld_sku: str = ""              # SKU từ JSON-LD
    jsonld_image: str = ""            # URL ảnh chính từ JSON-LD
    jsonld_raw: Dict = field(default_factory=dict)  # Raw JSON-LD Product data
    
    # Breadcrumb
    breadcrumb: List[str] = field(default_factory=list)  # ["Trang chủ", "Máy trợ thính", "Acosound"]
    breadcrumb_depth: int = 0         # Số tầng breadcrumb (sâu = chi tiết hơn)
    
    # Price
    has_price: bool = False
    price_text: str = ""              # Giá hiển thị chính (thường là giá sale)
    regular_price: str = ""           # Giá gốc (trước KM, từ <del> hoặc class)
    sale_price: str = ""              # Giá khuyến mãi (từ <ins> hoặc class)
    
    # Spec table
    has_spec_table: bool = False
    spec_rows: List[List[str]] = field(default_factory=list)  # [["Thương hiệu", "Acosound"], ...]
    
    # Open Graph
    og_type: str = ""                 # product, article, website...
    og_title: str = ""


@dataclass
class PageContent:
    """Lưu trữ nội dung của một trang"""
    url: str
    title: str
    meta_description: str
    headings: List[str]
    paragraphs: List[str]
    images: List[ImageInfo]  # Danh sách ảnh
    full_text: str
    depth: int
    structured: StructuredData = field(default_factory=StructuredData)  # Dữ liệu cấu trúc


@dataclass
class ScraperConfig:
    """Cấu hình cho scraper"""
    max_depth: int = 3                    # Độ sâu tối đa khi cào
    max_pages: int = 50                   # Số trang tối đa
    delay_between_requests: float = 0.5   # Delay giữa các request (giây)
    timeout: int = 30                     # Timeout cho mỗi request
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    # Các pattern URL cần bỏ qua
    exclude_patterns: List[str] = field(default_factory=lambda: [
        r'\.pdf$', r'\.jpg$', r'\.png$', r'\.gif$', r'\.svg$',
        r'\.css$', r'\.js$', r'\.zip$', r'\.doc$', r'\.xlsx$',
        r'/wp-admin/', r'/wp-includes/', r'/cart/', r'/checkout/',
        r'facebook\.com', r'twitter\.com', r'linkedin\.com', r'youtube\.com',
        r'#', r'mailto:', r'tel:', r'javascript:'
    ])
    
    # Các từ khóa để ưu tiên cào (liên quan đến thông tin doanh nghiệp)
    priority_keywords: List[str] = field(default_factory=lambda: [
        'about', 've-chung-toi', 'gioi-thieu', 'gia-tri', 'value',
        'why-us', 'tai-sao-chon', 'dich-vu', 'service', 'chuyen-mon',
        'expertise', 'mission', 'vision', 'su-menh', 'tam-nhin',
        'difference', 'khac-biet', 'core', 'philosophy', 'triet-ly',
        'team', 'doi-ngu', 'history', 'lich-su', 'story', 'cau-chuyen'
    ])


class MultiLevelScraper:
    """
    Scraper đa tầng cho website doanh nghiệp
    
    Flow:
    1. Bắt đầu từ URL gốc (Level 0)
    2. Tìm tất cả internal links
    3. Ưu tiên các link có keyword quan trọng
    4. Cào nội dung từng trang
    5. Tiếp tục với các link con (Level 1, 2, ...)
    """
    
    def __init__(self, base_url: str, config: Optional[ScraperConfig] = None):
        self.base_url = base_url.rstrip('/')
        self.config = config or ScraperConfig()
        self.domain = urlparse(base_url).netloc
        
        # Tracking
        self.visited_urls: Set[str] = set()
        self.pages: List[PageContent] = []
        self.failed_urls: List[str] = []
        
        import threading
        self._failed_lock = threading.Lock()
        self._thread_local = threading.local()  # Session riêng cho mỗi thread
        
        # Lưu headers config — sẽ dùng khi tạo session per-thread
        self._session_headers = {
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }
    
    def _is_valid_url(self, url: str) -> bool:
        """Kiểm tra URL có hợp lệ để cào không"""
        # Phải cùng domain
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != self.domain:
            return False
        
        # Không match các pattern exclude
        for pattern in self.config.exclude_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        return True
    
    def _normalize_url(self, url: str, current_url: str) -> Optional[str]:
        """Chuẩn hóa URL về dạng tuyệt đối"""
        if not url:
            return None
        
        # Loại bỏ fragment (#)
        url = url.split('#')[0]
        
        # Chuyển về absolute URL
        full_url = urljoin(current_url, url)
        
        # Loại bỏ trailing slash để tránh duplicate
        full_url = full_url.rstrip('/')
        
        return full_url if self._is_valid_url(full_url) else None
    
    def _get_priority_score(self, url: str) -> int:
        """Tính điểm ưu tiên cho URL dựa trên keywords"""
        score = 0
        url_lower = url.lower()
        
        for keyword in self.config.priority_keywords:
            if keyword in url_lower:
                score += 10
        
        return score
    
    def _extract_structured_data(self, soup: BeautifulSoup, url: str) -> StructuredData:
        """
        Trích xuất dữ liệu cấu trúc TRƯỚC KHI decompose tags.
        Phải gọi TRƯỚC khi xóa <script>, <nav>, <table>.
        """
        sd = StructuredData()
        
        # ========== 1. JSON-LD (từ <script type="application/ld+json">) ==========
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or "")
                self._parse_jsonld(data, sd)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # ========== 2. BREADCRUMB HTML (từ <nav>, <ol>, <div> class=breadcrumb) ==========
        bc_patterns = [
            ('nav', {'class': re.compile(r'breadcrumb', re.I)}),
            ('ol', {'class': re.compile(r'breadcrumb', re.I)}),
            ('ul', {'class': re.compile(r'breadcrumb', re.I)}),
            ('div', {'class': re.compile(r'breadcrumb', re.I)}),
        ]
        if not sd.breadcrumb:  # Chưa có từ JSON-LD
            for tag_name, attrs in bc_patterns:
                bc_elem = soup.find(tag_name, attrs)
                if bc_elem:
                    items = []
                    for li in bc_elem.find_all(['li', 'a']):
                        text = li.get_text(strip=True)
                        if text and len(text) < 60 and text not in ('»', '>', '/', '|'):
                            if text not in items:  # Tránh duplicate
                                items.append(text)
                    if items:
                        sd.breadcrumb = items[:8]
                        sd.breadcrumb_depth = len(items)
                        break
        
        # ========== 3. GIÁ SẢN PHẨM (tách rõ giá gốc vs giá sale) ==========
        # Strategy: tìm container giá (class chứa "price"), 
        # trong đó <del>=giá gốc, <ins>=giá sale
        _price_class_re = re.compile(r'price|gia', re.I)
        
        for elem in soup.find_all(class_=_price_class_re)[:15]:
            text = elem.get_text(strip=True)
            if not text or len(text) > 80 or not re.search(r'\d', text):
                continue
            
            sd.has_price = True
            
            # Tìm <del> (giá gốc gạch ngang) và <ins> (giá sale) trong container
            del_tag = elem.find('del')
            ins_tag = elem.find('ins')
            
            if del_tag and ins_tag:
                # WooCommerce pattern: <del>giá gốc</del> <ins>giá sale</ins>
                del_text = del_tag.get_text(strip=True)
                ins_text = ins_tag.get_text(strip=True)
                if re.search(r'\d', del_text):
                    sd.regular_price = del_text[:40]
                if re.search(r'\d', ins_text):
                    sd.sale_price = ins_text[:40]
                sd.price_text = sd.sale_price or sd.regular_price
                break
            elif del_tag and not ins_tag:
                # Chỉ có giá gốc (gạch ngang, hết hàng?)
                del_text = del_tag.get_text(strip=True)
                if re.search(r'\d', del_text):
                    sd.regular_price = del_text[:40]
                    sd.price_text = sd.regular_price
                break
            else:
                # Không có del/ins — check class cụ thể
                elem_classes = ' '.join(elem.get('class', []))
                lower_cls = elem_classes.lower()
                
                if any(kw in lower_cls for kw in ['regular', 'origin', 'old', 'list', 'goc', 'cu']):
                    if not sd.regular_price:
                        sd.regular_price = text[:40]
                elif any(kw in lower_cls for kw in ['sale', 'current', 'new', 'special', 'final', 'khuyen-mai', 'km']):
                    if not sd.sale_price:
                        sd.sale_price = text[:40]
                else:
                    # Class chung chung — lấy làm giá chính nếu chưa có
                    if not sd.price_text:
                        sd.price_text = text[:40]
        
        # Reconcile: đảm bảo price_text luôn có giá trị
        if sd.has_price and not sd.price_text:
            sd.price_text = sd.sale_price or sd.regular_price
        
        # ========== 4. BẢNG THÔNG SỐ (<table>) ==========
        for table in soup.find_all('table')[:5]:
            rows = []
            for tr in table.find_all('tr')[:15]:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells and any(len(c) > 2 for c in cells):
                    rows.append(cells)
            if len(rows) >= 2:  # Ít nhất 2 dòng mới coi là spec table
                sd.has_spec_table = True
                sd.spec_rows = rows[:15]
                break
        
        # ========== 5. OPEN GRAPH ==========
        og_type_tag = soup.find('meta', property='og:type')
        if og_type_tag:
            sd.og_type = og_type_tag.get('content', '')
        og_title_tag = soup.find('meta', property='og:title')
        if og_title_tag:
            sd.og_title = og_title_tag.get('content', '')
        
        return sd
    
    def _parse_jsonld(self, data, sd: StructuredData):
        """
        Parse JSON-LD data (có thể là dict, list, hoặc chứa @graph).
        Ưu tiên tìm @type=Product, fallback sang Article/WebPage.
        """
        if isinstance(data, list):
            for item in data:
                self._parse_jsonld(item, sd)
            return
        
        if not isinstance(data, dict):
            return
        
        # Xử lý @graph
        if "@graph" in data:
            for item in data["@graph"]:
                self._parse_jsonld(item, sd)
            return
        
        item_type = data.get("@type", "")
        
        # ===== Product — ưu tiên cao nhất =====
        if item_type == "Product":
            sd.jsonld_type = "Product"
            sd.jsonld_name = str(data.get("name", ""))[:200]
            sd.jsonld_description = str(data.get("description", ""))[:500]
            sd.jsonld_sku = str(data.get("sku", ""))
            sd.jsonld_brand = str(data.get("brand", {}).get("name", "")) if isinstance(data.get("brand"), dict) else str(data.get("brand", ""))
            sd.jsonld_raw = data
            
            # Image
            img = data.get("image", "")
            if isinstance(img, list):
                sd.jsonld_image = str(img[0]) if img else ""
            elif isinstance(img, dict):
                sd.jsonld_image = str(img.get("url", ""))
            else:
                sd.jsonld_image = str(img)
            
            # Price (offers) — lấy cả price, lowPrice, highPrice
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                currency = offers.get("priceCurrency", "")
                
                # Giá chính (price hoặc lowPrice)
                price = offers.get("price", "")
                low_price = offers.get("lowPrice", "")
                high_price = offers.get("highPrice", "")
                
                if price:
                    sd.jsonld_price = f"{price} {currency}".strip()
                elif low_price:
                    sd.jsonld_price = f"{low_price} {currency}".strip()
                
                # Nếu có cả lowPrice và highPrice → ghi range
                if low_price and high_price and str(low_price) != str(high_price):
                    sd.jsonld_price = f"{low_price}~{high_price} {currency}".strip()
                
                if sd.jsonld_price:
                    sd.has_price = True
                    # Chỉ fill price_text nếu HTML chưa tìm được
                    if not sd.price_text and not sd.sale_price and not sd.regular_price:
                        sd.price_text = sd.jsonld_price
        
        # ===== BreadcrumbList =====
        elif item_type == "BreadcrumbList":
            items = data.get("itemListElement", [])
            if isinstance(items, list):
                bc_items = []
                for item in sorted(items, key=lambda x: x.get("position", 0)):
                    name = item.get("name", "")
                    if not name and isinstance(item.get("item"), dict):
                        name = item["item"].get("name", "")
                    if name:
                        bc_items.append(str(name))
                if bc_items and not sd.breadcrumb:  # Chỉ ghi nếu chưa có
                    sd.breadcrumb = bc_items
                    sd.breadcrumb_depth = len(bc_items)
        
        # ===== Article / WebPage — chỉ lưu nếu chưa có Product =====
        elif item_type in ("Article", "NewsArticle", "BlogPosting", "WebPage") and not sd.jsonld_type:
            sd.jsonld_type = item_type
            sd.jsonld_name = str(data.get("name", data.get("headline", "")))[:200]
            sd.jsonld_description = str(data.get("description", ""))[:500]

    def _extract_page_content(self, url: str, html: str, depth: int) -> PageContent:
        """Trích xuất nội dung từ HTML"""
        soup = BeautifulSoup(html, 'lxml')
        
        # ========== STRUCTURED DATA — TRƯỚC KHI DECOMPOSE ==========
        structured = self._extract_structured_data(soup, url)
        
        # ========== TRÍCH XUẤT ẢNH TRƯỚC KHI XÓA TAGS ==========
        images = self._extract_images(soup, url)
        if images:
            print(f"      🖼️ Tìm thấy {len(images)} ảnh trong trang")
        
        # Loại bỏ script, style, nav, footer
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
            tag.decompose()
        
        # Title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        
        # Meta description
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag and meta_tag.get('content'):
            meta_desc = meta_tag['content']
        
        # Headings (h1, h2, h3)
        headings = []
        for tag in ['h1', 'h2', 'h3']:
            for heading in soup.find_all(tag):
                text = heading.get_text(strip=True)
                if text and len(text) > 2:
                    headings.append(text)
        
        # Paragraphs — chỉ <p> và <li>, KHÔNG lấy div/span (gây duplicate nặng)
        paragraphs = []
        for p in soup.find_all(['p', 'li']):
            text = p.get_text(strip=True)
            if text and 20 < len(text) < 2000:
                if text not in paragraphs:
                    paragraphs.append(text)
        
        # Full text (cho AI phân tích)
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        full_text = main_content.get_text(separator='\n', strip=True) if main_content else ""
        
        return PageContent(
            url=url,
            title=title,
            meta_description=meta_desc,
            headings=headings,
            paragraphs=paragraphs[:50],  # Giới hạn 50 paragraphs
            images=images,
            full_text=full_text[:15000],  # Giới hạn 15k ký tự
            depth=depth,
            structured=structured
        )
    
    def _extract_images(self, soup: BeautifulSoup, page_url: str) -> List[ImageInfo]:
        """
        Trích xuất URL ảnh từ trang
        Lọc bỏ: icon, tracking pixel, ảnh quá nhỏ
        """
        images = []
        seen_urls = set()
        
        # Các pattern để loại bỏ ảnh không cần thiết (icon, logo, tracking, etc.)
        EXCLUDE_PATTERNS = [
            # Icon và logo
            r'icon', r'logo', r'favicon', r'avatar', r'badge',
            r'24x24', r'32x32', r'48x48', r'64x64', r'16x16',  # Kích thước icon phổ biến
            r'-ic-', r'_ic_', r'/ic/', r'/icons?/',  # Pattern icon trong URL
            
            # Tracking và analytics
            r'pixel', r'tracking', r'analytics', r'beacon',
            r'1x1', r'spacer', r'blank', r'transparent',
            
            # UI elements
            r'button', r'arrow', r'spinner', r'loading', r'loader',
            r'cart', r'wishlist', r'share', r'social',
            r'star', r'rating', r'review',
            r'nav', r'menu', r'header', r'footer',
            r'banner', r'promo', r'ad-', r'ads-',
            
            # Social media
            r'facebook\.com', r'twitter\.com', r'google-analytics',
            r'zalo', r'messenger', r'youtube', r'tiktok',
            r'ytimg\.com',  # YouTube thumbnail CDN
            
            # File types không cần
            r'\.gif$', r'\.svg$',
            
            # Pattern cụ thể cho các website VN
            r'content/.*24x24', r'content/.*32x32',  # TGDD icons
            r'common/Common',  # TGDD common assets
        ]
        
        for img in soup.find_all('img'):
            # Lấy src - thử nhiều attribute khác nhau (lazy loading)
            src = (
                img.get('data-src') or 
                img.get('data-lazy-src') or 
                img.get('data-original') or
                img.get('data-srcset') or
                img.get('data-lazy') or
                img.get('data-image') or
                img.get('data-url') or
                img.get('srcset', '').split(',')[0].split(' ')[0] or  # Lấy URL đầu tiên từ srcset
                img.get('src')
            )
            
            if not src:
                continue
            
            # Chuyển về absolute URL
            # Xử lý URL bắt đầu bằng // (thiếu protocol)
            if src.startswith('//'):
                src = 'https:' + src
            img_url = urljoin(page_url, src)
            
            # Skip nếu đã có hoặc là data URI
            if img_url in seen_urls or img_url.startswith('data:'):
                continue
            
            # Kiểm tra exclude patterns
            should_exclude = False
            for pattern in EXCLUDE_PATTERNS:
                if re.search(pattern, img_url, re.IGNORECASE):
                    should_exclude = True
                    break
            
            if should_exclude:
                continue
            
            # Kiểm tra kích thước (nếu có)
            width = img.get('width', '')
            height = img.get('height', '')
            
            try:
                w = int(str(width).replace('px', '').replace('%', '')) if width else 0
                h = int(str(height).replace('px', '').replace('%', '')) if height else 0
                # Bỏ qua ảnh quá nhỏ (icon, pixel) - tăng ngưỡng lên 100px
                if (w > 0 and w < 100) or (h > 0 and h < 100):
                    continue
            except ValueError:
                pass
            
            # Lấy alt và title
            alt = img.get('alt', '').strip()
            title = img.get('title', '').strip()
            
            # ===== SCORING: Ưu tiên ảnh sản phẩm =====
            score = 0
            
            # Alt/title dài = có thể là tên sản phẩm
            if len(alt) > 20:
                score += 2
            if len(title) > 20:
                score += 2
            
            # URL pattern ảnh sản phẩm
            product_url_patterns = ['product', 'images', 'slider', 'gallery', 'main']
            for p in product_url_patterns:
                if p in img_url.lower():
                    score += 1
            
            # Kích thước lớn = ảnh chính
            if w >= 300 or h >= 300:
                score += 2
            
            # Skip ảnh điểm thấp (có thể là icon không được filter trước đó)
            if score < 1 and (w == 0 and h == 0):  # Không có size info và điểm thấp
                # Kiểm tra thêm: nếu alt quá ngắn, skip
                if len(alt) < 10 and len(title) < 10:
                    continue
            
            # Lấy context (text xung quanh ảnh)
            context = ""
            parent = img.parent
            if parent:
                # Tìm text trong parent hoặc siblings
                context_text = parent.get_text(strip=True)
                if context_text and len(context_text) < 500:
                    context = context_text
            
            # Thêm vào danh sách (kèm score để sort sau)
            seen_urls.add(img_url)
            images.append(ImageInfo(
                url=img_url,
                alt=alt,
                title=title,
                context=context[:200]  # Giới hạn 200 ký tự
            ))
        
        # Tìm thêm ảnh từ background-image trong style
        for elem in soup.find_all(style=True):
            style = elem.get('style', '')
            bg_match = re.search(r'background-image:\s*url\(["\']?([^"\')]+)["\']?\)', style)
            if bg_match:
                bg_url = urljoin(page_url, bg_match.group(1))
                if bg_url not in seen_urls and not bg_url.startswith('data:'):
                    seen_urls.add(bg_url)
                    images.append(ImageInfo(
                        url=bg_url,
                        alt="",
                        title="background-image",
                        context=""
                    ))
        
        return images[:50]  # Giới hạn 50 ảnh mỗi trang
    
    def _extract_links(self, html: str, current_url: str) -> List[str]:
        """Trích xuất tất cả internal links từ HTML"""
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            normalized = self._normalize_url(href, current_url)
            
            if normalized and normalized not in self.visited_urls:
                links.append(normalized)
        
        # Loại bỏ duplicate và sắp xếp theo priority
        unique_links = list(set(links))
        unique_links.sort(key=lambda x: self._get_priority_score(x), reverse=True)
        
        return unique_links
    
    def _get_session(self) -> requests.Session:
        """Lấy hoặc tạo session riêng cho thread hiện tại (thread-safe)"""
        if not hasattr(self._thread_local, 'session'):
            session = requests.Session()
            session.headers.update(self._session_headers)
            self._thread_local.session = session
        return self._thread_local.session
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch nội dung HTML của một trang (thread-safe: session riêng per-thread)"""
        try:
            session = self._get_session()
            response = session.get(
                url, 
                timeout=self.config.timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Chặn cross-domain redirect
            final_domain = urlparse(response.url).netloc
            if final_domain and final_domain != self.domain:
                print(f"  [SKIP] Cross-domain redirect: {url} → {response.url}")
                return None
            
            # Chỉ xử lý HTML
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return None
            
            # Fix encoding: nhiều website VN không khai charset trong Content-Type
            if response.encoding and response.encoding.lower() == 'iso-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
            
            return response.text
            
        except requests.RequestException as e:
            print(f"  [ERROR] Không thể fetch {url}: {str(e)}")
            with self._failed_lock:
                self.failed_urls.append(url)
            return None
    
    def crawl(self) -> List[PageContent]:
        """
        Bắt đầu quá trình cào đa tầng (ĐA LUỒNG)
        
        Returns:
            List[PageContent]: Danh sách nội dung các trang đã cào
        """
        print(f"\n{'='*60}")
        print(f"🕷️  BẮT ĐẦU CÀO ĐA TẦNG (MULTI-THREADED)")
        print(f"{'='*60}")
        print(f"🌐 URL gốc: {self.base_url}")
        print(f"📊 Max depth: {self.config.max_depth}")
        print(f"📄 Max pages: {self.config.max_pages}")
        print(f"{'='*60}\n")
        
        # Concurrency Control
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        self.visited_lock = threading.Lock() # Lock để ghi vào visited_urls
        self.results_lock = threading.Lock() # Lock để ghi vào pages list
        
        # Queue: (url, depth) - Sử dụng list làm queue đơn giản
        # Trong mô hình đa luồng phức tạp, ta sẽ submit task mới vào executor.
        # Ở đây dùng mô hình "Phát triển theo chiều rộng (BFS)" từng lớp để dễ quản lý depth.
        
        current_layer = [(self.base_url, 0)]
        self.visited_urls.add(self.base_url)
        
        total_processed = 0
        
        # Cào theo từng lớp độ sâu (Layer-by-Layer BFS)
        # Cách này dễ quản lý depth hơn là recursive thread
        
        max_threads = 10 # Số luồng tối đa
        
        with tqdm(total=self.config.max_pages, desc="Đang cào (Threads)", unit="trang") as pbar:
            while current_layer and total_processed < self.config.max_pages:
                
                # Chỉ lấy đủ số lượng cần thiết
                if total_processed + len(current_layer) > self.config.max_pages:
                    current_layer = current_layer[:self.config.max_pages - total_processed]
                
                print(f"\n--- Đang xử lý lớp có {len(current_layer)} pages ---")
                
                next_layer_candidates = [] # URL tìm thấy cho lớp tiếp theo
                
                # Submit tất cả URL trong lớp hiện tại vào ThreadPool
                with ThreadPoolExecutor(max_workers=max_threads) as executor:
                    future_to_url = {
                        executor.submit(self._process_single_url, url, depth): (url, depth) 
                        for url, depth in current_layer
                    }
                    
                    for future in as_completed(future_to_url):
                        url, depth = future_to_url[future]
                        try:
                            result_page, new_links = future.result()
                            if result_page:
                                with self.results_lock:
                                    self.pages.append(result_page)
                                    total_processed += 1
                                    pbar.update(1)
                                    
                                    # Hiển thị log ngắn gọn
                                    print(f"  ✓ [Depth {depth}] Xong: {url[:60]}... ({len(new_links)} links)")

                                # Gom link mới
                                next_layer_candidates.extend([(link, depth + 1) for link in new_links])
                                
                        except Exception as e:
                            print(f"  ❌ Lỗi thread {url}: {e}")
                
                # Chuẩn bị cho lớp tiếp theo
                current_layer = []
                # Lọc duplicate và check visited CHO LỚP TIẾP THEO
                # (Lưu ý: _process_single_url không add vào visited toàn cục để tránh race condition phức tạp,
                # ta làm ở main thread này an toàn hơn)
                
                for link, d in next_layer_candidates:
                    if d <= self.config.max_depth:
                        if link not in self.visited_urls:
                            self.visited_urls.add(link)
                            current_layer.append((link, d))
                
                # Nếu đã đủ số trang hoặc không còn gì để cào -> Dừng
                if total_processed >= self.config.max_pages:
                    break
                    
                # Delay nhỏ giữa các lớp để thở
                time.sleep(1)

        # Summary
        print(f"\n{'='*60}")
        print(f"✅ HOÀN THÀNH CÀO")
        print(f"{'='*60}")
        print(f"📄 Số trang đã cào: {len(self.pages)}")
        print(f"❌ Số trang thất bại: {len(self.failed_urls)}")
        print(f"{'='*60}\n")
        
        return self.pages

    def _process_single_url(self, url: str, depth: int):
        """Hàm xử lý cho một worker thread"""
        # Fetch content
        html = self._fetch_page(url)
        if not html:
            return None, []
        
        # Extract content
        page_content = self._extract_page_content(url, html, depth)
        
        # Extract links (nhưng chưa filter visited ở đây để tối ưu lock)
        new_links = []
        if depth < self.config.max_depth:
            new_links = self._extract_links(html, url)
        
        # Random delay nhỏ để tránh DDOS
        import random
        time.sleep(random.uniform(0.1, 0.5))
        
        return page_content, new_links
    
    def to_json(self) -> str:
        """Xuất kết quả ra JSON"""
        # Tổng hợp tất cả ảnh unique
        all_images = []
        seen_img_urls = set()
        for p in self.pages:
            for img in p.images:
                if img.url not in seen_img_urls:
                    seen_img_urls.add(img.url)
                    all_images.append({
                        'url': img.url,
                        'alt': img.alt,
                        'title': img.title,
                        'context': img.context,
                        'source_page': p.url
                    })
        
        data = {
            'base_url': self.base_url,
            'total_pages': len(self.pages),
            'total_images': len(all_images),
            'all_images': all_images,  # NEW: Tất cả ảnh unique
            'pages': [
                {
                    'url': p.url,
                    'title': p.title,
                    'meta_description': p.meta_description,
                    'headings': p.headings,
                    'paragraphs': p.paragraphs,
                    'images': [{'url': img.url, 'alt': img.alt, 'title': img.title} for img in p.images],
                    'depth': p.depth
                }
                for p in self.pages
            ]
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def save_to_file(self, filepath: str):
        """Lưu kết quả ra file JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
        print(f"💾 Đã lưu kết quả vào: {filepath}")


# ============================================================
# SITEMAP SCRAPER (cào theo sitemap.xml)
# ============================================================

class SitemapScraper(MultiLevelScraper):
    """
    Scraper cào theo sitemap.xml thay vì theo thẻ <a>
    Hiệu quả hơn cho các website có sitemap chuẩn
    """
    
    def __init__(self, base_url: str, config: Optional[ScraperConfig] = None):
        super().__init__(base_url, config)
        self.sitemap_urls = []
    
    # Map tên sitemap con → priority mặc định (khi không có <priority> trong XML)
    SITEMAP_TYPE_PRIORITY = {
        'product': 0.9,    # Trang SẢN PHẨM → ưu tiên cao nhất
        'post': 0.7,       # Trang bài viết/blog
        'page': 0.6,       # Trang tĩnh (about, contact...)
        'category': 0.2,   # Trang DANH MỤC → ưu tiên thấp
        'product_cat': 0.2,
        'product_tag': 0.1,
        'tag': 0.1,
        'pa_': 0.1,        # Product attribute taxonomy (WooCommerce)
    }
    
    def _infer_priority_from_sitemap_name(self, sitemap_url: str) -> float:
        """Suy luận priority từ TÊN FILE sitemap con.
        Ví dụ: sitemap-post-type-product.xml → 0.9
               sitemap-taxonomy-category.xml → 0.2
        """
        url_lower = sitemap_url.lower()
        for keyword, priority in self.SITEMAP_TYPE_PRIORITY.items():
            if keyword in url_lower:
                return priority
        return 0.5  # Default nếu không nhận ra loại
    
    def _fetch_sitemap(self, sitemap_url: str, inferred_priority: float = 0.5) -> List[dict]:
        """Lấy danh sách URLs từ sitemap, kèm priority + lastmod.
        
        Args:
            sitemap_url: URL của sitemap
            inferred_priority: Priority suy luận từ tên file sitemap cha
            
        Returns: List[{url, priority, lastmod, source_sitemap}]
        """
        entries = []
        
        try:
            response = self._get_session().get(sitemap_url, timeout=30)
            response.raise_for_status()
            content = response.text
            
            soup = BeautifulSoup(content, 'lxml-xml')
            
            # Kiểm tra xem có phải sitemap index không
            sitemap_tags = soup.find_all('sitemap')
            if sitemap_tags:
                print(f"  📁 Sitemap index, tìm thấy {len(sitemap_tags)} sitemap con")
                for sitemap in sitemap_tags:
                    loc = sitemap.find('loc')
                    if loc:
                        child_url = loc.text.strip()
                        # Suy luận priority từ TÊN FILE sitemap con (chỉ dùng để SẮP XẾP, KHÔNG skip)
                        child_priority = self._infer_priority_from_sitemap_name(child_url)
                        sitemap_type = child_url.split('/')[-1]  # Tên file
                        print(f"     → {sitemap_type} (inferred priority: {child_priority})")
                        
                        # Thu thập TẤT CẢ sitemap con — để AI classifier lọc sau
                        # Priority chỉ quyết định THỨ TỰ cào, KHÔNG quyết định skip
                        child_entries = self._fetch_sitemap(child_url, child_priority)
                        entries.extend(child_entries)
            else:
                # Sitemap thường — parse cả priority + lastmod
                url_tags = soup.find_all('url')
                for url_tag in url_tags:
                    loc = url_tag.find('loc')
                    if not loc:
                        continue
                    page_url = loc.text.strip()
                    if not self._is_valid_url(page_url):
                        continue
                    
                    # Parse priority — nếu XML có <priority> thì dùng, không thì dùng inferred
                    priority_tag = url_tag.find('priority')
                    try:
                        priority = float(priority_tag.text.strip()) if priority_tag else inferred_priority
                    except (ValueError, AttributeError):
                        priority = inferred_priority
                    
                    # Parse lastmod
                    lastmod_tag = url_tag.find('lastmod')
                    lastmod = lastmod_tag.text.strip() if lastmod_tag else ''
                    
                    # Bonus: trang cập nhật gần đây (<6 tháng) → +0.05
                    if lastmod:
                        try:
                            from datetime import datetime, timezone
                            # Parse ISO format lastmod
                            mod_date = datetime.fromisoformat(lastmod.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            months_old = (now - mod_date).days / 30
                            if months_old < 6:
                                priority = min(priority + 0.05, 1.0)
                        except (ValueError, TypeError):
                            pass
                    
                    entries.append({
                        'url': page_url,
                        'priority': round(priority, 2),
                        'lastmod': lastmod,
                        'source_sitemap': sitemap_url.split('/')[-1],
                    })
                
                print(f"  📄 Tìm thấy {len(entries)} URLs trong {sitemap_url.split('/')[-1]} (base P={inferred_priority})")
                
        except Exception as e:
            print(f"  ❌ Lỗi đọc sitemap {sitemap_url}: {e}")
        
        # Sort theo priority giảm dần (trang sản phẩm lên đầu, danh mục xuống cuối)
        entries.sort(key=lambda x: -x['priority'])
        
        return entries
    
    def _find_sitemap_url(self) -> Optional[str]:
        """Tìm URL của sitemap"""
        possible_paths = [
            '/sitemap.xml',
            '/sitemap_index.xml',
            '/sitemap-index.xml',
            '/sitemaps.xml',
            '/sitemap1.xml',
            '/post-sitemap.xml',
            '/page-sitemap.xml',
        ]
        
        for path in possible_paths:
            sitemap_url = self.base_url + path
            try:
                print(f"  🔍 Đang thử: {sitemap_url}")
                # Dùng GET thay vì HEAD vì một số server không hỗ trợ HEAD
                response = self.session.get(sitemap_url, timeout=15)
                print(f"     → Status: {response.status_code}")
                if response.status_code == 200 and ('<?xml' in response.text[:100] or '<urlset' in response.text[:500] or '<sitemapindex' in response.text[:500]):
                    print(f"  ✅ Tìm thấy sitemap: {sitemap_url}")
                    return sitemap_url
            except Exception as e:
                print(f"     → Lỗi: {e}")
                continue
        
        # Thử từ robots.txt
        try:
            robots_url = self.base_url + '/robots.txt'
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        print(f"  ✅ Tìm thấy sitemap từ robots.txt: {sitemap_url}")
                        return sitemap_url
        except:
            pass
        
        return None
    
    def crawl(self) -> List[PageContent]:
        """Cào theo sitemap — ưu tiên trang chủ + trang priority cao."""
        print(f"\n{'='*60}")
        print(f"🗺️  SITEMAP SCRAPER")
        print(f"{'='*60}")
        print(f"🌐 Website: {self.base_url}")
        
        # Tìm sitemap
        sitemap_url = self._find_sitemap_url()
        
        if not sitemap_url:
            print("  ⚠️ Không tìm thấy sitemap, chuyển sang cào thường...")
            return super().crawl()
        
        # Lấy URLs từ sitemap (đã sort theo priority)
        sitemap_entries = self._fetch_sitemap(sitemap_url)
        
        if not sitemap_entries:
            print("  ⚠️ Sitemap rỗng, chuyển sang cào thường...")
            return super().crawl()
        
        # ===== ĐẢM BẢO HOMEPAGE NẰM ĐẦU TIÊN =====
        from urllib.parse import urlparse
        base_parsed = urlparse(self.base_url)
        homepage_variants = [
            self.base_url,
            self.base_url + '/',
            self.base_url.rstrip('/'),
            f"{base_parsed.scheme}://{base_parsed.netloc}",
            f"{base_parsed.scheme}://{base_parsed.netloc}/",
        ]
        
        # Tách homepage ra khỏi list, đặt lên đầu
        homepage_entry = None
        other_entries = []
        for entry in sitemap_entries:
            if entry['url'].rstrip('/') in [h.rstrip('/') for h in homepage_variants]:
                homepage_entry = entry
            else:
                other_entries.append(entry)
        
        # Nếu homepage không có trong sitemap → tạo entry giả với priority cao nhất
        if not homepage_entry:
            homepage_entry = {'url': self.base_url, 'priority': 1.0, 'lastmod': ''}
            print(f"  🏠 Homepage không có trong sitemap → thêm thủ công")
        
        # Homepage luôn đầu tiên + phần còn lại theo priority giảm dần
        ordered_entries = [homepage_entry] + other_entries
        
        # Log ưu tiên
        top5 = ordered_entries[:5]
        print(f"  📊 Top 5 trang ưu tiên:")
        for i, e in enumerate(top5):
            print(f"     {i+1}. [P={e['priority']:.1f}] {e['url'][:70]}")
        
        # Giới hạn số trang
        urls_to_crawl = [e['url'] for e in ordered_entries[:self.config.max_pages]]
        # Backward compatibility: lưu sitemap_urls dạng list[str]
        self.sitemap_urls = urls_to_crawl
        
        print(f"📄 Sẽ cào {len(urls_to_crawl)} trang (homepage first, sorted by priority)")
        print(f"{'='*60}\n")
        
        # Cào song song
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with tqdm(total=len(urls_to_crawl), desc="Cào từ Sitemap", unit="trang") as pbar:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {
                    executor.submit(self._process_single_url, url, 0): url 
                    for url in urls_to_crawl
                }
                
                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        page_content, _ = future.result()
                        if page_content:
                            self.pages.append(page_content)
                            pbar.update(1)
                    except Exception as e:
                        print(f"  ❌ Lỗi {url}: {e}")
        
        print(f"\n✅ Đã cào {len(self.pages)} trang từ sitemap (homepage + priority order)")
        return self.pages


# ============================================================
# PLAYWRIGHT SCRAPER (cho JavaScript-rendered pages)
# ============================================================

class PlaywrightScraper(MultiLevelScraper):
    """
    Scraper sử dụng Playwright cho các trang render bằng JavaScript
    Kế thừa từ MultiLevelScraper
    """
    
    def __init__(self, base_url: str, config: Optional[ScraperConfig] = None):
        super().__init__(base_url, config)
        self._browser = None
        self._page = None
    
    def _init_browser(self):
        """Khởi tạo browser Playwright"""
        from playwright.sync_api import sync_playwright
        
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        self._page.set_extra_http_headers({
            'User-Agent': self.config.user_agent
        })
    
    def _close_browser(self):
        """Đóng browser"""
        if self._browser:
            self._browser.close()
        if hasattr(self, '_playwright'):
            self._playwright.stop()
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """Override: Fetch trang bằng Playwright (SINGLE THREAD ONLY)"""
        try:
            if not self._browser:
                self._init_browser()
            
            self._page.goto(url, wait_until='networkidle', timeout=self.config.timeout * 1000)
            
            # Đợi thêm để JS render
            self._page.wait_for_timeout(2000)
            
            return self._page.content()
            
        except Exception as e:
            print(f"  [ERROR] Playwright không thể fetch {url}: {str(e)}")
            with self._failed_lock:
                self.failed_urls.append(url)
            return None
    
    def crawl(self) -> List[PageContent]:
        """
        Override: Crawl tuần tự (KHÔNG multi-thread).
        Playwright page object KHÔNG thread-safe — nếu dùng ThreadPoolExecutor,
        nhiều thread sẽ gọi page.goto() cùng lúc → crash hoặc nhận HTML sai trang.
        """
        from tqdm import tqdm
        
        print(f"\n{'='*60}")
        print(f"🎭 PLAYWRIGHT SCRAPER (Single-Thread BFS)")
        print(f"{'='*60}")
        print(f"🌐 URL gốc: {self.base_url}")
        print(f"📊 Max depth: {self.config.max_depth}")
        print(f"📄 Max pages: {self.config.max_pages}")
        print(f"⚠️  Chế độ tuần tự (Playwright không hỗ trợ multi-thread)")
        print(f"{'='*60}\n")
        
        try:
            current_layer = [(self.base_url, 0)]
            self.visited_urls.add(self.base_url)
            total_processed = 0
            
            with tqdm(total=self.config.max_pages, desc="Đang cào (Playwright)", unit="trang") as pbar:
                while current_layer and total_processed < self.config.max_pages:
                    # Cắt layer nếu quá max
                    remaining = self.config.max_pages - total_processed
                    if len(current_layer) > remaining:
                        current_layer = current_layer[:remaining]
                    
                    next_layer_candidates = []
                    
                    for url, depth in current_layer:
                        html = self._fetch_page(url)
                        if not html:
                            continue
                        
                        page_content = self._extract_page_content(url, html, depth)
                        self.pages.append(page_content)
                        total_processed += 1
                        pbar.update(1)
                        
                        print(f"  ✓ [Depth {depth}] {url[:60]}...")
                        
                        # Extract links cho layer tiếp
                        if depth < self.config.max_depth:
                            new_links = self._extract_links(html, url)
                            next_layer_candidates.extend([(link, depth + 1) for link in new_links])
                        
                        # Delay
                        import time
                        time.sleep(self.config.delay_between_requests)
                    
                    # Chuẩn bị layer tiếp theo
                    current_layer = []
                    for link, d in next_layer_candidates:
                        if d <= self.config.max_depth and link not in self.visited_urls:
                            self.visited_urls.add(link)
                            current_layer.append((link, d))
                    
                    if total_processed >= self.config.max_pages:
                        break
            
            print(f"\n✅ Playwright crawl xong: {len(self.pages)} trang")
            return self.pages
            
        finally:
            self._close_browser()


if __name__ == "__main__":
    # Test nhanh
    url = input("Nhập URL website cần cào: ").strip()
    
    if not url:
        print("Vui lòng nhập URL!")
    else:
        config = ScraperConfig(max_depth=2, max_pages=20)
        scraper = MultiLevelScraper(url, config)
        pages = scraper.crawl()
        scraper.save_to_file("output/scraped_data.json")
