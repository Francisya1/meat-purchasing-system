import streamlit as st
import pandas as pd
import re

from modules.google_db import clean_string
from tabs.tab1_update import find_price_columns

def render_tab3(STATIC_DICT, cat_data, HEADER_MAP, parsed_history):
    st.header("大規模入貨決策支援")
    with st.form("bulk_form"):
        col_b1, col_b2 = st.columns([4, 1])
        with col_b1: bulk_query = st.text_input("🎯 第一步：搜尋目標產品 (如: 雞翼, 西冷):", placeholder="輸入任意關鍵字開始找尋...")
        with col_b2:
            st.markdown("<br>", unsafe_allow_html=True)
            submit_bulk = st.form_submit_button("🔍 搜尋目標", use_container_width=True)
            
    if submit_bulk and bulk_query:
        bulk_q_clean = clean_string(bulk_query)
        search_aliases = set([bulk_q_clean])
        
        # 💡 Phase 2: 智能雙向切詞
        for key, aliases in STATIC_DICT.items():
            if bulk_q_clean in aliases or bulk_q_clean in key or key in bulk_q_clean:
                search_aliases.update(aliases)
                search_aliases.add(key)
                
        st.info(f"🧠 智能搜尋擴展：`{', '.join(search_aliases)}`")
        bulk_matches = []
        for sn, all_vals in cat_data.items():
            if not all_vals: continue
            sup_cols = {}
            for sup_name in HEADER_MAP.keys():
                lb_col, _ = find_price_columns(all_vals, sup_name, HEADER_MAP)
                sup_cols[sup_name] = {"LB": lb_col - 1}

            for row in all_vals[2:]:
                if not row: continue
                sku = str(row[0]).strip()
                std_name = " ".join([str(row[i]).strip() for i in range(1, min(6, len(row))) if str(row[i]).strip()])
                clean_sku = clean_string(sku); clean_std = clean_string(std_name)
                
                if any(alias in clean_sku or alias in clean_std for alias in search_aliases):
                    current_prices = {}
                    for sup_name, cols in sup_cols.items():
                        lb_col = cols["LB"]
                        if lb_col != -2 and lb_col < len(row):
                            val_str = str(row[lb_col]).strip()
                            nums = re.findall(r'\d+\.?\d*', val_str)
                            # 💡 Phase 2: 強制剔除 $0 產品
                            if nums and float(nums[0]) > 0 and "sold out" not in val_str.lower():
                                current_prices[sup_name] = round(float(nums[0]), 1)
                    bulk_matches.append({"sku": sku, "name": std_name, "origin": str(row[1]).strip() if len(row)>1 else "未標明", "current_prices": current_prices})
        
        if not bulk_matches:
            st.warning("沒有在母表中找到符合該關鍵字的產品。"); st.session_state['bulk_matches'] = None
        else: 
            st.session_state['bulk_matches'] = bulk_matches
            
    if st.session_state.get('bulk_matches'):
        matches = st.session_state['bulk_matches']
        
        # 💡 Phase 2: 沉底排序法 (讓沒有任何現價的產品排到最下面)
        matches = sorted(matches, key=lambda x: 0 if len(x['current_prices']) > 0 else 1)
        
        st.markdown("### 🎯 第二步：精準鎖定 (點擊下拉選單過濾)")
        col_f1, col_f2 = st.columns(2)
        all_origins = sorted(list(set([m['origin'] for m in matches if m['origin']])))
        all_skus = sorted(list(set([f"[{m['sku']}] {m['name']}" for m in matches])))
        with col_f1: f_origins = st.multiselect("🌍 鎖定產地", all_origins, placeholder="全部產地 (可選多個)")
        with col_f2: f_skus = st.multiselect("📌 鎖定精準 SKU / 品名", all_skus, placeholder="全部產品 (可選多個)")
        st.markdown("---")
        
        filtered_matches = matches
        if f_origins: filtered_matches = [m for m in filtered_matches if m['origin'] in f_origins]
        if f_skus: filtered_matches = [m for m in filtered_matches if f"[{m['sku']}] {m['name']}" in f_skus]
        
        if not filtered_matches: st.warning("⚠️ 此篩選條件下沒有產品，請放寬條件。")
        else:
            for item in filtered_matches:
                sku = item['sku']
                sku_history = [x for x in parsed_history if x['sku'] == sku and x['price'] > 0]
                date_prices = {}
                for rec in sku_history:
                    d_str = rec['date'].strftime('%Y-%m-%d')
                    if d_str not in date_prices or rec['price'] < date_prices[d_str]: date_prices[d_str] = rec['price']
                sorted_dates = sorted(date_prices.keys(), reverse=True)
                last_3_records = [(d, date_prices[d]) for d in sorted_dates[:3]]
                if last_3_records: last_3_html = "<br>".join([f"📅 {d} 報價: <b>${p:.1f}</b>" for d, p in last_3_records])
                else: last_3_html = "<span style='color:#999;'>尚無歷史真實報價紀錄</span>"
                historical_min = min(date_prices.values()) if date_prices else None
                current_min = min(item['current_prices'].values()) if item['current_prices'] else None
                
                current_tags_html = ""
                if item['current_prices']:
                    for sup, price in item['current_prices'].items():
                        is_cheapest = (price == current_min)
                        css_class = "bulk-price-tag bulk-cheapest" if is_cheapest else "bulk-price-tag"
                        star = "🏆 " if is_cheapest else ""
                        current_tags_html += f"<span class='{css_class}'>{star}{sup}: ${price:.1f}</span>"
                else: current_tags_html = "<span class='bulk-price-tag' style='color:#999; text-decoration:line-through;'>全行斷貨 (Sold out)</span>"
                
                conclusion_html = ""
                card_style = ""
                if current_min is None: 
                    conclusion_html = f"<div class='bulk-warning' style='background:#f9f9f9; color:#777; border-color:#ccc;'>⚠️ <b>系統分析：</b> 目前全行斷貨，無貨可入。</div>"
                    card_style = "opacity: 0.6; filter: grayscale(100%);" # 💡 斷貨的卡片灰階處理
                elif historical_min is None: 
                    conclusion_html = f"<div class='bulk-conclusion' style='color:#555; border-color:#999; background:#f0f0f0;'>ℹ️ <b>系統分析：</b> 無過去報價可比對，請依現價 ${current_min:.1f} 自行判斷。</div>"
                else:
                    if current_min <= historical_min: conclusion_html = f"<div class='bulk-conclusion'>💡 <b>強烈建議入貨：</b> 現時最低價 (${current_min:.1f}) 已平過或等同於歷史絕對低位！</div>"
                    else:
                        diff = current_min - historical_min
                        conclusion_html = f"<div class='bulk-warning'>⚠️ <b>建議觀望或講價：</b> 現價 (${current_min:.1f}) 距離你曾買過的歷史最低價 (${historical_min:.1f}) 貴了 ${diff:.1f}。</div>"

                bulk_card_html = f"<div class='bulk-card' style='{card_style}'><div class='bulk-header'>【{item['origin']}】 {item['name']} (SKU: {sku})</div><div class='bulk-section'><b>👀 現時全行各家報價：</b><br>{current_tags_html}</div><div class='bulk-history'><b>📈 過去 3 次真實報價紀錄：</b><br>{last_3_html}</div>{conclusion_html}</div>"
                st.markdown(bulk_card_html, unsafe_allow_html=True)
