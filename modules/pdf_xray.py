# modules/pdf_xray.py
import re

# 全局高頻特徵字典（產地與品牌）
KNOWN_BRANDS = ["CP", "IBP", "EXCEL", "SWIFT", "NATIONAL", "AURORA", "TYSON", "SEARA", "SADIA", "PERDUE", "JBS", "BRF", "KILCOY", "MIDFIELD", "TEYS", "AMH", "CAB", "PRIME", "CHOICE"]
KNOWN_ORIGINS = ["越南", "美國", "巴西", "荷蘭", "加拿大", "澳洲", "紐西蘭", "泰國", "中國", "日本", "丹麥", "西班牙", "愛爾蘭", "英國", "智利", "烏拉圭", "阿根廷", "波蘭", "法國", "德國", "印度"]

def extract_price(text):
    if not text: return None
    clean_text = str(text).replace(" ", "") 
    if "清" in clean_text: return "清"
    nums = [float(n) for n in re.findall(r'\d+\.?\d*', clean_text) if 2 <= float(n) <= 5000]
    return nums[-1] if nums else None

def extract_unit(text, fallback_unit="LB"):
    if not text: return fallback_unit
    up_str = str(text).upper()
    if "KG" in up_str or "公斤" in up_str or "/K" in up_str: return "KG"
    if "LB" in up_str or "磅" in up_str or re.search(r'\b[P]\b', up_str) or "/P" in up_str or "(P)" in up_str: 
        if "*" in up_str or "X" in up_str: return "箱/件"
        return "LB"
    if "箱" in up_str or "CTN" in up_str or "CASE" in up_str or "包" in up_str or "PKT" in up_str or "隻" in up_str or "PC" in up_str: return "箱/件"
    return fallback_unit

def deep_decode_item(raw_name, p_price_str, p_unit_str):
    """
    深度文字解碼引擎：負責切分產地、品牌、純品名、包裝規格，並修復「清貨」造成的統計崩潰
    """
    if not raw_name:
        return "未標明", "未知品牌", "無名貨品", "無規格", "未知單位", None, None

    # 隱性通道解碼：抽離出品名與供應商標籤
    if "@@@" in str(raw_name):
        up_name, supplier = str(raw_name).split("@@@", 1)
    else:
        up_name, supplier = str(raw_name), "未知供應商"

    up_name = up_name.strip()
    price = extract_price(p_price_str)
    
    extracted_origin = "未標明"
    extracted_brand = "未知品牌"
    extracted_spec = "預設包裝"
    detected_unit = "LB"
    is_clearing = (price == "清" or "清" in up_name or "清" in str(p_price_str))

    # ==========================================
    # 🎯 供應商專屬文字特徵解碼 (Custom Extraction)
    # ==========================================
    if supplier == "哲朗":
        up_name = re.sub(r'^\d+\s*[xX]\s*', '', up_name).strip() 
        up_name = re.sub(r'\b\d+\s*[xX]\b', '', up_name).strip()
        spec_match = re.search(r'\b\d+\s*(?:[gG]|[kK][gG]|[包入隻箱]|\*|[xX])\s*\d*\b', up_name)
        if spec_match:
            extracted_spec = spec_match.group(0).strip()
            up_name = up_name.replace(spec_match.group(0), "").strip()

    elif supplier == "萬安(遠東)":
        spec_match = re.search(r'\b\d+\s*(?:[gG]|[kK][gG]|[包箱磅])\s*[xX*]\s*\d+\b|\b\d+\s*(?:[gG]|[kK][gG]|[包箱磅LBS])\b', up_name, re.IGNORECASE)
        if spec_match:
            extracted_spec = spec_match.group(0).strip()
            up_name = up_name.replace(spec_match.group(0), "").strip()

    elif supplier in ["新興城", "廣隆", "一峰行"]:
        spec_match = re.search(r'[\(\[\uff08].*?[\)\]\uff09]|\b\d+\s*(?:[gG]|[kK][gG]|[包箱隻磅]|\*|[xX])\s*\d*\b', up_name, re.IGNORECASE)
        if spec_match:
            extracted_spec = spec_match.group(0).strip("()（）[]")
            up_name = up_name.replace(spec_match.group(0), "").strip()

    elif supplier == "金山洋行":
        spec_match = re.search(r'\b\d+\s*(?:LBS|LB|KG|G|OZ|CTN)\b', up_name, re.IGNORECASE)
        if spec_match:
            extracted_spec = spec_match.group(0).strip()
            up_name = up_name.replace(spec_match.group(0), "").strip()

    elif supplier == "恆盛":
        spec_match = re.search(r'\b\d+\s*(?:[kK][gG]|磅|包|件|箱)\b', up_name, re.IGNORECASE)
        if spec_match:
            extracted_spec = spec_match.group(0).strip()
            up_name = up_name.replace(spec_match.group(0), "").strip()

    elif supplier == "浩新":
        spec_match = re.search(r'[\(\[\uff08].*?[\)\]\uff09]|\b\d+\s*(?:[gG]|[kK][gG]|[包箱隻磅]|\*|[xX])\s*\d*\b', up_name, re.IGNORECASE)
        if spec_match:
            extracted_spec = spec_match.group(0).strip("()（）[]")
            up_name = up_name.replace(spec_match.group(0), "").strip()

    # ==========================================
    # 🎯 全域產地與品牌抽離
    # ==========================================
    for origin in KNOWN_ORIGINS:
        if origin in up_name:
            extracted_origin = origin
            up_name = up_name.replace(origin, "").strip() 
            break
            
    for brand in KNOWN_BRANDS:
        if brand in up_name.upper():
            extracted_brand = brand
            up_name = re.sub(re.escape(brand), "", up_name, flags=re.IGNORECASE).strip()
            break

    # 還原純品名
    clean_product_name = re.sub(r'\s+', ' ', up_name).strip(",. /|*-+=\\痕，。:：")
    if not clean_product_name:
        clean_product_name = "未命名貨品"

    # ==========================================
    # 🎯 計價單位智慧推導
    # ==========================================
    raw_unit_upper = str(p_unit_str).upper()
    if "KG" in raw_unit_upper or "公斤" in raw_unit_upper or "/K" in raw_unit_upper: detected_unit = "KG"
    elif "箱" in raw_unit_upper or "CTN" in raw_unit_upper or "包" in raw_unit_upper or "隻" in raw_unit_upper or "PC" in raw_unit_upper: detected_unit = "箱/件"

    box_signals = [r'\*', r'X', r'箱', r'包', r'CTN', r'PKT', r'\d+\s*加\s*\d+']
    has_box_signal = any(re.search(signal, str(raw_name) + str(extracted_spec), re.IGNORECASE) for signal in box_signals)
    if has_box_signal and isinstance(price, (int, float)) and price > 100:
        detected_unit = "箱/件"

    # ==========================================
    # 🎯 數值型態修復 (遇到清貨返回 None，防止 Pandas 崩潰)
    # ==========================================
    if is_clearing:
        return extracted_origin, extracted_brand, clean_product_name.replace("清", "").strip(), extracted_spec, "停止報價", None, None

    price_lb, price_kg = None, None
    if isinstance(price, (int, float)):
        if detected_unit == "LB":
            price_lb = round(price, 1)
            price_kg = round(price * 2.2046, 1)
        elif detected_unit == "KG":
            price_lb = round(price / 2.2046, 1)
            price_kg = round(price, 1)
        else:
            price_lb = round(price, 1)
            price_kg = round(price, 1)

    return extracted_origin, extracted_brand, clean_product_name, extracted_spec, detected_unit, price_lb, price_kg

def parse_supplier_row(selected_supplier, cells):
    """
    🔍 八大供應商 PDF 欄位佈局深度解碼區
    """
    extracted_parts = []
    
    if selected_supplier == "萬安(遠東)":
        if len(cells) >= 4 and cells[1]:
            name_text = str(cells[1]).strip() 
            price_text = cells[3]
            unit_text = cells[4] if len(cells) > 4 else ""
            extracted_parts.append((f"{name_text}@@@{selected_supplier}", price_text, unit_text))
            
    elif selected_supplier == "新興城":
        if len(cells) >= 3 and cells[1]: extracted_parts.append((f"{cells[1]}@@@{selected_supplier}", cells[2], cells[2]))
        if len(cells) >= 7 and cells[5]: extracted_parts.append((f"{cells[5]}@@@{selected_supplier}", cells[6], cells[6]))
        
    elif selected_supplier == "廣隆":
        if len(cells) >= 3 and cells[1]: extracted_parts.append((f"{cells[1]}@@@{selected_supplier}", cells[2], cells[2]))
        if len(cells) >= 7 and cells[5]: extracted_parts.append((f"{cells[5]}@@@{selected_supplier}", cells[6], cells[6]))
        
    elif selected_supplier == "一峰行":
        if len(cells) >= 3 and cells[1]: extracted_parts.append((f"{cells[1]}@@@{selected_supplier}", cells[2], cells[2]))
        if len(cells) >= 7 and cells[5]: extracted_parts.append((f"{cells[5]}@@@{selected_supplier}", cells[6], cells[6]))
        
    elif selected_supplier == "金山洋行":
        for i, cell in enumerate(cells):
            if len(cell) > 5 and not re.match(r'^\d', cell): 
                if i+2 < len(cells): extracted_parts.append((f"{cell}@@@{selected_supplier}", cells[i+1], cells[i+2]))
                
    elif selected_supplier == "恆盛": 
        for i, cell in enumerate(cells):
            if len(cell) > 4 and not re.match(r'^[\d\.]+$', cell) and "貨品" not in cell:
                for offset in [1, 2]:
                    if i + offset < len(cells):
                        val_str = cells[i + offset]
                        if re.search(r'\d+\.\d+', val_str) or "$" in val_str:
                            extracted_parts.append((f"{cell}@@@{selected_supplier}", val_str, cells[i + offset + 1] if i + offset + 1 < len(cells) else ""))
                            break
                            
    elif selected_supplier == "浩新":
        if len(cells) >= 5 and cells[2]: extracted_parts.append((f"{cells[2]}@@@{selected_supplier}", cells[4], cells[5] if len(cells)>5 else ""))
        
    elif selected_supplier == "哲朗":
        full_str = " ".join([c for c in cells if c])
        matches = re.finditer(r'([^\$清]+?)(?:\$([0-9\.]+)|(清))\s*(?:/([A-Za-z包箱隻個磅公斤]+))?', full_str)
        for m in matches:
            name_part = m.group(1).strip()
            price_part = m.group(2) if m.group(2) else "清"
            unit_part = m.group(4) if m.group(4) else ""
            if len(name_part) > 2:
                extracted_parts.append((f"{name_part}@@@{selected_supplier}", price_part, unit_part))
                
    return extracted_parts