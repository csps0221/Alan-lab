import json
import os
from datetime import datetime

from anthropic import Anthropic
from google import genai
from openai import OpenAI
from PIL import Image
import streamlit as st
from streamlit_cropper import st_cropper

# ==========================================
# 0. 系統初始化與主題配色設定
# ==========================================
st.set_page_config(page_title="A.lab 解題實驗室", layout="centered")

THEMES = {
    "全黑夜間": {
        "bg": "#000000",
        "text": "#FFFFFF",
        "primary": "#FFFFFF",
        "primary_text": "#000000",
        "card": "#121212",
        "sub_text": "#CCCCCC",
    },
    "清霧白": {
        "bg": "#F8F9FA",
        "text": "#1A1A1A",
        "primary": "#2D3748",
        "primary_text": "#FFFFFF",
        "card": "#FFFFFF",
        "sub_text": "#718096",
    },
    "燕麥米": {
        "bg": "#F4F1EA",
        "text": "#3D3A36",
        "primary": "#8C7A6B",
        "primary_text": "#FFFFFF",
        "card": "#FAF8F5",
        "sub_text": "#8A837A",
    },
    "森林綠": {
        "bg": "#E8F0EC",
        "text": "#1C3326",
        "primary": "#2D5A44",
        "primary_text": "#FFFFFF",
        "card": "#F2F7F4",
        "sub_text": "#5C7869",
    },
}

# 全局歷史紀錄初始化
if "history_logs" not in st.session_state:
  st.session_state.history_logs = []

# ==========================================
# 1. 帳號與 Session 狀態管理
# ==========================================
ADMIN_USER = "Alan2580"
ADMIN_PASSWORD = "csps106121"
DEFAULT_USER_PASSWORD = "2580"

if "daily_limit" not in st.session_state:
  st.session_state.daily_limit = 5

if "users_db" not in st.session_state:
  st.session_state.users_db = {
      "王小明": {
          "password": DEFAULT_USER_PASSWORD,
          "first_login": True,
          "used_today": 0,
      },
      "張小華": {
          "password": DEFAULT_USER_PASSWORD,
          "first_login": True,
          "used_today": 0,
      },
      "測試使用者": {
          "password": DEFAULT_USER_PASSWORD,
          "first_login": True,
          "used_today": 0,
      },
  }

if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
if "user_role" not in st.session_state:
  st.session_state.user_role = ""
if "user_name" not in st.session_state:
  st.session_state.user_name = ""
if "must_change_password" not in st.session_state:
  st.session_state.must_change_password = False

# --- 側邊選單 ---
if st.session_state.logged_in:
  with st.sidebar:
    st.title("☰ 選單")
    st.write(f"👤 **{st.session_state.user_name}**")
    st.divider()

    if st.session_state.user_role == "admin":
      menu_options = ["⚙️ 系統管理", "📝 開始解題", "📚 所有人解題紀錄"]
    else:
      menu_options = ["📝 開始解題", "📚 我的解題紀錄"]

    menu_option = st.radio(
        "功能導航", menu_options, index=0, label_visibility="collapsed"
    )

    st.divider()
    st.subheader("🎨 視覺主題設定")
    selected_theme = st.selectbox("選擇主題配色", list(THEMES.keys()), index=0)

    st.divider()
    if st.button("🚪 登出", type="secondary", use_container_width=True):
      st.session_state.logged_in = False
      st.session_state.user_role = ""
      st.session_state.user_name = ""
      st.session_state.must_change_password = False
      st.rerun()
else:
  selected_theme = "全黑夜間"
  menu_option = "📝 開始解題"

t = THEMES[selected_theme]

# CSS 設定
st.markdown(
    f"""
<style>
    /* 全局背景與文字 */
    .stApp, div[data-testid="stSidebar"] {{
        background-color: {t["bg"]} !important;
        color: {t["text"]} !important;
    }}
    
    /* 所有文字圖層設置在最上層 */
    p, span, h1, h2, h3, h4, h5, h6, label {{
        color: {t["text"]} !important;
        position: relative;
        z-index: 10;
    }}

    /* 一般按鈕、選單等元件 */
    div.stButton > button, 
    div[data-baseweb="select"] > div, 
    div[data-baseweb="popover"] *, 
    ul[role="listbox"] li {{
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border-color: #FFFFFF !important;
    }}

    /* 🔵 帳號與密碼輸入框（含右側眼睛圖示元件，皆設為深藍色背景、白色文字） */
    input, textarea, div[data-baseweb="input"], div[data-baseweb="input"] > div {{
        background-color: #1E3A8A !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border-color: #1E3A8A !important;
    }}

    /* 密碼顯示/隱藏按鈕圖示樣式優化 */
    div[data-baseweb="input"] button {{
        background-color: #1E3A8A !important;
        color: #FFFFFF !important;
        border: none !important;
    }}

    /* 🔴 專屬登入按鈕（紅色背景、白色文字、懸停不變色） */
    div.login-btn-container button {{
        background-color: #E53E3E !important;
        color: #FFFFFF !important;
        border-color: #E53E3E !important;
        font-weight: bold !important;
    }}

    div.login-btn-container button p,
    div.login-btn-container button span {{
        color: #FFFFFF !important;
    }}

    div.login-btn-container button:hover,
    div.login-btn-container button:active,
    div.login-btn-container button:focus {{
        background-color: #E53E3E !important;
        color: #FFFFFF !important;
        border-color: #E53E3E !important;
        box-shadow: none !important;
    }}

    /* 取消一般元件滑鼠移過（Hover）的變色效果 */
    div.stButton > button:hover,
    div.stButton > button:active,
    div.stButton > button:focus,
    div[data-baseweb="select"] > div:hover,
    ul[role="listbox"] li:hover {{
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border-color: #FFFFFF !important;
        box-shadow: none !important;
    }}

    /* 步驟圖示 */
    .step-number {{
        background-color: #FFFFFF;
        color: #000000 !important;
        border-radius: 50%;
        width: 28px;
        height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 14px;
        margin-right: 10px;
    }}
    
    .step-header {{
        display: flex;
        align-items: center;
        font-size: 18px;
        font-weight: 700;
        color: {t["text"]};
        margin-bottom: 8px;
    }}
    
    .sub-text {{
        color: {t["sub_text"]} !important;
        font-size: 13px;
        margin-left: 38px;
        margin-top: -6px;
        margin-bottom: 14px;
    }}
</style>
""",
    unsafe_allow_html=True,
)

# --- 登入畫面 ---
if not st.session_state.logged_in:
  st.title("🔑 A.lab 登入系統")
  st.caption("請輸入您的姓名/帳號與密碼")

  input_user = st.text_input("姓名 / 管理員帳號")
  input_password = st.text_input("密碼", type="password")

  # 包裹容器套用專屬紅色按鈕 CSS 樣式
  st.markdown('<div class="login-btn-container">', unsafe_allow_html=True)
  login_submitted = st.button("登入", type="primary", use_container_width=True)
  st.markdown("</div>", unsafe_allow_html=True)

  if login_submitted:
    if input_user == ADMIN_USER and input_password == ADMIN_PASSWORD:
      st.session_state.logged_in = True
      st.session_state.user_role = "admin"
      st.session_state.user_name = "系統管理員"
      st.session_state.must_change_password = False
      st.success("歡迎管理者登入！")
      st.rerun()
    elif (
        input_user in st.session_state.users_db
        and st.session_state.users_db[input_user]["password"] == input_password
    ):
      st.session_state.logged_in = True
      st.session_state.user_role = "user"
      st.session_state.user_name = input_user
      if st.session_state.users_db[input_user]["first_login"]:
        st.session_state.must_change_password = True
      else:
        st.session_state.must_change_password = False
      st.rerun()
    else:
      st.error("❌ 帳號或密碼錯誤！")
  st.stop()

# --- 強制修改密碼畫面 ---
if st.session_state.must_change_password:
  st.warning("🔒 這是您首次登入（或密碼已被重置），請先設定新密碼！")
  st.subheader("修改個人密碼")

  pwd1 = st.text_input("請輸入新密碼", type="password")
  pwd2 = st.text_input("再次確認新密碼", type="password")

  if st.button("確認更新密碼", type="primary"):
    if not pwd1 or not pwd2:
      st.error("請輸入完整密碼！")
    elif pwd1 != pwd2:
      st.error("二次輸入的密碼不一致，請重新檢查！")
    elif pwd1 == DEFAULT_USER_PASSWORD:
      st.warning(
          f"新密碼不能與預設密碼 ({DEFAULT_USER_PASSWORD}) 相同，請設定新密碼！"
      )
    else:
      u_name = st.session_state.user_name
      st.session_state.users_db[u_name]["password"] = pwd1
      st.session_state.users_db[u_name]["first_login"] = False
      st.session_state.must_change_password = False
      st.success("🎉 密碼修改成功！即將進入系統...")
      st.rerun()
  st.stop()

# --- 頂部狀態列 ---
top_col1, top_col2 = st.columns([3, 1])
with top_col1:
  role_label = (
      "👑 管理員 (無限次數)"
      if st.session_state.user_role == "admin"
      else "👤 使用者"
  )
  st.write(f"當前使用者：**{st.session_state.user_name}** ({role_label})")
  if st.session_state.user_role == "user":
    user_info = st.session_state.users_db[st.session_state.user_name]
    used = user_info.get("used_today", 0)
    limit = st.session_state.daily_limit
    remains = max(0, limit - used)
    st.caption(f"📊 今日提問額度：**{remains}/{limit}** 題（已用 {used} 題）")

st.divider()

# ==========================================
# 2. API Key 設定與核心邏輯
# ==========================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", "")
SYSTEM_PROMPT = """
你是一位嚴謹的考題解析專家。請分析使用者提供的題目，並嚴格只回傳以下 JSON 格式（不要包含任何 Markdown 標記，直接輸出 JSON 內容）：
{
  "ans": "正確答案選項（例如 A、B、C 或 D，若是非選擇題請給出簡短最終答案）",
  "reasoning": "詳細的解題步驟與觀念說明"
}
"""


def extract_text_from_images(image_list: list, extra_info: str = "") -> str:
  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    ocr_prompt = f"請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明：{extra_info}"
    contents = image_list + [ocr_prompt]
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=contents
    )
    return response.text.strip()
  except Exception as e:
    return f"[圖片辨識失敗]: {str(e)}"


def call_gemini(question_text):
  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{SYSTEM_PROMPT}\n\n題目：{question_text}",
    )
    return response.text
  except Exception as e:
    return json.dumps(
        {"ans": "錯誤", "reasoning": f"Gemini API 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def call_chatgpt(question_text):
  try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"題目：{question_text}"},
        ],
    )
    return response.choices[0].message.content
  except Exception as e:
    return json.dumps(
        {"ans": "錯誤", "reasoning": f"ChatGPT API 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def call_claude(question_text):
  try:
    client = Anthropic(api_key=CLAUDE_API_KEY)
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"題目：{question_text}"}],
    )
    return response.content[0].text
  except Exception as e:
    return json.dumps(
        {"ans": "錯誤", "reasoning": f"Claude API 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def parse_ai_json(raw_text):
  try:
    clean_text = raw_text.strip().replace("```json", "").replace("
