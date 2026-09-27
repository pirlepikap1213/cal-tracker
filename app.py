import streamlit as st
import pandas as pd
from datetime import datetime
import json
import base64
from openai import OpenAI

# --- ページ基本設定 ＆ ブラウザ自動翻訳エラー防止 ---
st.set_page_config(page_title="AI食事カロリー記録", page_icon="🥗", layout="centered")

st.markdown("""
    <html lang="ja" class="notranslate" translate="no">
    <head>
        <meta name="google" content="notranslate" />
    </head>
""", unsafe_allow_html=True)

# --- APIキー＆目標カロリーの設定 ---
api_key = st.secrets.get("OPENAI_API_KEY")
target_calories = st.secrets.get("TARGET_CALORIES", 2000)

if not api_key:
    st.error("OPENAI_API_KEY が設定されていません。Streamlit Cloudの Secrets から設定してください。")
    st.stop()

client = OpenAI(api_key=api_key)

# --- CSVデータの読み込み・保存処理 ---
CSV_FILE = "food_log.csv"

def load_data():
    try:
        df = pd.read_csv(CSV_FILE)
        if not df.empty and "日付" in df.columns:
            df["日付"] = pd.to_datetime(df["日付"])
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=["日付", "食品名", "推定カロリー(kcal)"])

def save_data(df):
    df.to_csv(CSV_FILE, index=False)

df_log = load_data()

st.title("🥗 AI食事カロリー記録")

# ==========================================
# 1. 本日の進捗状況（ダッシュボード）
# ==========================================
today_str = datetime.now().strftime("%Y-%m-%d")
today_calories = 0

if not df_log.empty:
    df_log["年月日"] = pd.to_datetime(df_log["日付"]).dt.strftime("%Y-%m-%d")
    today_df = df_log[df_log["年月日"] == today_str]
    today_calories = int(today_df["推定カロリー(kcal)"].sum())

# 進捗バーと数値インジケーター
progress = min(today_calories / target_calories, 1.0)
st.progress(progress)

col1, col2 = st.columns(2)
col1.metric("本日の合計", f"{today_calories:,} kcal", delta=f"{today_calories - target_calories} kcal (目標比)", delta_color="inverse")
col2.metric("目標カロリー", f"{target_calories:,} kcal")

st.divider()

# ==========================================
# 2. 食事の記録（写真またはテキスト）
# ==========================================
st.subheader("📝 食事を記録")

tab1, tab2, tab3 = st.tabs(["📷 カメラで撮影", "📁 写真を選択", "💬 テキスト入力"])

uploaded_image_bytes = None
food_input = None

with tab1:
    camera_img = st.camera_input("カメラ撮影")
    if camera_img:
        uploaded_image_bytes = camera_img.getvalue()

with tab2:
    file_img = st.file_uploader("画像ファイル選択", type=["jpg", "jpeg", "png"])
    if file_img:
        uploaded_image_bytes = file_img.getvalue()

with tab3:
    text_input = st.text_input("食事内容を入力（例: カレーライス 1皿）")
    if text_input:
        food_input = text_input

if st.button("AIで解析して記録", type="primary", use_container_width=True):
    if uploaded_image_bytes or food_input:
        with st.spinner("AIがカロリーを推測中..."):
            
            prompt_system = """
            あなたは栄養士AIです。ユーザーが提示した食事内容（テキストまたは画像）から概算カロリー（kcal）を推測してください。
            回答は必ず以下のJSON形式のみで出力してください（余計な説明文やMarkdownは含めないでください）。
            {
              "food_name": "食品名（短く分かりやすい名称）",
              "calories": 数値（整数）
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
                messages_content.append({"type": "text", "text": "画像の食事のカロリーを推測してください。"})

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

                now = datetime.now()
                new_data = pd.DataFrame([{
                    "日付": now,
                    "食品名": food_name,
                    "推定カロリー(kcal)": calories
                }])
                
                # 必要最小限の列に揃えて追加
                df_log_save = pd.concat([df_log[["日付", "食品名", "推定カロリー(kcal)"]], new_data], ignore_index=True)
                save_data(df_log_save)
                
                st.success(f"「{food_name}」（約 {calories} kcal）を記録しました！")
                st.rerun()

            except Exception as e:
                st.error(f"解析エラーが発生しました: {e}")
    else:
        st.warning("写真撮影・選択またはテキストを入力してください。")

st.divider()

# ==========================================
# 3. 本日の記録編集＆過去ログ（タップして表示）
# ==========================================
if not df_log.empty:
    # 削除・編集用のデータセット作成
    df_display = df_log.copy()
    df_display["年月日"] = pd.to_datetime(df_display["日付"]).dt.strftime("%Y-%m-%d")
    df_display["日時"] = pd.to_datetime(df_display["日付"]).dt.strftime("%Y-%m-%d %H:%M")

    # --- 本日の記録＆編集・削除 ---
    st.subheader("✏️ 本日の記録・編集")
    today_records = df_display[df_display["年月日"] == today_str]

    if not today_records.empty:
        st.caption("食品名やカロリーを直接タップして編集できます。削除する場合は「削除」欄にチェックを入れてください。")
        
        # 編集可能なデータエディタ（食品名とカロリーが直接編集できます）
        today_records_edit = today_records[["日時", "食品名", "推定カロリー(kcal)"]].copy()
        today_records_edit.insert(0, "削除", False)
        
        edited_today = st.data_editor(
            today_records_edit,
            column_config={
                "推定カロリー(kcal)": st.column_config.NumberColumn("カロリー(kcal)", min_value=0, step=10, format="%d kcal"),
                "日時": st.column_config.TextColumn("日時", disabled=True)
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("変更・削除を保存", type="secondary"):
            # 削除にチェックが入っていないものを残す
            keep_indices = today_records.index[~edited_today["削除"]]
            
            # 編集後の値を元のdf_logに反映
            for idx, (_, row) in zip(keep_indices, edited_today[~edited_today["削除"]].iterrows()):
                df_log.loc[idx, "食品名"] = row["食品名"]
                df_log.loc[idx, "推定カロリー(kcal)"] = row["推定カロリー(kcal)"]

            # チェックされた削除行を全体のログから除外
            remove_indices = today_records.index[edited_today["削除"]]
            df_log_updated = df_log.drop(index=remove_indices)

            save_data(df_log_updated[["日付", "食品名", "推定カロリー(kcal)"]])
            st.success("記録を更新しました。")
            st.rerun()
    else:
        st.info("本日の記録はまだありません。")

    st.write("")

    # --- 過去の記録（折りたたみ/アコーディオン） ---
    past_records = df_display[df_display["年月日"] != today_str]
    
    with st.expander("📂 過去の記録を見る（タップで開く）"):
        if not past_records.empty:
            # 日別合計サマリー
            past_daily = past_records.groupby("年月日")["推定カロリー(kcal)"].sum().reset_index()
            past_daily = past_daily.sort_values(by="年月日", ascending=False)
            
            st.write("▼ 日別合計一覧")
            st.dataframe(past_daily, use_container_width=True, hide_index=True)

            st.write("▼ 過去の全詳細履歴")
            st.dataframe(
                past_records[["日時", "食品名", "推定カロリー(kcal)"]].sort_values(by="日時", ascending=False),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.write("過去の記録はありません。")
