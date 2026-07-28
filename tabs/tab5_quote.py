import streamlit as st
import pandas as pd
from datetime import datetime

def render_tab5():
    st.header("🛒 智能報價與利潤計算車")
    
    # 💡 1. 報價對象管理
    col_r1, col_r2 = st.columns([2, 2])
    with col_r1:
        restaurant_name = st.text_input("🏢 報價對象 (餐廳 / 客戶名稱)：", value=st.session_state.get('quote_restaurant', ''), placeholder="例如：大快活...")
        st.session_state['quote_restaurant'] = restaurant_name

    st.markdown("""
    把搜尋到的正確產品加入這裡，方便統一管理並即時回報給餐廳。  
    <span style="color:#D9534F; font-weight:bold;">💡 編輯提示：請在表格內的「成本」或「📝 輸入數值」欄位上【雙擊兩下 (Double Click)】，即可手動輸入更改數字！</span>
    """, unsafe_allow_html=True)

    if not st.session_state.get('quote_cart'):
        st.info("📦 報價車目前是空的。請先到「日常搜尋」找尋合適的產品，打勾並加入報價車！")
        return

    df_cart = pd.DataFrame(st.session_state['quote_cart'])
    
    col_add, col_gap = st.columns([1, 4])
    with col_add:
        if st.button("➕ 手動加入空白行"):
            st.session_state['quote_cart'].append({
                "supplier": "手動輸入", "name": "新產品", "cost": 0.0,
                "mode": "設定利潤(%)算售價", "input_val": 12.0, "final_price": 0.0, "profit_dollar": 0.0, "profit_pct": 0.0, "note": ""
            })
            st.rerun()

    df_cart.insert(0, "🗑️ 刪除", False)

    # 💡 2. 互動表格渲染
    edited_df = st.data_editor(
        df_cart,
        column_config={
            "🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除", default=False),
            "supplier": st.column_config.TextColumn("供應商 (可雙擊修改)"),
            "name": st.column_config.TextColumn("產品名稱 (可雙擊修改)"),
            "cost": st.column_config.NumberColumn("成本 ($)", format="%.1f"),
            "mode": st.column_config.SelectboxColumn("🧮 運算模式", options=["設定利潤(%)算售價", "直接設定售價($)"]),
            "input_val": st.column_config.NumberColumn("📝 輸入數值 (利潤% / 售價$)", format="%.1f"),
            "final_price": st.column_config.NumberColumn("🎯 最終售價 ($)", disabled=True, format="%.1f"),
            "profit_dollar": st.column_config.NumberColumn("💰 實賺 ($)", disabled=True, format="%.1f"),
            "profit_pct": st.column_config.NumberColumn("📊 利潤 (%)", disabled=True, format="%.1f%%"),
            "note": st.column_config.TextColumn("備註/產地 (可雙擊修改)")
        },
        use_container_width=True, hide_index=True, key="quote_cart_editor", height=max(200, len(df_cart)*45 + 50)
    )

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        if st.button("🚀 執行運算並儲存進度", type="primary", use_container_width=True):
            new_cart = []
            for idx, row in edited_df.iterrows():
                if row["🗑️ 刪除"]: continue
                
                cost = float(row["cost"])
                mode = row["mode"]
                inp = float(row["input_val"])
                
                final_price = 0.0
                prof_d = 0.0
                prof_p = 0.0

                if mode == "設定利潤(%)算售價":
                    if inp >= 100:
                        st.warning(f"⚠️ {row['name']} 的利潤不能大於或等於 100%！系統已強制調整為 99%。")
                        inp = 99.0
                    if inp > 0 and cost > 0:
                        final_price = cost / (1 - (inp / 100))
                        prof_d = final_price - cost
                        prof_p = inp
                else: # 直接設定售價
                    final_price = inp
                    if final_price > 0 and cost > 0:
                        prof_d = final_price - cost
                        prof_p = (prof_d / final_price) * 100

                new_cart.append({
                    "supplier": row["supplier"],
                    "name": row["name"],
                    "cost": round(cost, 2),
                    "mode": mode,
                    "input_val": round(inp, 2),
                    "final_price": round(final_price, 2),
                    "profit_dollar": round(prof_d, 2),
                    "profit_pct": round(prof_p, 2),
                    "note": row["note"]
                })
            
            st.session_state['quote_cart'] = new_cart
            st.rerun()
            
    with col3:
        if st.button("🧹 清空報價車", use_container_width=True):
            st.session_state['quote_cart'] = []
            st.rerun()

    # ==========================================
    # 💡 3. 一鍵輸出與發送模組
    # ==========================================
    if any(item.get("final_price", 0) > 0 for item in st.session_state['quote_cart']):
        st.markdown("---")
        target_name = restaurant_name if restaurant_name.strip() else '未命名客戶'
        st.subheader(f"📤 輸出報價單：{target_name}")
        
        export_data = []
        quote_text = f"老闆你好，以下是為【{target_name}】準備的最新報價：\n\n"
        
        for item in st.session_state['quote_cart']:
            # CSV 內部專用，包含成本利潤
            export_data.append({
                "供應商": item['supplier'],
                "產品名稱": item['name'],
                "備註/產地": item['note'],
                "成本 ($/LB)": item['cost'],
                "設定模式": item['mode'],
                "設定數值": item['input_val'],
                "最終報價 ($/LB)": item['final_price'],
                "實賺 ($/LB)": item['profit_dollar'],
                "毛利 (%)": f"{item['profit_pct']}%"
            })
            # WhatsApp 複製用，只顯示品名、產地與售價 (隱藏成本)
            note_str = f" ({item['note']})" if item['note'] else ""
            quote_text += f"▪️ {item['name']}{note_str}：${item['final_price']:.1f} / LB\n"
        
        quote_text += "\n如有需要請隨時通知，謝謝！"
        export_df = pd.DataFrame(export_data)
        
        col_ex1, col_ex2 = st.columns([1, 1])
        with col_ex1:
            st.markdown("💬 **WhatsApp / Email 發送格式 (已隱藏成本)**")
            st.write("直接點擊右上角的複製按鈕，即可貼上傳送！")
            st.code(quote_text, language="markdown")
            
        with col_ex2:
            st.markdown("📊 **下載內部試算表 (包含詳細成本與利潤)**")
            st.write("下載為 CSV 檔，可直接用 Excel 開啟存檔備查。")
            csv = export_df.to_csv(index=False, encoding='utf-8-sig')
            filename = f"報價單_{target_name}_{datetime.now().strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 下載內部 CSV 試算表",
                data=csv,
                file_name=filename,
                mime="text/csv",
                type="primary",
                use_container_width=True
            )
