import pdfplumber
import re

def clean_for_match(text):
    if not text: return ""
    s = str(text).lower()
    s = re.sub(r'[\s\.\(\)\[\]\-\_\*，,]', '', s)
    s = s.replace('1', 'i').replace('0', 'o').replace('l', 'i')
    aliases = {"美國":"美", "巴西":"巴", "澳洲":"澳", "英國":"英", "紐西蘭":"紐", "阿根廷":"阿", "烏拉圭":"烏", "加拿大":"加", "抄碼":"抄"}
    for k, v in aliases.items(): s = s.replace(k, v)
    return s

def get_keywords(name):
    return [clean_for_match(p) for p in str(name).split() if clean_for_match(p)]

def scan_pdf_with_anchors(pdf_bytes, targets, supplier_name=""):
    all_rows = []
    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        cells = [str(c).replace('\n', ' ').strip() if c else "" for c in row]
                        if any(cells): all_rows.append(cells)
            text = page.extract_text()
            if text:
                for line in text.split('\n'):
                    if line.strip():
                        fake_cells = [c.strip() for c in re.split(r' {2,}|\t', line.strip()) if c.strip()]
                        all_rows.append(fake_cells)

    extracted_items = {}
    found_skus = set()
    sorted_targets = sorted(targets, key=lambda x: len(str(x['name'])), reverse=True)

    for target in sorted_targets:
        target_name = str(target['name'])
        keywords = get_keywords(target_name)
        if not keywords: continue
        
        for row in all_rows:
            if target['sku'] in found_skus: break
                
            for col_idx, cell in enumerate(row):
                if cell == "[CONSUMED]": continue
                
                cell_clean = clean_for_match(cell)
                
                if all(kw in cell_clean for kw in keywords):
                    search_cells = row[col_idx : col_idx+4]
                    search_str = " ".join(search_cells)
                    search_str = re.sub(r'\$\s*([\d\s\.]+)', lambda m: '$' + m.group(1).replace(" ", ""), search_str)
                    
                    last_idx = 0
                    for orig_p in target_name.split():
                        p_pat = r'\s*'.join(re.escape(c) for c in orig_p if c.isalnum() or c in '()[]-')
                        if not p_pat: continue
                        m = re.search(p_pat, search_str, re.IGNORECASE)
                        if m and m.end() > last_idx:
                            last_idx = m.end()
                            
                    right_side = search_str[last_idx:]
                    
                    is_sold_out = False
                    qing_match = re.search(r'\b清\b|清(?!真|水|遠)', right_side)
                    
                    price_match = None
                    explicit_price = re.search(r'\$\s*(\d+\.\d+|\d+)', right_side)
                    
                    if explicit_price:
                        price_match = explicit_price
                    elif qing_match:
                        is_sold_out = True
                    else:
                        # 💡 終極防護：加入 kK 識別，專剋新興城的 15.0K 寫法，阻止跨欄抓取 9.5P
                        unit_price = re.search(r'(?<![a-zA-Z0-9\-\.\u4e00-\u9fa5])(\d+\.\d+|\d+)\s*(?:[pP磅kK]|/P|/p|lb|/lb|kg|/kg|/k)(?![a-zA-Z0-9\u4e00-\u9fa5])', right_side, re.IGNORECASE)
                        if unit_price:
                            price_match = unit_price
                        else:
                            nums = list(re.finditer(r'(?<![a-zA-Z0-9\-\.\u4e00-\u9fa5])(\d+\.\d+|\d+)(?![a-zA-Z0-9\.\u4e00-\u9fa5])', right_side))
                            valid = [m for m in nums if float(m.group(1)) < 1000]
                            if valid: price_match = valid[-1] 

                    if is_sold_out:
                        raw_price = 0.0
                        unit = "SOLD_OUT"
                    elif price_match:
                        raw_price = float(price_match.group(1))
                        
                        # 💡 直接從抓到的價錢標籤判斷單位 (15.0K 就是 KG，9.5P 就是 LB)
                        match_text = price_match.group(0).lower()
                        if 'k' in match_text or 'kg' in match_text or '公斤' in match_text:
                            unit = "KG"
                        elif 'p' in match_text or 'lb' in match_text or '磅' in match_text:
                            unit = "LB"
                        elif supplier_name == "形澧": 
                            unit = "LB"
                        else:
                            ctx = right_side.lower()
                            if re.search(r'(kg|公斤|/k)', ctx): unit = "KG"
                            elif re.search(r'(lb|磅|/l|/p)', ctx): unit = "LB"
                            else:
                                full_row = " ".join(row).lower()
                                if "kg" in full_row or "公斤" in full_row:
                                    if "lb" not in full_row and "磅" not in full_row:
                                        unit = "KG"
                                    else:
                                        unit = "LB"
                                else:
                                    unit = "LB"
                    else:
                        continue 

                    extracted_items[target['sku']] = {
                        'raw_price': raw_price,
                        'guessed_unit': unit,
                        'raw_name': target_name,
                        'matched_line': " | ".join(search_cells)
                    }
                    found_skus.add(target['sku'])
                    row[col_idx] = "[CONSUMED]"
                    break

    return extracted_items