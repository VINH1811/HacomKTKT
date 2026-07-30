import urllib.request
import urllib.parse
import re
import logging

logger = logging.getLogger(__name__)


class SearchBlockedError(RuntimeError):
    """Công cụ tìm kiếm tạm chặn do gọi quá nhiều, không phải không có giá."""


class MarketPriceFetcher:
    @staticmethod
    def fetch_market_prices(item_name: str, unit: str) -> dict:
        """
        Query DuckDuckGo for the material name + unit to find current online market prices.
        
        Returns a dict:
        {
            "prices": [float],
            "min_price": float | None,
            "max_price": float | None,
            "avg_price": float | None,
            "snippets": [str],
        }
        """
        # Preserve the full description and size specifications for accurate search
        core_name = item_name.strip().replace('"', '').replace("'", "")
        
        # Formulate a clean Vietnamese-optimized search query
        # Using "báo giá [vật tư]" is highly effective for local distributors
        query = f'báo giá {core_name}'
        print(f"[*] Đang tra cứu giá thị trường Web Search cho: '{query}'")
        
        # Adding kl=vn-vi forces DuckDuckGo to return Vietnamese local results
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}&kl=vn-vi"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")

            # DuckDuckGo trả trang "anomaly" khi bị gọi quá dày: HTTP vẫn 200
            # nhưng không có kết quả nào. Phải phân biệt với trường hợp tìm được
            # trang mà trong đó không có giá — hai chuyện khác hẳn nhau.
            if 'result__a' not in html and re.search(r'anomaly|unusual traffic',
                                                     html, re.IGNORECASE):
                raise SearchBlockedError(
                    "DuckDuckGo tạm chặn do gọi quá nhanh")

            # Extract snippets inside <a class="result__snippet" ...>text</a>
            snippets_raw = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = []
            for snip in snippets_raw:
                # Remove any HTML tags
                clean = re.sub(r'<[^>]*>', '', snip).strip()
                # Unescape some common HTML entities
                clean = clean.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
                if clean:
                    snippets.append(clean)
            
            # Parse prices from snippets
            prices = []
            # Optimized regex pattern:
            # 1. Matches formatted numbers followed by currency or unit/slash symbols (e.g. 55.000đ, 120.000/m, 150.000đ/bộ, 55000 vnd)
            # 2. Matches numbers preceded by price indicators (e.g. giá: 55.000, đơn giá 120.000)
            # Uses negative lookahead (?!\w) on 'đ' and \b on currency names to prevent matching words like "để", "đến"
            pattern_currency = r'(?<![\d\.,])(\d{1,3}(?:[\.,]\d{3})+|\d{4,9})\s*(?:đ(?!\w)|vnd\b|vnđ\b|đồng\b|dong\b|/|đ/)'
            pattern_preceded = r'\b(?:giá|đơn giá|bán|chỉ|từ|đến)\b\s*[:\-]?\s*(?<![\d\.,])(\d{1,3}(?:[\.,]\d{3})+|\d{4,9})\b'
            
            for text in snippets:
                # 1. Clean Vietnamese phone numbers of various grouping formats:
                # E.g. 0902 80 5359, 0902.805.359, 090 280 5359, 024.3756.7890
                text_clean = re.sub(r'\b0\d{1,4}(?:[-.\s]\d{2,4}){2,3}\b', '', text)
                text_clean = re.sub(r'\b(?:\+?84|0)\d{9,10}\b', '', text_clean)
                text_clean = re.sub(r'(?:liên hệ|lh|hotline|sđt|tel|phone)[:\-]?\s*\d+[\s.-]?\d+[\s.-]?\d+', '', text_clean, flags=re.IGNORECASE)
                
                # Type 1: Suffix based matching (e.g. 55.000đ)
                for m in re.finditer(pattern_currency, text_clean, re.IGNORECASE):
                    price_str = m.group(1).replace(".", "").replace(",", "")
                    try:
                        price = float(price_str)
                        # Sanity check: MEP prices usually in this range, exclude years (e.g. 2024, 2025)
                        if 1000 <= price <= 500000000 and int(price) not in {2023, 2024, 2025, 2026, 2027}:
                            prices.append(price)
                    except ValueError:
                        continue
                
                # Type 2: Prefix based matching (e.g. giá: 55.000)
                for m in re.finditer(pattern_preceded, text_clean, re.IGNORECASE):
                    price_str = m.group(1).replace(".", "").replace(",", "")
                    try:
                        price = float(price_str)
                        if 1000 <= price <= 500000000 and int(price) not in {2023, 2024, 2025, 2026, 2027}:
                            prices.append(price)
                    except ValueError:
                        continue
            
            # Clean and filter duplicates
            prices = sorted(list(set(prices)))
            
            min_price = min(prices) if prices else None
            max_price = max(prices) if prices else None
            avg_price = sum(prices) / len(prices) if prices else None
            
            return {
                "prices": prices,
                "min_price": min_price,
                "max_price": max_price,
                "avg_price": avg_price,
                "snippets": snippets[:6], # top 6 search snippets for context
                # ok        = tra cứu được và có giá
                # no_prices = tra cứu được nhưng trang không ghi giá
                "status": "ok" if prices else "no_prices",
                "message": "" if prices else
                           "Tra cứu được nhưng các trang không ghi rõ đơn giá.",
            }
        except SearchBlockedError as e:
            logger.warning("Tra cứu giá thị trường bị chặn tạm thời: %s", e)
            return {
                "prices": [], "min_price": None, "max_price": None,
                "avg_price": None, "snippets": [],
                "status": "blocked",
                "message": "Công cụ tìm kiếm tạm chặn do truy vấn quá nhiều. "
                           "Vui lòng thử lại sau ít phút.",
            }
        except Exception as e:
            logger.error("Failed to fetch market prices from DuckDuckGo: %s", e)
            return {
                "prices": [],
                "min_price": None,
                "max_price": None,
                "avg_price": None,
                "snippets": [],
                "status": "error",
                "message": f"Không kết nối được công cụ tìm kiếm ({type(e).__name__}).",
            }
