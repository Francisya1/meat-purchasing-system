# modules/google_db.py
import streamlit as st
import gspread
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SUPPLIERS = ["新興城", "廣隆", "金山洋行", "哲朗", "浩新", "一峰行", "恆盛", "萬安(遠東)", "形澧"]
DRIVE_FOLDER_ID = "1w8e_TzqTwELTFgiSU1AEyulv3UyJKzXT"
# 💡 將新的 Google Sheet ID 設為常數
NEW_SHEET_ID = "181Zx5T1OLwnE08uf86-_bi_FK22PwCfbuB_Pr7AG2rE"

def clean_string(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', text).upper()

def get_credentials():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    if "gcp_service_account" in st.secrets:
        creds_info = st.secrets["gcp_service_account"]
        return Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        return Credentials.from_service_account_file('credentials.json', scopes=scopes)

def get_google_connection():
    try:
        creds = get_credentials()
        gc = gspread.authorize(creds)
        # 💡 核心更改：使用 open_by_key 精準綁定唯一 ID
        sh = gc.open_by_key(NEW_SHEET_ID)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, sh, drive_service
    except Exception as e:
        st.error(f"🚨 Google 連線失敗，請檢查憑證設定：{e}")
        st.stop()

@st.cache_data(ttl=600)
def fetch_all_google_data():
    gc, sh = get_google_connection()[:2]
    
    # 1. 抓取 Mapping 字典
    mapping_data = sh.worksheet('Mapping').get_all_records()
    target_dict = {}
    for row in mapping_data:
        sup = str(row.get('供應商', '')).strip()
        raw_name = str(row.get('供應商原文', '')).strip()
        sku = str(row.get('對應SKU', '')).strip()
        if sup and raw_name and sku:
            if sup not in target_dict: target_dict[sup] = []
            target_dict[sup].append({"sku": sku, "name": raw_name, "clean_name": clean_string(raw_name)})
            
    # 2. 抓取四大母表
    cat_data = {}
    all_origins = [] 
    for sn in ['Beef', 'Pork', 'Chicken', 'Lamp']:
        try:
            vals = sh.worksheet(sn).get_all_values()
            cat_data[sn] = vals
            if len(vals) > 2:
                for row in vals[2:]:
                    if len(row) > 1 and row[1].strip():
                        all_origins.append(row[1].strip())
        except: pass
        
    # 3. 抓取歷史紀錄
    try: hist_vals = sh.worksheet("History_Log").get_all_values()
    except: hist_vals = []
        
    global_origins = sorted(list(set(all_origins))) 
    return target_dict, cat_data, hist_vals, global_origins

def get_drive_connection():
    creds = get_credentials()
    return build('drive', 'v3', credentials=creds)
