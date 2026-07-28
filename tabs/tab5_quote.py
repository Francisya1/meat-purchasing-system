import streamlit as st
import pandas as pd

def render_tab5():
    st.header("🛒 智能報價與利潤計算車")
    st.markdown("""
    把搜尋到的正確產品加入這裡，方便統一管理並即時回報給餐廳。  
    **計算公式：** `(最終售價 - 成本) ÷ 最終售價 = 實際利潤%`  
    *👉 你可以選擇輸入「目標利潤(%)」讓系統算售價，或是直接輸入「自訂售價($)」讓系統逆推利潤。*
    """)

    if not st.session_state.get('quote_cart'):
        st.info("📦 報價車目前是空的。請先到「日常搜尋」找尋合適的產品，打勾並加入報價車！")
        return

    # 將 Session State 轉為 DataFrame 方便渲染
    df_cart = pd.DataFrame(st.session_state['quote_cart'])
    
    col_add, col_gap = st.columns([1, 4])
    with col_add:
        if st.button("➕ 手動加入空白行"):
            st.session_state['quote_cart'].append({
                "supplier": "手動輸入", "name": "新產品", "cost": 0.0,
                "mode": "設定利潤(%)算售價", "input_val": 12.0, "final_price": 0.0, "profit_dollar": 0.0, "profit_pct": 0.0, "note": ""
            })
            st.rerun()

    # 插入刪除按鈕
    df_cart.insert(0, "🗑️ 刪除", False)

    # 渲染互動表格
    edited_df = st.data_editor(
        df_cart,
        column_config={
            "🗑️ 刪除": st.column_config.CheckboxColumn("🗑️ 刪除", default=False),
            "supplier": st.column_config.TextColumn("供應商 (可修改)"),
            "name": st.column_config.TextColumn("產品名稱 (可修改)"),
            "cost": st.column_config.NumberColumn("成本 ($/LB)", min_value=0.0, format="%.2f"),
            "mode": st.column_config.SelectboxColumn("🧮 運算模式", options=["設定利潤(%)算售價", "直接設定售價($)"]),
            "input_val": st.column_config.NumberColumn("📝 輸入數值", min_value=0.0, format="%.2f", help="輸入如 12 代表 12% 利潤；若選售價模式，輸入如 45 代表賣 $45"),
            "final_price": st.column_config.NumberColumn("🎯 最終售價 ($)", disabled=True, format="%.2f"),
            "profit_dollar": st.column_config.NumberColumn("💰 實賺 ($)", disabled=True, format="%.2f"),
            "profit_pct": st.column_config.NumberColumn("📊 實際利潤 (%)", disabled=True, format="%.1f%%"),
            "note": st.column_config.TextColumn("備註 (可選)")
        },
        use_container_width=True, hide_index=True
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

                # 💡 核心商業邏輯運算
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
                    "cost": cost,
                    "mode": mode,
                    "input_val": inp,
                    "final_price": final_price,
                    "profit_dollar": prof_d,
                    "profit_pct": prof_p,
                    "note": row["note"]
                })
            
            st.session_state['quote_cart'] = new_cart
            st.rerun()
            
    with col3:
        if st.button("🧹 一鍵清空報價車", use_container_width=True):
            st.session_state['quote_cart'] = []
            st.rerun()