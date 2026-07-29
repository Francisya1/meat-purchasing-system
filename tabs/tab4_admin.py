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

from modules.google_db import clean_string, get_google_connection, fetch_all_google_data, get_drive_connection, DRIVE_FOLDER_ID
from tabs.tab1_update import find_price_columns, extract_robust_pool

def render_tab4(ACTIVE_SUPPLIERS, HEADER_MAP, target_dict, cat_data, ignore_dict, STATIC_DICT, get_wavy_loading_html):
    st.header("⚙️ 系統管理與防呆中心")
    st.error("⚠️ **警告：此區塊為系統管理員與開發者專用。** 一般同事請勿操作，以免影響系統資料庫。")
    
    all_db_options = ["請選擇對應產品..."]
    sku_std_map = {}
    for sn, vals in cat_data.items():
        if vals and len(vals) > 2:
            for r in vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                if not sku: continue
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                all_db_options.append(f"[{sku}] {std_name}")
                sku_std_map[sku] = std_name

    st.markdown("### 📡 Phase 3: 智能新品雷達 (Inbox)")
    with st.form("radar_form"):
        col_r1, col_r2, col_r3 = st.columns([1, 1, 2])
        with col_r1: radar_sup = st.selectbox("選擇要掃描的供應商", ACTIVE_SUPPLIERS)
        with col_r2:
            hk_tz = pytz.timezone('Asia/Hong_Kong')
            radar_date = st.date_input("🗓️ 報價單日期", datetime.now(hk_tz))
        with col_r3: radar_file = st.file_uploader("上傳報價單進行深層掃描", type="pdf")
        submit_radar = st.form_submit_button("🚀 啟動新品雷達掃描", use_container_width=True)
        
    if submit_radar and radar_file:
        st.session_state['radar_date_str'] = radar_date.strftime("%Y-%m-%d")
        radar_ph = st.empty()
        radar_ph.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
        
        pdf_bytes = io.BytesIO(radar_file.read())
        new_filename = f"{radar_sup}_{radar_date.strftime('%Y-%m-%d')}.pdf"
        try:
            drive_service = get_drive_connection()
            pdf_bytes.seek(0)
            query = f"name='{new_filename}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
            existing_files = drive_service.files().list(q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
            media = MediaIoBaseUpload(pdf_bytes, mimetype='application/pdf', resumable=False)
            if existing_files:
                file_id = existing_files[0]['id']
                drive_service.files().update(fileId=file_id, media_body=media, supportsAllDrives=True).execute()
                st.toast(f"🔄 發現同日檔案，已成功【覆蓋更新】雲端報價單: {new_filename}")
            else:
                file_metadata = {'name': new_filename, 'parents': [DRIVE_FOLDER_ID]}
                drive_service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
                st.toast(f"✅ 報價單已成功自動備份至雲端: {new_filename}")
        except Exception as e: pass

        pdf_bytes.seek(0)
        robust_pool = extract_robust_pool(pdf_bytes, radar_sup)
        
        existing_mappings = [clean_string(m['name']) for m in target_dict.get(radar_sup, []) if len(clean_string(m['name'])) > 1]
        ignored_items = [clean_string(ig) for ig in ignore_dict.get(radar_sup, []) if len(clean_string(ig)) > 1]
        
        unmapped_items = []
        for c_raw, r_data in robust_pool.items():
            is_mapped = False
            for em in existing_mappings:
                if em == c_raw:
                    is_mapped = True; break
                if len(em) >= 4 and len(c_raw) >= 4 and (em in c_raw or c_raw in em):
                    is_mapped = True; break
                    
            is_ignored = False
            for ig in ignored_items:
                if ig == c_raw:
                    is_ignored = True; break
                if len(ig) >= 3 and len(c_raw) >= 3 and (ig in c_raw or c_raw in ig):
                    is_ignored = True; break
            
            if not is_mapped and not is_ignored:
                price_val = r_data['price']
                if price_val == "清" or "sold" in str(price_val).lower():
                    price_num = 0.0
                    preview_price = "Sold out (清)"
                else:
                    nums = re.findall(r'\d+\.?\d*', str(price_val))
                    if nums:
                        price_num = float(nums[0])
                        if "kg" in clean_string(str(r_data.get('unit', ''))): price_num = price_num / 2.2046
                        price_num = round(price_num, 1)
                        preview_price = f"${price_num} / LB"
                    else:
                        price_num = 0.0; preview_price = "無價錢"
                
                best_match = "請選擇對應產品..."
                max_score = 0
                for opt in all_db_options:
                    if opt == "請選擇對應產品...": continue
                    opt_clean = clean_string(opt.split(']')[-1])
                    score = 0
                    opt_words = [clean_string(w) for w in opt.split(']')[-1].split() if len(clean_string(w)) > 0]
                    if not opt_words: opt_words = [opt_clean]
                    for w in opt_words:
                        if w in c_raw: score += len(w) * 2
                    for key, aliases in STATIC_DICT.items():
                        all_terms = [key] + aliases
                        if any(clean_string(t) in c_raw for t in all_terms):
                            if any(clean_string(t) in opt_clean for t in all_terms):
                                score += 10
                    if score > max_score and score > 0:
                        max_score = score
                        best_match = opt
                        
                unmapped_items.append({
                    "✔️ 寫入 Mapping": False,
                    "報價單原文": r_data['raw_name'],
                    "對應母表產品 (AI建議)": best_match,
                    "✏️ 手動新價(LB)": price_num,
                    "👀 系統試抓價錢": preview_price
                })
        
        radar_ph.empty()
        
        if not unmapped_items:
            st.success("🎉 太棒了！這份報價單裡的所有產品都已經被你 Mapping 或加入黑名單了！")
            st.session_state['inbox_data'] = None
        else:
            unique_unmapped = {item["報價單原文"]: item for item in unmapped_items}.values()
            st.session_state['inbox_data'] = list(unique_unmapped)
            st.session_state['radar_sup'] = radar_sup
            
    if st.session_state.get('inbox_data'):
        st.warning(f"📥 系統發現了 **{len(st.session_state['inbox_data'])}** 個未追蹤的產品！")
        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
        with col_btn1:
            if st.button("☑️ 全部勾選 (準備寫入)", key="t4_check"):
                for item in st.session_state['inbox_data']: item["✔️ 寫入 Mapping"] = True
                st.rerun()
        with col_btn2:
            if st.button("☐ 全部取消勾選", key="t4_uncheck"):
                for item in st.session_state['inbox_data']: item["✔️ 寫入 Mapping"] = False
                st.rerun()

        inbox_df = pd.DataFrame(st.session_state['inbox_data'])
        edited_inbox = st.data_editor(
            inbox_df[["✔️ 寫入 Mapping", "報價單原文", "對應母表產品 (AI建議)", "✏️ 手動新價(LB)", "👀 系統試抓價錢"]],
            column_config={
                "✔️ 寫入 Mapping": st.column_config.CheckboxColumn("✔️ 寫入 Mapping"),
                "報價單原文": st.column_config.TextColumn("報價單原文", disabled=True),
                "對應母表產品 (AI建議)": st.column_config.SelectboxColumn("對應母表產品 (AI建議)", options=all_db_options),
                "✏️ 手動新價(LB)": st.column_config.NumberColumn("✏️ 手動新價(LB)", format="%.1f", min_value=0.0),
                "👀 系統試抓價錢": st.column_config.TextColumn("👀 系統試抓價錢", disabled=True)
            },
            use_container_width=True, hide_index=True, height=500
        )
        
        if st.button("💾 將打勾的項目寫入 Mapping 並同步更新價錢", type="primary", key="t4_save"):
            loading_ph5 = st.empty(); loading_ph5.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection(); map_ws = sh.worksheet('Mapping')
            map_adds = []; updates_by_sheet = {}; formats_by_sheet = {}; history_records = []
            sys_today = datetime.now(pytz.timezone('Asia/Hong_Kong')).strftime("%Y-%m-%d %H:%M:%S")
            quote_date_str = st.session_state.get('radar_date_str', sys_today.split()[0])
            
            for idx, row in edited_inbox.iterrows():
                if row["✔️ 寫入 Mapping"]:
                    raw_name = row["報價單原文"]; selected_sku_str = row["對應母表產品 (AI建議)"]; manual_price = row["✏️ 手動新價(LB)"]
                    if "請選擇" in selected_sku_str: st.error(f"❌ 產品 `{raw_name}` 沒有指定對應產品！"); loading_ph5.empty(); st.stop()
                        
                    match = re.search(r'\[(.*?)\]', selected_sku_str)
                    if match:
                        pure_sku = match.group(1)
                        map_adds.append([st.session_state['radar_sup'], raw_name, pure_sku])
                        if pd.notna(manual_price) and float(manual_price) > 0:
                            val_lb = float(manual_price); val_kg = round(val_lb * 2.2046, 1); target_sn = None; target_row_idx = -1
                            for sn, vals in cat_data.items():
                                if not vals: continue
                                for r_idx, r in enumerate(vals):
                                    if r_idx < 2 or not r: continue
                                    if str(r[0]).strip() == pure_sku: target_sn = sn; target_row_idx = r_idx + 1; break
                                if target_sn: break
                            if target_sn:
                                lb_col, kg_col = find_price_columns(cat_data[target_sn], st.session_state['radar_sup'], HEADER_MAP)
                                fmt = cellFormat(backgroundColor=color(1.0, 0.95, 0.6))
                                if lb_col != -1:
                                    c_a1 = gspread.utils.rowcol_to_a1(target_row_idx, lb_col)
                                    updates_by_sheet.setdefault(target_sn, []).append({'range': c_a1, 'values': [[val_lb]]})
                                    formats_by_sheet.setdefault(target_sn, []).append((c_a1, fmt))
                                if kg_col != -1:
                                    c_a1 = gspread.utils.rowcol_to_a1(target_row_idx, kg_col)
                                    updates_by_sheet.setdefault(target_sn, []).append({'range': c_a1, 'values': [[val_kg]]})
                                    formats_by_sheet.setdefault(target_sn, []).append((c_a1, fmt))
                                history_records.append([sys_today, quote_date_str, st.session_state['radar_sup'], pure_sku, raw_name, val_lb, val_kg])
            
            if map_adds: map_ws.append_rows(map_adds)
            if updates_by_sheet:
                for sn in updates_by_sheet:
                    sh.worksheet(sn).batch_update(updates_by_sheet[sn])
                    if sn in formats_by_sheet and formats_by_sheet[sn]: format_cell_ranges(sh.worksheet(sn), formats_by_sheet[sn])
            if history_records: sh.worksheet('History_Log').append_rows(history_records)
            if map_adds or updates_by_sheet:
                fetch_all_google_data.clear(); loading_ph5.empty(); st.balloons(); st.success(f"🎉 成功新增了 {len(map_adds)} 筆 Mapping！")
                st.session_state['inbox_data'] = None; time.sleep(2); st.rerun()

    st.markdown("---")
    st.markdown("### 🎯 Phase 4: 價格錨點異常偵測 (同行平均值)")
    if st.button("🔍 掃描全庫同行價格異常", use_container_width=True):
        loading_ph6 = st.empty(); loading_ph6.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
        gc, sh, _ = get_google_connection()
        try: mapping_data_raw = sh.worksheet('Mapping').get_all_records()
        except: mapping_data_raw = []
            
        map_lookup = {}
        for idx, r in enumerate(mapping_data_raw):
            sup = str(r.get('供應商','')).strip(); sku = str(r.get('對應SKU','')).strip(); raw = str(r.get('供應商原文','')).strip()
            if sup and sku and raw: map_lookup.setdefault((sup, sku), []).append({'raw': raw, 'row': idx + 2})
                
        anomalies = []
        for sn, vals in cat_data.items():
            if not vals: continue
            sup_cols = {}
            for sup_name in HEADER_MAP.keys():
                lb_col, _ = find_price_columns(vals, sup_name, HEADER_MAP)
                sup_cols[sup_name] = lb_col - 1
                
            for r in vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                prices = {}
                for sup, col_idx in sup_cols.items():
                    if col_idx != -2 and col_idx < len(r):
                        p_str = str(r[col_idx]).strip()
                        nums = re.findall(r'\d+\.?\d*', p_str)
                        if nums and float(nums[0]) > 0 and "sold out" not in p_str.lower(): prices[sup] = float(nums[0])
                            
                if len(prices) >= 2:
                    avg_p = sum(prices.values()) / len(prices)
                    for sup, p in prices.items():
                        diff_pct = (p - avg_p) / avg_p
                        if abs(diff_pct) >= 0.15: 
                            status = f"🔴 貴 {diff_pct*100:.1f}%" if diff_pct > 0 else f"🔵 平 {abs(diff_pct)*100:.1f}%"
                            for info in map_lookup.get((sup, sku), [{'raw': "未知(未綁定或手動填入)", 'row': -1}]):
                                if info['row'] != -1:
                                    anomalies.append({
                                        "🗑️ 刪除": False, "✔️ 修正": False,
                                        "供應商": sup, "報價單原文": info['raw'], "原綁定 SKU": f"[{sku}] {std_name}",
                                        "該行平均價": avg_p, "異常價錢": p, "系統判定": status,
                                        "🔄 重新綁定至 (新SKU)": "請選擇對應產品...", "✏️ 手動修正價(LB)": None,
                                        "excel_row": info['row'], "pure_sku": sku
                                    })
        loading_ph6.empty()
        if anomalies: st.session_state['anomaly_data'] = sorted(anomalies, key=lambda x: abs(float(x['異常價錢']) - float(x['該行平均價'])), reverse=True)
        else: st.success("✅ 掃描完成！全庫沒有發現偏離超過 15% 的異常價錢！"); st.session_state['anomaly_data'] = None

    if st.session_state.get('anomaly_data'):
        df_anom = pd.DataFrame(st.session_state['anomaly_data'])
        df_anom["該行平均價"] = df_anom["該行平均價"].apply(lambda x: f"${x:.1f}")
        df_anom["異常價錢"] = df_anom["異常價錢"].apply(lambda x: f"${x:.1f}")
        
        edited_anom = st.data_editor(
            df_anom,
            column_config={
                "🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除"), "✔️ 修正": st.column_config.CheckboxColumn("✔️ 修正"),
                "供應商": st.column_config.TextColumn(disabled=True), "報價單原文": st.column_config.TextColumn(disabled=True),
                "原綁定 SKU": st.column_config.TextColumn(disabled=True), "該行平均價": st.column_config.TextColumn(disabled=True),
                "異常價錢": st.column_config.TextColumn(disabled=True), "系統判定": st.column_config.TextColumn(disabled=True),
                "🔄 重新綁定至 (新SKU)": st.column_config.SelectboxColumn("🔄 重新綁定至 (新SKU)", options=all_db_options),
                "✏️ 手動修正價(LB)": st.column_config.NumberColumn("✏️ 手動修正價(LB)", format="%.1f"), "excel_row": None, "pure_sku": None
            },
            use_container_width=True, hide_index=True, height=400
        )
        
        if st.button("💾 執行同行異常修正", type="primary", key="fix_anom"):
            loading_ph7 = st.empty(); loading_ph7.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection(); mapping_ws = sh.worksheet('Mapping')
            cells_to_update = []; rows_to_delete = []; price_upd_dict = {}
            for idx, row in edited_anom.iterrows():
                is_del = row.get("🗑️ 刪除", False); is_fix = row.get("✔️ 修正", False); target_row = row.get("excel_row", -1)
                if (is_del or is_fix) and target_row != -1:
                    if is_del: rows_to_delete.append(int(target_row))
                    else:
                        pure_sku = row.get("pure_sku", ""); new_sku_full = row.get("🔄 重新綁定至 (新SKU)", "")
                        if "請選擇" not in new_sku_full and new_sku_full.strip():
                            match = re.search(r'\[(.*?)\]', new_sku_full)
                            if match:
                                pure_sku = match.group(1)
                                cells_to_update.append({'range': gspread.utils.rowcol_to_a1(int(target_row), 3), 'values': [[pure_sku]]})

                        new_price = row.get("✏️ 手動修正價(LB)")
                        if pd.notna(new_price) and float(new_price) > 0:
                            v_lb = float(new_price); v_kg = round(v_lb * 2.2046, 1); sup = row["供應商"]
                            tgt_sn = None; tgt_r_idx = -1
                            for sn, vals in cat_data.items():
                                if not vals: continue
                                for r_idx, cv in enumerate(vals):
                                    if r_idx < 2 or not cv: continue
                                    if str(cv[0]).strip() == pure_sku: tgt_sn = sn; tgt_r_idx = r_idx + 1; break
                                if tgt_sn: break
                            if tgt_sn:
                                lb_col, kg_col = find_price_columns(cat_data[tgt_sn], sup, HEADER_MAP)
                                if lb_col != -1: price_upd_dict.setdefault(tgt_sn, []).append({'range': gspread.utils.rowcol_to_a1(tgt_r_idx, lb_col), 'values': [[v_lb]]})
                                if kg_col != -1: price_upd_dict.setdefault(tgt_sn, []).append({'range': gspread.utils.rowcol_to_a1(tgt_r_idx, kg_col), 'values': [[v_kg]]})

            for r in sorted(list(set(rows_to_delete)), reverse=True): mapping_ws.delete_rows(r)
            if cells_to_update: mapping_ws.batch_update(cells_to_update)
            if price_upd_dict:
                for sn, upds in price_upd_dict.items(): sh.worksheet(sn).batch_update(upds)
            if rows_to_delete or cells_to_update or price_upd_dict:
                fetch_all_google_data.clear(); loading_ph7.empty(); st.balloons()
                st.session_state['anomaly_data'] = None; time.sleep(1.5); st.rerun()

    # ==========================================
    # 💡 終極防線: Phase 6 絕對歷史防呆
    # ==========================================
    st.markdown("---")
    st.markdown("### 🚨 Phase 6: 絕對歷史防呆 (全庫價格體檢)")
    st.write("同行平均值如果集體標錯就沒用了。這裡會調出**「產品過去半年的歷史平均價」**，如果今天的價錢比歷史均價暴漲或暴跌超過 40%，或者出現不合理的極端值 (如 $3/LB)，系統將強制介入！")
    
    if st.button("🚀 執行絕對歷史價格大掃描", use_container_width=True):
        loading_ph_hist = st.empty(); loading_ph_hist.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
        gc, sh, _ = get_google_connection()
        
        # 取得歷史資料建立基準線
        try: hist_raw = sh.worksheet('History_Log').get_all_values()
        except: hist_raw = []
        
        sku_hist_prices = {}
        if len(hist_raw) > 1:
            for hr in hist_raw[1:]:
                if len(hr) >= 6:
                    try:
                        sku = str(hr[3] if len(hr)>=7 else hr[2]).strip()
                        p = float(hr[5] if len(hr)>=7 else hr[4])
                        if p > 0: sku_hist_prices.setdefault(sku, []).append(p)
                    except: pass
        
        hist_baseline = {k: sum(v)/len(v) for k, v in sku_hist_prices.items()}
        
        abs_anomalies = []
        for sn, vals in cat_data.items():
            if not vals: continue
            sup_cols = {}
            for sup_name in HEADER_MAP.keys():
                lb_col, _ = find_price_columns(vals, sup_name, HEADER_MAP)
                sup_cols[sup_name] = lb_col - 1
                
            for r in vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                
                for sup, col_idx in sup_cols.items():
                    if col_idx != -2 and col_idx < len(r):
                        p_str = str(r[col_idx]).strip()
                        nums = re.findall(r'\d+\.?\d*', p_str)
                        if nums and float(nums[0]) > 0 and "sold out" not in p_str.lower():
                            current_p = float(nums[0])
                            is_anom = False; msg = ""; ref_val = ""
                            
                            # 1. 極端值測試 (肉類不可能小於 $5，除非是特例，這裡抓 <$3 或 >$300)
                            if current_p < 3.0 or current_p > 300.0:
                                is_anom = True; msg = "⚠️ 違反常理極端價"; ref_val = "系統常理 ($3~$300)"
                            # 2. 歷史斷層測試
                            elif sku in hist_baseline:
                                baseline = hist_baseline[sku]
                                diff = (current_p - baseline) / baseline
                                if abs(diff) >= 0.40: # 偏差大於 40%
                                    is_anom = True; msg = f"📈 暴漲 {diff*100:.0f}%" if diff > 0 else f"📉 暴跌 {abs(diff)*100:.0f}%"; ref_val = f"歷史均價 ${baseline:.1f}"
                                    
                            if is_anom:
                                abs_anomalies.append({
                                    "✔️ 修正價錢": False,
                                    "供應商": sup, "SKU 與 品名": f"[{sku}] {std_name}",
                                    "當前錯誤價": current_p, "參考基準": ref_val, "警報原因": msg,
                                    "✏️ 手動修正價(LB)": current_p, "pure_sku": sku
                                })
                                
        loading_ph_hist.empty()
        if abs_anomalies: st.session_state['abs_anom_data'] = abs_anomalies
        else: st.success("✅ 掃描完成！全庫所有價錢都在合理的歷史軌道內，沒有暴漲暴跌！"); st.session_state['abs_anom_data'] = None

    if st.session_state.get('abs_anom_data'):
        df_abs = pd.DataFrame(st.session_state['abs_anom_data'])
        df_abs["當前錯誤價"] = df_abs["當前錯誤價"].apply(lambda x: f"${x:.1f}")
        
        edited_abs = st.data_editor(
            df_abs,
            column_config={
                "✔️ 修正價錢": st.column_config.CheckboxColumn("✔️ 修正價錢"),
                "供應商": st.column_config.TextColumn(disabled=True), "SKU 與 品名": st.column_config.TextColumn(disabled=True),
                "當前錯誤價": st.column_config.TextColumn(disabled=True), "參考基準": st.column_config.TextColumn(disabled=True),
                "警報原因": st.column_config.TextColumn(disabled=True),
                "✏️ 手動修正價(LB)": st.column_config.NumberColumn("✏️ 手動修正價(LB)", format="%.1f"), "pure_sku": None
            },
            use_container_width=True, hide_index=True, height=400
        )
        
        if st.button("💾 執行絕對歷史異常價錢修正", type="primary", key="fix_abs"):
            loading_ph9 = st.empty(); loading_ph9.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection(); price_upd_dict = {}
            
            for idx, row in edited_abs.iterrows():
                if row.get("✔️ 修正價錢", False):
                    new_price = row.get("✏️ 手動修正價(LB)")
                    pure_sku = row.get("pure_sku", "")
                    sup = row.get("供應商", "")
                    
                    if pd.notna(new_price) and float(new_price) > 0 and pure_sku:
                        v_lb = float(new_price); v_kg = round(v_lb * 2.2046, 1)
                        tgt_sn = None; tgt_r_idx = -1
                        for sn, vals in cat_data.items():
                            if not vals: continue
                            for r_idx, cv in enumerate(vals):
                                if r_idx < 2 or not cv: continue
                                if str(cv[0]).strip() == pure_sku: tgt_sn = sn; tgt_r_idx = r_idx + 1; break
                            if tgt_sn: break
                        if tgt_sn:
                            lb_col, kg_col = find_price_columns(cat_data[tgt_sn], sup, HEADER_MAP)
                            if lb_col != -1: price_upd_dict.setdefault(tgt_sn, []).append({'range': gspread.utils.rowcol_to_a1(tgt_r_idx, lb_col), 'values': [[v_lb]]})
                            if kg_col != -1: price_upd_dict.setdefault(tgt_sn, []).append({'range': gspread.utils.rowcol_to_a1(tgt_r_idx, kg_col), 'values': [[v_kg]]})

            if price_upd_dict:
                for sn, upds in price_upd_dict.items(): sh.worksheet(sn).batch_update(upds)
                fetch_all_google_data.clear(); loading_ph9.empty(); st.balloons()
                st.session_state['abs_anom_data'] = None; time.sleep(1.5); st.rerun()
            else: loading_ph9.empty(); st.warning("⚠️ 沒有勾選任何操作項目或無有效填寫。")

    st.markdown("---")
    st.markdown("### 🗂️ Phase 5: 深度 Mapping 總管")
    tab5_1, tab5_2 = st.tabs(["🤖 AI 語意錯綁偵測", "🔍 手動全庫搜尋"])
    
    with tab5_1:
        if st.button("🚀 執行 AI 語意巡邏", use_container_width=True):
            p5_loading1 = st.empty(); p5_loading1.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection()
            try: mapping_data_raw = sh.worksheet('Mapping').get_all_records()
            except: mapping_data_raw = []
            
            suspicious_semantic = []
            stop_chars = set("巴西美國澳洲紐西蘭中國阿根廷日本急凍冷藏新鮮廠牌kglb磅件箱x*1234567890. -/")
            for idx, row in enumerate(mapping_data_raw):
                sup = str(row.get('供應商','')).strip(); raw = str(row.get('供應商原文','')).strip(); sku = str(row.get('對應SKU','')).strip()
                std_name = sku_std_map.get(sku, "")
                if not std_name: continue
                clean_raw = clean_string(raw).lower(); clean_std = clean_string(std_name).lower()
                is_sus = False; reason = ""

                found_main_keys = [(k, aliases) for k, aliases in STATIC_DICT.items() if k in clean_std or any(a in clean_std for a in aliases)]
                if found_main_keys:
                    passed = False
                    for k, aliases in found_main_keys:
                        if k in clean_raw or any(a in clean_raw for a in aliases): passed = True; break
                    if not passed: is_sus = True; reason = "關鍵字完全不符 (語意衝突)"
                else:
                    set_std = set(clean_std) - stop_chars; set_raw = set(clean_raw) - stop_chars
                    if set_std and set_raw and len(set_std & set_raw) == 0: is_sus = True; reason = "零文字重疊 (疑似錯綁)"

                if is_sus:
                    suspicious_semantic.append({
                        "🗑️ 刪除": False, "✔️ 修正 SKU": False,
                        "供應商": sup, "報價單原文": raw, "原綁定 SKU": f"[{sku}] {std_name}",
                        "系統判定": f"🚨 {reason}", "🔄 重新綁定至 (新SKU)": "請選擇對應產品...", "excel_row": idx + 2
                    })
            p5_loading1.empty()
            if suspicious_semantic: st.session_state['semantic_data'] = suspicious_semantic
            else: st.success("✅ 巡邏完成！系統認為目前的 Mapping 語意都很合理！"); st.session_state['semantic_data'] = None

        if st.session_state.get('semantic_data'):
            edited_sem = st.data_editor(
                pd.DataFrame(st.session_state['semantic_data']),
                column_config={"🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除"), "✔️ 修正 SKU": st.column_config.CheckboxColumn("✔️ 修正 SKU"), "供應商": st.column_config.TextColumn(disabled=True), "報價單原文": st.column_config.TextColumn(disabled=True), "原綁定 SKU": st.column_config.TextColumn(disabled=True), "系統判定": st.column_config.TextColumn(disabled=True), "🔄 重新綁定至 (新SKU)": st.column_config.SelectboxColumn("🔄 重新綁定至 (新SKU)", options=all_db_options), "excel_row": None},
                use_container_width=True, hide_index=True, height=400
            )
            if st.button("💾 執行語意修正", type="primary", key="fix_sem_map"):
                p5_loading2 = st.empty(); p5_loading2.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
                gc, sh, _ = get_google_connection(); map_ws = sh.worksheet('Mapping')
                c_upd = []; r_del = []
                for idx, row in edited_sem.iterrows():
                    is_d = row.get("🗑️ 刪除", False); is_f = row.get("✔️ 修正 SKU", False); tr = row.get("excel_row", -1)
                    if tr != -1:
                        if is_d: r_del.append(int(tr))
                        elif is_f:
                            ns = row.get("🔄 重新綁定至 (新SKU)", "")
                            if "請選擇" not in ns and ns.strip():
                                m = re.search(r'\[(.*?)\]', ns)
                                if m: c_upd.append({'range': gspread.utils.rowcol_to_a1(int(tr), 3), 'values': [[m.group(1)]]})
                for r in sorted(list(set(r_del)), reverse=True): map_ws.delete_rows(r)
                if c_upd: map_ws.batch_update(c_upd)
                if r_del or c_upd:
                    fetch_all_google_data.clear(); p5_loading2.empty(); st.session_state['semantic_data'] = None; time.sleep(1); st.rerun()

    with tab5_2:
        search_kw = st.text_input("🔍 手動搜尋 Mapping", placeholder="例如: 廣隆, 雞翼, 3010")
        if search_kw.strip():
            gc, sh, _ = get_google_connection()
            try: all_maps_raw = sh.worksheet('Mapping').get_all_records()
            except: all_maps_raw = []
            
            filtered_maps = []
            for idx, r in enumerate(all_maps_raw):
                sup = str(r.get('供應商','')).strip(); raw = str(r.get('供應商原文','')).strip(); sku = str(r.get('對應SKU','')).strip()
                kw_low = search_kw.lower()
                if kw_low in sup.lower() or kw_low in raw.lower() or kw_low in sku.lower():
                    filtered_maps.append({"🗑️ 刪除": False, "✔️ 修正 SKU": False, "供應商": sup, "報價單原文": raw, "目前綁定 SKU": f"[{sku}] {sku_std_map.get(sku, '')}", "🔄 修改為 (新SKU)": "請選擇對應產品...", "excel_row": idx + 2})
            if filtered_maps:
                edited_full_map = st.data_editor(
                    pd.DataFrame(filtered_maps),
                    column_config={"🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除"), "✔️ 修正 SKU": st.column_config.CheckboxColumn("✔️ 修正 SKU"), "供應商": st.column_config.TextColumn(disabled=True), "報價單原文": st.column_config.TextColumn(disabled=True), "目前綁定 SKU": st.column_config.TextColumn(disabled=True), "🔄 修改為 (新SKU)": st.column_config.SelectboxColumn("🔄 修改為 (新SKU)", options=all_db_options), "excel_row": None},
                    use_container_width=True, hide_index=True, height=min(500, len(filtered_maps)*40 + 40)
                )
                if st.button("💾 執行操作", type="primary", key="fix_full_map"):
                    p5_loading3 = st.empty(); p5_loading3.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
                    map_ws = sh.worksheet('Mapping'); c_upd = []; r_del = []
                    for idx, row in edited_full_map.iterrows():
                        is_d = row.get("🗑️ 刪除", False); is_f = row.get("✔️ 修正 SKU", False); tr = row.get("excel_row", -1)
                        if tr != -1:
                            if is_d: r_del.append(int(tr))
                            elif is_f:
                                ns = row.get("🔄 修改為 (新SKU)", "")
                                if "請選擇" not in ns and ns.strip():
                                    m = re.search(r'\[(.*?)\]', ns)
                                    if m: c_upd.append({'range': gspread.utils.rowcol_to_a1(int(tr), 3), 'values': [[m.group(1)]]})
                    for r in sorted(list(set(r_del)), reverse=True): map_ws.delete_rows(r)
                    if c_upd: map_ws.batch_update(c_upd)
                    if r_del or c_upd: fetch_all_google_data.clear(); p5_loading3.empty(); time.sleep(1); st.rerun()
