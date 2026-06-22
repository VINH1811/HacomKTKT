import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

file_path = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025\4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"
out_file = "inspect_vk.txt"

with open(out_file, "w", encoding="utf-8") as out:
    try:
        xl = pd.ExcelFile(file_path)
        out.write(f"Sheets in Van Khanh: {', '.join(xl.sheet_names)}\n")
        
        # Look at BoQ chi tiet
        sheet_name = "BoQ chi tiet"
        df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=40)
        out.write(f"\nSheet: {sheet_name}\n")
        out.write(f"Shape: {df.shape}\n")
        out.write("First 35 rows:\n")
        out.write(df.to_string())
        out.write("\n")
        
        # Let's inspect column headers (maybe rows 3 to 10)
        out.write("\nRow headers analysis:\n")
        for i in range(10):
            row_vals = df.iloc[i].dropna().tolist()
            out.write(f"Row {i}: {row_vals}\n")
            
    except Exception as e:
        out.write(f"Error reading Van Khanh: {e}\n")

print("Done. Output in inspect_vk.txt")
