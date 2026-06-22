import os
import sys
import pandas as pd
import openpyxl

# Set encoding to UTF-8 for safety
sys.stdout.reconfigure(encoding='utf-8')

folder = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025"
files = [f for f in os.listdir(folder) if f.endswith('.xlsx')]

out_file = "inspect_result.txt"
with open(out_file, "w", encoding="utf-8") as out:
    out.write("Files in folder:\n")
    for i, f in enumerate(files):
        out.write(f"{i}: {f}\n")

    for file_name in files:
        file_path = os.path.join(folder, file_name)
        out.write(f"\n==================================================\n")
        out.write(f"File: {file_name}\n")
        try:
            xl = pd.ExcelFile(file_path)
            out.write(f"Sheets: {', '.join(xl.sheet_names)}\n")
            for sheet in xl.sheet_names[:3]: # inspect first few sheets
                df = pd.read_excel(file_path, sheet_name=sheet, nrows=25)
                out.write(f"\nSheet: {sheet}\n")
                out.write(f"Shape: {df.shape}\n")
                out.write("First 20 rows:\n")
                out.write(df.head(20).to_string())
                out.write("\n")
        except Exception as e:
            out.write(f"Error reading {file_name}: {e}\n")

print("Done inspecting files. Results written to inspect_result.txt")
