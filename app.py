import streamlit as st
import gspread
from gspread_formatting import *
import pandas as pd
import re
import io
import random
import time
from datetime import datetime, timedelta
import pytz
import pdfplumber

from modules.google_db import (
    get_google_connection, get_drive_connection, fetch_all_google_data,
    clean_string, SUPPLIERS, DRIVE_FOLDER_ID
)
from modules.anchor_engine import scan_pdf_with_anchors
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

st.set_page_config(page_title="更新報價及搜尋系統 - Francis", layout="wide", page_icon="📊")

# ==========================================
# 🎨 修復副作用的精準 CSS
# ==========================================
hide_st_style = """
<style>
    [data-testid="stHeader"] { background-color: transparent !important; }
    [data-testid="stActionElements"] { display: none !important; }
    footer { visibility: hidden; display: none !important; }
    [data-testid="stStatusWidget"] { visibility: hidden; display: none !important; }

    :root, .stApp, [data-testid="stAppViewContainer"] {
        --background-color: #FFFFFF !important;
        --secondary-background-color: #F8F9FA !important;
        --text-color: #111111 !important;
        background-color: #FFFFFF !important; color: #111111 !important;
    }
    [data-testid="stSidebar"], .stSidebar {
        background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0 !important;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp span, .stApp label {
        color: #111111 !important;
    }
    div[data-testid="stForm"] {
        background-color: #FFFFFF !important; border: 1px solid #CCCCCC !important;
        border-radius: 12px !important; padding: 30px !important; box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
    }
    .stApp input, .stApp select, [data-baseweb="select"] {
        background-color: #F9F9F9 !important; color: #111111 !important; border-color: #CCCCCC !important;
    }
    .stButton > button, div[data-testid="stForm"] button {
        background-color: #1F77B4 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 6px !important; font-weight: bold !important; box-shadow: 0 2px 5px rgba(31, 119, 180, 0.3) !important;
    }
    .stButton > button:hover, div[data-testid="stForm"] button:hover { 
        background-color: #155B8C !important; color: #FFFFFF !important;
    }
    /* 全選按鈕的特殊樣式 */
    button[title="View fullscreen"] { display: none !important; }

    .product-card {
        padding: 12px 15px !important; border: 1px solid #DEDEDE !important; 
        border-radius: 8px !important; margin-bottom: 8px !important; background-color: #FAFAFA !important;
    }
    .product-card-header {
        display: flex !important; justify-content: space-between !important; align-items: center !important;
        border-bottom: 1px dashed #CCCCCC !important; padding-bottom: 6px !important; margin-bottom: 6px !important;
    }
    .product-card-title { font-size: 16px !important; font-weight: 900 !important; color: #111111 !important; margin: 0 !important; }
    .product-card-body { font-size: 12px !important; color: #666666 !important; line-height: 1.6 !important; }
    .product-card-price-row {
        display: flex !important; justify-content: space-between !important; align-items: center !important; margin-top: 6px !important;
    }
    .product-card-price { color: #D9534F !important; font-size: 18px !important; font-weight: bold !important; }
    .badge { 
        padding: 3px 8px !important; border-radius: 4px !important; font-size: 11px !important; font-weight: bold !important; 
        background-color: #E6F7FF !important; color: #0066CC !important; 
    }
    .badge-danger { background-color: #FFEEEE !important; color: #D9534F !important; }
    
    @keyframes wave-animation { 0%, 40%, 100% { transform: translateY(0); } 20% { transform: translateY(-12px); color: #1F77B4; } }
    .wave-text { font-size: 22px; font-weight: bold; text-align: center; padding: 40px; color: #555555; }
    .wave-text span { display: inline-block; animation: wave-animation 1.5s infinite; }
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

def get_wavy_loading_html():
    msgs = [["正","在","為","你","制","作"," 🍣","🌮","🍧","🍜","🥗"," 中..."], ["正","在","飼","養"," 🐂","🐖","🐓"," 中..."]]
    chars = random.choice(msgs)
    spans = "".join([f"<span style='animation-delay: {i*0.1}s'>{c}</span>" for i, c in enumerate(chars)])
    return f"<div class='wave-text'>{spans}</div>"

def check_password():
    if "login_success" not in st.session_state:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                st.markdown("<h2 style='text-align: center; margin-top:0; padding-top:0;'>更新報價及搜尋系統</h2><hr style='margin-top:0;'>", unsafe_allow_html=True)
                username = st.text_input("👤 使用者名稱", placeholder="你的名字 (例如: Francis)")
                password = st.text_input("🔑 密碼", type="password")
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("🚀 登入 / Enter", use_container_width=True)
                
                if submitted:
                    if not username.strip(): st.warning("⚠️ 請填寫使用者名稱！")
                    elif password == "Meat2026":
                        st.session_state["login_success"] = True
                        st.session_state["username"] = username.strip()
                        st.rerun()
                    else: st.error("❌ 密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password(): st.stop()

if 'preview_data' not in st.session_state: st.session_state['preview_data'] = None

ACTIVE_SUPPLIERS = sorted(list(set(SUPPLIERS + ["形澧"])))
HEADER_MAP = {
    "新興城": {"LB": "新興城 $/LB", "KG": "新興城 $/KG"}, "金山洋行": {"LB": "金山 ($/lb)", "KG": "金山 ($/KG)"},
    "廣隆": {"LB": "廣隆 $/LB", "KG": "廣隆 $/KG"}, "哲朗": {"LB": "哲朗 $/LB", "KG": "哲朗 $/KG"},
    "浩新": {"LB": "浩新 $/LB", "KG": "浩新 $/KG"}, "一峰行": {"LB": "一峰行 $/LB", "KG": "一峰行 $/KG"},
    "恆盛": {"LB": "恆盛 $/LB", "KG": "恆盛 $/KG"}, "萬安(遠東)": {"LB": "萬安 ($/lb)", "KG": "萬安 ($/kg)"}, "形澧": {"LB": "形澧 $/LB", "KG": "形澧 $/KG"} 
}
FILENAME_MAPPING = { "06-07-2026": "新興城", "FEB-2026": "廣隆", "29-Jun-2026": "金山洋行", "哲朗": "哲朗", "Price list": "浩新", "一峰行": "一峰行", "2026-06-22": "恆盛", "萬安": "萬安(遠東)", "形澧": "形澧" }

loading_ph = st.empty()
loading_ph.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
target_dict, cat_data, hist_vals, global_origins = fetch_all_google_data()
loading_ph.empty()

with st.sidebar:
    st.markdown(f"### 👋 歡迎回來, **{st.session_state.get('username', 'User')}**!")
    st.markdown("---")
    if len(hist_vals) > 1: st.metric(label="母表追蹤產品數", value=sum(len(v)-2 for v in cat_data.values() if v))
    st.markdown("### 各供應商最後報價")
    if len(hist_vals) > 1:
        latest_dates = {}
        for row in hist_vals[1:]:
            if len(row) >= 6:
                if len(row) >= 7 and re.match(r'\d{4}-\d{2}-\d{2}', row[1]): quote_date = row[1]; sup = row[2]
                else: quote_date = row[0].split()[0]; sup = row[1]
                if sup in ACTIVE_SUPPLIERS: latest_dates[sup] = quote_date
        for sup in ACTIVE_SUPPLIERS:
            date_str = latest_dates.get(sup, "尚未更新")
            if date_str == "尚未更新": st.warning(f"**{sup}** : {date_str}")
            else: st.success(f"**{sup}** : {date_str}")
    st.caption("版本號: v11.6 (全選按鈕 & 一鍵斷貨版)")

tab1, tab2 = st.tabs(["一鍵更新報價", "搜尋"])

# ----------------------------------------------------
# 📌 分頁一：一鍵更新報價 (加入一鍵斷貨 & 全選按鈕)
# ----------------------------------------------------
with tab1:
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
                        
                        is_correct = (sku_db.startswith('1') and sheet_name == 'Beef') or (sku_db.startswith('2') and sheet_name == 'Pork') or (sku_db.startswith('3') and sheet_name == 'Chicken') or (sku_db.startswith('4') and sheet_name == 'Lamp')
                        if not is_correct: continue
                        
                        old_price_lb = None
                        if lb_col != -1 and lb_col - 1 < len(r):
                            old_val = str(r[lb_col - 1]).strip()
                            nums = re.findall(r'\d+\.?\d*', old_val)
                            if nums and float(nums[0]) > 0 and "sold out" not in old_val.lower(): 
                                old_price_lb = float(nums[0])
                        
                        # 💡 正常找到的產品
                        if sku_db in extracted_items:
                            data = extracted_items[sku_db]
                            raw_price = data['raw_price']; unit = data['guessed_unit']
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

                            all_preview.append({
                                "✔️ 寫入": not is_anomaly and not is_sold_out_detected,
                                "🛑 斷貨": is_sold_out_detected, # 新增斷貨快捷鍵
                                "SKU": sku_db, "產品原文": data['raw_name'],
                                "舊價(LB)": f"${old_price_lb}" if old_price_lb else "空",
                                "✏️ 手動新價(LB)": data['price_lb'] if not is_sold_out_detected else 0.0,
                                "變動狀態": status, "差額": delta_str, 
                                "追蹤行蹤": data['matched_line'], "target_row": row_idx + 1, "lb_col": lb_col, "kg_col": kg_col, "sheet_name": sheet_name, "sort_key": sort_key
                            })
                            
                        # 💡 疑似斷貨：母表有紀錄，但新 PDF 找不到
                        elif old_price_lb is not None:
                            all_preview.append({
                                "✔️ 寫入": False, # 預設不勾選防呆
                                "🛑 斷貨": True,  # 預設幫你把「斷貨」打勾！如果你要寫入，只需勾前面的「寫入」即可
                                "SKU": sku_db, "產品原文": "⚠️ 報價單中找不到此產品",
                                "舊價(LB)": f"${old_price_lb}",
                                "✏️ 手動新價(LB)": 0.0,
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
            
            # 💡 新增：全選 / 取消全選 按鈕
            st.info("💡 提示：請先使用【全選 / 取消全選】設定好大範圍，再去單獨微調價錢，以免重置你剛打好的數字。")
            col_btn1, col_btn2, _ = st.columns([1, 1, 3])
            with col_btn1:
                if st.button("☑️ 全部勾選 (寫入)"):
                    for item in st.session_state['preview_data']: item["✔️ 寫入"] = True
                    st.rerun()
            with col_btn2:
                if st.button("☐ 全部取消勾選"):
                    for item in st.session_state['preview_data']: item["✔️ 寫入"] = False
                    st.rerun()
            
            # 建立可編輯表格 (加入 🛑 斷貨 列)
            edited_df = st.data_editor(
                df_preview,
                column_config={
                    "✔️ 寫入": st.column_config.CheckboxColumn("✔️ 寫入 (勾選)", help="取消勾選則不更新此產品"),
                    "🛑 斷貨": st.column_config.CheckboxColumn("🛑 斷貨", help="勾選後，系統將強制以 Sold out 寫入，無視右方填寫的價錢"),
                    "✏️ 手動新價(LB)": st.column_config.NumberColumn("✏️ 手動新價(LB)", format="%.1f", help="若價格有誤，可直接點擊修改"),
                    "target_row": None, "lb_col": None, "kg_col": None, "sheet_name": None, "sort_key": None
                },
                disabled=["SKU", "產品原文", "舊價(LB)", "變動狀態", "差額", "追蹤行蹤"],
                use_container_width=True, hide_index=True, height=500
            )
            
            if st.button("💾 確認無誤，將『已勾選』資料寫入雲端母表", type="primary"):
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
                    if not row["✔️ 寫入"]: continue # 略過未勾選的
                    update_count += 1
                    sn = row["sheet_name"]
                    if sn not in updates_by_sheet: updates_by_sheet[sn] = []; formats_by_sheet[sn] = []
                    
                    bg_color = color(1.0, 0.6, 0.6) if "🚨" in row["變動狀態"] else color(0.8, 1.0, 0.8) if "📉" in row["變動狀態"] else color(1.0, 0.8, 0.8) if "📈" in row["變動狀態"] else color(0.9, 0.9, 0.9) if "🛑" in row["變動狀態"] else color(1.0, 0.95, 0.6) 
                    fmt = cellFormat(backgroundColor=bg_color)
                    
                    # 💡 判斷斷貨勾選邏輯，免除手動輸入0的痛苦
                    if row["🛑 斷貨"]:
                        val_lb = "Sold out"
                        val_kg = "Sold out"
                    else:
                        manual_price = row["✏️ 手動新價(LB)"]
                        if pd.isna(manual_price) or float(manual_price) <= 0.0:
                            val_lb = "Sold out"
                            val_kg = "Sold out"
                        else:
                            val_lb = float(manual_price)
                            val_kg = round(val_lb * 2.2046, 1)
                    
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
                    st.success(f"🎉 成功寫入 {update_count} 筆資料至 Google 母表！")
                    st.session_state['preview_data'] = None
                    time.sleep(1.5)
                    st.rerun()
                else:
                    loading_ph3.empty()
                    st.warning("⚠️ 沒有勾選任何資料寫入。")

# ----------------------------------------------------
# 📌 分頁二：搜尋 
# ----------------------------------------------------
with tab2:
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
        
        STATIC_DICT = {
            "雞翼": ["中亦", "中翼", "雞翼", "雞中翼", "翼"], "牛上腦": ["牛上腦", "肩胛肉眼", "chuckroll"],
            "雞比": ["雞比", "雞脾", "餅比", "餅脾", "雞腿", "脾肉", "比肉", "全脾", "雞下脾"],
            "牛小排": ["牛小排", "牛仔骨", "shortrib", "牛排"], "金錢展": ["金展", "金錢展", "金錢𦟌"], "肉眼": ["肉眼", "ribeye"]
        }
        for key, aliases in STATIC_DICT.items():
            if key in q_clean or q_clean in key: search_aliases.update(aliases)
                
        for sn, all_vals in cat_data.items():
            if category_filter != "全部" and category_filter.split(" ")[0] != sn: continue 
            if not all_vals: continue
            for r in all_vals[2:]:
                if not r: continue
                sku = str(r[0]).strip()
                std_name = " ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                if q_clean in clean_string(sku) or q_clean in clean_string(std_name):
                    for sup, targets in target_dict.items():
                        for t in targets:
                            if t['sku'] == sku: search_aliases.add(clean_string(t['name']))
                            
        st.info(f"🧠 智能搜尋擴展：`{', '.join(search_aliases)}` (範圍: {category_filter})")

        sub_tab1, sub_tab2 = st.tabs(["📂 搜尋已建立內容", "☁️ 所有供應商中尋找"])

        with sub_tab1:
            search_ph1 = st.empty()
            search_ph1.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            
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
                if category_filter != "全部" and category_filter.split(" ")[0] != sn: continue
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
                    if selected_origins and origin not in selected_origins: continue
                        
                    std_name = " | ".join([str(r[i]).strip() for i in range(1, min(6, len(r))) if str(r[i]).strip()])
                    clean_sku = clean_string(sku); clean_std = clean_string(std_name)
                    
                    if any(alias in clean_sku or alias in clean_std for alias in search_aliases):
                        for sup_name, cols in sup_cols.items():
                            lb_col_idx = cols["LB"]
                            if lb_col_idx != -1 and lb_col_idx < len(r):
                                p_val_str = str(r[lb_col_idx]).strip()
                                nums = re.findall(r'\d+\.?\d*', p_val_str)
                                
                                is_sold_out_now = "sold out" in p_val_str.lower() or not nums
                                hist_alert = ""
                                price_lb_numeric = 99999.9 
                                display_price = "Sold out"
                                
                                if sku in history_prices:
                                    past_records = sorted(history_prices[sku], key=lambda x: x['date'], reverse=True)
                                    valid_past_prices = [x['price'] for x in past_records if x['price'] > 0]
                                    
                                    if is_sold_out_now and len(valid_past_prices) > 0:
                                        hist_alert = "🔥 曾經熱賣，現已斷貨！(上次報價有售)"
                                    elif not is_sold_out_now:
                                        display_price = round(float(nums[0]), 1)
                                        price_lb_numeric = display_price
                                        p30 = [x for x in valid_past_prices if past_records[valid_past_prices.index(x)]['date'] >= d30]
                                        p60 = [x for x in valid_past_prices if past_records[valid_past_prices.index(x)]['date'] >= d60]
                                        p90 = [x for x in valid_past_prices if past_records[valid_past_prices.index(x)]['date'] >= d90]
                                        if p90 and display_price <= min(p90): hist_alert = "🔥🔥🔥 90天新低"
                                        elif p60 and display_price <= min(p60): hist_alert = "🔥🔥 60天新低"
                                        elif p30 and display_price <= min(p30): hist_alert = "🔥 30天新低"
                                
                                if not is_sold_out_now and not hist_alert:
                                    display_price = round(float(nums[0]), 1)
                                    price_lb_numeric = display_price
                                
                                if display_price != "Sold out" or hist_alert:
                                    compare_results.append({
                                        "SKU": sku, "產地": origin, "標準品名": std_name, "供應商": sup_name,
                                        "每磅均價 ($/LB)": display_price, "sort_price": price_lb_numeric,
                                        "歷史低價提醒": hist_alert
                                    })
            search_ph1.empty()
                                    
            if compare_results:
                df_compare = pd.DataFrame(compare_results).sort_values(by="sort_price")
                cheapest = df_compare.iloc[0]
                
                if cheapest['每磅均價 ($/LB)'] != "Sold out":
                    st.markdown(f"""
                    <div style='background-color:#e8f5e9 !important; padding: 15px; border-radius: 8px; border-left: 5px solid #4caf50; margin-bottom: 15px;'>
                        <span style='font-size:12px; color:#2e7d32; font-weight:bold;'>🏆 最平首選推薦</span>
                        <h3 style='margin:5px 0 0 0; color:#1b5e20; font-size:18px;'>【{cheapest['供應商']}】 {cheapest['標準品名']}</h3>
                        <h2 style='margin:5px 0 0 0; color:#2e7d32; font-size:24px; font-weight:900;'>${cheapest['每磅均價 ($/LB)']:.1f} <span style="font-size:14px; font-weight:normal;">/ LB</span></h2>
                    </div>
                    """, unsafe_allow_html=True)
                
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
                    
                    st.markdown(f"""
                    <div class="product-card">
                        <div class="product-card-header">
                            <span class="product-card-title">【{row['供應商']}】 {row['標準品名']}</span>
                            {f'<span class="badge" style="background-color: #E0E0E0 !important; color: #333333 !important;">{diff_text}</span>' if diff_text else ''}
                        </div>
                        <div class="product-card-body">
                            產地: <span style="color:#0066cc; font-weight:bold;">{row['產地']}</span> | SKU: {row['SKU']}
                        </div>
                        <div class="product-card-price-row">
                            <span class="product-card-price" style="color: {price_color} !important;">{price_display}</span>
                            {alert_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else: 
                st.warning("🔍 沒找到符合條件的報價。")

        with sub_tab2:
            st.info("💡 提示：雲端盲掃模式因沒有預先設定的分類，搜尋將會比對所有找到的內容。")
            # 雲端搜尋維持正常運作...
