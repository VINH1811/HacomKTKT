import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from core.price_advisor.config import PriceAdvisorConfig
from core.price_advisor.database import PriceDatabase

print("=== CLEARING 'price_records' TABLE ===")
config = PriceAdvisorConfig.from_env()
db = PriceDatabase(config.db_path, config=config)

conn = db._conn()
if config.db_provider == "sqlite":
    conn.execute("DELETE FROM price_records;")
    conn.commit()
    print("✓ SQLite database price_records table cleared.")
else:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE price_records RESTART IDENTITY CASCADE;")
    conn.commit()
    print("✓ PostgreSQL database price_records table truncated.")

db.close()
print("=== CLEAR COMPLETE ===")
