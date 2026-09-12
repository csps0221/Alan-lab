import base64
from datetime import datetime
from io import BytesIO
import json
import os

from google import genai
from openai import OpenAI
import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_cropper import st_cropper

# ==========================================
# 0. 設定檔存取機制 (Json 本地資料庫)
# ==========================================
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "daily_limit": 5,
    "selected_gemini_model": "gemini-2.0-flash",
    "selected_openai_model": "gpt-4o-mini",
    "enable_gemini": True,
    "enable_openai": True,
    "subjects": ["理化", "生物", "地科", "數學", "其他"],
    "bug_reports": [],
    "users_db": {
        "王小明": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
        },
        "張小華": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
        },
        "測試使用者": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
        },
    },
}


def load_config():
  """載入設定檔，若不存在則建立預設檔"""
  if not os.path.exists(CONFIG_FILE):
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      cfg = json.load(f)
      if "subjects" not in cfg:
        cfg["subjects"] = DEFAULT_CONFIG["subjects"]
      if "bug_reports" not in cfg:
        cfg["bug_reports"] = []
      return cfg
  except Exception:
    return DEFAULT_CONFIG


def save_config_from_session():
  """將目前的 Session 狀態同步儲存至 json 檔案"""
  config_data = {
      "daily_limit": st.session_state.daily_limit,
      "selected_gemini_model": st.session_state.selected_gemini_model,
      "selected_openai_model": st.session_state.selected_openai_model,
      "enable_gemini": st.session_state.enable_gemini,
      "enable_openai": st.session_state.enable_openai,
      "subjects": st.session_state.subjects,
      "bug_reports": st.session_state.bug_reports,
      "users_db": st.session_state.users_db,
  }
  save_config(config_data)


def save_config(config_data):
  """寫入 json 檔案"""
  with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(config_data, f, ensure_ascii=False, indent=4)


def image_to_base64(pil_img):
  buffered = BytesIO()
  pil_img.save(buffered, format="JPEG")
  return base64.b64encode(buffered.getvalue()).decode("utf-8")


def base64_to_image(b64_str):
  img_data = base64.b64decode(b64_str)
  return Image.open(BytesIO(img_data))


# ==========================================
# 1. 系統初始化與【加深版】主題配色設定
# ==========================================
st.set_page_config(
    page_title="A.lab 解題實驗室", page_icon="🧪", layout="centered"
)

config = load_config()

# 🎨 全面加深與強化對比的主題庫
THEMES = {
    "全黑夜間": {
        "bg": "#0B0E14",
        "sidebar_bg": "#12161F",
        "card_bg": "#1A1F2C",
        "text": "#E6EDF3",
        "sub_text": "#9198A1",
        "primary": "#C92A2A",
        "primary_hover": "#A61E1E",
        "input_bg": "#12161F",
        "input_text": "#FFFFFF",
        "border": "#2D3545",
    },
    "極簡純黑": {
        "bg": "#000000",
        "sidebar_bg": "#0A0A0A",
        "card_bg": "#141414",
        "text": "#F0F0F0",
        "sub_text": "#8C8C8C",
        "primary": "#B71C1C",
        "primary_hover": "#8E0000",
        "input_bg": "#1F1F1F",
        "input_text": "#FFFFFF",
        "border": "#2A2A2A",
    },
    "深邃石墨": {
        "bg": "#1A1C1E",
        "sidebar_bg": "#22252A",
        "card_bg": "#2C3036",
        "text": "#ECEFF1",
        "sub_text": "#90A4AE",
        "primary": "#1565C0",
        "primary_hover": "#0D47A1",
        "input_bg": "#22252A",
        "input_text": "#FFFFFF",
        "border": "#373D45",
    },
    "沉穩大地": {
        "bg": "#1C1917",
        "sidebar_bg": "#292524",
        "card_bg": "#3D3A37",
        "text": "#F5F5F4",
        "sub_text": "#A8A29E",
        "primary": "#B45309",
        "primary_hover": "#92400E",
        "input_bg": "#292524",
        "input_text": "#FFFFFF",
        "border": "#524C46",
    },
    "深海藍黑": {
        "bg": "#0F172A",
        "sidebar_bg": "#1E293B",
        "card_bg": "#334155",
        "text": "#F8FAFC",
        "sub_text": "#94A3B8",
        "primary": "#0284C7",
        "primary_hover": "#0369A1",
        "input_bg": "#1E293B",
        "input_text": "#FFFFFF",
        "border": "#475569",
    },
    "沉木墨綠": {
        "bg": "#0D1F17",
        "sidebar_bg": "#142E23",
        "card_bg": "#1D3D30",
        "text": "#ECFDF5",
        "sub_text": "#6EE7B7",
        "primary": "#047857",
        "primary_hover": "#065F46",
        "input_bg": "#142E23",
        "input_text": "#FFFFFF",
        "border": "#275945",
    },
}

if "history_logs" not in st.session_state:
  st.session_state.history_logs = []

MODEL_OPTIONS = {
    "Gemini": [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "ChatGPT": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
}

# 從 json 設定初始化狀態
if "daily_limit" not in st.session_state:
  st.session_state.daily_limit = config.get("daily_limit", 5)

if "users_db" not in st.session_state:
  st.session_state.users_db = config.get(
      "users_db", DEFAULT_CONFIG["users_db"]
  )

if "subjects" not in st.session_state:
  st.session_state.subjects = config.get(
      "subjects", DEFAULT_CONFIG["subjects"]
  )

if "bug_reports" not in st.session_state:
  st.session_state.bug_reports = config.get("bug_reports", [])

if "selected_gemini_model" not in st.session_state:
  st.session_state.selected_gemini_model = config.get(
      "selected_gemini_model", "gemini-2.0-flash"
  )

if "selected_openai_model" not in st.session_state:
  st.session_state.selected_openai_model = config.get(
      "selected_openai_model", "gpt-4o-mini"
  )

if "enable_gemini" not in st.session_state:
  st.session_state.enable_gemini = config.get("enable_gemini", True)

if "enable_openai" not in st.session_state:
  st.session_state.enable_openai = config.get("enable_openai", True)

if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
if "user_role" not in st.session_state:
  st.session_state.user_role = ""
if "user_name" not in st.session_state:
  st.session_state.user_name = ""
if "must_change_password" not in st.session_state:
  st.session_state.must_change_password = False

# --- 帳號設定 ---
ADMIN_USER = "Alan2580"
ADMIN_PASSWORD = "csps106121"
DEFAULT_USER_PASSWORD = "2580"

# --- 側邊選單與主題選擇 ---
if st.session_state.logged_in:
  with st.sidebar:
    st.title("☰ 選單")
    st.write(f"👤 **{st.session_state.user_name}**")
    st.divider()

    if st.session_state.user_role == "admin":
      menu_options = [
          "⚙️ 系統管理",
          "🐛 使用者錯誤回報",
          "📝 開始解題",
          "📚 所有人解題紀錄",
      ]
    else:
      menu_options = ["📝 開始解題", "📚 我的解題紀錄"]

    menu_option = st.radio(
        "功能導航", menu_options, index=0, label_visibility="collapsed"
    )

    # 管理員模型開關與版本切換
    if st.session_state.user_role == "admin":
      st.divider()
      st.subheader("🤖 AI 模型開關與版本控制")

      g_chk = st.checkbox(
          "啟用 Gemini 模型", value=st.session_state.enable_gemini
      )
      if g_chk != st.session_state.enable_gemini:
        st.session_state.enable_gemini = g_chk
        save_config_from_session()

      if st.session_state.enable_gemini:
        g_sel = st.selectbox(
            "Gemini 模型版本",
            MODEL_OPTIONS["Gemini"],
            index=MODEL_OPTIONS["Gemini"].index(
                st.session_state.selected_gemini_model
            ),
        )
        if g_sel != st.session_state.selected_gemini_model:
          st.session_state.selected_gemini_model = g_sel
          save_config_from_session()

      o_chk = st.checkbox(
          "啟用 ChatGPT 模型", value=st.session_state.enable_openai
      )
      if o_chk != st.session_state.enable_openai:
        st.session_state.enable_openai = o_chk
        save_config_from_session()

      if st.session_state.enable_openai:
        o_sel = st.selectbox(
            "ChatGPT 模型版本",
            MODEL_OPTIONS["ChatGPT"],
            index=MODEL_OPTIONS["ChatGPT"].index(
                st.session_state.selected_openai_model
            ),
        )
        if o_sel != st.session_state.selected_openai_model:
          st.session_state.selected_openai_model = o_sel
          save_config_from_session()

    st.divider()
    st.subheader("🎨 視覺主題設定")
    selected_theme = st.selectbox(
        "選擇風格主題", list(THEMES.keys()), index=0, key="theme_selector"
    )

    st.divider()
    if st.button("🚪 登出", use_container_width=True):
      st.session_state.logged_in = False
      st.session_state.user_role = ""
      st.session_state.user_name = ""
      st.session_state.must_change_password = False
      st.rerun()
else:
  selected_theme = "全黑夜間"
  menu_option = "📝 開始解題"

# 取得目前選定的主題顏色字典
t = THEMES[selected_theme]

# 注入加深版動態全域 CSS 美化
st.markdown(
    f"""
<style>
    /* 全局背景與文字 */
    .stApp {{
        background-color: {t["bg"]} !important;
        color: {t["text"]} !important;
    }}
    section[data-testid="stSidebar"] {{
        background-color: {t["sidebar_bg"]} !important;
        border-right: 1px solid {t["border"]} !important;
    }}
    p, span, h1, h2, h3, h4, h5, h6, label, div {{
        color: {t["text"]} !important;
    }}
    
    /* 按鈕樣式 (含 Hover 動效) */
    div.stButton > button,
    button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-primary"] {{
        background-color: {t["primary"]} !important;
        color: #FFFFFF !important;
        border: 1px solid {t["primary"]} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.2s ease-in-out !important;
    }}
    div.stButton > button *, button * {{
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }}
    div.stButton > button:hover,
    div.stButton > button:focus,
    div.stButton > button:active {{
        background-color: {t["primary_hover"]} !important;
        border-color: {t["primary_hover"]} !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
        transform: translateY(-1px);
    }}
    
    /* 輸入框與文字域 */
    input, textarea, div[data-baseweb="input"] > div {{
        background-color: {t["input_bg"]} !important;
        color: {t["input_text"]} !important;
        -webkit-text-fill-color: {t["input_text"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 6px !important;
    }}
    
    /* 下拉選單 & 彈窗卡片 */
    div[data-baseweb="select"] > div,
    div[data-baseweb="popover"] *,
    ul[role="listbox"] li {{
        background-color: {t["card_bg"]} !important;
        color: {t["text"]} !important;
        border-color: {t["border"]} !important;
    }}
    
    /* Expander 折疊面板卡片化 */
    div[data-testid="stExpander"] {{
        background-color: {t["card_bg"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
    }}
    
    /* Status & Alerts 區塊背景 */
    div[data-testid="stStatusWidget"] {{
        background-color: {t["card_bg"]} !important;
        border: 1px solid {t["border"]} !important;
    }}
    
    /* 自訂步驟標題 */
    .step-number {{
        background-color: {t["primary"]};
        color: #FFFFFF !important;
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

  login_submitted = st.button("登入", use_container_width=True)

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

  if st.button("確認更新密碼", use_container_width=True):
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
      save_config_from_session()
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
GEMINI_API_KEY = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
OPENAI_API_KEY = str(st.secrets.get("OPENAI_API_KEY", "")).strip()

SYSTEM_PROMPT = """
你是一位嚴謹的考題解析專家。請分析使用者提供的題目，並嚴格只回傳以下 JSON 格式（不要包含任何 Markdown 標記，補充繁體中文解析）：
{
  "ans": "正確答案選項（例如 A、B、C 或 D，若是非選擇題請給出簡短最終答案）",
  "reasoning": "詳細的解題步驟與觀念說明"
}
"""


def extract_text_from_images(image_list: list, extra_info: str = "") -> str:
  if not GEMINI_API_KEY:
    return "[圖片辨識失敗]: 請先在 Streamlit Secrets 設定 GEMINI_API_KEY"

  ocr_prompt = f"請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明：{extra_info}"

  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    clean_model = st.session_state.selected_gemini_model.replace("models/", "")
    models_to_try = [
        clean_model,
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
    ]

    for model_name in models_to_try:
      try:
        contents = image_list + [ocr_prompt]
        response = client.models.generate_content(
            model=model_name, contents=contents
        )
        if response and response.text:
          return response.text.strip()
      except Exception:
        continue
    return (
        "[圖片辨識失敗]: 模型無法辨識內容，請確認 Gemini API Key"
        " 是否有效。"
    )
  except Exception as e:
    return f"[圖片辨識失敗]: {str(e)}"


def call_gemini(question_text):
  if not GEMINI_API_KEY:
    return json.dumps(
        {
            "ans": "未設定 Key",
            "reasoning": "未在 Secrets 中設定 GEMINI_API_KEY。",
        },
        ensure_ascii=False,
    )

  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    clean_model = st.session_state.selected_gemini_model.replace("models/", "")
    models_to_try = [
        clean_model,
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
    ]
    last_err = ""

    for m_name in models_to_try:
      try:
        response = client.models.generate_content(
            model=m_name,
            contents=f"{SYSTEM_PROMPT}\n\n題目：{question_text}",
        )
        if response and response.text:
          return response.text
      except Exception as err:
        last_err = str(err)
        continue

    return json.dumps(
        {"ans": "失敗", "reasoning": f"Gemini API 呼叫失敗: {last_err}"},
        ensure_ascii=False,
    )
  except Exception as e:
    return json.dumps(
        {"ans": "失敗", "reasoning": f"Gemini API 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def call_chatgpt(question_text):
  if not OPENAI_API_KEY:
    return json.dumps(
        {
            "ans": "未設定 Key",
            "reasoning": "未在 Secrets 中設定 OPENAI_API_KEY。",
        },
        ensure_ascii=False,
    )
  try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=st.session_state.selected_openai_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"題目：{question_text}"},
        ],
    )
    return response.choices[0].message.content
  except Exception as e:
    return json.dumps(
        {"ans": "失敗", "reasoning": f"ChatGPT API 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def parse_ai_json(raw_text):
  try:
    clean_text = (
        raw_text.strip().replace("```json", "").replace("```", "").strip()
    )
    data = json.loads(clean_text)
    ans = data.get("ans", "未知").strip().upper()
    reasoning = data.get("reasoning", "無解析內容")
    return ans, reasoning
  except Exception:
    return "格式解析失敗", raw_text


# ==========================================
# 3. 頁面渲染分流
# ==========================================

# ⚙️ 頁面 1：管理員後台控制頁面
if menu_option == "⚙️ 系統管理":
  st.title("⚙️ 管理員控制後台")
  st.caption("調整系統設定、管理科目與使用者狀態")

  # --- 📚 科目清單管理 ---
  st.subheader("📚 管理科目選單")
  st.write(
      "目前的科目：", " | ".join([f"`{s}`" for s in st.session_state.subjects])
  )

  col_s1, col_s2 = st.columns([3, 1])
  new_sub = col_s1.text_input(
      "新增科目名稱", placeholder="例如：地科、歷史", key="add_sub_input"
  )
  if col_s2.button("➕ 新增科目"):
    if new_sub.strip():
      if new_sub in st.session_state.subjects:
        st.warning("該科目已存在！")
      else:
        st.session_state.subjects.append(new_sub.strip())
        save_config_from_session()
        st.success(f"已成功新增科目：{new_sub}")
        st.rerun()

  del_sub = st.selectbox(
      "選擇要刪除的科目", ["請選擇"] + st.session_state.subjects
  )
  if st.button("🗑️ 刪除選取科目"):
    if del_sub != "請選擇":
      st.session_state.subjects.remove(del_sub)
      save_config_from_session()
      st.success(f"已刪除科目：{del_sub}")
      st.rerun()

  st.divider()

  st.subheader("🤖 AI 模型關閉與版本控制")
  mod_col1, mod_col2 = st.columns(2)
  with mod_col1:
    g_check = st.checkbox(
        "啟用 Gemini 模型",
        value=st.session_state.enable_gemini,
        key="admin_gemini_chk",
    )
    if g_check != st.session_state.enable_gemini:
      st.session_state.enable_gemini = g_check
      save_config_from_session()

    if st.session_state.enable_gemini:
      g_sel_val = st.selectbox(
          "Gemini 模型選擇",
          MODEL_OPTIONS["Gemini"],
          index=MODEL_OPTIONS["Gemini"].index(
              st.session_state.selected_gemini_model
          ),
          key="admin_gemini_sel",
      )
      if g_sel_val != st.session_state.selected_gemini_model:
        st.session_state.selected_gemini_model = g_sel_val
        save_config_from_session()

  with mod_col2:
    o_check = st.checkbox(
        "啟用 ChatGPT 模型",
        value=st.session_state.enable_openai,
        key="admin_openai_chk",
    )
    if o_check != st.session_state.enable_openai:
      st.session_state.enable_openai = o_check
      save_config_from_session()

    if st.session_state.enable_openai:
      o_sel_val = st.selectbox(
          "ChatGPT 模型選擇",
          MODEL_OPTIONS["ChatGPT"],
          index=MODEL_OPTIONS["ChatGPT"].index(
              st.session_state.selected_openai_model
          ),
          key="admin_openai_sel",
      )
      if o_sel_val != st.session_state.selected_openai_model:
        st.session_state.selected_openai_model = o_sel_val
        save_config_from_session()

  st.divider()
  st.subheader("🎯 每日提問額度設定")
  new_limit = st.number_input(
      "全站使用者每日預設可提問數",
      min_value=1,
      max_value=100,
      value=st.session_state.daily_limit,
  )
  if st.button("更新預設每日題數上限"):
    st.session_state.daily_limit = new_limit
    save_config_from_session()
    st.success(f"已將每日提問上限更新為：{new_limit} 題，並完成存檔！")
    st.rerun()

  st.divider()
  st.subheader("➕ 新增使用者帳號")
  c1, c2 = st.columns(2)
  new_name = c1.text_input("使用者姓名", key="new_u_name")
  new_pass = c2.text_input(
      "預設密碼", value=DEFAULT_USER_PASSWORD, key="new_u_pass"
  )

  if st.button("新增使用者帳號"):
    if new_name and new_pass:
      st.session_state.users_db[new_name] = {
          "password": new_pass,
          "first_login": True,
          "used_today": 0,
      }
      save_config_from_session()
      st.success(
          f"已成功新增使用者：{new_name}（預設密碼：{new_pass}）！"
      )
      st.rerun()
    else:
      st.warning("請填寫姓名與預設密碼！")

  st.divider()
  st.subheader("📋 目前使用者名單與狀態管理")

  for u_name, info in list(st.session_state.users_db.items()):
    col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 1, 1])
    col_a.write(f"**姓名**：{u_name}")

    used = info.get("used_today", 0)
    col_b.write(f"**今日使用**：`{used}/{st.session_state.daily_limit}` 題")

    if col_c.button("🔄 重置題數", key=f"reset_limit_{u_name}"):
      st.session_state.users_db[u_name]["used_today"] = 0
      save_config_from_session()
      st.toast(f"已重置 {u_name} 今日已用題數為 0，並存檔！")
      st.rerun()

    if col_d.button("🔑 還原密碼", key=f"reset_pwd_{u_name}"):
      st.session_state.users_db[u_name]["password"] = DEFAULT_USER_PASSWORD
      st.session_state.users_db[u_name]["first_login"] = True
      save_config_from_session()
      st.toast(f"已將 {u_name} 的密碼重置為預設值，並存檔！")
      st.rerun()

    if col_e.button("🗑️", key=f"del_{u_name}"):
      del st.session_state.users_db[u_name]
      save_config_from_session()
      st.toast(f"已刪除 {u_name}，並更新存檔！")
      st.rerun()

# 🐛 頁面 1.5：管理員查看錯誤回報頁面
elif menu_option == "🐛 使用者錯誤回報":
  st.title("🐛 使用者錯誤回報管理")
  st.caption("檢視使用者送出的問題與截圖報告")
  st.divider()

  reports = st.session_state.bug_reports

  if not reports:
    st.info("目前沒有任何錯誤回報！")
  else:
    st.write(f"共收到 **{len(reports)}** 則問題回報：")

    for idx, item in enumerate(reversed(reports)):
      real_idx = len(reports) - 1 - idx
      status_tag = (
          "✅ 已處理" if item.get("status") == "resolved" else "⏳ 待處理"
      )

      with st.expander(
          f"📌 [{item['time']}] 回報人：{item['user']} | 狀態：{status_tag}"
      ):
        st.write(f"**回報時間**：{item['time']}")
        st.write(f"**回報人**：{item['user']}")
        st.write("**問題描述**：")
        st.info(item["description"])

        if item.get("image_b64"):
          st.write("**附帶照片 / 截圖：**")
          img = base64_to_image(item["image_b64"])
          st.image(img, use_container_width=True)

        col_b1, col_b2 = st.columns(2)
        if item.get("status") != "resolved":
          if col_b1.button("標記為已處理", key=f"resolve_{real_idx}"):
            st.session_state.bug_reports[real_idx]["status"] = "resolved"
            save_config_from_session()
            st.toast("已標記為處理完成！")
            st.rerun()

        if col_b2.button("刪除此回報", key=f"del_bug_{real_idx}"):
          st.session_state.bug_reports.pop(real_idx)
          save_config_from_session()
          st.toast("已成功刪除此筆回報！")
          st.rerun()

# 📚 頁面 2：解題紀錄頁面
elif menu_option in ["📚 我的解題紀錄", "📚 所有人解題紀錄"]:
  title_text = (
      "📚 全站解題紀錄"
      if st.session_state.user_role == "admin"
      else "📚 我的解題紀錄"
  )
  st.title(title_text)
  st.caption("歷次檢索與解析紀錄匯總與備份存檔")
  st.divider()

  base_logs = (
      st.session_state.history_logs
      if st.session_state.user_role == "admin"
      else [
          log
          for log in st.session_state.history_logs
          if log["user"] == st.session_state.user_name
      ]
  )

  if not base_logs:
    st.info("目前尚無任何解題紀錄！")
  else:
    st.subheader("🔍 條件篩選與存檔下載")
    filter_col1, filter_col2 = st.columns(2)

    available_users = ["全部使用者"] + list(
        set([log["user"] for log in base_logs])
    )
    available_subjects = ["全部科目"] + st.session_state.subjects

    with filter_col1:
      selected_user_filter = (
          st.selectbox("選擇使用者", available_users)
          if st.session_state.user_role == "admin"
          else st.session_state.user_name
      )

    with filter_col2:
      selected_subject_filter = st.selectbox("選擇科目", available_subjects)

    filtered_logs = base_logs
    if selected_user_filter != "全部使用者":
      filtered_logs = [
          log for log in filtered_logs if log["user"] == selected_user_filter
      ]
    if selected_subject_filter != "全部科目":
      filtered_logs = [
          log
          for log in filtered_logs
          if log["subject"] == selected_subject_filter
      ]

    st.caption(f"共找到 **{len(filtered_logs)}** 筆符合條件的紀錄")

    if filtered_logs:
      dl_col1, dl_col2 = st.columns(2)

      json_data = json.dumps(filtered_logs, ensure_ascii=False, indent=2)
      dl_col1.download_button(
          label="💾 存檔下載 (JSON 檔)",
          data=json_data,
          file_name=(
              f"alab_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
          ),
          mime="application/json",
          use_container_width=True,
      )

      df = pd.DataFrame(filtered_logs)
      csv_data = df.to_csv(index=False).encode("utf-8-sig")
      dl_col2.download_button(
          label="📊 存檔下載 (Excel CSV 檔)",
          data=csv_data,
          file_name=(
              f"alab_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
          ),
          mime="text/csv",
          use_container_width=True,
      )

    st.divider()

    if not filtered_logs:
      st.warning("沒有找到符合選取條件的紀錄。")
    else:
      for item in reversed(filtered_logs):
        with st.expander(
            f"📌 [{item['time']}] 使用者：{item['user']} |"
            f" 科目：{item['subject']} - 答案：{item['ans']}"
        ):
          st.write(f"**提問人**：{item['user']}")
          st.write(f"**提問時間**：{item['time']}")
          st.write(f"**科目**：{item['subject']}")
          st.write(f"**補充說明**：{item['extra_info'] or '無'}")
          st.write("**解析說明**：")
          st.write(item["reasoning"])

# 📝 頁面 3：開始解題頁面
elif menu_option == "📝 開始解題":
  st.caption("A.LAB")
  st.title("自然科解題實驗室")
  st.caption("拆解步驟，訂正錯誤，清晰脈絡，梳理思路")
  st.divider()

  st.markdown(
      """
    <div class="step-header"><span class="step-number">1</span>上傳題目圖片</div>
    <div class="sub-text">可上傳 1~6 張，題目與解答皆可上傳</div>
    """,
      unsafe_allow_html=True,
  )

  uploaded_files = st.file_uploader(
      "",
      type=["png", "jpg", "jpeg"],
      accept_multiple_files=True,
      label_visibility="collapsed",
  )

  if "cropped_images" not in st.session_state:
    st.session_state.cropped_images = {}

  if uploaded_files:
    if len(uploaded_files) > 6:
      st.error("⚠️ 最多上傳 6 張圖片！")
    else:
      tabs = st.tabs([f"圖片 {i+1}" for i in range(len(uploaded_files))])
      for idx, file in enumerate(uploaded_files):
        with tabs[idx]:
          raw_img = Image.open(file)
          cropped_img = st_cropper(
              raw_img,
              realtime_update=True,
              box_color=t["primary"],
              key=f"crop_{idx}",
          )
          st.session_state.cropped_images[idx] = cropped_img

  st.divider()

  st.markdown(
      """
    <div class="step-header"><span class="step-number">2</span>設定題目資訊</div>
    <div class="sub-text">科目、參考答案與補充敘述</div>
    """,
      unsafe_allow_html=True,
  )

  subject = st.selectbox("科目", st.session_state.subjects)
  std_answer = st.text_input(
      "標準參考答案（選填）", placeholder="例如 B、ACD、2.5 mol..."
  )
  extra_info = st.text_input(
      "補充敘述（選填）", placeholder="有需要再補充，例如：想特別問 C 選項"
  )

  col_btn1, col_btn2 = st.columns(2)
  with col_btn1:
    start_btn = st.button("開始解題", use_container_width=True)
  with col_btn2:
    clear_btn = st.button("清除目前題目", use_container_width=True)

  st.divider()

  st.markdown(
      """
    <div class="step-header"><span class="step-number">3</span>觀念解析與 AI 交叉驗證</div>
    <div class="sub-text">答案 ➔ 觀念解析 ➔ 多模態選項比對</div>
    """,
      unsafe_allow_html=True,
  )

  if start_btn:
    can_submit = True

    if not st.session_state.enable_gemini and not st.session_state.enable_openai:
      can_submit = False
      st.error("⚠️ 管理員已將所有 AI 模型關閉，目前無法進行解題！")

    if st.session_state.user_role == "user" and can_submit:
      u_name = st.session_state.user_name
      used = st.session_state.users_db[u_name].get("used_today", 0)
      limit = st.session_state.daily_limit
      if used >= limit:
        can_submit = False
        st.error(
            f"⚠️ 您今日的提問額度（{limit}"
            " 題）已用完！請明日再試或聯繫管理員。"
        )

    if can_submit:
      final_images = (
          [
              st.session_state.cropped_images[i]
              for i in range(len(uploaded_files))
              if i in st.session_state.cropped_images
          ]
          if uploaded_files
          else []
      )

      if not final_images:
        st.warning("請先上傳至少一張題目圖片！")
      else:
        if st.session_state.user_role == "user":
          st.session_state.users_db[st.session_state.user_name][
              "used_today"
          ] += 1
          save_config_from_session()

        with st.status(
            "🚀 實驗室正在解析題目與進行 AI 比對...", expanded=True
        ) as status:
          st.write("🔍 **步驟 1**：Gemini 多圖視覺 OCR 辨識中...")
          q_text = extract_text_from_images(final_images, extra_info)

          st.write("🤖 **步驟 2**：啟用之 AI 模型平行呼叫中...")

          if st.session_state.enable_gemini:
            g_raw = call_gemini(q_text)
            g_ans, g_reason = parse_ai_json(g_raw)
          else:
            g_ans, g_reason = "未啟用", "管理員已關閉此模型"

          if st.session_state.enable_openai:
            c_raw = call_chatgpt(q_text)
            c_ans, c_reason = parse_ai_json(c_raw)
          else:
            c_ans, c_reason = "未啟用", "管理員已關閉此模型"

          main_ans = g_ans if st.session_state.enable_gemini else c_ans
          main_reason = (
              g_reason if st.session_state.enable_gemini else c_reason
          )

          now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
          st.session_state.history_logs.append({
              "user": st.session_state.user_name,
              "time": now_str,
              "subject": subject,
              "ans": main_ans,
              "reasoning": main_reason,
              "extra_info": extra_info,
          })

          status.update(label="🎉 解析完成！", state="complete")

        active_answers = []
        if st.session_state.enable_gemini:
          active_answers.append(g_ans)
        if st.session_state.enable_openai:
          active_answers.append(c_ans)

        valid_answers = [
            ans
            for ans in active_answers
            if ans not in ["未設定 Key", "失敗", "格式解析失敗", "未知", "未啟用"]
        ]

        if valid_answers and len(set(valid_answers)) == 1:
          st.success(f"✅ **AI 驗證答案一致：【 {valid_answers[0]} 】**")
        elif len(valid_answers) > 1 and len(set(valid_answers)) > 1:
          st.warning(
              f"⚠️ **AI 答案存在分歧！** (Gemini: {g_ans} | ChatGPT: {c_ans})"
          )
        elif valid_answers:
          st.info(
              f"💡 **AI 解析答案：【 {valid_answers[0]} 】** (單模型模式)"
          )
        else:
          st.error(
              "❌ 無法取得有效答案，請檢查 Secrets 中的 API Key"
              " 設定與剩餘額度。"
          )

        enabled_count = sum([
            st.session_state.enable_gemini,
            st.session_state.enable_openai,
        ])
        if enabled_count > 0:
          res_cols = st.columns(enabled_count)
          col_idx = 0

          if st.session_state.enable_gemini:
            with res_cols[col_idx]:
              st.subheader(
                  f"🤖 Gemini ({st.session_state.selected_gemini_model})"
              )
              st.write(f"**答案**：`{g_ans}`")
              st.write(g_reason)
            col_idx += 1

          if st.session_state.enable_openai:
            with res_cols[col_idx]:
              st.subheader(
                  f"🟢 ChatGPT ({st.session_state.selected_openai_model})"
              )
              st.write(f"**答案**：`{c_ans}`")
              st.write(c_reason)
            col_idx += 1

  else:
    st.info(
        "尚未產生題目詳解，完成上方步驟並點擊「開始解題」後，解析會顯示在這裡。"
    )

  # --- 🐛 使用者錯誤/問題回報區塊 ---
  st.divider()
  with st.expander("🚨 發現題目解析有誤或系統異常？點此向管理員回報"):
    st.write("若 AI 解析錯誤或圖片讀取失敗，請填寫以下資訊回報給管理員處理：")
    bug_desc = st.text_area(
        "請詳細說明遇到的問題或錯誤答案", key="bug_desc_input"
    )
    bug_img_file = st.file_uploader(
        "上傳問題畫面/題目照片（選填）",
        type=["png", "jpg", "jpeg"],
        key="bug_img_input",
    )

    if st.button("📤 送出問題回報", use_container_width=True):
      if not bug_desc.strip():
        st.warning("請先填寫問題說明再送出！")
      else:
        img_b64 = ""
        if bug_img_file is not None:
          pil_bug_img = Image.open(bug_img_file)
          img_b64 = image_to_base64(pil_bug_img)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_data = {
            "user": st.session_state.user_name,
            "time": now_str,
            "description": bug_desc.strip(),
            "image_b64": img_b64,
            "status": "pending",
        }

        st.session_state.bug_reports.append(report_data)
        save_config_from_session()
        st.success(
            "🎉"
            " 回報已成功送出！管理員會盡快檢視與處理，謝謝你的協助。"
        )