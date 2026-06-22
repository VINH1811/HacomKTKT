import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

folder = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025"
files = [
    "1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx",
    "4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"
]

with open("inspect_phat_sinh.txt", "w", encoding="utf-8") as out:
    for file_name in files:
        path = os.path.join(folder, file_name)
        out.write(f"\n==================================================\n")
        out.write(f"File: {file_name}\n")
        try:
            xl = pd.ExcelFile(path)
            for sheet in xl.sheet_names:
                if 'tổng hợp' in sheet.lower() or 'tong' in sheet.lower() or 'bia' in sheet.lower():
                    continue
                df = pd.read_excel(path, sheet_name=sheet)
                
                # Check description column
                desc_col = None
                for col in df.columns:
                    if df[col].astype(str).str.lower().str.contains('diễn giải|mô tả').any():
                        desc_col = col
                        break
                if desc_col is None:
                    desc_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                
                # Search for "phát sinh" or "ngoài kl" or similar
                for idx, val in enumerate(df[desc_col]):
                    val_str = str(val).lower()
                    if 'phát sinh' in val_str or 'ngoài kl' in val_str or 'ngoài danh mục' in val_str:
                        stt_val = df.iloc[idx, 0] if len(df.columns) > 0 else ""
                        out.write(f"  Sheet: {sheet} | Row {idx} | STT: {stt_val} | Value: {val}\n")
                        
        except Exception as e:
            out.write(f"Error: {e}\n")

print("Done. Output in inspect_phat_sinh.txt")
