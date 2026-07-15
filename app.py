import streamlit as st
import gspread
from gspread_formatting import *
import pandas as pd
import re
import io
from datetime import datetime, timedelta
import pytz
import pdfplumber

from modules.google_db import (
    get_google_connection, get_drive_connection, fetch_all_google_data,
    clean_string, SUPPLIERS, DRIVE_FOLDER_ID
)

from modules.anchor_engine import scan_pdf_with_anchors
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

st.set_page_config(page_title="肉類批發智慧採購系統", layout="wide", page_icon="🥩")

if 'preview_data' not in st.session_state: st.session_state['preview_data'] = None
if 'current_supplier' not in st.session_state: st.session_state['current_supplier'] = None
if 'current_quote_date' not in st.session_state: st.session_state['current_quote_date'] = None
if 'cloud_db' not in st.session_state: st.session_state['cloud_db'] = None

ACTIVE_SUPPLIERS = sorted(list(set(SUPPLIERS + ["形澧"])))

HEADER_MAP = {
    "新興城": {"LB": "新興城 $/LB", "KG": "新興城 $/KG"},
    "金山洋行": {"LB": "金山 ($/lb)", "KG": "金山 ($/KG)"},
    "廣隆": {"LB": "廣隆 $/LB", "KG": "廣隆 $/KG"},
    "哲朗": {"LB": "哲朗 $/LB", "KG": "哲朗 $/KG"},
    "浩新": {"LB": "浩新 $/LB", "KG": "浩新 $/KG"},
    "一峰行": {"LB": "一峰行 $/LB", "KG": "一峰行 $/KG"},
    "恆盛": {"LB": "恆盛 $/LB", "KG": "恆盛 $/KG"},
    "萬安(遠東)": {"LB": "萬安 ($/lb)", "KG": "萬安 ($/kg)"},
    "形澧": {"LB": "形澧 $/LB", "KG": "形澧 $/KG"} 
}

FILENAME_MAPPING = {
    "06-07-2026": "新興城", "FEB-2026": "廣隆", "29-Jun-2026": "金山洋行",
    "哲朗": "哲朗", "Price list": "浩新", "一峰行": "一峰行",
    "2026-06-22": "恆盛", "萬安": "萬安(遠東)", "形澧": "形澧"
}

target_dict, cat_data, hist_vals, global_origins = fetch_all_google_data()

with st.sidebar:
    st.title("📊 採購系統儀表板")
    if len(hist_vals) > 1:
        st.metric(label="目前追蹤產品數", value=sum(len(v)-2 for v in cat_data.values() if v), delta="已啟用")
    
    st.markdown("### 各供應商最後報價")
    if len(hist_vals) > 1:
        latest_dates = {}
        for row in hist_vals[1:]:
            if len(row) >= 6:
                if len(row) >= 7 and re.match(r'\d{4}-\d{2}-\d{2}', row[1]):
                    quote_date = row[1]; sup = row[2]
                else:
                    quote_date = row[0].split()[0]; sup = row[1]
                if sup in ACTIVE_SUPPLIERS: latest_dates[sup] = quote_date
        for sup in ACTIVE_SUPPLIERS:
            date_str = latest_dates.get(sup, "尚未更新")
            if date_str == "尚未更新": st.warning(f"**{sup}** : {date_str}")
            else: st.success(f"**{sup}** : {date_str}")
    else: st.info("尚無歷史紀錄")
    st.markdown("---")
    st.caption("肉類批發智慧採購系統 v10.3 (極速過濾版)")

tab1, tab2 = st.tabs(["🚀 報價一鍵更新系統", "💰 跨供應商情報雷達 (Tab 2)"])

# ==========================================
# 🚀 TAB 1: 報價一鍵更新系統
# ==========================================
with tab1:
    st.header("🚀 報價單一鍵分析與雲端同步")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1: selected_supplier = st.selectbox("請選擇本次提交的供應商：", ACTIVE_SUPPLIERS, key="sync_sup", on_change=lambda: st.session_state.update(preview_data=None))
    with col2:
        hk_tz = pytz.timezone('Asia/Hong_Kong')
        quote_date = st.date_input("🗓️ 請選擇報價單真實日期：", datetime.now(hk_tz), on_change=lambda: st.session_state.update(preview_data=None))
    with col3: uploaded_file = st.file_uploader("上傳 PDF 報價單", type="pdf", key="sync_file", on_change=lambda: st.session_state.update(preview_data=None))

    if uploaded_file is not None:
        if st.button("🚀 開始分析並自動備份至雲端", type="primary"):
            targets = target_dict.get(selected_supplier, [])
            if not targets: st.error(f"❌ 字典中找不到【{selected_supplier}】的產品。")
            else:
                pdf_bytes = io.BytesIO(uploaded_file.read())
                with st.spinner('☁️ 正在備份至雲端...'):
                    try:
                        drive_service = get_drive_connection()
                        pdf_bytes.seek(0)
                        new_filename = f"{selected_supplier}_{quote_date.strftime('%Y-%m-%d')}.pdf"
                        file_metadata = {'name': new_filename, 'parents': [DRIVE_FOLDER_ID]}
                        media = MediaIoBaseUpload(pdf_bytes, mimetype='application/pdf', resumable=True)
                        drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                    except Exception as e: pass
                
                with st.spinner('正在解剖 PDF...'):
                    pdf_bytes.seek(0)
                    extracted_items = scan_pdf_with_anchors(pdf_bytes, targets, selected_supplier)

                with st.spinner('計算升跌狀態...'):
                    thirty_days_ago = datetime.now() - timedelta(days=30)
                    history_lows = {}
                    if len(hist_vals) > 1:
                        for hr in hist_vals[1:]:
                            if len(hr) >= 6:
                                date_str = hr[0].split()[0] if " " in hr[0] else hr[0]
                                try:
                                    rec_date = datetime.strptime(date_str, "%Y-%m-%d")
                                    if rec_date >= thirty_days_ago:
                                        h_sku = str(hr[3] if len(hr) >= 7 else hr[2]).strip()
                                        h_price_lb = float(hr[5] if len(hr) >= 7 else hr[4])
                                        if h_sku not in history_lows or h_price_lb < history_lows[h_sku]: history_lows[h_sku] = h_price_lb
                                except: pass

                    all_preview = []
                    for sheet_name, all_vals in cat_data.items():
                        if not all_vals: continue
                        lb_col, kg_col = -1, -1
                        for r_idx in range(min(10, len(all_vals))):
                            for c_idx, cv in enumerate(all_vals[r_idx]):
                                c_str = clean_string(str(cv))
                                if clean_string(HEADER_MAP.get(selected_supplier, {}).get("LB", f"{selected_supplier}$/LB")) in c_str: lb_col = c_idx + 1
                                if clean_string(HEADER_MAP.get(selected_supplier, {}).get("KG", f"{selected_supplier}$/KG")) in c_str: kg_col = c_idx + 1
                            if lb_col != -1 or kg_col != -1: break

                        for row_idx, r in enumerate(all_vals):
                            if row_idx < 2 or not r: continue
                            sku_db = str(r[0]).strip()
                            if not sku_db: continue
                            if sku_db in extracted_items:
                                is_correct = (sku_db.startswith('1') and sheet_name == 'Beef') or (sku_db.startswith('2') and sheet_name == 'Pork') or (sku_db.startswith('3') and sheet_name == 'Chicken') or (sku_db.startswith('4') and sheet_name == 'Lamp')
                                if not is_correct: continue
                                
                                data = extracted_items[sku_db]
                                old_price_lb = None
                                if lb_col != -1 and lb_col - 1 < len(r):
                                    old_val = str(r[lb_col - 1]).strip()
                                    nums = re.findall(r'\d+\.?\d*', old_val)
                                    if nums and float(nums[0]) > 0 and "sold out" not in old_val.lower(): 
                                        old_price_lb = float(nums[0])
                                
                                raw_price = data['raw_price']
                                unit = data['guessed_unit']
                                status = "🆕 新增"; delta_str = "-"; is_anomaly = False
                                
                                if unit == "SOLD_OUT":
                                    status = "🛑 斷貨 (清)"
                                    data['price_lb'] = "Sold out"
                                    data['price_kg'] = "Sold out"
                                    sort_key = 2
                                else:
                                    if old_price_lb is not None and old_price_lb > 0:
                                        old_price_kg = old_price_lb * 2.2046
                                        diff_if_lb = abs(raw_price - old_price_lb) / old_price_lb
                                        diff_if_kg = abs(raw_price - old_price_kg) / old_price_kg
                                        if diff_if_lb < 0.30 and diff_if_kg > 0.30: unit = "LB"
                                        elif diff_if_kg < 0.30 and diff_if_lb > 0.30: unit = "KG"
                                    
                                    price_lb = raw_price if unit != "KG" else raw_price / 2.2046
                                    price_kg = raw_price if unit == "KG" else raw_price * 2.2046
                                    data['price_lb'] = round(price_lb, 1)
                                    data['price_kg'] = round(price_kg, 1)

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

                                all_preview.append({
                                    "SKU": sku_db, "產品原文": data['raw_name'],
                                    "舊價(LB)": f"${old_price_lb}" if old_price_lb else "空",
                                    "新價(LB)": f"${data['price_lb']:.1f}" if unit != "SOLD_OUT" else "Sold out",
                                    "新價(KG)": f"${data['price_kg']:.1f}" if unit != "SOLD_OUT" else "Sold out",
                                    "變動狀態": status, "差額": delta_str, "欄位狀態": "✅" if (lb_col!=-1 or kg_col!=-1) else "❌",
                                    "追蹤行蹤": data['matched_line'], "target_row": row_idx + 1, "lb_col": lb_col, "kg_col": kg_col,
                                    "sheet_name": sheet_name, "price_lb": data['price_lb'], "price_kg": data['price_kg'],
                                    "is_anomaly": is_anomaly, "sort_key": sort_key
                                })
                                    
                st.session_state['preview_data'] = sorted(all_preview, key=lambda x: x['sort_key'])
                st.session_state['current_supplier'] = selected_supplier
                st.session_state['current_quote_date'] = quote_date.strftime("%Y-%m-%d")

    if st.session_state['preview_data'] is not None:
        df_preview = pd.DataFrame(st.session_state['preview_data'])
        if len(df_preview) > 0:
            changed = len(df_preview[df_preview['sort_key'] < 4]); unchanged = len(df_preview[df_preview['sort_key'] == 4])
            st.success(f"🎉 **成功抓取 {len(df_preview)} 個產品！** (變動：{changed} | 無變動：{unchanged})")
            
            display_df = df_preview.drop(columns=['target_row', 'lb_col', 'kg_col', 'sheet_name', 'price_lb', 'price_kg', 'is_anomaly', 'sort_key'], errors='ignore')
            def highlight_anomaly(x):
                df_colors = pd.DataFrame('', index=x.index, columns=x.columns)
                for i in x.index:
                    status = str(x.loc[i, '變動狀態'])
                    if "🚨" in status: df_colors.loc[i, :] = 'background-color: #ffcccc; color: red;'
                    elif "🛑" in status: df_colors.loc[i, :] = 'background-color: #e6e6e6; color: #555;'
                    elif "➖" in status: df_colors.loc[i, :] = 'color: #999;'
                return df_colors
            st.dataframe(display_df.style.apply(highlight_anomaly, axis=None), height=600)
        
        all_cols_missing = all(item["lb_col"] == -1 and item["kg_col"] == -1 for item in st.session_state['preview_data']) if len(st.session_state['preview_data'])>0 else False
        if st.button("💾 確認無誤，寫入雲端", type="primary", disabled=all_cols_missing):
            with st.spinner('📦 正在寫入...'):
                gc, sh, _ = get_google_connection()
                history_records = []
                hk_tz = pytz.timezone('Asia/Hong_Kong')
                sys_today = datetime.now(hk_tz).strftime("%Y-%m-%d %H:%M:%S")
                quote_date_str = st.session_state['current_quote_date']
                history_records.append([sys_today, quote_date_str, st.session_state['current_supplier'], "系統紀錄", "更新日期", "-", "-"])
                
                updates_by_sheet = {}; formats_by_sheet = {}
                for item in st.session_state['preview_data']:
                    sn = item["sheet_name"]
                    if sn not in updates_by_sheet: updates_by_sheet[sn] = []; formats_by_sheet[sn] = []
                    
                    bg_color = color(1.0, 0.6, 0.6) if item.get("is_anomaly") else color(0.8, 1.0, 0.8) if "📉" in item["變動狀態"] else color(1.0, 0.8, 0.8) if "📈" in item["變動狀態"] else color(0.9, 0.9, 0.9) if "🛑" in item["變動狀態"] else color(1.0, 0.95, 0.6) 
                    fmt = cellFormat(backgroundColor=bg_color)
                    
                    if item["lb_col"] != -1:
                        cell_a1 = gspread.utils.rowcol_to_a1(item["target_row"], item["lb_col"])
                        val = "Sold out" if item["price_lb"] == "Sold out" else item["price_lb"]
                        updates_by_sheet[sn].append({'range': cell_a1, 'values': [[val]]}); formats_by_sheet[sn].append((cell_a1, fmt))
                    if item["kg_col"] != -1:
                        cell_a1 = gspread.utils.rowcol_to_a1(item["target_row"], item["kg_col"])
                        val = "Sold out" if item["price_kg"] == "Sold out" else item["price_kg"]
                        updates_by_sheet[sn].append({'range': cell_a1, 'values': [[val]]}); formats_by_sheet[sn].append((cell_a1, fmt))
                    history_records.append([sys_today, quote_date_str, st.session_state['current_supplier'], item["SKU"], item["產品原文"], item["price_lb"], item["price_kg"]])
                
                for sn in updates_by_sheet:
                    target_ws = sh.worksheet(sn)
                    if updates_by_sheet[sn]: target_ws.batch_update(updates_by_sheet[sn])
                    if formats_by_sheet[sn]: format_cell_ranges(target_ws, formats_by_sheet[sn])
                sh.worksheet("History_Log").append_rows(history_records)
                fetch_all_google_data.clear() 
                st.balloons(); st.success("🎉 更新大成功！"); st.session_state['preview_data'] = None; st.rerun()

# ==========================================
# 🚀 TAB 2: 智能格價雷達 (含歷史低價 & 雲端極速過濾)
# ==========================================
with tab2:
    st.header("💰 跨供應商情報雷達 (模糊語義版)")
    search_query = st.text_input("🔍 輸入關鍵字 (如: 雞翼、牛上腦)：", placeholder="系統具備智能字典，搜尋「雞比」會自動尋找「餅脾」等同義詞...")
    
    q_clean = clean_string(search_query) if search_query else ""
    search_aliases = set([q_clean])
    
    if q_clean:
        STATIC_DICT = {
            "雞翼": ["中亦", "中翼", "雞翼", "雞中翼", "翼"],
            "牛上腦": ["牛上腦", "肩胛肉眼", "chuckroll"],
            "雞比": ["雞比", "雞脾", "餅比", "餅脾", "雞腿", "脾肉", "比肉", "全脾", "雞下脾"],
            "牛小排": ["牛小排", "牛仔骨", "shortrib", "牛排"],
            "金錢展": ["金展", "金錢展", "金錢𦟌"],
            "肉眼": ["肉眼", "ribeye"]
        }
        for key, aliases in STATIC_DICT.items():
            if key in q_clean or q_clean in key:
                search_aliases.update(aliases)
                
        for sn, all_vals in cat_data.items():
            if not all_vals: continue
            for r in all_vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                if q_clean in clean_string(sku) or q_clean in clean_string(std_name):
                    for sup, targets in target_dict.items():
                        for t in targets:
                            if t['sku'] == sku: search_aliases.add(clean_string(t['name']))
                            
        st.info(f"🧠 AI 已將 `{q_clean}` 智能展開為：`{', '.join(search_aliases)}` 進行聯合搜尋。")

        st.markdown("### 1️⃣ 母表建檔產品 (即時比價與歷史低價雷達)")
        
        # 💡 歷史低價數據預處理
        history_prices = {}
        if len(hist_vals) > 1:
            for hr in hist_vals[1:]:
                if len(hr) >= 6:
                    date_str = hr[1].split()[0] if " " in hr[1] else hr[1] 
                    try:
                        rec_date = datetime.strptime(date_str, "%Y-%m-%d")
                        h_sku = str(hr[3] if len(hr) >= 7 else hr[2]).strip()
                        h_price_lb = float(hr[5] if len(hr) >= 7 else hr[4])
                        if h_sku not in history_prices: history_prices[h_sku] = []
                        history_prices[h_sku].append({'date': rec_date, 'price': h_price_lb})
                    except: pass

        d30 = datetime.now() - timedelta(days=30)
        d60 = datetime.now() - timedelta(days=60)
        d90 = datetime.now() - timedelta(days=90)

        compare_results = []
        for sn, all_vals in cat_data.items():
            if not all_vals: continue
            sup_cols = {sup: {"LB": -1} for sup in HEADER_MAP}
            for r_idx in range(min(10, len(all_vals))):
                for c_idx, cv in enumerate(all_vals[r_idx]):
                    c_str = clean_string(str(cv))
                    for sup_name, sup_headers in HEADER_MAP.items():
                        if clean_string(sup_headers["LB"]) == c_str: sup_cols[sup_name]["LB"] = c_idx
            
            for row_idx, r in enumerate(all_vals[2:]):
                if not r: continue
                sku = str(r[0]).strip()
                origin = str(r[1]).strip() if len(r) > 1 else "未標明"
                std_name = " | ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                
                clean_sku = clean_string(sku); clean_std = clean_string(std_name)
                if any(alias in clean_sku or alias in clean_std for alias in search_aliases):
                    for sup_name, cols in sup_cols.items():
                        lb_col_idx = cols["LB"]
                        if lb_col_idx != -1 and lb_col_idx < len(r):
                            p_val_str = str(r[lb_col_idx]).strip()
                            nums = re.findall(r'\d+\.?\d*', p_val_str)
                            if nums and float(nums[0]) > 0:
                                price_lb = round(float(nums[0]), 1)
                                
                                # 💡 30/60/90天 歷史低價提醒機制
                                hist_alert = "-"
                                if sku in history_prices:
                                    p30 = [x['price'] for x in history_prices[sku] if x['date'] >= d30]
                                    p60 = [x['price'] for x in history_prices[sku] if x['date'] >= d60]
                                    p90 = [x['price'] for x in history_prices[sku] if x['date'] >= d90]
                                    
                                    if p90 and price_lb <= min(p90): hist_alert = "🔥🔥🔥 90天新低"
                                    elif p60 and price_lb <= min(p60): hist_alert = "🔥🔥 60天新低"
                                    elif p30 and price_lb <= min(p30): hist_alert = "🔥 30天新低"

                                compare_results.append({
                                    "SKU": sku, "產地": origin, "標準品名": std_name, "供應商": sup_name,
                                    "每磅均價 ($/LB)": price_lb, "每公斤均價 ($/KG)": round(price_lb * 2.2046, 1),
                                    "歷史低價提醒": hist_alert
                                })
                                
        if compare_results:
            unique_origins = sorted(list(set([res['產地'] for res in compare_results])))
            selected_origins = st.multiselect("🌍 產地快速篩選 (可複選)：", unique_origins, default=[])
            
            if selected_origins:
                compare_results = [res for res in compare_results if res['產地'] in selected_origins]
                
            if compare_results:
                df_compare = pd.DataFrame(compare_results).sort_values(by="每磅均價 ($/LB)")
                cheapest = df_compare.iloc[0]
                df_compare['差價 (比最平)'] = df_compare['每磅均價 ($/LB)'] - cheapest['每磅均價 ($/LB)']
                df_compare['差價 (比最平)'] = df_compare['差價 (比最平)'].apply(lambda x: f"+${x:.1f}" if x > 0 else "-")
                df_compare = df_compare[['SKU', '標準品名', '產地', '供應商', '每磅均價 ($/LB)', '每公斤均價 ($/KG)', '差價 (比最平)', '歷史低價提醒']]
                
                st.success(f"🏆 最平首選：【{cheapest['供應商']}】 **${cheapest['每磅均價 ($/LB)']:.1f}** / LB")
                st.dataframe(df_compare.style.highlight_min(subset=['每磅均價 ($/LB)'], color='lightgreen').format({'每磅均價 ($/LB)': "{:.1f}", '每公斤均價 ($/KG)': "{:.1f}"}))
            else: st.warning("🔍 在你選擇的產地中，沒找到符合條件的報價。")
        else: st.warning("🔍 沒找到符合條件的有效報價。")

    st.markdown("---")
    st.markdown("### 2️⃣ 雲端情報雷達 (未建檔產品盲掃)")
    
    col_scan, col_clean = st.columns(2)
    
    with col_scan:
        if st.button("📥 極速掃描雲端最新 PDF", type="primary", use_container_width=True):
            with st.spinner("☁️ 正在智能過濾並解剖各家最新 PDF..."):
                try:
                    drive_service = get_drive_connection()
                    # 加入 createdTime 排序條件，不再盲目下載 70 幾份
                    results = drive_service.files().list(
                        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false", 
                        fields="files(id, name, createdTime)"
                    ).execute()
                    files = results.get('files', [])
                    
                    if not files: st.warning("資料夾內沒有 PDF。")
                    else:
                        # 💡 效能救星：將雲端檔案依供應商分組，並只保留「最新上傳」的一份！
                        supplier_files = {}
                        for f in files:
                            fname = f['name']
                            sup = next((s for kw, s in FILENAME_MAPPING.items() if kw in fname), "未知供應商")
                            if sup not in supplier_files: supplier_files[sup] = []
                            supplier_files[sup].append(f)
                            
                        files_to_scan = []
                        for sup, flist in supplier_files.items():
                            flist.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
                            files_to_scan.append(flist[0]) # 每一家只掃最新那 1 份
                            
                        from modules.pdf_xray import parse_supplier_row, deep_decode_item
                        cloud_db = []
                        
                        # 進度條顯示，速度大幅提升
                        progress_bar = st.progress(0)
                        for idx, file in enumerate(files_to_scan):
                            progress_bar.progress((idx + 1) / len(files_to_scan), text=f"正在解剖 {file['name']}...")
                            
                            supplier = next((sup for kw, sup in FILENAME_MAPPING.items() if kw in file['name']), "未知供應商")
                            request = drive_service.files().get_media(fileId=file['id'])
                            fh = io.BytesIO()
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while not done: _, done = downloader.next_chunk()
                            fh.seek(0)
                            
                            with pdfplumber.open(fh) as pdf:
                                for page in pdf.pages:
                                    for table in page.extract_tables():
                                        for row in table:
                                            cells = [str(cell).replace('\n', '').strip() if cell else "" for cell in row]
                                            extracted_parts = parse_supplier_row(supplier, cells)
                                            for part in extracted_parts:
                                                p_name, p_price_str, p_unit_str = part
                                                if len(clean_string(p_name)) > 2: 
                                                    origin, brand, clean_pname, spec, unit, price_lb, price_kg = deep_decode_item(p_name, p_price_str, p_unit_str)
                                                    if price_lb and price_kg:
                                                        display_unit = unit if unit == "箱/件" else "LB"
                                                        cloud_db.append({
                                                            "供應商": supplier, "產地": origin, "品牌": brand,
                                                            "品名(純)": clean_pname, "包裝規格": spec,
                                                            "原始價格": f"${price_lb}/{display_unit}",
                                                            "換算價 ($/LB)": price_lb, "換算價 ($/KG)": price_kg, 
                                                            "來源檔案": file['name'],
                                                            "search_string": f"{origin} {brand} {clean_pname} {supplier}".lower().replace(' ', '')
                                                        })
                        st.session_state['cloud_db'] = cloud_db
                        st.success(f"✅ 極速盲掃完成！從最新的 {len(files_to_scan)} 份報價單中，共萃取 {len(cloud_db)} 筆資料！")
                except Exception as e: st.error(f"雲端解剖失敗：{e}")

    with col_clean:
        # 💡 一鍵清理舊檔案：防呆、防擁擠的終極武器
        if st.button("🧹 一鍵清理雲端舊檔案 (每家僅保留最新 2 份)", type="secondary", use_container_width=True):
            with st.spinner("正在掃描雲端垃圾檔案..."):
                try:
                    drive_service = get_drive_connection()
                    results = drive_service.files().list(
                        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false", 
                        fields="files(id, name, createdTime)"
                    ).execute()
                    files = results.get('files', [])
                    
                    supplier_files = {}
                    for f in files:
                        sup = next((s for kw, s in FILENAME_MAPPING.items() if kw in f['name']), "未知供應商")
                        if sup not in supplier_files: supplier_files[sup] = []
                        supplier_files[sup].append(f)
                    
                    deleted_count = 0
                    for sup, flist in supplier_files.items():
                        flist.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
                        # 保留最新的 2 份，其餘刪除
                        if len(flist) > 2:
                            for f_to_delete in flist[2:]:
                                drive_service.files().delete(fileId=f_to_delete['id']).execute()
                                deleted_count += 1
                                
                    if deleted_count > 0:
                        st.success(f"🧹 清理完成！共刪除了 {deleted_count} 份過期的報價單，雲端空間已釋放。")
                    else:
                        st.info("ℹ️ 雲端很乾淨，目前每家供應商的檔案都沒有超過 2 份，無需清理。")
                except Exception as e: st.error(f"清理失敗：{e}")

    if st.session_state['cloud_db']:
        st.markdown("### 📡 雲端未建檔情報庫")
        filtered_cloud = st.session_state['cloud_db']
        
        if q_clean:
            filtered_cloud = [item for item in filtered_cloud if any(alias in item["search_string"] for alias in search_aliases)]
            
        if filtered_cloud:
            unique_origins_cloud = sorted(list(set([item["產地"] for item in filtered_cloud])))
            selected_origins_cloud = st.multiselect("🌍 雲端產地快速篩選 (可複選)：", unique_origins_cloud, default=[])
            if selected_origins_cloud:
                filtered_cloud = [item for item in filtered_cloud if item["產地"] in selected_origins_cloud]
                
            df_cloud = pd.DataFrame(filtered_cloud).drop(columns=['search_string'])
            st.dataframe(df_cloud, height=500)
            st.caption("提示：你可以點擊欄位標題 (如『換算價』) 進行高低排序。")
        else: st.warning(f"ℹ️ 在未建檔的 PDF 情報庫中，沒找到與 `{q_clean}` 相關的產品。")