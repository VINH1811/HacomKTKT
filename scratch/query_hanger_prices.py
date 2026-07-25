import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from core.price_advisor.database import PriceDatabase
from core.price_advisor.config import PriceAdvisorConfig

config = PriceAdvisorConfig.from_env()
db = PriceDatabase(config.db_path, config=config)

print("=== QUERIED RECORDS FOR 'Giá treo trục ngang' ===")
records = db.search_similar([], top_k=20, status="active", query_text="Giá treo trục ngang")
for i, item in enumerate(records):
    rec = item.record
    print(f"Record #{i+1}:")
    print(f"  Item Name    : {rec.item_name}")
    print(f"  Spec         : {rec.material_spec}")
    print(f"  Unit         : {rec.unit}")
    print(f"  Unit Price   : {rec.unit_price:,.0f} VNĐ")
    print(f"  Project      : {rec.project_name}")
    print(f"  Source File  : {rec.source_file}")
    print(f"  Brand        : {rec.brand}")
    print(f"  Similarity   : {item.similarity_score:.4f}")
    print("-" * 50)
db.close()
