import streamlit as st
import pandas as pd
from datetime import datetime

def render_tab5():
    # ==========================================
    # 💡 終極 CSS 穿透：強制所有文字框為白底黑字
    # ==========================================
    st.markdown("""
    <style>
    div[data-baseweb="textarea"] > div { background-color: #FFFFFF !important; border: 2px solid #1F77B4 !important; }
    textarea { color: #000000 !important; background-color: #FFFFFF !important; -webkit-text-fill-color: #000000 !important; font-weight: 500 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    st.header("🛒 智能報價與利潤計算車")
    
    col_r1, col_r2 = st.columns([2, 2])
    with col_r1:
        restaurant_name = st.text_input("🏢 報價對象 (餐廳 / 客戶名稱)：", value=st.session_state.get('quote_restaurant', ''), placeholder="例如：大快活...")
        st.session_state['quote_restaurant'] = restaurant_name

    st.markdown("""
    <span style="color:#D9534F; font-weight:bold;">💡 雙向即時運算：雙擊表格直接修改「售價」或「利潤(%)」，點擊空白處後，系統會自動秒算另一邊！</span>
    """, unsafe_allow_html=True)

    if not st.session_state.get('quote_cart'):
        st.info("📦 報價車目前是空的。請先到「日常搜尋」找尋合適的產品，打勾並加入報價車！")
        return

    # ==========================================
    # 💡 初始化與預處理
    # ==========================================
    display_list = []
    for item in st.session_state['quote_cart']:
        if item.get('final_price', 0.0) == 0.0:
            cost = float(item.get('cost', 0.0))
            pct = 12.0
            fp = cost / (1 - (pct/100)) if cost > 0 else 0.0
            item['profit_pct'] = round(pct, 2)
            item['final_price'] = round(fp, 2)
            item['profit_dollar'] = round(fp - cost, 2)
        
        display_item = item.copy()
        display_item["🗑️ 刪除"] = False
        display_list.append(display_item)
        
    df_cart = pd.DataFrame(display_list)
    cols_order = ["🗑️ 刪除", "supplier", "name", "cost", "final_price", "profit_pct", "profit_dollar", "note"]
    
    for col in cols_order:
        if col not in df_cart.columns: df_cart[col] = ""
    df_cart = df_cart[cols_order]

    col_add, col_gap = st.columns([1, 5])
    with col_add:
        if st.button("➕ 手動加入空白行"):
            st.session_state['quote_cart'].append({
                "supplier": "手動輸入", "name": "新產品", "cost": 0.0,
                "final_price": 0.0, "profit_pct": 12.0, "profit_dollar": 0.0, "note": ""
            })
            st.rerun()

    # ==========================================
    # 💡 互動表格渲染 (雙向直覺修改)
    # ==========================================
    edited_df = st.data_editor(
        df_cart,
        column_config={
            "🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除"),
            "supplier": st.column_config.TextColumn("供應商"),
            "name": st.column_config.TextColumn("產品名稱"),
            "cost": st.column_config.NumberColumn("成本 ($/LB)", format="%.2f"),
            "final_price": st.column_config.NumberColumn("🎯 最終售價 ($)", format="%.2f", help="雙擊修改售價，系統會自動反推利潤"),
            "profit_pct": st.column_config.NumberColumn("📊 利潤 (%)", format="%.1f", help="雙擊修改利潤，系統會自動重算售價"),
            "profit_dollar": st.column_config.NumberColumn("💰 實賺 ($)", disabled=True, format="%.2f"),
            "note": st.column_config.TextColumn("備註/產地")
        },
        use_container_width=True, hide_index=True, key="quote_cart_editor", height=max(200, len(df_cart)*45 + 50)
    )

    # ==========================================
    # ⚡ 真・即時雙向運算引擎
    # ==========================================
    has_changes = False
    new_cart = []
    for idx, row in edited_df.iterrows():
        if row["🗑️ 刪除"]:
            has_changes = True
            continue
        
        old_item = st.session_state['quote_cart'][idx]
        
        cost = float(row["cost"]) if pd.notna(row["cost"]) else 0.0
        fp = float(row["final_price"]) if pd.notna(row["final_price"]) else 0.0
        pct = float(row["profit_pct"]) if pd.notna(row["profit_pct"]) else 0.0
        
        old_cost = float(old_item.get("cost", 0.0))
        old_fp = float(old_item.get("final_price", 0.0))
        old_pct = float(old_item.get("profit_pct", 0.0))
        
        if pct != old_pct:
            if pct >= 100: pct = 99.0
            fp = cost / (1 - (pct / 100)) if cost > 0 else 0.0
            has_changes = True
        elif fp != old_fp:
            pct = ((fp - cost) / fp * 100) if fp > 0 else 0.0
            has_changes = True
        elif cost != old_cost:
            fp = cost / (1 - (old_pct / 100)) if cost > 0 else 0.0
            pct = old_pct
            has_changes = True
        elif row["supplier"] != old_item.get("supplier") or row["name"] != old_item.get("name") or row["note"] != old_item.get("note"):
            has_changes = True
            
        pdol = fp - cost if fp > cost else 0.0

        new_cart.append({
            "supplier": row["supplier"],
            "name": row["name"],
            "cost": round(cost, 2),
            "final_price": round(fp, 2),
            "profit_pct": round(pct, 2),
            "profit_dollar": round(pdol, 2),
            "note": row["note"]
        })
        
    if has_changes:
        st.session_state['quote_cart'] = new_cart
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🧹 一鍵清空報價車", use_container_width=True):
        st.session_state['quote_cart'] = []
        st.rerun()

    # ==========================================
    # 📤 輸出模組 (解除了 key 鎖定，現在會顯示所有產品！)
    # ==========================================
    if any(item.get("final_price", 0) > 0 for item in st.session_state['quote_cart']):
        st.markdown("---")
        target_name = restaurant_name if restaurant_name.strip() else '未命名客戶'
        st.subheader(f"📤 輸出報價單：{target_name}")
        
        export_data = []
        client_text = f"老闆你好，以下是為【{target_name}】準備的最新報價：\n\n"
        internal_text = f"【{target_name}】內部機密報價紀錄：\n\n"
        
        for item in st.session_state['quote_cart']:
            export_data.append({
                "供應商": item['supplier'], "產品名稱": item['name'], "備註/產地": item['note'],
                "成本 ($/LB)": item['cost'], 
                "最終報價 ($/LB)": item['final_price'], "實賺 ($/LB)": item['profit_dollar'], "毛利 (%)": f"{item['profit_pct']}%"
            })
            
            note_str = f" ({item['note']})" if item['note'] else ""
            
            client_text += f"▪️ {item['name']}{note_str}：${item['final_price']:.1f} / LB\n"
            internal_text += f"▪️ 【{item['supplier']}】{item['name']}{note_str} ➡️ 售: ${item['final_price']:.1f} (成本:${item['cost']:.1f}, 利潤:{item['profit_pct']}%)\n"
        
        client_text += "\n如有需要請隨時通知，謝謝！"
        export_df = pd.DataFrame(export_data)
        
        col_ex1, col_ex2 = st.columns([1, 1])
        
        # 💡 解除 key 的鎖定，這樣每次新增產品，文字框才會即時更新顯示！
        with col_ex1:
            st.markdown("💬 **發給客人的版本 (已隱藏內部資訊)**")
            st.text_area("直接點擊框內並全選複製：", value=client_text, height=250)
            
        with col_ex2:
            st.markdown("🔒 **內部紀錄版本 (包含供應商與成本)**")
            st.text_area("留底專用，請勿傳給客人：", value=internal_text, height=250)

        st.markdown("<br>", unsafe_allow_html=True)
        csv = export_df.to_csv(index=False, encoding='utf-8-sig')
        filename = f"內部報價紀錄_{target_name}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        st.download_button(
            label="📥 下載內部 CSV 試算表 (完整數據)",
            data=csv,
            file_name=filename,
            mime="text/csv",
            type="primary",
            use_container_width=True
        )
