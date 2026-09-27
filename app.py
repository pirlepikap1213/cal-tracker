import streamlit as st
import pandas as pd
from datetime import datetime
import json
from openai import OpenAI

# セキュリティ対策：APIキーはStreamlitのSecret管理機能から安全に取得
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

CSV_FILE = "food_log.csv"

try:
    df_log = pd.read_csv(CSV_FILE)
except FileNotFoundError:
    df_log = pd.DataFrame(columns=["日付", "食品名", "推定カロリー(kcal)"])
    df_log.to_csv(CSV_FILE, index=False)

st.title("🥗 AIカロリー記録アプリ")

food_input = st.text_input("食べたものを入力してください")

if st.button("記録する"):
    if food_input:
        with st.spinner("AI推測中..."):
            prompt = f'食事: "{food_input}" のカロリーを推測し、{{"food_name": "名称", "calories": 数値}} のJSON形式のみで返してください。'
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            food_name = result.get("food_name", food_input)
            calories = int(result.get("calories", 0))

            today = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_data = pd.DataFrame([{"日付": today, "食品名": food_name, "推定カロリー(kcal)": calories}])
            
            df_log = pd.concat([df_log, new_data], ignore_index=True)
            df_log.to_csv(CSV_FILE, index=False)
            
            st.success(f"「{food_name}」を記録しました！（約 {calories} kcal）")

st.divider()
if not df_log.empty:
    st.metric(label="累計カロリー", value=f"{df_log['推定カロリー(kcal)'].sum():,} kcal")
    st.dataframe(df_log.sort_values(by="日付", ascending=False), use_container_width=True)
