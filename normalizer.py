import re

class Normalizer:
    def __init__(self):
        # 7 standard systems in the BOQ
        self.standard_systems = [
            "1. HT điện",
            "2. HT điện nhẹ",
            "3. HT CTN",
            "4.1 ĐH VRV",
            "4.2 Quạt",
            "4.3 DHKK & TG",
            "5. Ngăn cháy lan"
        ]

    def normalize_unit(self, unit_str):
        """
        Normalizes unit strings to standard Vietnamese characters.
        """
        if not unit_str:
            return ""
        
        u = unit_str.strip().lower()
        # Remove trailing dots or spaces
        u = re.sub(r'\.+$', '', u).strip()
        
        # Mapping common variations to standard units
        unit_map = {
            'm2': 'm²',
            'm2 ': 'm²',
            'm vuông': 'm²',
            'mét vuông': 'm²',
            'm3': 'm³',
            'm khối': 'm³',
            'mét khối': 'm³',
            'cai': 'cái',
            'cái': 'cái',
            'bo': 'bộ',
            'bộ': 'bộ',
            'm': 'm',
            'md': 'm',
            'mét': 'm',
            'mét dài': 'm',
            'kg': 'kg',
            'lit': 'lít',
            'lít': 'lít',
            'hop': 'hộp',
            'hộp': 'hộp',
            'lo': 'lô',
            'lô': 'lô',
            'chỗ': 'chỗ',
            'cho': 'chỗ',
            'tủ': 'tủ',
            'tu': 'tủ',
            'hệ thống': 'hệ thống',
            'he thong': 'hệ thống',
            'gói': 'gói',
            'goi': 'gói',
            'vị trí': 'vị trí',
            'vi tri': 'vị trí',
            'tấm': 'tấm',
            'tam': 'tấm',
            'quả': 'quả',
            'qua': 'quả',
        }
        
        if u in unit_map:
            return unit_map[u]
            
        # Fallback regex matches
        if re.match(r'^m2\b|^mét\s*vuông', u):
            return 'm²'
        if re.match(r'^m3\b|^mét\s*khối', u):
            return 'm³'
        if re.match(r'^m\b|^mét\s*dài|^md\b', u):
            return 'm'
        
        return unit_str.strip()

    def map_sheet_to_system(self, sheet_name):
        """
        Maps a sheet name to one of the 7 standard systems.
        """
        s = sheet_name.lower().strip()
        
        if '1.' in s or ('điện' in s and 'nhẹ' not in s and 'dien' in s):
            return "1. HT điện"
        if '2.' in s or 'nhẹ' in s or 'nhe' in s:
            return "2. HT điện nhẹ"
        if '3.' in s or 'ctn' in s or 'cấp thoát nước' in s or 'cap thoat' in s:
            return "3. HT CTN"
        if '4.1' in s or 'vrv' in s:
            return "4.1 ĐH VRV"
        if '4.2' in s or 'quạt' in s or 'quat' in s:
            return "4.2 Quạt"
        if '4.3' in s or 'dhkk' in s or 'điều hòa không khí' in s or 'dieu hoa' in s:
            return "4.3 DHKK & TG"
        if '5.' in s or 'ngăn cháy' in s or 'ngan chay' in s or 'lan' in s:
            return "5. Ngăn cháy lan"
            
        # Default fallbacks
        if 'điện' in s and 'nhẹ' not in s: return "1. HT điện"
        if 'điện nhẹ' in s or 'nhe' in s: return "2. HT điện nhẹ"
        if 'nước' in s or 'cấp thoát' in s: return "3. HT CTN"
        if 'vrv' in s or 'vrf' in s: return "4.1 ĐH VRV"
        if 'quạt' in s or 'quat' in s: return "4.2 Quạt"
        if 'điều hòa' in s or 'dhkk' in s: return "4.3 DHKK & TG"
        if 'cháy lan' in s or 'ngăn cháy' in s: return "5. Ngăn cháy lan"
        
        return sheet_name

    def normalize_items_multisheet(self, raw_sheets_data):
        """
        Normalizes items for files that have multiple sheets (e.g. Linh Anh, Searefico, Trí Trung).
        """
        normalized_items = []
        
        for sheet_name, rows in raw_sheets_data.items():
            system = self.map_sheet_to_system(sheet_name)
            current_section = "A" # Default section is A (theo KLMT)
            
            for row in rows:
                desc = row['description']
                stt = row['stt']
                unit = row['unit']
                
                # Check for section headings
                desc_lower = desc.lower()
                
                # We check if it is a section heading row
                # Header rows have empty unit, price, and qty
                is_header_row = (not unit and row['qty_invited'] is None and row['price'] is None)
                
                if is_header_row:
                    if 'phát sinh ngoài klmt' in desc_lower or 'phát sinh ngoài' in desc_lower or 'nhà thầu bổ sung' in desc_lower or stt.strip().upper() == 'B':
                        current_section = "B"
                    elif 'đầu mục công việc theo klmt' in desc_lower or stt.strip().upper() == 'A':
                        current_section = "A"
                
                # If this is a work item or has description
                if desc:
                    normalized_row = dict(row)
                    normalized_row['system'] = system
                    normalized_row['section'] = current_section
                    normalized_row['unit'] = self.normalize_unit(unit)
                    
                    # We classify row type:
                    # - header: unit is empty, qty_invited/qty_bid is None, price is None
                    # - component: unit is not empty, but price is None or 0 and it has quantities
                    # - priced: has unit, quantity, and price > 0
                    if is_header_row:
                        normalized_row['row_type'] = 'header'
                    elif unit and (row['qty_invited'] is not None or row['qty_bid'] is not None) and (row['price'] is None or row['price'] == 0):
                        normalized_row['row_type'] = 'component'
                    else:
                        normalized_row['row_type'] = 'priced'
                        
                    normalized_items.append(normalized_row)
                    
        return normalized_items

    def normalize_items_singlesheet(self, raw_sheet_rows):
        """
        Normalizes items for a single sheet containing all systems (e.g. Vân Khánh).
        Uses a sequential state machine to determine systems and sections.
        """
        normalized_items = []
        
        current_system = "1. HT điện"
        current_section = "A"
        
        for row in raw_sheet_rows:
            desc = row['description']
            stt = row['stt']
            unit = row['unit']
            
            # Check for section or system transitions in header rows
            desc_lower = desc.lower()
            is_header_row = (not unit and row['qty_invited'] is None and row['price'] is None)
            
            if is_header_row:
                # 1. Section transitions
                if 'phát sinh ngoài klmt' in desc_lower or 'phát sinh ngoài' in desc_lower or stt.strip().upper() == 'B':
                    current_section = "B"
                elif 'đầu mục công việc theo klmt' in desc_lower or stt.strip().upper() == 'A':
                    current_section = "A"
                
                # 2. System transitions
                if 'hạng mục: điện' in desc_lower or 'hệ thống điện' in desc_lower:
                    if 'nhẹ' not in desc_lower:
                        current_system = "1. HT điện"
                elif 'hạng mục: điện nhẹ' in desc_lower or 'hệ thống điện nhẹ' in desc_lower:
                    current_system = "2. HT điện nhẹ"
                elif 'hạng mục: cấp thoát nước' in desc_lower or 'hệ thống cấp thoát nước' in desc_lower or 'hệ thống bể bơi' in desc_lower:
                    current_system = "3. HT CTN"
                elif 'hạng mục: hvac' in desc_lower or 'hệ thống hvac' in desc_lower:
                    current_system = "4.1 ĐH VRV"
                elif 'quạt thông gió' in desc_lower or 'quạt tăng áp' in desc_lower or 'quạt hút' in desc_lower or 'quạt cấp' in desc_lower:
                    current_system = "4.2 Quạt"
                elif 'điều hòa khánh' in desc_lower or 'điều hòa không khí & thông gió phần chung' in desc_lower or 'ống gió lạnh điều hòa' in desc_lower or 'phân vật tư lắp đặt ống gió' in desc_lower or 'phân vật tư lắp đặt ống đồng' in desc_lower:
                    current_system = "4.3 DHKK & TG"
                elif 'hạng mục: ngăn cháy lan' in desc_lower or 'ngăn cháy lan' in desc_lower:
                    current_system = "5. Ngăn cháy lan"
            
            if desc:
                normalized_row = dict(row)
                normalized_row['system'] = current_system
                normalized_row['section'] = current_section
                normalized_row['unit'] = self.normalize_unit(unit)
                
                if is_header_row:
                    normalized_row['row_type'] = 'header'
                elif unit and (row['qty_invited'] is not None or row['qty_bid'] is not None) and (row['price'] is None or row['price'] == 0):
                    normalized_row['row_type'] = 'component'
                else:
                    normalized_row['row_type'] = 'priced'
                    
                normalized_items.append(normalized_row)
                
        return normalized_items

    def normalize(self, file_name, raw_file_data):
        """
        Main entry point for Normalizer. Checks if file is single-sheet or multi-sheet.
        """
        # If there is only one sheet in raw_file_data, it's a single-sheet file
        if len(raw_file_data) == 1:
            sheet_name = list(raw_file_data.keys())[0]
            return self.normalize_items_singlesheet(raw_file_data[sheet_name])
        else:
            return self.normalize_items_multisheet(raw_file_data)
