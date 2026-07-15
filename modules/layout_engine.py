# modules/layout_engine.py
import json
import os
import re

# 定義儲存佈局 DNA 的本機檔案名稱
LAYOUT_FILE = "supplier_layouts.json"

def load_layouts():
    """
    讀取本機的佈局 DNA。如果檔案不存在，則自動生成一個乾淨的空檔案。
    """
    if not os.path.exists(LAYOUT_FILE):
        with open(LAYOUT_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
        return {}
    
    with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_layout(supplier_name, layout_config):
    """
    儲存你在網頁上設定好的「答卷」(佈局規則)
    """
    layouts = load_layouts()
    layouts[supplier_name] = layout_config
    with open(LAYOUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(layouts, f, ensure_ascii=False, indent=4)
    return True

def apply_scissor(text, scissor_type, custom_symbol=""):
    """
    ✂️ 第一段預處理：視覺化剪刀引擎
    提供多種剪刀，用來把原本黏在一起的「欄位 0」精準切開
    """
    text = str(text).strip()
    if not text:
        return []

    if scissor_type == "space":
        # ✂️ 剪刀 A：以「連續兩個以上的空格」為界線切開
        return [part.strip() for part in re.split(r'\s{2,}', text) if part.strip()]
        
    elif scissor_type == "symbol":
        # ✂️ 剪刀 B：以「指定符號」(例如 | 或 $) 為界線切開
        if not custom_symbol: 
            return [text]
        return [part.strip() for part in text.split(custom_symbol) if part.strip()]
        
    elif scissor_type == "smart_price":
        # ✂️ 剪刀 C (終極剪刀)：智能價格尋標切割 (專剋哲朗等完全黏死無空格的排版)
        # 尋找 $ 或 清，並把它前後的文字強行一分為三
        matches = re.finditer(r'([^\$清]+?)(?:\$([0-9\.]+)|(清))\s*(?:/([A-Za-z包箱隻個磅公斤]+))?', text)
        results = []
        for m in matches:
            name_part = m.group(1).strip()
            price_part = m.group(2) if m.group(2) else "清"
            unit_part = m.group(4) if m.group(4) else "未標明"
            # 這裡回傳切好的三個小塊，讓你在前端可以分別指派 A、B、C
            results.extend([name_part, price_part, unit_part])
        return results if results else [text]
        
    # 如果選擇「不切割」(預設)
    return [text]

def test_scissor():
    """
    此為內部除錯用，不會影響網頁。
    """
    pass