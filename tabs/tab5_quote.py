import streamlit as st
import pandas as pd
from datetime import datetime

def render_tab5():
    st.header("🛒 智能報價與利潤計算車")
    
    col_r1, col_r2 = st.columns([2, 2])
    with col_r1:
        restaurant_name = st.text_input("🏢 報價對象 (餐廳 / 客戶名稱)：", value=st.session_state.get('quote_restaurant', ''), placeholder="例如：大快活...")
        st.session_state['quote_restaurant'] = restaurant_name

    st.markdown("""
    把搜尋到的正確產品加入這裡，方便統一管理。  
    <span style="color:#D9534F; font-weight:bold;">💡 全自動即時運算：表格內任何數字修改後 (輸入後點擊空白處或按 Enter)，系統會「瞬間自動重新計算」，完全不需要按按鈕！</span>
    """, unsafe_allow_html=True)

    if not st.session_state.get('quote_cart'):
        st.info("📦 報價車目前是空的。請先到「日常搜尋」找尋合適的產品，打勾並加入報價車！")
        return

    # ==========================================
    # 💡 核心：渲染前先計算最新的結果 (保證數據永遠是最新的)
    # ==========================================
    display_list = []
    for item in st.session_state['quote_cart']:
        cost = float(item.get('cost', 0.0))
        mode = item.get('mode', '設定利潤(%)')
        inp = float(item.get('input_val', 12.0))
        
        fp = 0.0; pdol = 0.0; ppct = 0.0
        
        if mode == "設定利潤(%)":
            if inp >= 100: inp = 99.0 # 防呆：利潤不能等於或大於 100%
            if inp > 0 and cost > 0:
                fp = cost / (1 - (inp / 100))
                pdol = fp - cost
                ppct = inp
        else: # 直接定售價($)
            fp = inp
            if fp > 0 and cost > 0:
                pdol = fp - cost
                ppct = (pdol / fp) * 100
                
        item['final_price'] = round(fp, 2)
        item['profit_dollar'] = round(pdol, 2)
        item['profit_pct'] = round(ppct, 2)
        item['input_val'] = inp 
        
        display_item = item.copy()
        display_item["🗑️ 刪除"] = False
        display_list.append(display_item)
        
    df_cart = pd.DataFrame(display_list)
    cols_order = ["🗑️ 刪除", "supplier", "name", "cost", "mode", "input_val", "final_price", "profit_dollar", "profit_pct", "note"]
    df_cart = df_cart[cols_order]

    col_add, col_gap = st.columns([1, 5])
    with col_add:
        if st.button("➕ 手動加入空白行"):
            st.session_state['quote_cart'].append({
                "supplier": "手動輸入", "name": "新產品", "cost": 0.0,
                "mode": "設定利潤(%)", "input_val": 12.0, "note": ""
            })
            st.rerun()

    # ==========================================
    # 💡 互動表格渲染 (支援雙擊修改)
    # ==========================================
    edited_df = st.data_editor(
        df_cart,
        column_config={
            "🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除"),
            "supplier": st.column_config.TextColumn("供應商"),
            "name": st.column_config.TextColumn("產品名稱"),
            "cost": st.column_config.NumberColumn("成本 ($/LB)", format="%.2f"),
            "mode": st.column_config.SelectboxColumn("🧮 運算模式", options=["設定利潤(%)", "直接定售價($)"]),
            "input_val": st.column_config.NumberColumn("📝 輸入數值", format="%.2f"),
            "final_price": st.column_config.NumberColumn("🎯 最終售價 ($)", disabled=True, format="%.2f"),
            "profit_dollar": st.column_config.NumberColumn("💰 實賺 ($)", disabled=True, format="%.2f"),
            "profit_pct": st.column_config.NumberColumn("📊 利潤 (%)", disabled=True, format="%.1f%%"),
            "note": st.column_config.TextColumn("備註/產地")
        },
        use_container_width=True, hide_index=True, key="quote_cart_editor", height=max(200, len(df_cart)*40 + 50)
    )

    # ==========================================
    # ⚡ 即時更新引擎：只要偵測到表格有改動，瞬間覆寫並重整畫面
    # ==========================================
    has_changes = False
    new_cart = []
    for idx, row in edited_df.iterrows():
        if row["🗑️ 刪除"]:
            has_changes = True
            continue
        
        old_item = st.session_state['quote_cart'][idx]
        new_item = {
            "supplier": row["supplier"],
            "name": row["name"],
            "cost": float(row["cost"]),
            "mode": row["mode"],
            "input_val": float(row["input_val"]),
            "note": row["note"]
        }
        
        # 檢查是否有人手動改了數字或文字
        for k in new_item:
            if new_item[k] != old_item.get(k):
                has_changes = True
                break
                
        new_cart.append(new_item)
        
    if has_changes:
        st.session_state['quote_cart'] = new_cart
        st.rerun() # 瞬間重整畫面，觸發上方的即時運算

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🧹 一鍵清空報價車", use_container_width=True):
        st.session_state['quote_cart'] = []
        st.rerun()

    # ==========================================
    # 📤 雙引擎輸出模組 (告別忍者隱身黑字)
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
                "成本 ($/LB)": item['cost'], "設定模式": item['mode'], "設定數值": item['input_val'],
                "最終報價 ($/LB)": item['final_price'], "實賺 ($/LB)": item['profit_dollar'], "毛利 (%)": f"{item['profit_pct']}%"
            })
            
            note_str = f" ({item['note']})" if item['note'] else ""
            
            # 1. 給客人的文字 (隱藏供應商、成本)
            client_text += f"▪️ {item['name']}{note_str}：${item['final_price']:.1f} / LB\n"
            
            # 2. 內部專用文字 (全開：顯示供應商、售價、成本、毛利)
            internal_text += f"▪️ 【{item['supplier']}】{item['name']}{note_str} ➡️ 售: ${item['final_price']:.1f} (成本:${item['cost']:.1f}, 利潤:{item['profit_pct']}%)\n"
        
        client_text += "\n如有需要請隨時通知，謝謝！"
        export_df = pd.DataFrame(export_data)
        
        # 使用 text_area 讓文字保持清晰，不會變成黑底黑字
        col_ex1, col_ex2 = st.columns([1, 1])
        with col_ex1:
            st.markdown("💬 **發給客人的版本 (已隱藏內部資訊)**")
            st.text_area("直接點擊框內並全選複製：", value=client_text, height=200, key="client_txt")
            
        with col_ex2:
            st.markdown("🔒 **內部紀錄版本 (包含供應商與成本)**")
            st.text_area("留底專用，請勿傳給客人：", value=internal_text, height=200, key="internal_txt")

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
