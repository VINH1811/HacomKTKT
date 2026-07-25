import urllib.request
import urllib.parse
import re
import json

def test_query(item_name, unit):
    # Formulate query variants
    core_name = item_name
    for sep in [",", "|", ";", " - "]:
        if sep in core_name:
            parts = core_name.split(sep)
            if len(parts[0].strip()) >= 6:
                core_name = parts[0]
                break
                
    core_name = core_name.strip().replace('"', '').replace("'", "")
    
    # Try different search queries
    queries = [
        f'{core_name} báo giá',
        f'{core_name} đơn giá {unit}',
        f'{core_name} giá'
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    for query in queries:
        print(f"\n[QUERY] Searching for: '{query}'")
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")
            
            snippets_raw = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            print(f"-> Found {len(snippets_raw)} snippets.")
            
            snippets = []
            for snip in snippets_raw:
                clean = re.sub(r'<[^>]*>', '', snip).strip()
                clean = clean.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
                if clean:
                    snippets.append(clean)
            
            # Print first 3 snippets for debugging
            for s in snippets[:3]:
                print(f"   Snippet: {s}")
                
            # Regex patterns to test
            patterns = [
                r'(\d{1,3}(?:[\.,]\d{3})+|\d{4,9})\s*(?:đ|vnd|vnđ|đồng|dong)',
                r'(\d{1,3}(?:[\.,]\d{3})+|\d{4,9})\s*(?:đ|vnd|vnđ|đồng|dong|/|đ/)'
            ]
            
            for pat in patterns:
                prices = []
                for text in snippets:
                    matches = re.finditer(pat, text, re.IGNORECASE)
                    for m in matches:
                        price_str = m.group(1).replace(".", "").replace(",", "")
                        try:
                            price = float(price_str)
                            if 1000 <= price <= 500000000:
                                prices.append(price)
                        except ValueError:
                            continue
                print(f"   Pattern [{pat}]: found prices {prices}")
                
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    test_query("Cáp đồng trần C25 xoắn tròn", "m")
    test_query("Đèn LED âm trần downlight 9W tròn D90", "bộ")
