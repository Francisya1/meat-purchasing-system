import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import re

# 👇 你的專屬密鑰已安全就位！
NEW_SHEET_ID = "181Zx5T1OLwnE08uf86-_bi_FK22PwCfbuB_Pr7AG2rE"
DRIVE_FOLDER_ID = "1w8e_TzqTwELTFgiSU1AEyulv3UyJKzXT"

SUPPLIERS = ["新興城", "金山洋行", "廣隆", "哲朗", "浩新", "一峰行", "恆盛", "萬安(遠東)"]

def clean_string(s):
    s = str(s).lower()
    s = re.sub(r'\s+', '', s)
    return s

def get_google_connection():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    s_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(s_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(NEW_SHEET_ID)
    drive_service = build('drive', 'v3', credentials=creds)
    return gc, sh, drive_service

def get_drive_connection():
    gc, sh, drive_service = get_google_connection()
    return drive_service

@st.cache_data(ttl=600)
def fetch_all_google_data():
    gc, sh, _ = get_google_connection()
    
    mapping_data = sh.worksheet('Mapping').get_all_records()
    target_dict = {}
    for row in mapping_data:
        sup = str(row.get('供應商', '')).strip()
        raw_name = str(row.get('供應商原文', '')).strip()
        sku = str(row.get('對應SKU', '')).strip()
        if sup and raw_name and sku:
            if sup not in target_dict:
                target_dict[sup] = []
            target_dict[sup].append({'sku': sku, 'name': raw_name})
            
    cat_data = {}
    global_origins = set()
    for cat in ['Beef', 'Pork', 'Chicken', 'Lamp']:
        try:
            ws = sh.worksheet(cat)
            vals = ws.get_all_values()
            cat_data[cat] = vals
            if len(vals) > 2:
                for r in vals[2:]:
                    if len(r) > 1 and str(r[1]).strip():
                        global_origins.add(str(r[1]).strip())
        except:
            cat_data[cat] = []
            
    try:
        hist_vals = sh.worksheet('History_Log').get_all_values()
    except:
        hist_vals = []
        
    # 💡 Phase 2 新增：讀取 Ignore_List 黑名單
    ignore_dict = {}
    try:
        ignore_data = sh.worksheet('Ignore_List').get_all_records()
        for row in ignore_data:
            sup = str(row.get('供應商', '')).strip()
            val = str(row.get('供應商原文', '')).strip()
            if sup and val:
                if sup not in ignore_dict:
                    ignore_dict[sup] = []
                ignore_dict[sup].append(val)
    except Exception:
        pass # 如果分頁不存在或空了，就回傳空字典
        
    return target_dict, cat_data, hist_vals, sorted(list(global_origins)), ignore_dict
