import streamlit as st
import pandas as pd
from datetime import datetime
import json
import base64
from openai import OpenAI
from PIL import Image

# --- APIキーの設定 ---
api_key = st.secrets.get("OPENAI_API_KEY")

if not api_key:
    st.error("OPENAI_API_KEY が設定されていません。Streamlit Cloudの Secrets から設定してください。")
    st.stop()

client = OpenAI(api_key=api_key)

# --- CSVファイルの読み込みと初期化 ---
CSV_FILE = "food_log.csv"

try:
    df_log = pd.read_csv(CSV_FILE)
    if not df_log.empty and "日付" in df_log.columns:
        df_log["日付"] = pd.to_datetime(df_log["日付"])
except (FileNotFoundError, pd.errors.EmptyDataError):
    df_log = pd.DataFrame(columns=["日付", "食品名", "推定カロリー(kcal)"])
    df_log.to_csv(CSV_FILE, index=False)

st.title("🥗 AI食事カロリー記録・計算アプリ")

# --- 1. 食べたものを記録する (テキスト or 写真) ---
st.subheader("1. 食べたものを記録する")

tab1, tab2 = st.tabs(["💬 テキストで入力", "📷 写真を添付"])

food_input = None
uploaded_image_bytes = None

with tab1:
    text_input = st.text_input("食べたものを入力（例: カレーライス 1皿、ゆで卵 2個）")
    if text_input:
        food_input = text_input

with tab2:
    img_file = st.file_uploader("食事の写真をアップロードしてください", type=["jpg", "jpeg", "png"])
    if img_file:
        uploaded_image_bytes = img_file.getvalue()
        st.image(uploaded_image_bytes, caption="アップロードした画像", use_container_width=True)

if st.button("カロリーを推測して記録"):
    if food_input or uploaded_image_bytes:
        with st.spinner("AIがカロリーを推測中..."):
            
            prompt_system = """
            あなたは栄養士AIです。ユーザーが提示した食事の内容（テキストまたは画像）から、概算カロリー（kcal）を推測してください。
            回答は必ず以下のJSON形式のみで出力してください（余計な説明文やMarkdown装飾は一切含めないでください）。
            {
              "food_name": "食品名（短く分かりやすい名称）",
              "calories": 数値（整数）
            }
            """

            # OpenAIに送るメッセージの作成
            messages_content = []

            if uploaded_image_bytes:
                # 画像をBase64エンコード
                base64_image = base64.b64encode(uploaded_image_bytes).decode('utf-8')
                mime_type = img_file.type
                messages_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                })
            
            if food_input:
                messages_content.append({"type": "text", "text": f"食事内容: {food_input}"})
            else:
                messages_content.append({"type": "text", "text": "添付した画像の食事カロリーを推測してください。"})

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
                
                food_name = result.get("food_name", food_input if food_input else "画像での記録")
                calories = int(result.get("calories", 0))

                # データの追加
                now = datetime.now()
                new_data = pd.DataFrame([{"日付": now, "食品名": food_name, "推定カロリー(kcal)": calories}])
                
                df_log = pd.concat([df_log, new_data], ignore_index=True)
                df_log.to_csv(CSV_FILE, index=False)
                
                st.success(f"「{food_name}」を記録しました！（約 {calories} kcal）")
                st.rerun()

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
    else:
        st.warning("テキストを入力するか、写真を添付してください。")

st.divider()

# --- 2. 日ごとの摂取カロリー集計 ---
st.subheader("2. 日ごとの摂取カロリー")

if not df_log.empty:
    df_log["年月日"] = pd.to_datetime(df_log["日付"]).dt.strftime("%Y-%m-%d")
    
    daily_summary = df_log.groupby("年月日")["推定カロリー(kcal)"].sum().reset_index()
    daily_summary = daily_summary.sort_values(by="年月日", ascending=False)

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_calories = daily_summary[daily_summary["年月日"] == today_str]["推定カロリー(kcal)"].sum()
    st.metric(label="本日の合計摂取カロリー", value=f"{today_calories:,} kcal")

    st.write("▼ 日別合計一覧")
    st.dataframe(daily_summary, use_container_width=True)
else:
    st.info("まだ記録がありません。")

st.divider()

# --- 3. 履歴一覧とデータの削除 ---
st.subheader("3. 記録の個別確認・削除")

if not df_log.empty:
    st.write("削除したい記録のチェックボックスにチェックを入れて「選択した項目を削除」を押してください。")

    df_display = df_log.copy()
    df_display["日時"] = pd.to_datetime(df_display["日付"]).dt.strftime("%Y-%m-%d %H:%M")
    
    df_display.insert(0, "削除", False)
    
    edited_df = st.data_editor(
        df_display[["削除", "日時", "食品名", "推定カロリー(kcal)"]],
        disabled=["日時", "食品名", "推定カロリー(kcal)"],
        hide_index=True,
        use_container_width=True
    )

    if st.button("選択した項目を削除", type="primary"):
        keep_rows = ~edited_df["削除"]
        df_log_updated = df_log[keep_rows].drop(columns=["年月日"], errors="ignore")
        df_log_updated.to_csv(CSV_FILE, index=False)
        
        st.success("選択した記録を削除しました。")
        st.rerun()
