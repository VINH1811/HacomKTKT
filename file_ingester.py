import os
import re
import pandas as pd
import numpy as np

class FileIngester:
    def __init__(self):
        pass

    def clean_string(self, val):
        if pd.isna(val):
            return ""
        return str(val).strip()

    def parse_float(self, val):
        if pd.isna(val):
            return None
        val_str = str(val).strip().replace(",", "")
        
        # Check for #REF! or other Excel errors
        if "#ref" in val_str.lower():
            return "REF_ERROR"
            
        # Extract number if it has text (e.g. formulas or unit names)
        # However, usually it should be a clean number.
        try:
            return float(val_str)
        except ValueError:
            # Try to find first numeric part
            matches = re.findall(r"[-+]?\d*\.\d+|\d+", val_str)
            if matches:
                try:
                    return float(matches[0])
                except ValueError:
                    pass
            return None

    def detect_header_rows(self, df):
        """
        Scans the first 15 rows of the dataframe to find the row index 
        with the maximum number of key table header keywords.
        Returns the header row index and the number of keywords matched.
        """
        nrows = min(15, len(df))
        keywords = ['stt', 'diễn giải', 'đơn vị', 'khối lượng', 'đơn giá', 'thành tiền', 'đvt', 'mã hiệu', 'ghi chú']
        
        max_kw_count = 0
        best_row_idx = 4 # default to row 4 (5th row)
        
        for r in range(nrows):
            row_str = " ".join([str(val).lower() for val in df.iloc[r].dropna()])
            count = sum(1 for kw in keywords if kw in row_str)
            if count > max_kw_count:
                max_kw_count = count
                best_row_idx = r
                
        return best_row_idx, max_kw_count

    def map_columns(self, df, header_row_idx):
        """
        Maps column indices to fields by scanning cells in the header row 
        and the subsequent row (for 2-level headers).
        """
        col_mapping = {
            'stt': None,
            'code': None,
            'description': None,
            'unit': None,
            'qty_invited': None,
            'qty_bid': None,
            'p_vl_chinh': None,
            'p_vl_phu': None,
            'p_nc_may': None,
            'p_quanly': None,
            'p_loinhuan': None,
            'price': None,
            'total': None,
            'note': None
        }
        
        ncols = len(df.columns)
        scores = {c: {
            'stt': 0, 'code': 0, 'desc': 0, 'unit': 0, 'qty_i': 0, 'qty_b': 0,
            'vl_chinh': 0, 'vl_phu': 0, 'nc_may': 0, 'quanly': 0, 'loinhuan': 0,
            'price': 0, 'total': 0, 'note': 0
        } for c in range(ncols)}
        
        header_rows = [header_row_idx]
        if header_row_idx + 1 < len(df):
            header_rows.append(header_row_idx + 1)
            
        for c in range(ncols):
            combined_header = ""
            for r in header_rows:
                cell_val = str(df.iloc[r, c]).strip()
                if not pd.isna(df.iloc[r, c]) and cell_val.lower() != "nan":
                    combined_header += " " + cell_val
                    
            val = combined_header.lower().strip()
            if not val:
                continue
                
            # STT
            if val in ['stt', 'số thứ tự', 'stt (1)', 'stt\n(1)', 'stt(1)']:
                scores[c]['stt'] += 20
            elif 'stt' in val or 'thứ tự' in val:
                scores[c]['stt'] += 10
                
            # Code (Mã hiệu)
            if val in ['mã hiệu', 'mã cv', 'mã hiệu\n(8)', 'mã hiệu (8)', 'mã số']:
                scores[c]['code'] += 20
            elif 'mã hiệu' in val:
                scores[c]['code'] += 10
                
            # Description
            if any(k in val for k in ['diễn giải', 'mô tả công việc', 'tên công việc', 'tên hạng mục', 'nội dung', 'diễn giải\n(2)', 'diễn giải (2)']):
                scores[c]['desc'] += 20
            elif 'mô tả' in val or 'diễn' in val:
                scores[c]['desc'] += 5
                
            # Unit
            if val in ['đơn vị', 'đvt', 'đơn vị tính', 'đơn vị\ntính', 'đơn vị\n(3)', 'đơn vị (3)']:
                scores[c]['unit'] += 20
            elif 'đơn vị' in val or 'đvt' in val:
                scores[c]['unit'] += 10
                
            # Quantity Invited
            if 'kl' in val or 'khối lượng' in val or 'số lượng' in val:
                if 'mời thầu' in val or 'klmt' in val or 'yêu cầu' in val or 'lần 2' in val or 'kl\nmời thầu\nlần 2' in val or 'kl\nmời thầu' in val:
                    scores[c]['qty_i'] += 20
                elif 'chào' in val or 'nhà thầu' in val:
                    scores[c]['qty_b'] += 20
                else:
                    scores[c]['qty_i'] += 5
                    scores[c]['qty_b'] += 5
                    
            # Price Components
            if 'vl chính' in val or 'vật liệu chính' in val or 'vl_chinh' in val:
                scores[c]['vl_chinh'] += 20
            elif 'vl chính' in val:
                scores[c]['vl_chinh'] += 10
                
            if 'vl phụ' in val or 'vật liệu phụ' in val or 'vl_phu' in val:
                scores[c]['vl_phu'] += 20
                
            if 'nc&m' in val or 'nhân công' in val or 'máy' in val or 'nc & máy' in val or 'nc' in val:
                scores[c]['nc_may'] += 20
                
            if 'quản lý' in val or 'cfql' in val or 'chi phí quản lý' in val or 'cf quản lý' in val:
                scores[c]['quanly'] += 20
                
            if 'lợi nhuận' in val or 'ln' in val:
                scores[c]['loinhuan'] += 20
                
            # Price (đơn giá tổng hợp)
            if 'đơn giá' in val or 'đg' in val:
                if 'tổng hợp' in val or 'đg tổng hợp' in val or 'đơn giá tổng hợp' in val:
                    scores[c]['price'] += 25
                elif 'vl' in val or 'nc' in val or 'phụ' in val:
                    # component prices
                    scores[c]['price'] -= 5
                else:
                    scores[c]['price'] += 10
                    
            # Total Amount (Thành tiền)
            if 'thành tiền' in val or 'tt' in val:
                if 'nhà thầu' in val or 'chào' in val or 'boq' in val or 'nhà thầu chào' in val:
                    scores[c]['total'] += 20
                else:
                    scores[c]['total'] += 10
                    
            # Ghi chú (Note)
            if 'ghi chú' in val or 'note' in val:
                scores[c]['note'] += 20

        # Assign columns greedily based on highest scores
        fields = ['stt', 'code', 'description', 'unit', 'qty_invited', 'qty_bid', 
                  'p_vl_chinh', 'p_vl_phu', 'p_nc_may', 'p_quanly', 'p_loinhuan', 
                  'price', 'total', 'note']
                  
        assigned = {}
        for field in fields:
            score_key = {
                'stt': 'stt', 'code': 'code', 'description': 'desc', 'unit': 'unit',
                'qty_invited': 'qty_i', 'qty_bid': 'qty_b',
                'p_vl_chinh': 'vl_chinh', 'p_vl_phu': 'vl_phu', 'p_nc_may': 'nc_may',
                'p_quanly': 'quanly', 'p_loinhuan': 'loinhuan',
                'price': 'price', 'total': 'total', 'note': 'note'
            }[field]
            
            # Find column with max score for this field
            best_col = None
            max_score = -99
            for c in range(ncols):
                # skip already assigned columns if it has a high score for something else
                if c in assigned.values() and field not in ['qty_invited', 'qty_bid', 'price', 'total']:
                    continue
                score = scores[c][score_key]
                if score > max_score:
                    max_score = score
                    best_col = c
            
            if max_score > 2: # threshold for minimum matching confidence
                col_mapping[field] = best_col
                assigned[field] = best_col
                
        # Resolve conflicts or fallbacks
        # If price is None but we have total unit price somewhere, we fallback to standard indexes:
        # In Hacom Mall files:
        # STT=0, Desc=1, Unit=2, QtyInv=3, NoteInv=4, QtyBid=5, Code=7, VL_Chinh=10, VL_Phu=11, NC_May=12, CFQL=13, LN=14, Price=15, TotalInv=16, TotalBid=17
        if col_mapping['stt'] is None and ncols > 0: col_mapping['stt'] = 0
        if col_mapping['description'] is None and ncols > 1: col_mapping['description'] = 1
        if col_mapping['unit'] is None and ncols > 2: col_mapping['unit'] = 2
        if col_mapping['qty_invited'] is None and ncols > 3: col_mapping['qty_invited'] = 3
        if col_mapping['qty_bid'] is None and ncols > 5: col_mapping['qty_bid'] = 5
        if col_mapping['code'] is None and ncols > 7: col_mapping['code'] = 7
        if col_mapping['price'] is None and ncols > 15: col_mapping['price'] = 15
        if col_mapping['total'] is None and ncols > 17: col_mapping['total'] = 17
        
        return col_mapping

    def ingest_sheet(self, df, sheet_name):
        """
        Parses a single sheet and returns a list of raw row dictionaries.
        """
        header_row_idx, score = self.detect_header_rows(df)
        col_mapping = self.map_columns(df, header_row_idx)
        
        # Start reading data after headers
        data_start_row = header_row_idx + 2
        if header_row_idx + 1 < len(df):
            # Check if row after header is column numbers (e.g. 1, 2, 3...)
            row_vals = [str(val).strip() for val in df.iloc[header_row_idx + 1].dropna()]
            is_numbers_row = all(val.isdigit() or '=' in val or '-' in val for val in row_vals if val)
            if is_numbers_row:
                data_start_row = header_row_idx + 2
            else:
                data_start_row = header_row_idx + 1
        
        raw_rows = []
        for idx in range(data_start_row, len(df)):
            row = df.iloc[idx]
            
            # Read cell values based on mapping
            stt = self.clean_string(row.iloc[col_mapping['stt']]) if col_mapping['stt'] is not None else ""
            code = self.clean_string(row.iloc[col_mapping['code']]) if col_mapping['code'] is not None else ""
            desc = self.clean_string(row.iloc[col_mapping['description']]) if col_mapping['description'] is not None else ""
            unit = self.clean_string(row.iloc[col_mapping['unit']]) if col_mapping['unit'] is not None else ""
            
            # Check if row is completely empty
            row_str = "".join([str(val) for val in row.dropna() if str(val).strip()])
            if not row_str:
                continue
                
            # Parse numbers and detect #REF! errors
            has_ref_error = False
            ref_error_cols = []
            
            qty_invited_val = row.iloc[col_mapping['qty_invited']] if col_mapping['qty_invited'] is not None else np.nan
            qty_bid_val = row.iloc[col_mapping['qty_bid']] if col_mapping['qty_bid'] is not None else np.nan
            price_val = row.iloc[col_mapping['price']] if col_mapping['price'] is not None else np.nan
            total_val = row.iloc[col_mapping['total']] if col_mapping['total'] is not None else np.nan
            
            # Parse qty_invited
            qty_invited = self.parse_float(qty_invited_val)
            if qty_invited == "REF_ERROR":
                has_ref_error = True
                ref_error_cols.append("KL Mời thầu")
                qty_invited = None
                
            # Parse qty_bid
            qty_bid = self.parse_float(qty_bid_val)
            if qty_bid == "REF_ERROR":
                has_ref_error = True
                ref_error_cols.append("KL Chào")
                qty_bid = None
                
            # Parse price
            price = self.parse_float(price_val)
            if price == "REF_ERROR":
                has_ref_error = True
                ref_error_cols.append("Đơn giá")
                price = None
                
            # Parse total
            total = self.parse_float(total_val)
            if total == "REF_ERROR":
                has_ref_error = True
                ref_error_cols.append("Thành tiền")
                total = None
                
            # Parse components
            p_vl_chinh = self.parse_float(row.iloc[col_mapping['p_vl_chinh']]) if col_mapping['p_vl_chinh'] is not None else None
            p_vl_phu = self.parse_float(row.iloc[col_mapping['p_vl_phu']]) if col_mapping['p_vl_phu'] is not None else None
            p_nc_may = self.parse_float(row.iloc[col_mapping['p_nc_may']]) if col_mapping['p_nc_may'] is not None else None
            p_quanly = self.parse_float(row.iloc[col_mapping['p_quanly']]) if col_mapping['p_quanly'] is not None else None
            p_loinhuan = self.parse_float(row.iloc[col_mapping['p_loinhuan']]) if col_mapping['p_loinhuan'] is not None else None
            
            # Also check text fields for #REF!
            for field, val in [("STT", stt), ("Mã hiệu", code), ("Diễn giải", desc), ("Đơn vị", unit)]:
                if "#ref" in val.lower():
                    has_ref_error = True
                    ref_error_cols.append(field)
                    
            raw_rows.append({
                'sheet_name': sheet_name,
                'row_idx': idx + 1,  # 1-indexed for spreadsheet reference
                'stt': stt,
                'code': code,
                'description': desc,
                'unit': unit,
                'qty_invited': qty_invited,
                'qty_bid': qty_bid,
                'p_vl_chinh': p_vl_chinh if p_vl_chinh != "REF_ERROR" else None,
                'p_vl_phu': p_vl_phu if p_vl_phu != "REF_ERROR" else None,
                'p_nc_may': p_nc_may if p_nc_may != "REF_ERROR" else None,
                'p_quanly': p_quanly if p_quanly != "REF_ERROR" else None,
                'p_loinhuan': p_loinhuan if p_loinhuan != "REF_ERROR" else None,
                'price': price,
                'total': total,
                'has_ref_error': has_ref_error,
                'ref_error_cols': ref_error_cols
            })
            
        return raw_rows

    def ingest_file(self, file_source):
        """
        Reads an Excel file from a file path or file-like object.
        Returns a dictionary mapping sheet names to lists of raw row dicts.
        """
        xl = pd.ExcelFile(file_source)
        sheets_data = {}
        
        for sheet in xl.sheet_names:
            sheet_lower = sheet.lower()
            # Filter out summary, cover or term sheets
            if any(k in sheet_lower for k in ['tổng hợp', 'tong hop', 'tong', 'bìa', 'bia', 'phạm vi', 'pham vi', 'điều khoản', 'dieu khoan', 'dmvt']):
                continue
                
            # Read sheet
            df = pd.read_excel(xl, sheet_name=sheet, header=None)
            rows = self.ingest_sheet(df, sheet)
            if rows:
                sheets_data[sheet] = rows
                
        return sheets_data
