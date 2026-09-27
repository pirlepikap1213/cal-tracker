import streamlit as st

# ページの基本設定 ＆ 自動翻訳防止のHTMLを差し込む
st.set_page_config(page_title="AI食事カロリー・PFC記録", page_icon="🥗", layout="centered")

# 自動翻訳による DOM 衝突（removeChild エラー）を防ぐ設定
st.markdown("""
    <html lang="ja" class="notranslate" translate="no">
    <head>
        <meta name="google" content="notranslate" />
    </head>
""", unsafe_allow_html=True)

import streamlit as st
import pandas as pd
from datetime import datetime
import json
import base64
from openai import OpenAI
from PIL import Image
import os

# --- 設定・クライアント初期化 ---
st.set_page_config(page_title="AI食事カロリー・PFC記録", page_icon="🥗", layout="centered")

api_key = st.secrets.get("OPENAI_API_KEY")
target_calories = st.secrets.get("TARGET_CALORIES", 2000)

if not api_key:
    st.error("OPENAI_API_KEY が設定されていません。Secretsを確認してください。")
    st.stop()

client = OpenAI(api_key=api_key)

# --- データ読み込み・初期化 ---
CSV_FILE = "food_log.csv"

def load_data():
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            if not df.empty and "日付" in df.columns:
                df["日付"] = pd.to_datetime(df["日付"])
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["日付", "食品名", "カロリー(kcal)", "タンパク質(g)", "脂質(g)", "炭水化物(g)"])

def save_data(df):
    df.to_csv(CSV_FILE, index=False)

df_log = load_data()

st.title("🥗 AI食事カロリー・PFC記録アプリ")

# --- 1. スマホ撮影 & PFC推測記録 ---
st.subheader("1. 食事を記録する")

tab1, tab2, tab3 = st.tabs(["📷 カメラで撮影", "📁 画像選択", "💬 テキスト入力"])

uploaded_image_bytes = None
food_input = None

with tab1:
    camera_img = st.camera_input("写真を撮影")
    if camera_img:
        uploaded_image_bytes = camera_img.getvalue()

with tab2:
    file_img = st.file_uploader("写真を選択", type=["jpg", "jpeg", "png"])
    if file_img:
        uploaded_image_bytes = file_img.getvalue()

with tab3:
    text_input = st.text_input("食事内容（例: カツ丼 1杯、ゆで卵 2個）")
    if text_input:
        food_input = text_input

if st.button("AIで解析して記録", type="primary", use_container_width=True):
    if uploaded_image_bytes or food_input:
        with st.spinner("AIがカロリーとPFCバランスを分析中..."):
            
            prompt_system = """
            あなたは管理栄養士AIです。食事内容から概算の「カロリー」「タンパク質(g)」「脂質(g)」「炭水化物(g)」を分析してください。
            回答は必ず以下のJSON形式のみで出力してください（他の文章やMarkdown装飾は含めないでください）。
            {
              "food_name": "食品名（短く分かりやすい名称）",
              "calories": カロリー数値（整数 kcal）,
              "protein": タンパク質数値（整数または小数 g）,
              "fat": 脂質数値（整数または小数 g）,
              "carbs": 炭水化物数値（整数または小数 g）
            }
            """

            messages_content = []

            if uploaded_image_bytes:
                base64_image = base64.b64encode(uploaded_image_bytes).decode('utf-8')
                messages_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })
            
            if food_input:
                messages_content.append({"type": "text", "text": f"食事内容: {food_input}"})
            else:
                messages_content.append({"type": "text", "text": "写真の食事のカロリーとPFCバランスを推測してください。"})

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": prompt_system},
                        {"role": "user", "content": messages_content}
                    ],
                    response_format={"type": "json_object"}
                )

                result = json.loads(response.choices[0].message.content)
                
                food_name = result.get("food_name", "食事記録")
                calories = int(result.get("calories", 0))
                protein = float(result.get("protein", 0))
                fat = float(result.get("fat", 0))
                carbs = float(result.get("carbs", 0))

                now = datetime.now()
                new_data = pd.DataFrame([{
                    "日付": now,
                    "食品名": food_name,
                    "カロリー(kcal)": calories,
                    "タンパク質(g)": protein,
                    "脂質(g)": fat,
                    "炭水化物(g)": carbs
                }])
                
                df_log = pd.concat([df_log, new_data], ignore_index=True)
                save_data(df_log)
                
                st.success(f"【{food_name}】 約 {calories} kcal (P:{protein}g / F:{fat}g / C:{carbs}g)")
                st.rerun()

            except Exception as e:
                st.error(f"解析エラー: {e}")
    else:
        st.warning("写真の撮影・添付またはテキストを入力してください。")

st.divider()

# --- 2. 今日の進捗 & PFCバランス ---
st.subheader("2. 本日の摂取進捗")

if not df_log.empty:
    df_log["年月日"] = pd.to_datetime(df_log["日付"]).dt.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    today_df = df_log[df_log["年月日"] == today_str]
    
    today_cal = today_df["カロリー(kcal)"].sum() if not today_df.empty else 0
    today_p = today_df["タンパク質(g)"].sum() if not today_df.empty else 0
    today_f = today_df["脂質(g)"].sum() if not today_df.empty else 0
    today_c = today_df["炭水化物(g)"].sum() if not today_df.empty else 0

    # 進捗バー表示
    progress = min(today_cal / target_calories, 1.0)
    st.progress(progress)
    
    col1, col2 = st.columns(2)
    col1.metric("今日の合計カロリー", f"{today_cal:,} kcal", delta=f"{today_cal - target_calories} kcal (目標比)", delta_color="inverse")
    col2.metric("目標カロリー", f"{target_calories:,} kcal")

    st.write("**本日のPFCバランス**")
    pfc_col1, pfc_col2, pfc_col3 = st.columns(3)
    pfc_col1.metric("タンパク質 (P)", f"{today_p:.1f} g")
    pfc_col2.metric("脂質 (F)", f"{today_f:.1f} g")
    pfc_col3.metric("炭水化物 (C)", f"{today_c:.1f} g")

st.divider()

# --- 3. 過去のカロリー推移グラフ ---
st.subheader("3. 過去のカロリー推移")

if not df_log.empty:
    daily_summary = df_log.groupby("年月日")["カロリー(kcal)"].sum().reset_index()
    daily_summary = daily_summary.sort_values(by="年月日")
    
    # 過去の折れ線グラフ表示
    st.line_chart(daily_summary.set_index("年月日"))

st.divider()

# --- 4. 履歴一覧とデータの削除 ---
st.subheader("4. 記録の確認・削除")

if not df_log.empty:
    df_display = df_log.copy()
    df_display["日時"] = pd.to_datetime(df_display["日付"]).dt.strftime("%Y-%m-%d %H:%M")
    df_display.insert(0, "削除", False)
    
    edited_df = st.data_editor(
        df_display[["削除", "日時", "食品名", "カロリー(kcal)", "タンパク質(g)", "脂質(g)", "炭水化物(g)"]],
        disabled=["日時", "食品名", "カロリー(kcal)", "タンパク質(g)", "脂質(g)", "炭水化物(g)"],
        hide_index=True,
        use_container_width=True
    )

    if st.button("選択した項目を削除"):
        keep_rows = ~edited_df["削除"]
        df_log_updated = df_log[keep_rows].drop(columns=["年月日"], errors="ignore")
        save_data(df_log_updated)
        st.success("削除しました。")
        st.rerun()
