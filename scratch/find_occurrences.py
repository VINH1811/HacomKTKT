from pathlib import Path

app_path = Path(r"c:\KHMT\HacomHolding\HacomKTKT\app.py")
content = app_path.read_text(encoding="utf-8")

lines = content.splitlines()
for idx, line in enumerate(lines):
    if any(k in line for k in ["PriceAdvisor", "price_advisor", "advisor"]):
        print(f"Line {idx+1}: {line}")
