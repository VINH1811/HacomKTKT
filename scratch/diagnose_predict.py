import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from core.price_advisor.advisor import PriceAdvisor
from core.price_advisor.config import PriceAdvisorConfig

print("=== DIAGNOSING PRICE ADVISOR PREDICT ===")

cfg = PriceAdvisorConfig.from_env()
print(f"Config ready: {cfg.is_ready}")
print(f"DB Provider: {cfg.db_provider}")
print(f"DB Path: {cfg.db_path}")
print(f"LLM Provider: {cfg.llm_provider}")
print(f"LLM Model: {cfg.llm_model}")
print(f"LLM Base URL: {cfg.base_url}")

try:
    advisor = PriceAdvisor(cfg)
    advisor._ensure_initialized()
    print("✓ Database and components initialized successfully.")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Search DB
print("\n--- STEP 1: RAG DB SEARCH ---")
item_name = "Cu/XLPE/PVC (1x240)mm2"
unit = "m"

try:
    query_embedding = advisor._embedder.embed_text(item_name) if advisor._embedder else []
    print(f"Generated embedding vector length: {len(query_embedding)}")
    similar_items = advisor._db.search_similar(
        query_embedding,
        top_k=cfg.max_similar_results,
        query_text=item_name
    )
    print(f"Retrieved {len(similar_items)} items from PostgreSQL RAG:")
    for idx, item in enumerate(similar_items):
        print(f"  [{idx+1}] {item.record.item_name} | ĐVT: {item.record.unit} | ĐG: {item.record.unit_price} | Tương đồng: {item.similarity:.4f} | brand: {item.record.brand} | project: {item.record.project_name}")
except Exception as e:
    print(f"❌ RAG DB search failed: {e}")
    import traceback
    traceback.print_exc()

# Query LLM
print("\n--- STEP 2: LLM QUERY ---")
try:
    context = advisor._guard.build_safe_prompt_context(
        item_name=item_name,
        item_unit=unit,
        similar_items=similar_items,
    )
    print("Calling LLM...")
    suggestion = advisor._llm.query_price(
        context=context,
        item_id="diag_item",
        item_name=item_name,
        unit=unit,
    )
    print("LLM Response Status:", suggestion.status)
    print("LLM Suggested Price:", suggestion.suggested_price)
    print("LLM Error Message:", suggestion.error_message)
    print("LLM Reasoning:", suggestion.reasoning)
except Exception as e:
    print(f"❌ LLM query failed: {e}")
    import traceback
    traceback.print_exc()

print("=== DIAGNOSIS COMPLETE ===")
