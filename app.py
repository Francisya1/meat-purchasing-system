import streamlit as st
import gspread
from gspread_formatting import *
import pandas as pd
import re
import io
import random
from datetime import datetime, timedelta
import pytz
import pdfplumber

from modules.google_db import (
    get_google_connection, get_drive_connection, fetch_all_google_data,
    clean_string, SUPPLIERS, DRIVE_FOLDER_ID
)
from modules.anchor_engine import scan_pdf_with_anchors
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# 💡 網頁設定
st.set_page_config(page_title="更新報價及搜尋系統 - Francis", layout="wide", page_icon="📊")

# ==========================================
# 🎨 完美色彩校正與 WAVE 動畫 CSS
# ==========================================
hide_st_style = """
<style>
    /* 1. 隱藏 Streamlit 預設工具列 */
    #MainMenu {visibility: hidden; display: none !important;}
    footer {visibility: hidden; display: none !important;}
    header {visibility: hidden; display: none !important;}
    [data-testid="stStatusWidget"] {visibility: hidden; display: none !important;}
    div[data-testid="stDecoration"] {visibility: hidden; display: none !important;}

    /* 2. 強制白底黑字 */
    :root, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        --background-color: #FFFFFF !important;
        --secondary-background-color: #F8F9FA !important;
        --text-color: #111111 !important;
        background-color: #FFFFFF !important;
        color: #111111 !important;
    }

    [data-testid="stSidebar"], .stSidebar {
        background-color: #F8F9FA !important;
        border-right: 1px solid #E0E0E0 !important;
    }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp span, .stApp label {
        color: #111111 !important;
    }
    
    /* 修復 Copy 按鈕與所有圖示全黑問題 */
    button svg, div[data-testid="stCodeBlock"] svg {
        fill: #666666 !important;
        stroke: #666666 !important;
        color: #666666 !important;
    }
    button:hover svg {
        fill: #111111 !important;
        stroke: #111111 !important;
    }

    /* 3. 完美登入框與表單美化 */
    div[data-testid="stForm"] {
        background-color: #FFFFFF !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 12px !important;
        padding: 30px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
    }
    .stApp input, .stApp select {
        background-color: #F9F9F9 !important;
        color: #111111 !important;
        border-color: #CCCCCC !important;
    }

    /* 4. 按鈕美化 */
    .stApp button {
        background-color: #1F77B4 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: bold !important;
        box-shadow: 0 2px 5px rgba(31, 119, 180, 0.3) !important;
    }
    .stApp button * { color: #FFFFFF !important; }
    .stApp button:hover { background-color: #155B8C !important; }

    /* 5. 重新排序的商品卡片設計 */
    .product-card {
        padding: 12px 15px !important; 
        border: 1px solid #DEDEDE !important; 
        border-radius: 8px !important; 
        margin-bottom: 8px !important; 
        background-color: #FAFAFA !important;
    }
    .product-card-header {
        display: flex !important; justify-content: space-between !important; align-items: center !important;
        border-bottom: 1px dashed #CCCCCC !important; padding-bottom: 6px !important; margin-bottom: 6px !important;
    }
    .product-card-title {
        font-size: 16px !important; font-weight: 900 !important; color: #111111 !important; margin: 0 !important;
    }
    .product-card-body {
        font-size: 12px !important; color: #666666 !important; line-height: 1.6 !important;
    }
    .product-card-price-row {
        display: flex !important; justify-content: space-between !important; align-items: center !important; margin-top: 6px !important;
    }
    .product-card-price {
        color: #D9534F !important; font-size: 18px !important; font-weight: bold !important;
    }
    .badge { 
        padding: 3px 8px !important; border-radius: 4px !important; font-size: 11px !important; font-weight: bold !important; 
        background-color: #E6F7FF !important; color: #0066CC !important; 
    }

    /* 6. 趣味 WAVE 波浪動畫引擎 */
    @keyframes wave-animation {
        0%, 40%, 100% { transform: translateY(0); }
        20% { transform: translateY(-12px); color: #1F77B4; }
    }
    .wave-text {
        font-size: 22px; font-weight: bold; text-align: center; padding: 40px; color: #555555;
    }
    .wave-text span {
        display: inline-block; animation: wave-animation 1.5s infinite;
    }
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# ==========================================
# 🌟 WAVE 動態文字產生器
# ==========================================
def get_wavy_loading_html():
    msgs = [
        ["正", "在", "為", "你", "制", "作", " 🍣", "🌮", "🍧", "🍜", "🥗", " 中..."],
        ["正", "在", "飼", "養", " 🐂", "🐖", "🐓", " 中..."],
        ["大", "廚", "正", "在", "火", "速", "切", "肉", " 🔪", "🥩", "🏃‍♂️", " 中..."]
    ]
    chars = random.choice(msgs)
    spans = "".join([f"<span style='animation-delay: {i*0.1}s'>{c}</span>" for i, c in enumerate(chars)])
    return f"<div class='wave-text'>{spans}</div>"

# ==========================================
# 🔒 企業登入牆 (完美整合至格仔內)
# ==========================================
def check_password():
    if "login_success" not in st.session_state:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            # 💡 標題直接寫進 form 裡面，確保完美包覆在格仔中
            with st.form("login_form"):
                st.markdown("<h2 style='text-align: center; margin-top:0; padding-top:0;'>更新報價及搜尋系統</h2>", unsafe_allow_html=True)
                st.markdown("<hr style='margin-top:0;'>", unsafe_allow_html=True)
                
                username = st.text_input("👤 使用者名稱", placeholder="你的名字 (例如: Francis)")
                password = st.text_input("🔑 密碼", type="password")
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("🚀 登入 / Enter", use_container_width=True)
                
                if submitted:
                    if not username.strip():
                        st.warning("⚠️ 請填寫使用者名稱！")
                    elif password == "Meat2026":
                        st.session_state["login_success"] = True
                        st.session_state["username"] = username.strip()
                        st.rerun()
                    else:
                        st.error("❌ 密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 👇 系統核心變數與資料載入
# ==========================================
if 'preview_data' not in st.session_state: st.session_state['preview_data'] = None
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

# 母表載入時也使用 WAVE 動畫
loading_ph = st.empty()
loading_ph.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
target_dict, cat_data, hist_vals, global_origins = fetch_all_google_data()
loading_ph.empty() # 載入完成後自動清除動畫

with st.sidebar:
    st.markdown(f"### 👋 歡迎回來, **{st.session_state.get('username', 'User')}**!")
    st.markdown("---")
    if len(hist_vals) > 1:
        st.metric(label="母表追蹤產品數", value=sum(len(v)-2 for v in cat_data.values() if v))
    st.markdown("### 各供應商最後報價")
    if len(hist_vals) > 1:
        latest_dates = {}
        for row in hist_vals[1:]:
            if len(row) >= 6:
                if len(row) >= 7 and re.match(r'\d{4}-\d{2}-\d{2}', row[1]):
                    quote_date = row[1]; sup = row[2]
                else: quote_date = row[0].split()[0]; sup = row[1]
                if sup in ACTIVE_SUPPLIERS: latest_dates[sup] = quote_date
        for sup in ACTIVE_SUPPLIERS:
            date_str = latest_dates.get(sup, "尚未更新")
            if date_str == "尚未更新": st.warning(f"**{sup}** : {date_str}")
            else: st.success(f"**{sup}** : {date_str}")
    st.caption("版本號: v11.3 (波浪動畫 & 完美重排版)")

# ==========================================
# 📊 介面佈局
# ==========================================
tab1, tab2 = st.tabs(["一鍵更新報價", "搜尋"])

# ----------------------------------------------------
# 📌 分頁一：一鍵更新報價
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
        if uploaded_file is None:
            st.error("⚠️ 請先上傳 PDF 檔案！")
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
                
                loading_ph2.empty() # 載入完成，清空波浪動畫

    if st.session_state['preview_data'] is not None:
        df_preview = pd.DataFrame(st.session_state['preview_data'])
        if len(df_preview) > 0:
            st.success(f"🎉 **成功抓取 {len(df_preview)} 個產品！**")
            display_df = df_preview.drop(columns=['target_row', 'lb_col', 'kg_col', 'sheet_name', 'price_lb', 'price_kg', 'is_anomaly', 'sort_key'], errors='ignore')
            def highlight_anomaly(x):
                df_colors = pd.DataFrame('', index=x.index, columns=x.columns)
                for i in x.index:
                    status = str(x.loc[i, '變動狀態'])
                    if "🚨" in status: df_colors.loc[i, :] = 'background-color: #ffcccc; color: red;'
                    elif "🛑" in status: df_colors.loc[i, :] = 'background-color: #e6e6e6; color: #555;'
                    elif "➖" in status: df_colors.loc[i, :] = 'color: #999;'
                return df_colors
            st.dataframe(display_df.style.apply(highlight_anomaly, axis=None), height=400, use_container_width=True)
        
        all_cols_missing = all(item["lb_col"] == -1 and item["kg_col"] == -1 for item in st.session_state['preview_data']) if len(st.session_state['preview_data'])>0 else False
        if st.button("💾 確認無誤，寫入雲端母表", type="primary", disabled=all_cols_missing):
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
            
            loading_ph3.empty()
            st.balloons(); st.success("🎉 更新大成功！資料已同步至 Google 母表。"); st.session_state['preview_data'] = None; 


# ----------------------------------------------------
# 📌 分頁二：搜尋
# ----------------------------------------------------
with tab2:
    with st.form("search_form"):
        col_s1, col_s2 = st.columns([4, 1])
        with col_s1:
            search_query = st.text_input("🔍 輸入關鍵字 (如: 雞翼、牛上腦)：", placeholder="輸入產品關鍵字...")
        with col_s2:
            st.markdown("<br>", unsafe_allow_html=True)
            submit_search = st.form_submit_button("🔍 搜尋 / Enter", use_container_width=True)

    if submit_search and search_query:
        q_clean = clean_string(search_query)
        search_aliases = set([q_clean])
        
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
                            
        st.info(f"🧠 智能搜尋擴展：`{', '.join(search_aliases)}`")

        sub_tab1, sub_tab2 = st.tabs(["📂 搜尋已建立內容", "☁️ 所有供應商中尋找"])

        # === 📂 搜尋已建立內容 ===
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
                                    hist_alert = ""
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
            search_ph1.empty()
                                    
            if compare_results:
                df_compare = pd.DataFrame(compare_results).sort_values(by="每磅均價 ($/LB)")
                cheapest = df_compare.iloc[0]
                
                st.markdown(f"""
                <div style='background-color:#e8f5e9 !important; padding: 15px; border-radius: 8px; border-left: 5px solid #4caf50; margin-bottom: 15px;'>
                    <span style='font-size:12px; color:#2e7d32; font-weight:bold;'>🏆 最平首選推薦</span>
                    <h3 style='margin:5px 0 0 0; color:#1b5e20; font-size:18px;'>【{cheapest['供應商']}】 {cheapest['標準品名']}</h3>
                    <h2 style='margin:5px 0 0 0; color:#2e7d32; font-size:24px; font-weight:900;'>${cheapest['每磅均價 ($/LB)']:.1f} <span style="font-size:14px; font-weight:normal;">/ LB</span></h2>
                </div>
                """, unsafe_allow_html=True)
                
                # 💡 重新排序的商品卡片：[供應商] 品名 為大標題
                for _, row in df_compare.iterrows():
                    alert_html = f"<span class='badge'>{row['歷史低價提醒']}</span>" if row['歷史低價提醒'] else ""
                    diff = row['每磅均價 ($/LB)'] - cheapest['每磅均價 ($/LB)']
                    diff_text = f"貴 ${diff:.1f}" if diff > 0 else "最平"
                    
                    st.markdown(f"""
                    <div class="product-card">
                        <div class="product-card-header">
                            <span class="product-card-title">【{row['供應商']}】 {row['標準品名']}</span>
                            <span class="badge" style="background-color: #E0E0E0 !important; color: #333333 !important;">{diff_text}</span>
                        </div>
                        <div class="product-card-body">
                            產地: <span style="color:#0066cc; font-weight:bold;">{row['產地']}</span> | SKU: {row['SKU']}
                        </div>
                        <div class="product-card-price-row">
                            <span class="product-card-price">${row['每磅均價 ($/LB)']:.1f} / LB</span>
                            {alert_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else: 
                st.warning("🔍 沒找到符合條件的報價。")

        # === ☁️ 所有供應商中尋找 ===
        with sub_tab2:
            search_ph2 = st.empty()
            search_ph2.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
            try:
                drive_service = get_drive_connection()
                results = drive_service.files().list(
                    q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false", 
                    fields="files(id, name, createdTime)"
                ).execute()
                files = results.get('files', [])
                
                if not files: 
                    search_ph2.empty()
                    st.warning("資料夾內沒有 PDF。")
                else:
                    supplier_files = {}
                    for f in files:
                        fname = f['name']
                        sup = next((s for kw, s in FILENAME_MAPPING.items() if kw in fname), "未知供應商")
                        if sup not in supplier_files: supplier_files[sup] = []
                        supplier_files[sup].append(f)
                        
                    files_to_scan = []
                    for sup, flist in supplier_files.items():
                        flist.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
                        files_to_scan.append(flist[0]) 
                        
                    from modules.pdf_xray import parse_supplier_row, deep_decode_item
                    cloud_db = []
                    
                    for idx, file in enumerate(files_to_scan):
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
                    
                    search_ph2.empty()
                    
                    filtered_cloud = [item for item in cloud_db if any(alias in item["search_string"] for alias in search_aliases)]
                    if filtered_cloud:
                        df_cloud = pd.DataFrame(filtered_cloud).sort_values(by="換算價 ($/LB)")
                        cheapest_cloud = df_cloud.iloc[0]
                        
                        st.markdown(f"""
                        <div style='background-color:#e3f2fd !important; padding: 15px; border-radius: 8px; border-left: 5px solid #1976d2; margin-bottom: 15px;'>
                            <span style='font-size:12px; color:#1565c0; font-weight:bold;'>🏆 雲端未建檔最平首選</span>
                            <h3 style='margin:5px 0 0 0; color:#0d47a1; font-size:18px;'>【{cheapest_cloud['供應商']}】 {cheapest_cloud['品名(純)']}</h3>
                            <h2 style='margin:5px 0 0 0; color:#1565c0; font-size:24px; font-weight:900;'>${cheapest_cloud['換算價 ($/LB)']:.1f} <span style="font-size:14px; font-weight:normal;">/ LB</span></h2>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 💡 重新排序的商品卡片：[供應商] 品名(純) 為大標題
                        for _, row in df_cloud.iterrows():
                            diff = row['換算價 ($/LB)'] - cheapest_cloud['換算價 ($/LB)']
                            diff_text = f"貴 ${diff:.1f}" if diff > 0 else "最平"
                            st.markdown(f"""
                            <div class="product-card">
                                <div class="product-card-header">
                                    <span class="product-card-title">【{row['供應商']}】 {row['品名(純)']}</span>
                                    <span class="badge" style="background-color: #E0E0E0 !important; color: #333333 !important;">{diff_text}</span>
                                </div>
                                <div class="product-card-body">
                                    產地: <span style="color:#0066cc; font-weight:bold;">{row['產地']}</span> | 規格: {row['包裝規格']} | 品牌: {row['品牌']}<br>
                                    <span style="font-size:10px; color:#888888 !important;">來源檔: {row['來源檔案']}</span>
                                </div>
                                <div class="product-card-price-row">
                                    <span class="product-card-price">${row['換算價 ($/LB)']:.1f} / LB</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    else: st.warning(f"ℹ️ 在雲端未建檔的情報中，沒找到與 `{search_query}` 相關的產品。")
            except Exception as e: 
                search_ph2.empty()
                st.error(f"雲端解剖失敗：{e}")
