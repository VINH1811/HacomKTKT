import os
import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

def clean_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

def identify_columns(df):
    """
    Scans the first 10 rows of a dataframe to identify key columns.
    Returns a dict mapping field name to column index.
    """
    col_mapping = {
        'stt': None,
        'code': None,
        'description': None,
        'unit': None,
        'qty_invited': None,
        'qty_bid': None,
        'price': None,
        'total': None,
    }
    
    # We look at cell values in the first 10 rows and all columns
    nrows = min(10, len(df))
    ncols = len(df.columns)
    
    # Score columns based on keywords found in their cells
    scores = {col: {'stt': 0, 'code': 0, 'desc': 0, 'unit': 0, 'qty_i': 0, 'qty_b': 0, 'price': 0, 'total': 0} for col in range(ncols)}
    
    for c in range(ncols):
        for r in range(nrows):
            val = str(df.iloc[r, c]).lower()
            if pd.isna(df.iloc[r, c]) or val == "nan":
                continue
            
            # STT
            if val in ['stt', 'số thứ tự', 'stt\n(1)', 'stt (1)']:
                scores[c]['stt'] += 10
            elif 'stt' in val:
                scores[c]['stt'] += 5
                
            # Code (Mã hiệu)
            if val in ['mã hiệu', 'mã số', 'mã cv', 'mã hiệu\n(8)', 'mã hiệu (8)']:
                scores[c]['code'] += 10
            elif 'mã hiệu' in val:
                scores[c]['code'] += 5
                
            # Description
            if any(k in val for k in ['diễn giải', 'mô tả công việc', 'tên công việc', 'tên hạng mục', 'nội dung']):
                scores[c]['desc'] += 10
                
            # Unit
            if val in ['đơn vị', 'đvt', 'đơn vị tính', 'đơn vị\ntính']:
                scores[c]['unit'] += 10
            elif 'đơn vị' in val or 'đvt' in val:
                scores[c]['unit'] += 5
                
            # Quantity Invited
            if 'kl' in val or 'khối lượng' in val or 'số lượng' in val:
                if 'mời thầu' in val or 'klmt' in val or 'yêu cầu' in val or 'lần 2' in val:
                    scores[c]['qty_i'] += 10
                elif 'chào' in val or 'nhà thầu' in val:
                    scores[c]['qty_b'] += 10
                else:
                    scores[c]['qty_i'] += 2
                    scores[c]['qty_b'] += 2
            
            # Price
            if 'đơn giá' in val or 'đg' in val:
                if 'tổng hợp' in val or 'đg tổng hợp' in val or 'đơn giá tổng hợp' in val:
                    scores[c]['price'] += 10
                elif 'vật liệu' in val or 'nhân công' in val:
                    # Detailed price components, ignore as main price column if possible
                    scores[c]['price'] -= 2
                else:
                    scores[c]['price'] += 5
                    
            # Total Amount
            if 'thành tiền' in val or 'tt' in val:
                scores[c]['total'] += 10
                
    # Now assign columns based on best score
    # STT
    col_mapping['stt'] = np.argmax([scores[c]['stt'] for c in range(ncols)])
    if scores[col_mapping['stt']]['stt'] < 2: col_mapping['stt'] = None
    
    # Code
    col_mapping['code'] = np.argmax([scores[c]['code'] for c in range(ncols)])
    if scores[col_mapping['code']]['code'] < 2: col_mapping['code'] = None
    
    # Description
    col_mapping['description'] = np.argmax([scores[c]['desc'] for c in range(ncols)])
    if scores[col_mapping['description']]['desc'] < 2: col_mapping['description'] = None
    
    # Unit
    col_mapping['unit'] = np.argmax([scores[c]['unit'] for c in range(ncols)])
    if scores[col_mapping['unit']]['unit'] < 2: col_mapping['unit'] = None
    
    # Qty Invited
    col_mapping['qty_invited'] = np.argmax([scores[c]['qty_i'] for c in range(ncols)])
    if scores[col_mapping['qty_invited']]['qty_i'] < 2: col_mapping['qty_invited'] = None
    
    # Qty Bid
    col_mapping['qty_bid'] = np.argmax([scores[c]['qty_b'] for c in range(ncols)])
    if scores[col_mapping['qty_bid']]['qty_b'] < 2: col_mapping['qty_bid'] = None
    
    # Price
    # Prefer columns that are not already assigned to STT, Description, Unit, Qty, Total
    price_scores = [scores[c]['price'] for c in range(ncols)]
    # Clear out indices that are already taken
    assigned = [col_mapping[k] for k in ['stt', 'code', 'description', 'unit', 'qty_invited', 'qty_bid'] if col_mapping[k] is not None]
    for a in assigned:
        if a < len(price_scores):
            price_scores[a] = -100
    col_mapping['price'] = np.argmax(price_scores)
    if price_scores[col_mapping['price']] < 2: col_mapping['price'] = None
    
    # Total
    total_scores = [scores[c]['total'] for c in range(ncols)]
    assigned = [col_mapping[k] for k in ['stt', 'code', 'description', 'unit', 'qty_invited', 'qty_bid', 'price'] if col_mapping[k] is not None]
    for a in assigned:
        if a < len(total_scores):
            total_scores[a] = -100
    col_mapping['total'] = np.argmax(total_scores)
    if total_scores[col_mapping['total']] < 2: col_mapping['total'] = None

    # Fallbacks and validations
    return col_mapping

def find_header_end_row(df, col_mapping):
    """
    Finds the row index where headers end and data starts.
    Usually it's the row after we find keywords like STT, Diễn giải, etc.
    """
    nrows = min(15, len(df))
    max_idx = 0
    keywords = ['stt', 'diễn giải', 'đơn vị', 'khối lượng', 'đơn giá', 'thành tiền', 'vl chính', 'dg tổng hợp', 'đg tổng hợp']
    for r in range(nrows):
        row_str = " ".join([str(val).lower() for val in df.iloc[r].dropna()])
        if any(kw in row_str for kw in keywords):
            max_idx = max(max_idx, r)
    return max_idx + 1

# Let's test on Linh Anh and Van Khanh files
folder = r"d:\Thực tập Halcom\code\5. Tong hop chao gia 11.12.2025"
test_files = [
    "1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx",
    "4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"
]

for file_name in test_files:
    path = os.path.join(folder, file_name)
    print(f"\n==========================================")
    print(f"Analyzing File: {file_name}")
    xl = pd.ExcelFile(path)
    # Check sheets
    for sheet in xl.sheet_names:
        if 'tổng hợp' in sheet.lower() or 'tong' in sheet.lower() or 'bia' in sheet.lower() or 'dmvt' in sheet.lower():
            continue
        print(f"\nSheet: {sheet}")
        df = pd.read_excel(path, sheet_name=sheet)
        col_mapping = identify_columns(df)
        print("Identified Columns:")
        for k, v in col_mapping.items():
            print(f"  {k}: index {v} (Name: {df.columns[v] if v is not None else 'Not Found'})")
            
        header_end = find_header_end_row(df, col_mapping)
        print(f"Header ends at row index: {header_end}")
        
        # Print first 5 data rows
        data_df = df.iloc[header_end:].copy()
        print("First 5 data rows parsed:")
        count = 0
        for idx, row in data_df.iterrows():
            stt = clean_str(row.iloc[col_mapping['stt']]) if col_mapping['stt'] is not None else ""
            desc = clean_str(row.iloc[col_mapping['description']]) if col_mapping['description'] is not None else ""
            unit = clean_str(row.iloc[col_mapping['unit']]) if col_mapping['unit'] is not None else ""
            qty_inv = row.iloc[col_mapping['qty_invited']] if col_mapping['qty_invited'] is not None else np.nan
            qty_bid = row.iloc[col_mapping['qty_bid']] if col_mapping['qty_bid'] is not None else np.nan
            price = row.iloc[col_mapping['price']] if col_mapping['price'] is not None else np.nan
            total = row.iloc[col_mapping['total']] if col_mapping['total'] is not None else np.nan
            
            # Skip empty rows
            if not stt and not desc and not unit and pd.isna(qty_inv) and pd.isna(price):
                continue
                
            print(f"  Row {idx} | STT: {stt} | Desc: {desc[:30]} | Unit: {unit} | QtyInv: {qty_inv} | QtyBid: {qty_bid} | Price: {price} | Total: {total}")
            count += 1
            if count >= 10:
                break
