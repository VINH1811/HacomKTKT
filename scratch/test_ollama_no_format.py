import urllib.request
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from core.price_advisor.config import PriceAdvisorConfig
from core.price_advisor.database import PriceDatabase
from core.price_advisor.egress_guard import EgressGuard
from core.price_advisor.llm_client import LLMClient, _build_user_prompt, SYSTEM_PROMPT

config = PriceAdvisorConfig.from_env()
db = PriceDatabase(config.db_path, config=config)
guard = EgressGuard(strict=True)

print("=== RETRIEVING CONTEXT ===")
description = "Đầu che cuối thanh dẫn End Closure"
similar_items = db.search_similar([], top_k=5, status="active", query_text=description)

context = guard.build_safe_prompt_context(
    item_name=description,
    item_unit="cái",
    similar_items=similar_items,
)
user_prompt = _build_user_prompt(context)

# We send request to Ollama WITHOUT the "format": "json" constraint
base_url = "http://localhost:50050"
api_url = f"{base_url}/api/chat"

payload = {
    "model": "qwen3:14b",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ],
    "stream": False,
    # "format": "json" <-- commented out
    "options": {
        "temperature": 0.1,
        "num_predict": 1024,
    }
}

print("\n--- CALLING OLLAMA WITHOUT FORMAT CONSTRAINT ---")
request = urllib.request.Request(
    api_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
        message = data.get("message") or {}
        content = message.get("content") or ""
        print("Raw content:")
        print(repr(content))
except Exception as e:
    print(f"Error: {e}")
