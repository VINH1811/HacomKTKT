import re
import numpy as np
import difflib

class ComparisonEngine:
    def __init__(self, similarity_threshold=0.80):
        self.similarity_threshold = similarity_threshold

    def clean_text(self, s):
        if not s:
            return ""
        return re.sub(r'\s+', ' ', str(s).strip().lower())

    def get_similarity(self, s1_clean, s2_clean):
        if not s1_clean or not s2_clean:
            return 0.0
        # O(1) exact match check
        if s1_clean == s2_clean:
            return 1.0
            
        # Length check fallback
        l1, l2 = len(s1_clean), len(s2_clean)
        ratio_len = min(l1, l2) / max(l1, l2)
        if ratio_len < 0.5: # If lengths are very different, they can't match
            return 0.0
            
        return difflib.SequenceMatcher(None, s1_clean, s2_clean).ratio()

    def align_rows(self, system, section, contractor_data):
        """
        Highly optimized alignment of rows across all contractors.
        Uses pre-cleaned descriptions, exact matching, and index sliding windows.
        """
        contractor_names = list(contractor_data.keys())
        if not contractor_names:
            return []
            
        # 1. Select the base contractor: the one with the most rows in this system/section
        base_contractor = sorted(contractor_names, key=lambda n: len([
            x for x in contractor_data[n] 
            if x['system'] == system and x['section'] == section
        ]), reverse=True)[0]
        
        base_items = [
            x for x in contractor_data[base_contractor] 
            if x['system'] == system and x['section'] == section
        ]
        
        # Pre-clean base descriptions
        for item in base_items:
            item['desc_clean'] = self.clean_text(item['description'])
            
        canonical_items = []
        canonical_by_stt = {}
        
        # Initialize canonical items
        for idx, item in enumerate(base_items):
            c_item = {
                'system': system,
                'section': section,
                'row_type': item['row_type'],
                'stt': item['stt'],
                'code': item['code'],
                'description': item['description'],
                'desc_clean': item['desc_clean'],
                'unit': item['unit'],
                'qty_invited': item['qty_invited'],
                'bids': {base_contractor: item}
            }
            canonical_items.append(c_item)
            
            stt_cleaned = item['stt'].strip().lower()
            if stt_cleaned:
                canonical_by_stt[stt_cleaned] = idx
            
        # 2. Match other contractors' rows against canonical_items, preserving order
        for contractor in contractor_names:
            if contractor == base_contractor:
                continue
                
            items = [
                x for x in contractor_data[contractor] 
                if x['system'] == system and x['section'] == section
            ]
            
            # Pre-clean descriptions
            for item in items:
                item['desc_clean'] = self.clean_text(item['description'])
                
            matched_canonical_indices = set()
            last_matched_idx = -1
            
            for item in items:
                matched_idx = None
                item_stt_cleaned = item['stt'].strip().lower()
                
                # OPTIMIZATION 1: Direct lookup by STT
                if item_stt_cleaned and item_stt_cleaned in canonical_by_stt:
                    idx = canonical_by_stt[item_stt_cleaned]
                    if idx not in matched_canonical_indices:
                        c_item = canonical_items[idx]
                        if item['row_type'] == c_item['row_type']:
                            sim = self.get_similarity(item['desc_clean'], c_item['desc_clean'])
                            if sim > 0.60:
                                matched_idx = idx
                                
                # OPTIMIZATION 2: Check the very next sequential item (common case)
                if matched_idx is None and last_matched_idx + 1 < len(canonical_items):
                    idx = last_matched_idx + 1
                    if idx not in matched_canonical_indices:
                        c_item = canonical_items[idx]
                        if item['row_type'] == c_item['row_type']:
                            sim = self.get_similarity(item['desc_clean'], c_item['desc_clean'])
                            if sim > 0.80:
                                matched_idx = idx
                                
                # OPTIMIZATION 3: Check sliding window around last_matched_idx
                if matched_idx is None:
                    # Look in a small window of +/- 15 around last_matched_idx
                    start_w = max(0, last_matched_idx - 15)
                    end_w = min(len(canonical_items), last_matched_idx + 15)
                    
                    best_score = 0.0
                    best_w_idx = None
                    
                    for i in range(start_w, end_w):
                        if i in matched_canonical_indices:
                            continue
                        c_item = canonical_items[i]
                        if item['row_type'] != c_item['row_type']:
                            continue
                            
                        stt_match = (item['stt'] and c_item['stt'] and item['stt'].lower() == c_item['stt'].lower())
                        desc_sim = self.get_similarity(item['desc_clean'], c_item['desc_clean'])
                        
                        score = 0.0
                        if item['row_type'] == 'header':
                            if stt_match and desc_sim > 0.70:
                                score = 0.7 + desc_sim * 0.3
                            else:
                                score = desc_sim
                        else:
                            if stt_match and desc_sim > 0.65:
                                score = 0.8 + desc_sim * 0.2
                            elif desc_sim > self.similarity_threshold:
                                score = desc_sim
                                
                        if score > best_score:
                            best_score = score
                            best_w_idx = i
                            
                    threshold = 0.75 if item['row_type'] == 'header' else 0.80
                    if best_w_idx is not None and best_score >= threshold:
                        matched_idx = best_w_idx
                        
                # OPTIMIZATION 4: Full search (ONLY for 'priced' items with longer descriptions)
                # Skip full search for headers and detailed components to avoid O(N^2) complexity on irrelevant rows
                if matched_idx is None and item['row_type'] == 'priced' and len(item['desc_clean']) > 15:
                    best_score = 0.0
                    best_full_idx = None
                    
                    for i, c_item in enumerate(canonical_items):
                        if i in matched_canonical_indices:
                            continue
                        if item['row_type'] != c_item['row_type']:
                            continue
                        
                        desc_sim = self.get_similarity(item['desc_clean'], c_item['desc_clean'])
                        if desc_sim > self.similarity_threshold:
                            if desc_sim > best_score:
                                best_score = desc_sim
                                best_full_idx = i
                                
                    if best_full_idx is not None:
                        matched_idx = best_full_idx

                # Handle matching result
                if matched_idx is not None:
                    canonical_items[matched_idx]['bids'][contractor] = item
                    matched_canonical_indices.add(matched_idx)
                    last_matched_idx = matched_idx
                    
                    # Merge code and qty_invited
                    if not canonical_items[matched_idx]['code'] and item['code']:
                        canonical_items[matched_idx]['code'] = item['code']
                    if canonical_items[matched_idx]['qty_invited'] is None and item['qty_invited'] is not None:
                        canonical_items[matched_idx]['qty_invited'] = item['qty_invited']
                else:
                    # Insert new canonical item
                    new_c_item = {
                        'system': system,
                        'section': section,
                        'row_type': item['row_type'],
                        'stt': item['stt'],
                        'code': item['code'],
                        'description': item['description'],
                        'desc_clean': item['desc_clean'],
                        'unit': item['unit'],
                        'qty_invited': item['qty_invited'],
                        'bids': {contractor: item}
                    }
                    
                    insert_idx = last_matched_idx + 1
                    if insert_idx >= len(canonical_items):
                        canonical_items.append(new_c_item)
                        insert_idx = len(canonical_items) - 1
                    else:
                        canonical_items.insert(insert_idx, new_c_item)
                        
                    last_matched_idx = insert_idx
                    
                    # Adjust indices of matched items
                    temp_set = set()
                    for idx in matched_canonical_indices:
                        if idx >= insert_idx:
                            temp_set.add(idx + 1)
                        else:
                            temp_set.add(idx)
                    matched_canonical_indices = temp_set
                    
                    # Rebuild STT map
                    canonical_by_stt.clear()
                    for idx_c, c_item in enumerate(canonical_items):
                        stt_cleaned = c_item['stt'].strip().lower()
                        if stt_cleaned:
                            canonical_by_stt[stt_cleaned] = idx_c
                            
        return canonical_items

    def compare_bids(self, contractor_data):
        """
        Main entry point for comparison. Aligns all items and computes differences.
        """
        contractor_names = list(contractor_data.keys())
        systems = [
            "1. HT điện",
            "2. HT điện nhẹ",
            "3. HT CTN",
            "4.1 ĐH VRV",
            "4.2 Quạt",
            "4.3 DHKK & TG",
            "5. Ngăn cháy lan"
        ]
        
        canonical_a_all = []
        canonical_b_all = []
        flags = []
        
        for system in systems:
            # 1. Align Section A (Invited)
            canonical_a = self.align_rows(system, "A", contractor_data)
            canonical_a_all.extend(canonical_a)
            
            # 2. Align Section B (Arising)
            canonical_b = self.align_rows(system, "B", contractor_data)
            canonical_b_all.extend(canonical_b)
            
        # Now analyze differences and flag items
        all_canonical = canonical_a_all + canonical_b_all
        
        # 1. Standard flags check
        for c_item in all_canonical:
            if c_item['row_type'] != 'priced':
                continue
                
            qty_invited = c_item['qty_invited']
            system = c_item['system']
            stt = c_item['stt']
            desc = c_item['description']
            section = c_item['section']
            
            # Collect unit prices for median calculation
            valid_prices = []
            
            for contractor in contractor_names:
                bid = c_item['bids'].get(contractor)
                
                # Check if contractor completely missed this item in Section A
                if section == "A" and (bid is None or bid.get('qty_bid') is None or bid.get('price') is None):
                    flags.append({
                        'contractor': contractor,
                        'system': system,
                        'stt': stt,
                        'description': desc,
                        'type': 'ITEM_MISSING',
                        'severity': 'HIGH',
                        'message': f"Nhà thầu thiếu hạng mục này trong phần thầu chính (theo KLMT).",
                        'delta_pct': 100.0,
                        'delta_abs': float(qty_invited * 0) if qty_invited else 0.0
                    })
                    continue
                
                if bid is None:
                    continue
                    
                # Check for #REF! error
                if bid.get('has_ref_error'):
                    flags.append({
                        'contractor': contractor,
                        'system': system,
                        'stt': stt,
                        'description': desc,
                        'type': 'REF_ERROR',
                        'severity': 'HIGH',
                        'message': f"Lỗi #REF! trong Excel tại các cột: {', '.join(bid['ref_error_cols'])}",
                        'delta_pct': 0.0,
                        'delta_abs': 0.0
                    })
                
                qty_bid = bid.get('qty_bid')
                price = bid.get('price')
                total = bid.get('total')
                
                # Check for quantity deviations in Section A
                if section == "A" and qty_invited is not None and qty_bid is not None:
                    if abs(qty_bid - qty_invited) > 1e-4:
                        diff = qty_bid - qty_invited
                        diff_pct = (diff / qty_invited * 100) if qty_invited > 0 else 100.0
                        flag_type = 'QTY_OVER' if diff > 0 else 'QTY_UNDER'
                        severity = 'HIGH' if abs(diff_pct) > 10 else 'MED'
                        flags.append({
                            'contractor': contractor,
                            'system': system,
                            'stt': stt,
                            'description': desc,
                            'type': flag_type,
                            'severity': severity,
                            'message': f"Khối lượng chào ({qty_bid:,.2f}) lệch so với KLMT ({qty_invited:,.2f}) là {diff_pct:+.2f}%.",
                            'delta_pct': diff_pct,
                            'delta_abs': diff
                        })
                
                # Check for arithmetic error (qty * price != total)
                if qty_bid is not None and price is not None and total is not None:
                    expected_total = qty_bid * price
                    if abs(total - expected_total) > 10.0:  # Threshold > 10 VNĐ
                        diff = total - expected_total
                        flags.append({
                            'contractor': contractor,
                            'system': system,
                            'stt': stt,
                            'description': desc,
                            'type': 'ARITHMETIC_ERROR',
                            'severity': 'HIGH',
                            'message': f"Sai lệch số học: Tích KL x Đơn giá = {expected_total:,.2f} VNĐ, nhưng nhà thầu ghi {total:,.2f} VNĐ (lệch {diff:,.2f} VNĐ).",
                            'delta_pct': (diff / expected_total * 100) if expected_total > 0 else 0.0,
                            'delta_abs': diff
                        })
                        
                if price is not None:
                    valid_prices.append((contractor, price))
            
            # 2. Check for unit price deviations compared to median
            if len(valid_prices) >= 2:
                prices_only = [p[1] for p in valid_prices]
                median_price = np.median(prices_only)
                
                if median_price > 0:
                    for contractor, price in valid_prices:
                        ratio = price / median_price
                        if ratio > 1.25:  # 25% higher than median
                            diff_pct = (ratio - 1) * 100
                            flags.append({
                                'contractor': contractor,
                                'system': system,
                                'stt': stt,
                                'description': desc,
                                'type': 'PRICE_HIGH',
                                'severity': 'MED',
                                'message': f"Đơn giá chào ({price:,.2f} VNĐ) cao hơn {diff_pct:.2f}% so với giá trung vị thầu ({median_price:,.2f} VNĐ).",
                                'delta_pct': diff_pct,
                                'delta_abs': price - median_price
                            })
                        elif ratio < 0.75:  # 25% lower than median
                            diff_pct = (1 - ratio) * 100
                            flags.append({
                                'contractor': contractor,
                                'system': system,
                                'stt': stt,
                                'description': desc,
                                'type': 'PRICE_LOW',
                                'severity': 'MED',
                                'message': f"Đơn giá chào ({price:,.2f} VNĐ) thấp hơn {diff_pct:.2f}% so với giá trung vị thầu ({median_price:,.2f} VNĐ).",
                                'delta_pct': -diff_pct,
                                'delta_abs': price - median_price
                            })

        # Calculate Summary data by System and Contractor
        summary_data = []
        for system in systems:
            row_data = {'Hệ thống': system}
            for contractor in contractor_names:
                invited_sum = 0.0
                bid_sum = 0.0
                arising_sum = 0.0
                
                # Section A items
                for c_item in canonical_a_all:
                    if c_item['system'] == system and c_item['row_type'] == 'priced':
                        bid = c_item['bids'].get(contractor)
                        if bid:
                            qty_invited = c_item['qty_invited']
                            qty_bid = bid.get('qty_bid')
                            price = bid.get('price')
                            total = bid.get('total')
                            
                            if total is not None:
                                bid_sum += total
                            elif qty_bid is not None and price is not None:
                                bid_sum += qty_bid * price
                                
                            if qty_invited is not None and price is not None:
                                invited_sum += qty_invited * price
                                
                # Section B items (arising)
                for c_item in canonical_b_all:
                    if c_item['system'] == system and c_item['row_type'] == 'priced':
                        bid = c_item['bids'].get(contractor)
                        if bid:
                            total = bid.get('total')
                            price = bid.get('price')
                            qty_bid = bid.get('qty_bid')
                            if total is not None:
                                arising_sum += total
                            elif qty_bid is not None and price is not None:
                                arising_sum += qty_bid * price
                                
                row_data[f'{contractor}_TheoKLMT'] = invited_sum
                row_data[f'{contractor}_Chào'] = bid_sum
                row_data[f'{contractor}_PhátSinh'] = arising_sum
                row_data[f'{contractor}_TổngCộng'] = bid_sum + arising_sum
                
            summary_data.append(row_data)
            
        # Compute ranking and automated comments
        comments = self.generate_comments(contractor_names, summary_data, flags)
        
        comparison_results = {
            'contractors': contractor_names,
            'canonical_a': canonical_a_all,
            'canonical_b': canonical_b_all,
            'flags': flags,
            'summary_data': summary_data,
            'comments': comments
        }
        
        return comparison_results

    def generate_comments(self, contractors, summary_data, flags):
        """
        Generates automated text comments summarizing key comparison insights.
        """
        comments = []
        
        # 1. Total cost comparison and ranking
        contractor_totals = {}
        for c in contractors:
            tot = sum(row[f'{c}_TổngCộng'] for row in summary_data)
            contractor_totals[c] = tot
            
        sorted_totals = sorted(contractor_totals.items(), key=lambda x: x[1])
        
        comments.append("### 1. Xếp hạng giá chào thầu (Tổng cộng trước VAT)")
        for rank, (name, total) in enumerate(sorted_totals, 1):
            comments.append(f" - **Hạng {rank}**: Nhà thầu **{name}** với tổng giá trị chào thầu: **{total:,.2f} VNĐ**")
            
        # Price diff analysis
        if len(sorted_totals) >= 2:
            best_name, best_val = sorted_totals[0]
            worst_name, worst_val = sorted_totals[-1]
            diff_pct = ((worst_val - best_val) / best_val * 100) if best_val > 0 else 0
            comments.append(f" - *Nhận xét*: Chênh lệch giữa giá chào thầu thấp nhất ({best_name}) và cao nhất ({worst_name}) là **{diff_pct:.2f}%** (tương đương **{worst_val - best_val:,.2f} VNĐ**).")
            
        # 2. System-by-system highlights
        comments.append("\n### 2. Phân tích theo hệ thống công việc")
        for row in summary_data:
            sys_name = row['Hệ thống']
            sys_totals = [(c, row[f'{c}_TổngCộng']) for c in contractors]
            sorted_sys = sorted(sys_totals, key=lambda x: x[1])
            comments.append(f" - **{sys_name}**: Nhà thầu **{sorted_sys[0][0]}** có giá chào thấp nhất (**{sorted_sys[0][1]:,.2f} VNĐ**); nhà thầu **{sorted_sys[-1][0]}** có giá chào cao nhất (**{sorted_sys[-1][1]:,.2f} VNĐ**).")
            
        # 3. Quality Audit & Flag highlights
        comments.append("\n### 3. Tổng hợp lỗi kỹ thuật & khối lượng chào thầu")
        
        # Count flags by type and contractor
        flag_counts = {c: {} for c in contractors}
        for flag in flags:
            c = flag['contractor']
            ftype = flag['type']
            flag_counts[c][ftype] = flag_counts[c].get(ftype, 0) + 1
            
        for c in contractors:
            counts = flag_counts[c]
            if not counts:
                comments.append(f" - Nhà thầu **{c}**: Không phát hiện lỗi kỹ thuật đáng kể.")
                continue
                
            issues = []
            if counts.get('ITEM_MISSING'):
                issues.append(f"bỏ thiếu **{counts['ITEM_MISSING']}** hạng mục thầu chính")
            if counts.get('REF_ERROR'):
                issues.append(f"gặp **{counts['REF_ERROR']}** lỗi #REF! trong bảng Excel")
            if counts.get('ARITHMETIC_ERROR'):
                issues.append(f"mắc **{counts['ARITHMETIC_ERROR']}** lỗi tính toán số học (KL x ĐG != Thành tiền)")
            if counts.get('QTY_OVER') or counts.get('QTY_UNDER'):
                qty_issues = counts.get('QTY_OVER', 0) + counts.get('QTY_UNDER', 0)
                issues.append(f"chào lệch khối lượng ở **{qty_issues}** hạng mục")
            if counts.get('PRICE_HIGH') or counts.get('PRICE_LOW'):
                price_issues = counts.get('PRICE_HIGH', 0) + counts.get('PRICE_LOW', 0)
                issues.append(f"đơn giá lệch lớn (>25%) ở **{price_issues}** hạng mục so với median")
                
            comments.append(f" - Nhà thầu **{c}**: Phát hiện " + ", ".join(issues) + ".")
            
        return "\n".join(comments)
