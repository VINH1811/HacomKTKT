import pandas as pd
from pathlib import Path

cleaned_excel = Path(r"c:\KHMT\HacomHolding\HacomKTKT\data\cleaned_prices.xlsx")
if cleaned_excel.exists():
    df = pd.read_excel(cleaned_excel)
    print(f"Total rows in cleaned_prices.xlsx: {len(df)}")
    
    # Extract sheet names from source_file column
    def extract_sheet(val):
        if pd.isna(val): return "Unknown"
        parts = str(val).split("|")
        return parts[-1].strip() if len(parts) > 1 else str(val)
        
    df["sheet"] = df["source_file"].apply(extract_sheet)
    sheet_counts = df["sheet"].value_counts()
    
    print("\n=== SHEET DISTRIBUTION IN CLEANED_PRICES.XLSX ===")
    for sheet, count in sheet_counts.items():
        print(f"  - Sheet '{sheet}': {count:,} records")
else:
    print("cleaned_prices.xlsx not found.")
