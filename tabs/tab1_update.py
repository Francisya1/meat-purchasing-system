import streamlit as st
import pandas as pd
import re
import io
import time
from datetime import datetime
import pytz
import gspread
from gspread_formatting import *
from googleapiclient.http import MediaIoBaseUpload
import pdfplumber

from modules.google_db import (
    get_google_connection, get_drive_connection, fetch_all_google_data,
    clean_string, DRIVE_FOLDER_ID
)
from modules.anchor_engine import scan_pdf_with_anchors

def find_price_columns(vals, supplier, header_map):
    lb_col, kg_col = -1, -1
    sup_clean = clean_string(supplier)
    h_lb = clean_string(header_map.get(supplier, {}).get("LB", ""))
    h_kg = clean_string(header_map.get(supplier, {}).get("KG", ""))
    
    for r_idx in range(min(5, len(vals))):
        if not vals[r_idx]: continue
        for c_idx, cv in enumerate(vals[r_idx]):
            c_str = clean_string(str(cv))
            if not c_str: continue
            
            if h_lb and h_lb == c_str: lb_col = c_idx + 1
            elif h_kg and h_kg == c_str: kg_col = c_idx + 1
            elif h_lb and h_lb in c_str and lb_col == -1: lb_col = c_idx + 1
            elif h_kg and h_kg in c_str and kg_col == -1: kg_col = c_idx + 1
            elif sup_clean in c_str:
                if "kg" in c_str: kg_col = c_idx + 1
                elif "lb" in c_str or "磅" in c_str: lb_col = c_idx + 1
                else:
                    if lb_col == -1: lb_col = c_idx + 1
                    elif kg_col == -1: kg_col = c_idx + 1
        if lb_col != -1 or kg_col != -1: break
    return lb_col, kg_col

def extract_robust_pool(pdf_bytes, supplier):
    robust_pool = {}
    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            lines = []
            text = page.extract_text()
            if text: lines.extend(text.split('\n'))
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_str = " ".join([str(c).replace('\n', ' ').strip() for c in row if c])
                    lines.append(row_str)
                    
            for line in lines:
                if supplier in ["萬安(遠東)", "浩新"]:
                    matches = re.finditer(r'(.*?)(?:\$|HKD|HK\$)\s*(\d+(?:\.\d+)?|清)\s*(磅|/\s*LB|/\s*KG|kg|lb|件|箱|/lb)?', line, re.IGNORECASE)
                    for match in matches:
                        raw_name = match.group(1).strip()
                        raw_name = re.sub(r'^(抄碼|\d+(\.\d+)?[Kk][Gg]?)\s*', '', raw_name, flags=re.IGNORECASE).strip()
                        raw_name = re.sub(r'[\$\s/\|]+$', '', raw_name).strip()
                        price_str = match.group(2)
                        unit_str = match.group(3) if match.group(3) else ""
                        
                        c_raw = clean_string(raw_name)
                        if len(c_raw) > 2:
                            robust_pool[c_raw] = {'price': price_str, 'unit': unit_str, 'raw_name': raw_name}
                elif supplier == "形澧":
                    line = line.strip()
                    if len(line) < 5: continue
                    line = re.sub(r'(?<=\d)\s+(kg|g|lb|lbs|oz)\b', r'\1', line, flags=re.IGNORECASE)
                    line = re.sub(r'\s*([*xX])\s*', r'\1', line)
                    tokens = re.split(r'\s+|\|', line)
                    raw_price = 0.0
                    price_str_for_split = ""
                    for token in reversed(tokens):
                        tc = re.sub(r'[^0-9\.a-zA-Z\u4e00-\u9fa5]', '', token)
                        if not tc: continue
                        if re.search(r'(kg|g|lb|lbs|oz|pc|box|箱|件)$', tc.lower()): continue
                        if re.match(r'^P\d+$', tc, re.IGNORECASE): continue
                        if re.match(r'^\d+(?:\.\d+)?$', tc):
                            val = float(tc)
                            if val > 0:
                                raw_price = val
                                price_str_for_split = token
                                break
                    if raw_price > 0:
                        raw_name = line.rsplit(price_str_for_split, 1)[0].strip()
                        raw_name = re.sub(r'[\s\|]+$', '', raw_name)
                        c_raw = clean_string(raw_name)
                        if len(c_raw) > 2:
                            robust_pool[c_raw] = {'price': str(raw_price), 'unit': "", 'raw_name': raw_name}
                else:
                    from modules.pdf_xray import parse_supplier_row
                    parts = parse_supplier_row(supplier, [line])
                    for part in parts:
                        p_name = part[0]
                        if "@@@" in p_name: p_name = p_name.split("@@@")[0]
                        c_raw = clean_string(p_name)
                        if len(c_raw) > 2:
                            robust_pool[c_raw] = {'price': part[1], 'unit': part[2], 'raw_name': p_name}
    return robust_pool

def render_tab1(ACTIVE_SUPPLIERS, HEADER_MAP, target_dict, cat_data, parsed_history, get_wavy_loading_html):
    st.header("更新及雲端同步")
    with st.form("upload_form"):
        col1, col2, col3 = st.columns([1.2, 1, 2])
        with col1: 
            selected_supplier = st.selectbox("請選擇本次提交的供應商：", ACTIVE_SUPPLIERS)
            st.markdown("<br>", unsafe_allow_html=True)
            submit_upload = st.form_submit_button("🚀 ENTER / 提交報價單", use_container_width=True)
        with col2:
            hk_tz = pytz.timezone('Asia/Hong_Kong')
            quote_date = st.date_input("🗓️ 報價單上的日期：", datetime.now(hk_tz))
        with col3: 
            uploaded_file = st.file_uploader("上傳 PDF 報價單", type="pdf")

    if submit_upload:
        if uploaded_file is None: st.error("⚠️ 請先上傳 PDF 檔案！")
        else:
            targets = target_dict.get(selected_supplier, [])
            if not targets: st.error(f"❌ 字典中找不到【{selected_supplier}】的產品。")
            else:
                loading_ph2 = st.empty()
                loading_ph2.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
                
                pdf_bytes = io.BytesIO(uploaded_file.read())
                try:
                    drive_service = get_drive_connection()
                    pdf_bytes.seek(0)
                    new_filename = f"{selected_supplier}_{quote_date.strftime('%Y-%m-%d')}.pdf"
                    file_metadata = {'name': new_filename, 'parents': [DRIVE_FOLDER_ID]}
                    media = MediaIoBaseUpload(pdf_bytes, mimetype='application/pdf', resumable=True)
                    drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                except Exception: pass
                
                pdf_bytes.seek(0)
                extracted_items = scan_pdf_with_anchors(pdf_bytes, targets, selected_supplier)
                
                pdf_bytes.seek(0)
                robust_pool = extract_robust_pool(pdf_bytes, selected_supplier)
                sku_to_raw = {t['sku']: t['name'] for t in targets}
                for sku, raw_name in sku_to_raw.items():
                    if sku not in extracted_items or extracted_items[sku]['guessed_unit'] == "SOLD_OUT":
                        clean_target = clean_string(raw_name)
                        for c_raw, r_data in robust_pool.items():
                            if clean_target in c_raw or c_raw in clean_target:
                                price_val = r_data['price']
                                if price_val == "清" or "sold" in str(price_val).lower():
                                    extracted_items[sku] = {'raw_price': 0.0, 'guessed_unit': 'SOLD_OUT', 'raw_name': r_data['raw_name'], 'matched_line': '深層救援成功'}
                                else:
                                    try:
                                        p_f = float(price_val)
                                        g_u = "KG" if "kg" in clean_string(r_data['unit']) else "LB"
                                        extracted_items[sku] = {'raw_price': p_f, 'guessed_unit': g_u, 'raw_name': r_data['raw_name'], 'matched_line': '深層救援成功'}
                                    except: pass
                                break

                history_lows = {}
                for x in parsed_history:
                    if x['sku'] not in history_lows or x['price'] < history_lows[x['sku']]:
                        history_lows[x['sku']] = x['price']

                all_preview = []
                for sheet_name, all_vals in cat_data.items():
                    if not all_vals: continue
                    lb_col, kg_col = find_price_columns(all_vals, selected_supplier, HEADER_MAP)

                    for row_idx, r in enumerate(all_vals):
                        if row_idx < 2 or not r: continue
                        sku_db = str(r[0]).strip()
                        if not sku_db: continue
                        
                        is_correct = (sku_db.startswith('1') and sheet_name == 'Beef') or (sku_db.startswith('2') and sheet_name == 'Pork') or (sku_db.startswith('3') and sheet_name == 'Chicken') or (sku_db.startswith('4') and sheet_name == 'Lamp')
                        if not is_correct: continue
                        
                        old_price_lb = None
                        if lb_col != -1 and lb_col - 1 < len(r):
                            old_val = str(r[lb_col - 1]).strip()
                            nums = re.findall(r'\d+\.?\d*', old_val)
                            if nums and float(nums[0]) > 0 and "sold out" not in old_val.lower(): 
                                old_price_lb = float(nums[0])
                        
                        if sku_db in extracted_items:
                            data = extracted_items[sku_db]
                            raw_price = data['raw_price']; unit = data['guessed_unit']
                            
                            if selected_supplier == "形澧":
                                m_line = str(data.get('matched_line', '')).strip()
                                if m_line and m_line != "-":
                                    m_line = re.sub(r'(?<=\d)\s+(kg|g|lb|lbs|oz)\b', r'\1', m_line, flags=re.IGNORECASE)
                                    m_line = re.sub(r'\s*([*xX])\s*', r'\1', m_line)
                                    tokens = re.split(r'\s+|\|', m_line)
                                    for token in reversed(tokens):
                                        tc = re.sub(r'[^0-9\.a-zA-Z\u4e00-\u9fa5]', '', token)
                                        if not tc: continue
                                        if re.search(r'(kg|g|lb|lbs|oz|pc|box|箱|件)$', tc.lower()): continue
                                        if re.match(r'^P\d+$', tc, re.IGNORECASE): continue
                                        if re.match(r'^\d+(?:\.\d+)?$', tc):
                                            val = float(tc)
                                            if val > 0:
                                                raw_price = val
                                                data['raw_price'] = raw_price
                                                break
                            
                            status = "🆕 新增"; delta_str = "-"; is_anomaly = False
                            is_sold_out_detected = (unit == "SOLD_OUT")
                            
                            if is_sold_out_detected:
                                status = "🛑 斷貨 (清)"
                                data['price_lb'] = "Sold out"; sort_key = 2
                            else:
                                if old_price_lb is not None and old_price_lb > 0:
                                    old_price_kg = old_price_lb * 2.2046
                                    if abs(raw_price - old_price_lb) / old_price_lb < 0.30 and abs(raw_price - old_price_kg) / old_price_kg > 0.30: unit = "LB"
                                    elif abs(raw_price - old_price_kg) / old_price_kg < 0.30 and abs(raw_price - old_price_lb) / old_price_lb > 0.30: unit = "KG"
                                price_lb = raw_price if unit != "KG" else raw_price / 2.2046
                                data['price_lb'] = round(price_lb, 1)

                                if old_price_lb is not None:
                                    delta = data['price_lb'] - old_price_lb
                                    delta_pct = abs(delta) / old_price_lb if old_price_lb > 0 else 0
                                    if delta_pct > 0.05:
                                        status = "🚨 異常 (>5%)"; is_anomaly = True; delta_str = f"{'+' if delta>0 else ''}{round(delta, 1)} ({(delta_pct*100):.1f}%)"
                                    elif delta > 0: status = "📈 升價"; delta_str = f"+{round(delta, 1)}"
                                    elif delta < 0: status = "📉 降價"; delta_str = f"{round(delta, 1)}"
                                    else: status = "➖ 無變動"; delta_str = "0"
                                if data['price_lb'] > 0 and sku_db in history_lows and not is_anomaly:
                                    if data['price_lb'] <= history_lows[sku_db]: status += " 🔥低位"
                                    
                                if "🚨" in status: sort_key = 1
                                elif "➖" in status: sort_key = 4
                                else: sort_key = 3
                                
                                if lb_col == -1: status = "⚠️ 母表無價錢欄位"

                            all_preview.append({
                                "✔️ 寫入": not is_anomaly and not is_sold_out_detected and lb_col != -1,
                                "🛑 斷貨": is_sold_out_detected,
                                "SKU": sku_db, "產品原文": data['raw_name'],
                                "舊價(LB)": f"${old_price_lb}" if old_price_lb else "空",
                                "✏️ 手動新價(LB)": data['price_lb'] if not is_sold_out_detected else 0.0,
                                "變動狀態": status, "差額": delta_str, 
                                "追蹤行蹤": data['matched_line'], "target_row": row_idx + 1, "lb_col": lb_col, "kg_col": kg_col, "sheet_name": sheet_name, "sort_key": sort_key
                            })
                            
                        elif old_price_lb is not None:
                            all_preview.append({
                                "✔️ 寫入": False, "🛑 斷貨": True, 
                                "SKU": sku_db, "產品原文": "⚠️ 報價單中找不到此產品",
                                "舊價(LB)": f"${old_price_lb}", "✏️ 手動新價(LB)": 0.0,
                                "變動狀態": "🛑 疑似下架/斷貨", "差額": "-", 
                                "追蹤行蹤": "-", "target_row": row_idx + 1, "lb_col": lb_col, "kg_col": kg_col, "sheet_name": sheet_name, "sort_key": 5
                            })
                                
                st.session_state['preview_data'] = sorted(all_preview, key=lambda x: x['sort_key'])
                st.session_state['current_supplier'] = selected_supplier
                st.session_state['current_quote_date'] = quote_date.strftime("%Y-%m-%d")
                loading_ph2.empty()

    if st.session_state['preview_data'] is not None:
        df_preview = pd.DataFrame(st.session_state['preview_data'])
        if len(df_preview) > 0:
            st.success(f"🎉 **成功分析 {len(df_preview)} 個產品！**")
            if any(r["lb_col"] == -1 for r in st.session_state['preview_data']):
                st.error("⚠️ 警告：系統在某些母表分頁中找不到此供應商的『價錢欄位』！請確認母表第一行的表頭名稱是否正確。")
            
            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            with col_btn1:
                if st.button("☑️ 全部勾選 (寫入)", key="t1_check"):
                    for item in st.session_state['preview_data']: item["✔️ 寫入"] = True
                    st.rerun()
            with col_btn2:
                if st.button("☐ 全部取消勾選", key="t1_uncheck"):
                    for item in st.session_state['preview_data']: item["✔️ 寫入"] = False
                    st.rerun()
            
            edited_df = st.data_editor(
                df_preview,
                column_config={
                    "✔️ 寫入": st.column_config.CheckboxColumn("✔️ 寫入 (勾選)"),
                    "🛑 斷貨": st.column_config.CheckboxColumn("🛑 斷貨"),
                    "✏️ 手動新價(LB)": st.column_config.NumberColumn("✏️ 手動新價(LB)", format="%.1f"),
                    "target_row": None, "lb_col": None, "kg_col": None, "sheet_name": None, "sort_key": None
                },
                disabled=["SKU", "產品原文", "舊價(LB)", "變動狀態", "差額", "追蹤行蹤"],
                use_container_width=True, hide_index=True, height=500
            )
            
            if st.button("💾 確認無誤，將『已勾選』資料寫入雲端母表", type="primary", key="t1_save"):
                loading_ph3 = st.empty()
                loading_ph3.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
                
                gc, sh, _ = get_google_connection()
                history_records = []
                hk_tz = pytz.timezone('Asia/Hong_Kong')
                sys_today = datetime.now(hk_tz).strftime("%Y-%m-%d %H:%M:%S")
                quote_date_str = st.session_state['current_quote_date']
                current_user = st.session_state.get("username", "未知用戶")
                history_records.append([sys_today, quote_date_str, st.session_state['current_supplier'], "系統紀錄", f"由 {current_user} 更新", "-", "-"])
                
                updates_by_sheet = {}; formats_by_sheet = {}
                update_count = 0
                
                for idx, row in edited_df.iterrows():
                    if not row["✔️ 寫入"] or row["lb_col"] == -1: continue
                    update_count += 1
                    sn = row["sheet_name"]
                    if sn not in updates_by_sheet: updates_by_sheet[sn] = []; formats_by_sheet[sn] = []
                    
                    bg_color = color(1.0, 0.6, 0.6) if "🚨" in row["變動狀態"] else color(0.8, 1.0, 0.8) if "📉" in row["變動狀態"] else color(1.0, 0.8, 0.8) if "📈" in row["變動狀態"] else color(0.9, 0.9, 0.9) if "🛑" in row["變動狀態"] else color(1.0, 0.95, 0.6) 
                    fmt = cellFormat(backgroundColor=bg_color)
                    
                    if row["🛑 斷貨"]: val_lb = "Sold out"; val_kg = "Sold out"
                    else:
                        manual_price = row["✏️ 手動新價(LB)"]
                        if pd.isna(manual_price) or float(manual_price) <= 0.0: val_lb = "Sold out"; val_kg = "Sold out"
                        else: val_lb = float(manual_price); val_kg = round(val_lb * 2.2046, 1)
                    
                    if row["lb_col"] != -1:
                        cell_a1 = gspread.utils.rowcol_to_a1(row["target_row"], row["lb_col"])
                        updates_by_sheet[sn].append({'range': cell_a1, 'values': [[val_lb]]}); formats_by_sheet[sn].append((cell_a1, fmt))
                    if row["kg_col"] != -1:
                        cell_a1 = gspread.utils.rowcol_to_a1(row["target_row"], row["kg_col"])
                        updates_by_sheet[sn].append({'range': cell_a1, 'values': [[val_kg]]}); formats_by_sheet[sn].append((cell_a1, fmt))
                    history_records.append([sys_today, quote_date_str, st.session_state['current_supplier'], row["SKU"], row["產品原文"], val_lb, val_kg])
                
                if update_count > 0:
                    for sn in updates_by_sheet:
                        target_ws = sh.worksheet(sn)
                        if updates_by_sheet[sn]: target_ws.batch_update(updates_by_sheet[sn])
                        if formats_by_sheet[sn]: format_cell_ranges(target_ws, formats_by_sheet[sn])
                    sh.worksheet("History_Log").append_rows(history_records)
                    fetch_all_google_data.clear() 
                    loading_ph3.empty()
                    st.balloons()
                    st.success(f"🎉 成功寫入 {update_count} 筆資料！")
                    st.session_state['preview_data'] = None
                    time.sleep(1.5)
                    st.rerun()
                else:
                    loading_ph3.empty(); st.warning("⚠️ 沒有勾選任何資料寫入。")