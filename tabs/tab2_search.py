import streamlit as st
import pandas as pd
import re
import io
import pdfplumber
from googleapiclient.http import MediaIoBaseDownload

from modules.google_db import clean_string, get_drive_connection, DRIVE_FOLDER_ID
from tabs.tab1_update import find_price_columns

def render_tab2(global_origins, STATIC_DICT, cat_data, HEADER_MAP, parsed_history, FILENAME_MAPPING, get_wavy_loading_html):
    with st.form("search_form"):
        col_s1, col_s2, col_s3, col_s4 = st.columns([3, 2, 2, 1])
        with col_s1: search_query = st.text_input("🔍 關鍵字 (如: 雞翼)：", placeholder="輸入產品...")
        with col_s2: selected_origins = st.multiselect("🌍 篩選產地 (選填)", global_origins, placeholder="全部產地")
        with col_s3: category_filter = st.selectbox("🥩 肉類分類 (強制隔離)", ["全部", "Beef (牛)", "Pork (豬)", "Chicken (雞)", "Lamp (羊)"])
        with col_s4: 
            st.markdown("<br>", unsafe_allow_html=True)
            submit_search = st.form_submit_button("🔍 搜尋", use_container_width=True)

    if submit_search and search_query:
        q_clean = clean_string(search_query)
        search_aliases = set([q_clean])
        for key, aliases in STATIC_DICT.items():
            if key in q_clean or q_clean in key: search_aliases.update(aliases)
                            
        st.info(f"🧠 智能搜尋擴展：`{', '.join(search_aliases)}` (範圍: {category_filter})")
        sub_tab1, sub_tab2 = st.tabs(["📂 搜尋已建立內容", "☁️ 所有供應商中尋找"])

        with sub_tab1:
            search_ph1 = st.empty()
            search_ph1.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            compare_results = []
            for sn, all_vals in cat_data.items():
                if category_filter != "全部" and category_filter.split(" ")[0] != sn: continue
                if not all_vals: continue
                sup_cols = {}
                for sup_name in HEADER_MAP.keys():
                    lb_col, _ = find_price_columns(all_vals, sup_name, HEADER_MAP)
                    sup_cols[sup_name] = {"LB": lb_col - 1} 

                for row_idx, r in enumerate(all_vals[2:]):
                    if not r: continue
                    sku = str(r[0]).strip()
                    origin = str(r[1]).strip() if len(r) > 1 else "未標明"
                    if selected_origins and origin not in selected_origins: continue
                    std_name = " | ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                    clean_sku = clean_string(sku); clean_std = clean_string(std_name)
                    
                    if any(alias in clean_sku or alias in clean_std for alias in search_aliases):
                        for sup_name, cols in sup_cols.items():
                            lb_col_idx = cols["LB"]
                            if lb_col_idx != -2:
                                p_val_str = str(r[lb_col_idx]).strip() if lb_col_idx < len(r) else ""
                                nums = re.findall(r'\d+\.?\d*', p_val_str)
                                is_sold_out_now = "sold out" in p_val_str.lower() or not nums
                                hist_alert = ""; price_lb_numeric = 99999.9; display_price = "Sold out"
                                valid_past_prices = [x['price'] for x in parsed_history if x['sku'] == sku and x['price'] > 0]
                                if is_sold_out_now and len(valid_past_prices) > 0: hist_alert = "🔥 曾經熱賣，現已斷貨！(上次報價有售)"
                                elif not is_sold_out_now:
                                    display_price = round(float(nums[0]), 1); price_lb_numeric = display_price
                                    if valid_past_prices and display_price <= min(valid_past_prices): hist_alert = "🔥🔥 歷史低位"
                                
                                compare_results.append({
                                    "SKU": sku, "產地": origin, "標準品名": std_name, "供應商": sup_name,
                                    "每磅均價 ($/LB)": display_price, "sort_price": price_lb_numeric, "歷史低價提醒": hist_alert
                                })
            search_ph1.empty()
            if compare_results:
                df_compare = pd.DataFrame(compare_results).sort_values(by="sort_price")
                cheapest = df_compare.iloc[0]
                if cheapest['每磅均價 ($/LB)'] != "Sold out":
                    st.markdown(f"<div style='background-color:#e8f5e9 !important; padding: 15px; border-radius: 8px; border-left: 5px solid #4caf50; margin-bottom: 15px;'><span style='font-size:12px; color:#2e7d32; font-weight:bold;'>🏆 最平首選推薦</span><h3 style='margin:5px 0 0 0; color:#1b5e20; font-size:18px;'>【{cheapest['供應商']}】 {cheapest['標準品名']}</h3><h2 style='margin:5px 0 0 0; color:#2e7d32; font-size:24px; font-weight:900;'>${cheapest['每磅均價 ($/LB)']:.1f} <span style='font-size:14px; font-weight:normal;'>/ LB</span></h2></div>", unsafe_allow_html=True)
                for _, row in df_compare.iterrows():
                    is_soldout_card = (row['每磅均價 ($/LB)'] == "Sold out")
                    badge_class = "badge badge-danger" if is_soldout_card else "badge"
                    alert_html = f"<span class='{badge_class}'>{row['歷史低價提醒']}</span>" if row['歷史低價提醒'] else ""
                    diff_text = ""
                    if not is_soldout_card and cheapest['每磅均價 ($/LB)'] != "Sold out":
                        diff = row['每磅均價 ($/LB)'] - cheapest['每磅均價 ($/LB)']
                        diff_text = f"貴 ${diff:.1f}" if diff > 0 else "最平"
                    price_display = "Sold out 斷貨" if is_soldout_card else f"${row['每磅均價 ($/LB)']:.1f} / LB"
                    price_color = "#999999" if is_soldout_card else "#D9534F"
                    diff_html = f"<span class='badge' style='background-color: #E0E0E0 !important; color: #333333 !important;'>{diff_text}</span>" if diff_text else ""
                    st.markdown(f"<div class='product-card'><div class='product-card-header'><span class='product-card-title'>【{row['供應商']}】 {row['標準品名']}</span>{diff_html}</div><div class='product-card-body'>產地: <span style='color:#0066cc; font-weight:bold;'>{row['產地']}</span> | SKU: {row['SKU']}</div><div class='product-card-price-row'><span class='product-card-price' style='color: {price_color} !important;'>{price_display}</span>{alert_html}</div></div>", unsafe_allow_html=True)
            else: st.warning("🔍 沒找到符合條件的報價。")

        with sub_tab2:
            st.info("💡 提示：雲端盲掃模式因沒有預先設定的分類，搜尋將會比對所有找到的內容。")
            search_ph2 = st.empty()
            search_ph2.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            try:
                drive_service = get_drive_connection()
                results = drive_service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false", fields="files(id, name, createdTime)").execute()
                files = results.get('files', [])
                if not files: search_ph2.empty(); st.warning("資料夾內沒有 PDF。")
                else:
                    supplier_files = {}
                    for f in files:
                        fname = f['name']
                        sup = next((s for kw, s in FILENAME_MAPPING.items() if kw in fname), "未知供應商")
                        if sup not in supplier_files: supplier_files[sup] = []
                        supplier_files[sup].append(f)
                    files_to_scan = [flist[0] for flist in supplier_files.values()] 
                        
                    from modules.pdf_xray import parse_supplier_row, deep_decode_item
                    cloud_db = []
                    
                    def process_cloud_item(raw_name_text, price_str, unit_str, supplier, file_name):
                        raw_name_text = re.sub(r'^(抄碼|\d+(\.\d+)?[Kk][Gg]?)\s*', '', raw_name_text).strip()
                        raw_name_text = re.sub(r'[\$\s/\|]+$', '', raw_name_text).strip()
                        clean_raw = clean_string(raw_name_text)
                        if len(clean_raw) < 2 or not re.search(r'[\u4e00-\u9fa5]', raw_name_text): return
                        if price_str == "清" or "sold" in str(price_str).lower(): return
                        origin, brand, clean_pname, spec, unit, price_lb, price_kg = deep_decode_item(raw_name_text, price_str, unit_str)
                        if price_lb:
                            cloud_db.append({
                                "供應商": supplier, "產地": origin, "品牌": brand, "品名(純)": clean_pname, "包裝規格": spec,
                                "換算價 ($/LB)": price_lb, "來源檔案": file_name, "search_string": f"{origin} {brand} {clean_pname} {supplier}".lower().replace(' ', '')
                            })
                    
                    for idx, file in enumerate(files_to_scan):
                        supplier = next((sup for kw, sup in FILENAME_MAPPING.items() if kw in file['name']), "未知供應商")
                        request = drive_service.files().get_media(fileId=file['id'])
                        fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while not done: _, done = downloader.next_chunk()
                        fh.seek(0)
                        
                        with pdfplumber.open(fh) as pdf:
                            for page in pdf.pages:
                                lines = []
                                text = page.extract_text()
                                if text: lines.extend(text.split('\n'))
                                tables = page.extract_tables()
                                for table in tables:
                                    for row in table:
                                        row_str = " ".join([str(c).replace('\n', ' ').strip() for c in row if c])
                                        lines.append(row_str)
                                
                                if supplier == "形澧":
                                    for line in lines:
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
                                            raw_name_text = line.rsplit(price_str_for_split, 1)[0].strip()
                                            process_cloud_item(raw_name_text, str(raw_price), "", supplier, file['name'])
                                else:
                                    for line in lines:
                                        matches = re.finditer(r'(.*?)(?:\$|HKD|HK\$)\s*(\d+(?:\.\d+)?|清)\s*(磅|/\s*LB|/\s*KG|kg|lb|件|箱|/lb)?', line, re.IGNORECASE)
                                        for match in matches:
                                            process_cloud_item(match.group(1), match.group(2), match.group(3) if match.group(3) else "", supplier, file['name'])
                                    for table in tables:
                                        for row in table:
                                            cells = [str(cell).replace('\n', '').strip() if cell else "" for cell in row]
                                            extracted_parts = parse_supplier_row(supplier, cells)
                                            for part in extracted_parts:
                                                p_name = part[0]
                                                if "@@@" in p_name: p_name = p_name.split("@@@")[0]
                                                process_cloud_item(p_name, part[1], part[2], supplier, file['name'])
                    search_ph2.empty()
                    
                    filtered_cloud = []
                    seen_cloud = set()
                    for item in cloud_db:
                        if any(alias in item["search_string"] for alias in search_aliases) and (not selected_origins or item["產地"] in selected_origins):
                            uid = f"{item['供應商']}_{item['品名(純)']}_{item['換算價 ($/LB)']}"
                            if uid not in seen_cloud:
                                seen_cloud.add(uid)
                                filtered_cloud.append(item)
                                
                    if filtered_cloud:
                        df_cloud = pd.DataFrame(filtered_cloud).sort_values(by="換算價 ($/LB)")
                        cheapest_cloud = df_cloud.iloc[0]
                        st.markdown(f"<div style='background-color:#e3f2fd !important; padding: 15px; border-radius: 8px; border-left: 5px solid #1976d2; margin-bottom: 15px;'><span style='font-size:12px; color:#1565c0; font-weight:bold;'>🏆 雲端未建檔最平首選</span><h3 style='margin:5px 0 0 0; color:#0d47a1; font-size:18px;'>【{cheapest_cloud['供應商']}】 {cheapest_cloud['品名(純)']}</h3><h2 style='margin:5px 0 0 0; color:#1565c0; font-size:24px; font-weight:900;'>${cheapest_cloud['換算價 ($/LB)']:.1f} <span style='font-size:14px; font-weight:normal;'>/ LB</span></h2></div>", unsafe_allow_html=True)
                        for _, row in df_cloud.iterrows():
                            diff = row['換算價 ($/LB)'] - cheapest_cloud['換算價 ($/LB)']
                            diff_text = f"貴 ${diff:.1f}" if diff > 0 else "最平"
                            diff_html_cloud = f"<span class='badge' style='background-color: #E0E0E0 !important; color: #333333 !important;'>{diff_text}</span>" if diff_text else ""
                            st.markdown(f"<div class='product-card'><div class='product-card-header'><span class='product-card-title'>【{row['供應商']}】 {row['品名(純)']}</span>{diff_html_cloud}</div><div class='product-card-body'>產地: <span style='color:#0066cc; font-weight:bold;'>{row['產地']}</span> | 規格: {row['包裝規格']} | 品牌: {row['品牌']}<br><span style='font-size:10px; color:#888888 !important;'>來源檔: {row['來源檔案']}</span></div><div class='product-card-price-row'><span class='product-card-price'>${row['換算價 ($/LB)']:.1f} / LB</span></div></div>", unsafe_allow_html=True)
                    else: st.warning(f"ℹ️ 在雲端未建檔的情報中，沒找到與 `{search_query}` 相關的產品。")
            except Exception as e: search_ph2.empty(); st.error(f"雲端解剖失敗：{e}")