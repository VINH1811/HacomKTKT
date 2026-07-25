import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from core.price_advisor.advisor import PriceAdvisor

print("=== TESTING PRICE ADVISOR FOR ITEM ===")
advisor = PriceAdvisor()

items = [
    {
        "item_id": "test_item_1",
        "item_name": "Đèn chùm treo thả",
        "unit": "bộ",
    }
]

res = advisor.suggest_prices(items)
print("Advisor results:")
print(f"Total items analyzed: {res.total_items_analyzed}")
print(f"Items with suggestions: {res.items_with_suggestions}")
print(f"Items failed: {res.items_failed}")
print(f"Warnings: {res.warnings}")

if res.suggestions:
    sug = res.suggestions[0]
    print("\nSuggestion Details:")
    print(f"  Item Name: {sug.item_name}")
    print(f"  Status: {sug.status}")
    print(f"  Min Price: {sug.min_price}")
    print(f"  Max Price: {sug.max_price}")
    print(f"  Suggested: {sug.suggested_price}")
    print(f"  Confidence: {sug.confidence}")
    print(f"  Error Message: {sug.error_message}")
    print(f"  Reasoning: {sug.reasoning}")
    print(f"  Price Comment: {sug.price_comment}")
else:
    print("\nNo suggestion returned.")

print("=== TEST COMPLETE ===")
