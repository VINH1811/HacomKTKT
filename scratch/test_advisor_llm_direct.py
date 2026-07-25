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
from core.price_advisor.llm_client import LLMClient, _build_user_prompt

config = PriceAdvisorConfig.from_env()
db = PriceDatabase(config.db_path, config=config)
guard = EgressGuard(strict=True)
llm = LLMClient(config)

print("=== RETRIEVING CONTEXT FOR TEST ITEM ===")
description = "Đầu che cuối thanh dẫn End Closure"
similar_items = db.search_similar([], top_k=5, status="active", query_text=description)

context = guard.build_safe_prompt_context(
    item_name=description,
    item_unit="cái",
    similar_items=similar_items,
)

user_prompt = _build_user_prompt(context)
print("\n--- USER PROMPT ---")
print(user_prompt)

print("\n--- CALLING OLLAMA DIRECTLY ---")
try:
    # We call ollama directly to see what it returns
    content, tokens = llm._call_ollama(user_prompt)
    print(f"Tokens Used: {tokens}")
    print("Raw Content:")
    print(repr(content))
except Exception as e:
    print(f"Error occurred during LLM call: {e}")
