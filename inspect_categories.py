import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

folder = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025"
files = [
    "1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx",
    "4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"
]

out_file = "inspect_categories.txt"
with open(out_file, "w", encoding="utf-8") as out:
    for file_name in files:
        path = os.path.join(folder, file_name)
        out.write(f"\n==================================================\n")
        out.write(f"File: {file_name}\n")
        try:
            xl = pd.ExcelFile(path)
            for sheet in xl.sheet_names:
                if 'tổng hợp' in sheet.lower() or 'tong' in sheet.lower() or 'bia' in sheet.lower():
                    continue
                out.write(f"\nSheet: {sheet}\n")
                df = pd.read_excel(path, sheet_name=sheet)
                # Find rows that look like category headers (e.g. description is uppercase or has HẠNG MỤC)
                # Let's search for columns that contain descriptions
                desc_col = None
                for col in df.columns:
                    # check if any cell in this col contains 'diễn giải' or 'mô tả'
                    if df[col].astype(str).str.lower().str.contains('diễn giải|mô tả').any():
                        desc_col = col
                        break
                if desc_col is None:
                    # fallback to column 1
                    desc_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                
                out.write(f"Using description column: {desc_col}\n")
                
                # Scan all rows
                for r_idx, val in enumerate(df[desc_col]):
                    val_str = str(val).strip()
                    if not val_str or val_str == "nan":
                        continue
                    # Check if it looks like a major header (e.g., contains 'HẠNG MỤC:', 'ĐẦU MỤC CÔNG VIỆC', or is all uppercase and longer than 5 chars)
                    if 'hạng mục' in val_str.lower() or 'đầu mục' in val_str.lower() or (val_str.isupper() and len(val_str) > 10):
                        # get STT as well
                        stt_val = df.iloc[r_idx, 0] if len(df.columns) > 0 else ""
                        out.write(f"  Row {r_idx} | STT: {stt_val} | Header: {val_str}\n")
                        
        except Exception as e:
            out.write(f"Error: {e}\n")

print("Done. Output in inspect_categories.txt")
