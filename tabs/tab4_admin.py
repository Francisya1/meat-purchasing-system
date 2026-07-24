import streamlit as st
import pandas as pd
import re
import io
import time
from datetime import datetime
import pytz
import gspread
from gspread_formatting import *
import pdfplumber

from modules.google_db import clean_string, get_google_connection, fetch_all_google_data
from tabs.tab1_update import find_price_columns, extract_robust_pool

def render_tab4(ACTIVE_SUPPLIERS, HEADER_MAP, target_dict, cat_data, ignore_dict, STATIC_DICT, get_wavy_loading_html):
    st.header("⚙️ 系統管理與防呆中心")
    st.error("⚠️ **警告：此區塊為系統管理員與開發者專用。** 一般同事請勿操作，以免影響系統資料庫。")
    
    all_db_options = ["請選擇對應產品..."]
    for sn, vals in cat_data.items():
        if vals and len(vals) > 2:
            for r in vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                if not sku: continue
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                all_db_options.append(f"[{sku}] {std_name}")

    st.markdown("### 📡 Phase 3: 智能新品雷達 (Inbox)")
    st.write("上傳一份報價單，系統將自動比對現有 Mapping 與黑名單，把「未追蹤的全新產品」全部挖出來。確認無誤後，系統會幫你同步建立 Mapping 與寫入最新價錢！")

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
                        if "kg" in clean_string(str(r_data.get('unit', ''))): 
                            price_num = price_num / 2.2046
                        price_num = round(price_num, 1)
                        preview_price = f"${price_num} / LB"
                    else:
                        price_num = 0.0
                        preview_price = "無價錢"
                    
                expanded_keywords = set([c_raw])
                for key, aliases in STATIC_DICT.items():
                    if any(a in c_raw for a in aliases):
                        expanded_keywords.update(aliases)
                        expanded_keywords.add(key)
                
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
            st.success("🎉 太棒了！這份報價單裡的所有產品都已經被你 Mapping 或加入黑名單了，沒有任何遺漏！")
            st.session_state['inbox_data'] = None
        else:
            unique_unmapped = {item["報價單原文"]: item for item in unmapped_items}.values()
            st.session_state['inbox_data'] = list(unique_unmapped)
            st.session_state['radar_sup'] = radar_sup
            
    if st.session_state.get('inbox_data'):
        st.warning(f"📥 系統從 `{st.session_state['radar_sup']}` 的報價單中，發現了 **{len(st.session_state['inbox_data'])}** 個未追蹤的產品！")
        
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
        inbox_df = inbox_df[["✔️ 寫入 Mapping", "報價單原文", "對應母表產品 (AI建議)", "✏️ 手動新價(LB)", "👀 系統試抓價錢"]]
        
        edited_inbox = st.data_editor(
            inbox_df,
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
            loading_ph5 = st.empty()
            loading_ph5.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            
            gc, sh, _ = get_google_connection()
            map_ws = sh.worksheet('Mapping')
            
            map_adds = []
            updates_by_sheet = {}
            formats_by_sheet = {}
            history_records = []
            
            hk_tz = pytz.timezone('Asia/Hong_Kong')
            sys_today = datetime.now(hk_tz).strftime("%Y-%m-%d %H:%M:%S")
            quote_date_str = st.session_state.get('radar_date_str', sys_today.split()[0])
            
            for idx, row in edited_inbox.iterrows():
                if row["✔️ 寫入 Mapping"]:
                    raw_name = row["報價單原文"]
                    selected_sku_str = row["對應母表產品 (AI建議)"]
                    manual_price = row["✏️ 手動新價(LB)"]
                    
                    if "請選擇" in selected_sku_str:
                        st.error(f"❌ 產品 `{raw_name}` 已打勾，但沒有指定對應的母表產品！")
                        loading_ph5.empty()
                        st.stop()
                        
                    match = re.search(r'\[(.*?)\]', selected_sku_str)
                    if match:
                        pure_sku = match.group(1)
                        map_adds.append([st.session_state['radar_sup'], raw_name, pure_sku])
                        
                        if pd.notna(manual_price) and float(manual_price) > 0:
                            val_lb = float(manual_price)
                            val_kg = round(val_lb * 2.2046, 1)
                            
                            target_sn = None
                            target_row_idx = -1
                            for sn, vals in cat_data.items():
                                if not vals: continue
                                for r_idx, r in enumerate(vals):
                                    if r_idx < 2 or not r: continue
                                    if str(r[0]).strip() == pure_sku:
                                        target_sn = sn
                                        target_row_idx = r_idx + 1
                                        break
                                if target_sn: break
                                
                            if target_sn:
                                lb_col, kg_col = find_price_columns(cat_data[target_sn], st.session_state['radar_sup'], HEADER_MAP)
                                bg_color = color(1.0, 0.95, 0.6) 
                                fmt = cellFormat(backgroundColor=bg_color)
                                
                                if lb_col != -1:
                                    cell_a1 = gspread.utils.rowcol_to_a1(target_row_idx, lb_col)
                                    updates_by_sheet.setdefault(target_sn, []).append({'range': cell_a1, 'values': [[val_lb]]})
                                    formats_by_sheet.setdefault(target_sn, []).append((cell_a1, fmt))
                                if kg_col != -1:
                                    cell_a1 = gspread.utils.rowcol_to_a1(target_row_idx, kg_col)
                                    updates_by_sheet.setdefault(target_sn, []).append({'range': cell_a1, 'values': [[val_kg]]})
                                    formats_by_sheet.setdefault(target_sn, []).append((cell_a1, fmt))
                                    
                                history_records.append([sys_today, quote_date_str, st.session_state['radar_sup'], pure_sku, raw_name, val_lb, val_kg])
            
            if map_adds: 
                map_ws.append_rows(map_adds)
            if updates_by_sheet:
                for sn in updates_by_sheet:
                    target_ws = sh.worksheet(sn)
                    target_ws.batch_update(updates_by_sheet[sn])
                    if sn in formats_by_sheet and formats_by_sheet[sn]:
                        format_cell_ranges(target_ws, formats_by_sheet[sn])
            if history_records:
                sh.worksheet('History_Log').append_rows(history_records)
                
            if map_adds or updates_by_sheet:
                fetch_all_google_data.clear()
                loading_ph5.empty()
                st.balloons()
                st.success(f"🎉 成功新增了 {len(map_adds)} 筆 Mapping！")
                st.session_state['inbox_data'] = None
                time.sleep(2)
                st.rerun()
            else:
                loading_ph5.empty()
                st.warning("⚠️ 沒有勾選任何項目寫入，或母表中無價錢欄位可更新。")

    st.markdown("---")
    st.markdown("### 🎯 Phase 4: 價格錨點異常偵測 (AI 自動糾錯)")
    st.write("利用同行報價作為基準，如果某供應商的價錢偏離同行平均超過 **15%**，系統將自動列出，讓你檢查是否因為錯綁了不同等級的產品。你可以選擇 **修正 (覆蓋)** 或直接 **刪除該 Mapping**。")
    
    if st.button("🔍 掃描全庫價格異常", use_container_width=True):
        loading_ph6 = st.empty()
        loading_ph6.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
        gc, sh, _ = get_google_connection()
        try:
            mapping_ws = sh.worksheet('Mapping')
            mapping_data_raw = mapping_ws.get_all_records()
        except:
            mapping_data_raw = []
            
        # 💡 修復: 記錄每筆 Mapping 的絕對行數，作為隱形追蹤標籤
        map_lookup = {}
        for idx, r in enumerate(mapping_data_raw):
            excel_row = idx + 2 # Google Sheet 的資料從第 2 行開始
            sup = str(r.get('供應商','')).strip()
            sku = str(r.get('對應SKU','')).strip()
            raw = str(r.get('供應商原文','')).strip()
            if sup and sku and raw:
                map_lookup.setdefault((sup, sku), []).append({'raw': raw, 'row': excel_row})
                
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
                        if nums and float(nums[0]) > 0 and "sold out" not in p_str.lower():
                            prices[sup] = float(nums[0])
                            
                if len(prices) >= 2:
                    avg_p = sum(prices.values()) / len(prices)
                    for sup, p in prices.items():
                        diff_pct = (p - avg_p) / avg_p
                        if abs(diff_pct) >= 0.15: 
                            status = f"🔴 貴 {diff_pct*100:.1f}%" if diff_pct > 0 else f"🔵 平 {abs(diff_pct)*100:.1f}%"
                            raw_infos = map_lookup.get((sup, sku), [{'raw': "未知(未綁定或手動填入)", 'row': -1}])
                            
                            for info in raw_infos:
                                if info['row'] != -1:
                                    anomalies.append({
                                        "🗑️ 刪除此 Mapping": False,
                                        "✔️ 修正": False,
                                        "供應商": sup,
                                        "報價單原文": info['raw'],
                                        "原綁定 SKU": f"[{sku}] {std_name}",
                                        "該行平均價": avg_p,
                                        "異常價錢": p,
                                        "系統判定": status,
                                        "🔄 重新綁定至 (新SKU)": "請選擇對應產品...",
                                        "excel_row": info['row'] # 隱形標籤
                                    })
                                
        loading_ph6.empty()
        if anomalies:
            st.session_state['anomaly_data'] = sorted(anomalies, key=lambda x: abs(float(x['異常價錢']) - float(x['該行平均價'])), reverse=True)
        else:
            st.success("✅ 掃描完成！全庫沒有發現偏離超過 15% 的異常價錢，目前的 Mapping 應該相當準確！")
            st.session_state['anomaly_data'] = None

    if st.session_state.get('anomaly_data'):
        df_anom = pd.DataFrame(st.session_state['anomaly_data'])
        df_anom["該行平均價"] = df_anom["該行平均價"].apply(lambda x: f"${x:.1f}")
        df_anom["異常價錢"] = df_anom["異常價錢"].apply(lambda x: f"${x:.1f}")
        
        # 💡 將整個 DataFrame 傳入，利用 column_config 隱藏 excel_row 欄位
        edited_anom = st.data_editor(
            df_anom,
            column_config={
                "🗑️ 刪除此 Mapping": st.column_config.CheckboxColumn("🗑️ 刪除此 Mapping", help="勾選後將直接從資料庫移除此紀錄"),
                "✔️ 修正": st.column_config.CheckboxColumn("✔️ 修正"),
                "供應商": st.column_config.TextColumn(disabled=True),
                "報價單原文": st.column_config.TextColumn(disabled=True),
                "原綁定 SKU": st.column_config.TextColumn(disabled=True),
                "該行平均價": st.column_config.TextColumn(disabled=True),
                "異常價錢": st.column_config.TextColumn(disabled=True),
                "系統判定": st.column_config.TextColumn(disabled=True),
                "🔄 重新綁定至 (新SKU)": st.column_config.SelectboxColumn("🔄 重新綁定至 (新SKU)", options=all_db_options),
                "excel_row": None # 完美隱藏追蹤標籤
            },
            use_container_width=True, hide_index=True, height=400
        )
        
        if st.button("💾 執行操作 (刪除 或 修正)", type="primary", key="fix_anom"):
            loading_ph7 = st.empty()
            loading_ph7.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection()
            mapping_ws = sh.worksheet('Mapping')
            
            cells_to_update = []
            rows_to_delete = []
            
            for idx, row in edited_anom.iterrows():
                is_del = row.get("🗑️ 刪除此 Mapping", False)
                is_fix = row.get("✔️ 修正", False)
                target_row = row.get("excel_row", -1)
                
                if (is_del or is_fix) and target_row != -1:
                    if is_del:
                        rows_to_delete.append(int(target_row))
                    else:
                        new_sku_full = row.get("🔄 重新綁定至 (新SKU)", "")
                        if "請選擇" not in new_sku_full:
                            match = re.search(r'\[(.*?)\]', new_sku_full)
                            if match:
                                pure_sku = match.group(1)
                                cell_a1 = gspread.utils.rowcol_to_a1(int(target_row), 3) # C欄是對應SKU
                                cells_to_update.append({'range': cell_a1, 'values': [[pure_sku]]})

            # 💡 由下往上刪除，絕對不會切錯行
            for r in sorted(list(set(rows_to_delete)), reverse=True):
                mapping_ws.delete_rows(r)
                
            if cells_to_update:
                mapping_ws.batch_update(cells_to_update)
                
            if rows_to_delete or cells_to_update:
                fetch_all_google_data.clear()
                loading_ph7.empty()
                st.balloons()
                st.success(f"🎉 成功刪除 {len(rows_to_delete)} 筆 / 修正 {len(cells_to_update)} 筆紀錄！")
                st.session_state['anomaly_data'] = None
                time.sleep(2.5)
                st.rerun()
            else:
                loading_ph7.empty()
                st.warning("⚠️ 沒有勾選任何操作項目。")

    st.markdown("---")
    st.markdown("### 🩺 Phase 1: Mapping 母表健康體檢")
    if st.button("🚀 立即執行全面體檢", use_container_width=True):
        loading_ph4 = st.empty()
        loading_ph4.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
        gc, sh, _ = get_google_connection()
        try:
            mapping_ws = sh.worksheet('Mapping')
            mapping_data_raw = mapping_ws.get_all_records()
        except Exception as e:
            mapping_data_raw = []
            
        valid_skus = set()
        for sn, vals in cat_data.items():
            if vals and len(vals) > 2:
                for r in vals[2:]:
                    if r and str(r[0]).strip():
                        valid_skus.add(str(r[0]).strip())
                        
        errors = []
        for idx, row in enumerate(mapping_data_raw):
            excel_row = idx + 2 
            sup = str(row.get('供應商', '')).strip()
            raw_name = str(row.get('供應商原文', '')).strip()
            sku = str(row.get('對應SKU', '')).strip()
            
            if not sup or not raw_name or not sku:
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "❌ 欄位空白"})
                continue
            if sku not in valid_skus:
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "👻 幽靈 SKU"})
            
            name_clean = raw_name.lower()
            if sku.startswith('1') and any(x in name_clean for x in ['豬', 'pork', '雞', 'chicken', '羊', 'lamp', 'lamb']):
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "🚨 類別衝突 (應為牛)"})
            elif sku.startswith('2') and any(x in name_clean for x in ['牛', 'beef', '雞', 'chicken', '羊', 'lamp', 'lamb']):
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "🚨 類別衝突 (應為豬)"})
            elif sku.startswith('3') and any(x in name_clean for x in ['牛', 'beef', '豬', 'pork', '羊', 'lamp', 'lamb']):
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "🚨 類別衝突 (應為雞)"})
            elif sku.startswith('4') and any(x in name_clean for x in ['牛', 'beef', '豬', 'pork', '雞', 'chicken']):
                errors.append({"🗑️ 刪除此行": False, "行數": excel_row, "供應商": sup, "產品原文": raw_name, "SKU": sku, "錯誤類型": "🚨 類別衝突 (應為羊)"})
        
        loading_ph4.empty()
        if errors:
            st.warning(f"⚠️ 體檢完成！發現 **{len(errors)}** 個問題。你可以勾選直接刪除，或回 Google Excel 手動修正。")
            st.session_state['health_errors'] = errors
        else:
            st.balloons(); st.success("✅ 體檢完美通過！")
            st.session_state['health_errors'] = None

    if st.session_state.get('health_errors'):
        df_err = pd.DataFrame(st.session_state['health_errors'])
        edited_err = st.data_editor(
            df_err,
            column_config={
                "🗑️ 刪除此行": st.column_config.CheckboxColumn("🗑️ 刪除此行"),
                "行數": st.column_config.NumberColumn(disabled=True),
                "供應商": st.column_config.TextColumn(disabled=True),
                "產品原文": st.column_config.TextColumn(disabled=True),
                "SKU": st.column_config.TextColumn(disabled=True),
                "錯誤類型": st.column_config.TextColumn(disabled=True)
            },
            use_container_width=True, hide_index=True
        )
        if st.button("💾 刪除勾選的錯誤紀錄", type="primary", key="del_err"):
            loading_ph8 = st.empty()
            loading_ph8.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            gc, sh, _ = get_google_connection()
            mapping_ws = sh.worksheet('Mapping')
            
            rows_to_del = []
            for idx, row in edited_err.iterrows():
                if row["🗑️ 刪除此行"]:
                    rows_to_del.append(int(row["行數"]))
                    
            for r in sorted(list(set(rows_to_del)), reverse=True):
                mapping_ws.delete_rows(r)
                
            if rows_to_del:
                fetch_all_google_data.clear()
                loading_ph8.empty()
                st.success(f"🎉 成功刪除 {len(rows_to_del)} 筆錯誤紀錄！")
                st.session_state['health_errors'] = None
                time.sleep(1.5)
                st.rerun()
            else:
                loading_ph8.empty()
                st.warning("⚠️ 沒有勾選任何刪除項目。")

    st.markdown("---")
    st.markdown("### 🚯 Phase 2: 黑名單 (Ignore List) 快速管理")
    with st.form("add_ignore_form"):
        col_ig1, col_ig2 = st.columns([1, 2])
        with col_ig1: ig_sup = st.selectbox("選擇供應商", ACTIVE_SUPPLIERS)
        with col_ig2: ig_val = st.text_input("輸入要忽略的產品原文 (如: 膠袋, 運費)")
        submit_ig = st.form_submit_button("➕ 快速加入單筆黑名單", use_container_width=True)
        
        if submit_ig and ig_val:
            gc, sh, _ = get_google_connection()
            sh.worksheet('Ignore_List').append_row([ig_sup, ig_val, datetime.now(pytz.timezone('Asia/Hong_Kong')).strftime("%Y-%m-%d %H:%M:%S")])
            fetch_all_google_data.clear()
            st.success(f"✅ 已加入黑名單！")
            time.sleep(1.5)
            st.rerun()
