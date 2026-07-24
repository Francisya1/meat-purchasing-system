import streamlit as st
import streamlit.components.v1 as components
import random
import time
from datetime import datetime
import re

st.set_page_config(page_title="更新報價及搜尋系統 - Francis", layout="wide", page_icon="📊")

# ==========================================
# 🗄️ 全域系統抽屜 (Session State) 初始化
# ==========================================
if 'login_success' not in st.session_state: st.session_state['login_success'] = False
if 'username' not in st.session_state: st.session_state['username'] = "User"
if 'preview_data' not in st.session_state: st.session_state['preview_data'] = None
if 'current_supplier' not in st.session_state: st.session_state['current_supplier'] = None
if 'current_quote_date' not in st.session_state: st.session_state['current_quote_date'] = None
if 'bulk_matches' not in st.session_state: st.session_state['bulk_matches'] = None
if 'inbox_data' not in st.session_state: st.session_state['inbox_data'] = None
if 'radar_sup' not in st.session_state: st.session_state['radar_sup'] = None
if 'radar_date_str' not in st.session_state: st.session_state['radar_date_str'] = None
if 'anomaly_data' not in st.session_state: st.session_state['anomaly_data'] = None

# ==========================================
# 🍪 Cookie 管理與異步防呆機制
# ==========================================
try:
    from streamlit_cookies_controller import CookieController
    cookie_controller = CookieController()
    has_cookie_lib = True
except ImportError:
    has_cookie_lib = False
    cookie_controller = None

# ==========================================
# 📥 匯入底層模組與拆分後的分頁
# ==========================================
from modules.google_db import fetch_all_google_data, SUPPLIERS, clean_string
from tabs.tab1_update import render_tab1
from tabs.tab2_search import render_tab2
from tabs.tab3_analysis import render_tab3
from tabs.tab4_admin import render_tab4

components.html(
    """
    <script>
    const stopC = function(e) {
        if (e.key === 'c' || e.key === 'C') {
            if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.stopImmediatePropagation();
            }
        }
    };
    window.parent.document.addEventListener('keydown', stopC, true);
    window.document.addEventListener('keydown', stopC, true);
    </script>
    """, height=0, width=0
)

hide_st_style = """
<style>
    [data-testid="stHeader"] { background-color: transparent !important; }
    [data-testid="stActionElements"] { display: none !important; }
    footer { visibility: hidden; display: none !important; }
    [data-testid="stStatusWidget"] { visibility: hidden; display: none !important; }
    :root, .stApp, [data-testid="stAppViewContainer"] {
        --background-color: #FFFFFF !important; --secondary-background-color: #F8F9FA !important;
        --text-color: #111111 !important; background-color: #FFFFFF !important; color: #111111 !important;
    }
    [data-testid="stSidebar"], .stSidebar { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0 !important; }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp span, .stApp label { color: #111111 !important; }
    div[data-testid="stForm"] {
        background-color: #FFFFFF !important; border: 1px solid #CCCCCC !important;
        border-radius: 12px !important; padding: 30px !important; box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
    }
    .stApp input, .stApp select, [data-baseweb="select"] { background-color: #F9F9F9 !important; color: #111111 !important; border-color: #CCCCCC !important; }
    .stButton > button, div[data-testid="stForm"] button {
        background-color: #1F77B4 !important; color: #FFFFFF !important; border: none !important;
        border-radius: 6px !important; font-weight: bold !important; box-shadow: 0 2px 5px rgba(31, 119, 180, 0.3) !important;
    }
    .stButton > button:hover, div[data-testid="stForm"] button:hover { background-color: #155B8C !important; color: #FFFFFF !important; }
    button[title="View fullscreen"] { display: none !important; }
    
    .product-card { padding: 12px 15px !important; border: 1px solid #DEDEDE !important; border-radius: 8px !important; margin-bottom: 8px !important; background-color: #FAFAFA !important; transition: 0.3s; }
    .product-card-header { display: flex !important; justify-content: space-between !important; align-items: center !important; border-bottom: 1px dashed #CCCCCC !important; padding-bottom: 6px !important; margin-bottom: 6px !important; }
    .product-card-title { font-size: 16px !important; font-weight: 900 !important; color: #111111 !important; margin: 0 !important; }
    .product-card-body { font-size: 12px !important; color: #666666 !important; line-height: 1.6 !important; }
    .product-card-price-row { display: flex !important; justify-content: space-between !important; align-items: center !important; margin-top: 6px !important; }
    .product-card-price { color: #D9534F !important; font-size: 18px !important; font-weight: bold !important; }
    
    /* 💡 Phase 2: 斷貨產品沉底與灰階樣式 */
    .sold-out-card { opacity: 0.55 !important; background-color: #F0F0F0 !important; border: 1px dashed #BBBBBB !important; }
    .sold-out-card:hover { opacity: 0.8 !important; }
    .sold-out-price { color: #888888 !important; font-size: 15px !important; text-decoration: line-through; }
    
    .badge { padding: 3px 8px !important; border-radius: 4px !important; font-size: 11px !important; font-weight: bold !important; background-color: #E6F7FF !important; color: #0066CC !important; }
    .badge-danger { background-color: #FFEEEE !important; color: #D9534F !important; }
    .bulk-card { border: 2px solid #1F77B4; border-radius: 10px; padding: 15px; margin-bottom: 15px; background-color: #F4F9FC; }
    .bulk-header { font-size: 18px; font-weight: 900; color: #1F77B4; border-bottom: 2px solid #1F77B4; padding-bottom: 8px; margin-bottom: 10px; }
    .bulk-section { font-size: 14px; color: #333; margin-bottom: 10px; line-height: 1.6; }
    .bulk-price-tag { display: inline-block; background: #fff; border: 1px solid #ddd; padding: 4px 8px; border-radius: 5px; margin: 2px 4px 2px 0; font-size: 13px; font-weight: bold; }
    .bulk-cheapest { border-color: #D9534F; color: #D9534F; }
    .bulk-history { background: #fff; padding: 10px; border-radius: 6px; border: 1px dashed #bbb; margin-bottom: 10px; }
    .bulk-conclusion { background: #E8F5E9; padding: 10px; border-radius: 6px; color: #2E7D32; font-weight: bold; border-left: 5px solid #4CAF50; margin-bottom: 5px; }
    .bulk-warning { background: #FFF3E0; padding: 10px; border-radius: 6px; color: #E65100; font-weight: bold; border-left: 5px solid #FF9800; margin-bottom: 5px; }
    @keyframes wave-animation { 0%, 40%, 100% { transform: translateY(0); } 20% { transform: translateY(-12px); color: #1F77B4; } }
    .wave-text { font-size: 22px; font-weight: bold; text-align: center; padding: 40px; color: #555555; }
    .wave-text span { display: inline-block; animation: wave-animation 1.5s infinite; }
</style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

def get_wavy_loading_html():
    msgs = [["正","在","為","你","制","作"," 🍣","🌮","🍧","🍜","🥗"," 中..."], ["大","廚","正","在","火","速","切","肉"," 🔪","🥩","🏃‍♂️"," 中..."]]
    chars = random.choice(msgs)
    spans = "".join([f"<span style='animation-delay: {i*0.1}s'>{c}</span>" for i, c in enumerate(chars)])
    return f"<div class='wave-text'>{spans}</div>"

# ==========================================
# 🔑 智慧登入系統 (完美防護 F5)
# ==========================================
def check_password():
    if st.session_state.get("login_success"):
        return True

    if has_cookie_lib:
        auth_cookie = cookie_controller.get('meat_app_auth')
        if auth_cookie == "Meat2026_Logged_In":
            st.session_state["login_success"] = True
            st.session_state["username"] = cookie_controller.get('meat_app_user') or "User"
            return True
            
        # 💡 終極防呆：給前端一次喘息的機會，如果是剛打開網頁，強迫停止腳本讓前端繪製
        if 'cookie_wait_done' not in st.session_state:
            st.session_state['cookie_wait_done'] = True
            st.markdown("<h3 style='text-align:center; padding-top:100px; color:#999;'>🔄 正在驗證安全連線，請稍候...</h3>", unsafe_allow_html=True)
            st.stop() # 腳本中斷，等待前端回傳 Cookie 觸發自動 Rerun

    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h2 style='text-align: center; margin-top:0; padding-top:0;'>更新報價及搜尋系統</h2><hr style='margin-top:0;'>", unsafe_allow_html=True)
            username = st.text_input("👤 使用者名稱", placeholder="你的名字 (例如: Francis)")
            password = st.text_input("🔑 密碼", type="password")
            
            remember_me = False
            if has_cookie_lib:
                remember_me = st.checkbox("☑️ 記住我 (保持登入狀態 30 天)")

            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("🚀 登入 / Enter", use_container_width=True)
            
            if submitted:
                if not username.strip(): 
                    st.warning("⚠️ 請填寫使用者名稱！")
                elif password == "Meat2026":
                    st.session_state["login_success"] = True
                    st.session_state["username"] = username.strip()
                    
                    if remember_me and has_cookie_lib:
                        try:
                            cookie_controller.set('meat_app_auth', "Meat2026_Logged_In", max_age=30*86400, path='/')
                            cookie_controller.set('meat_app_user', username.strip(), max_age=30*86400, path='/')
                        except: pass
                    st.rerun()
                else: 
                    st.error("❌ 密碼錯誤，請重新輸入！")
    return False

if not check_password(): st.stop()

# ==========================================
# ⚙️ 系統常數與設定
# ==========================================
ACTIVE_SUPPLIERS = sorted(list(set(SUPPLIERS + ["形澧"])))
HEADER_MAP = {
    "新興城": {"LB": "新興城 $/LB", "KG": "新興城 $/KG"}, "金山洋行": {"LB": "金山 ($/lb)", "KG": "金山 ($/KG)"},
    "廣隆": {"LB": "廣隆 $/LB", "KG": "廣隆 $/KG"}, "哲朗": {"LB": "哲朗 $/LB", "KG": "哲朗 $/KG"},
    "浩新": {"LB": "浩新 $/LB", "KG": "浩新 $/KG"}, "一峰行": {"LB": "一峰行 $/LB", "KG": "一峰行 $/KG"},
    "恆盛": {"LB": "恆盛 $/LB", "KG": "恆盛 $/KG"}, "萬安(遠東)": {"LB": "萬安 ($/lb)", "KG": "萬安 ($/kg)"}, "形澧": {"LB": "形澧 $/LB", "KG": "形澧 $/KG"} 
}
FILENAME_MAPPING = { "06-07-2026": "新興城", "FEB-2026": "廣隆", "29-Jun-2026": "金山洋行", "哲朗": "哲朗", "Price list": "浩新", "一峰行": "一峰行", "2026-06-22": "恆盛", "萬安": "萬安(遠東)", "形澧": "形澧" }

STATIC_DICT = {
    "雞翼": ["中亦", "中翼", "雞翼", "雞中翼", "翼"],
    "牛上腦": ["牛上腦", "肩胛肉眼", "chuckroll", "chuck", "上腦"],
    "雞比": ["雞比", "雞脾", "餅比", "餅脾", "雞腿", "脾肉", "比肉", "全脾", "雞下脾"],
    "牛小排": ["牛小排", "牛仔骨", "shortrib", "牛排"],
    "金錢展": ["金展", "金錢展", "金錢𦟌", "牛展", "shin", "shank", "展"],
    "肉眼": ["肉眼", "ribeye", "rib-eye"],
    "西冷": ["西冷", "striploin", "sirloin"],
    "牛柳": ["牛柳", "tenderloin", "fillet"],
    "豬扒": ["豬扒", "pork chop"],
    "梅肉": ["梅肉", "pork collar", "豬梅肉", "脢肉"],
    "豬肋排": ["豬肋排", "肋排", "spare rib", "sparerib", "仔骨"],
    "肥牛": ["肥牛", "胸腹", "pastrami", "plate", "short plate", "牛腩"]
}

loading_ph = st.empty()
loading_ph.markdown(get_wavy_loading_html(), unsafe_allow_html=True)
target_dict, cat_data, hist_vals, global_origins, ignore_dict = fetch_all_google_data()
loading_ph.empty()

parsed_history = []
if len(hist_vals) > 1:
    for hr in hist_vals[1:]:
        if len(hr) >= 6:
            try:
                date_str = hr[1].split()[0] if " " in hr[1] else hr[1]
                q_date = datetime.strptime(date_str, "%Y-%m-%d")
                sku = str(hr[3] if len(hr) >= 7 else hr[2]).strip()
                price = float(hr[5] if len(hr) >= 7 else hr[4])
                parsed_history.append({'date': q_date, 'sku': sku, 'price': price})
            except: pass

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
            
    st.markdown("---")
    if has_cookie_lib and st.button("🚪 登出系統", use_container_width=True):
        try:
            cookie_controller.remove('meat_app_auth')
            cookie_controller.remove('meat_app_user')
        except: pass
        st.session_state.clear()
        st.rerun()
        
    st.caption("版本號: v29.0 (無縫登入 & 智能搜尋版)")

tab1, tab2, tab3, tab4 = st.tabs(["一鍵更新報價", "日常搜尋", "📊 智能入貨分析", "⚙️ 系統管理 (開發者專用)"])

with tab1: render_tab1(ACTIVE_SUPPLIERS, HEADER_MAP, target_dict, cat_data, parsed_history, get_wavy_loading_html)
with tab2: render_tab2(global_origins, STATIC_DICT, cat_data, HEADER_MAP, parsed_history, FILENAME_MAPPING, get_wavy_loading_html)
with tab3: render_tab3(STATIC_DICT, cat_data, HEADER_MAP, parsed_history)
with tab4: render_tab4(ACTIVE_SUPPLIERS, HEADER_MAP, target_dict, cat_data, ignore_dict, STATIC_DICT, get_wavy_loading_html)
