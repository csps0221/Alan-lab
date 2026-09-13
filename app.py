import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
import os
import random
import threading
import time

from google import genai
from google.genai.errors import APIError
from openai import OpenAI
import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_cropper import st_cropper

# ==========================================
# 0. 安全的設定檔存取機制 (Json 本地資料庫)
# ==========================================
CONFIG_FILE = "config.json"
FILE_LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "daily_limit": 5,
    "selected_gemini_model": "gemini-2.5-flash",
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
        "測試使用者": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
        },
    },
}


def load_config():
  if not os.path.exists(CONFIG_FILE):
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      cfg = json.load(f)
      for key, val in DEFAULT_CONFIG.items():
        if key not in cfg:
          cfg[key] = val
      return cfg
  except Exception as e:
    st.error(f"載入設定檔失敗，已還原為預設設定: {e}")
    return DEFAULT_CONFIG


def save_config(config_data):
  with FILE_LOCK:
    temp_file = f"{CONFIG_FILE}.tmp"
    try:
      with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)
      os.replace(temp_file, CONFIG_FILE)
    except Exception as e:
      if os.path.exists(temp_file):
        os.remove(temp_file)
      st.error(f"儲存設定失敗: {e}")


def save_config_from_session():
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


def base64_to_image(b64_str):
  img_data = base64.b64decode(b64_str)
  return Image.open(BytesIO(img_data))


# ---------------------------------------------------------
# 模型名稱過濾與舊模型自動校正 (修復 404 NOT_FOUND 錯誤)
# ---------------------------------------------------------
def sanitize_model_name(model_name: str) -> str:
  clean = str(model_name).replace("models/", "").strip()
  deprecated_map = {
      "gemini-1.5-flash": "gemini-2.5-flash",
      "gemini-1.5-pro": "gemini-2.5-pro",
      "gemini-2.0-flash": "gemini-2.5-flash",
  }
  return deprecated_map.get(clean, clean)


# ==========================================
# 1. 系統初始化與主題視覺
# ==========================================
st.set_page_config(
    page_title="A.lab 自然科解題實驗室", page_icon="🧪", layout="centered"
)

config = load_config()

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
        "card_gemini": "#16233B",
        "card_openai": "#122B22",
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
        "card_gemini": "#181824",
        "card_openai": "#14241B",
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
        "card_gemini": "#212D40",
        "card_openai": "#1D332A",
    },
}

MODEL_OPTIONS = {
    "Gemini": [
        "gemini-2.5-flash",
        "gemini-3.6-flash",
        "gemini-2.5-pro",
    ],
    "ChatGPT": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
}

# --- Session 初始化 ---
if "history_logs" not in st.session_state:
  st.session_state.history_logs = []
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

# 載入並進行舊型號淨化
init_gemini_model = sanitize_model_name(
    config.get("selected_gemini_model", "gemini-2.5-flash")
)
if init_gemini_model not in MODEL_OPTIONS["Gemini"]:
  init_gemini_model = "gemini-2.5-flash"

if "selected_gemini_model" not in st.session_state:
  st.session_state.selected_gemini_model = init_gemini_model
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

ADMIN_USER = "Alan2580"
ADMIN_PASSWORD = "csps106121"
DEFAULT_USER_PASSWORD = "2580"

# --- 側邊欄 ---
if st.session_state.logged_in:
  with st.sidebar:
    st.title("☰ 選單")
    st.write(f"👤 **{st.session_state.user_name}**")
    st.divider()

    menu_options = (
        [
            "⚙️ 系統管理",
            "🐛 使用者錯誤回報",
            "📝 開始解題",
            "📚 所有人解題紀錄",
        ]
        if st.session_state.user_role == "admin"
        else ["📝 開始解題", "📚 我的解題紀錄"]
    )
    menu_option = st.radio(
        "功能導航", menu_options, index=0, label_visibility="collapsed"
    )

    if st.session_state.user_role == "admin":
      st.divider()
      st.subheader("🤖 AI 模型控制")

      g_chk = st.checkbox(
          "啟用 Gemini 模型", value=st.session_state.enable_gemini
      )
      if g_chk != st.session_state.enable_gemini:
        st.session_state.enable_gemini = g_chk
        save_config_from_session()

      if st.session_state.enable_gemini:
        current_g_model = sanitize_model_name(
            st.session_state.selected_gemini_model
        )
        if current_g_model not in MODEL_OPTIONS["Gemini"]:
          current_g_model = MODEL_OPTIONS["Gemini"][0]

        g_sel = st.selectbox(
            "Gemini 版本",
            MODEL_OPTIONS["Gemini"],
            index=MODEL_OPTIONS["Gemini"].index(current_g_model),
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
            "ChatGPT 版本",
            MODEL_OPTIONS["ChatGPT"],
            index=MODEL_OPTIONS["ChatGPT"].index(
                st.session_state.selected_openai_model
            ),
        )
        if o_sel != st.session_state.selected_openai_model:
          st.session_state.selected_openai_model = o_sel
          save_config_from_session()

    st.divider()
    st.subheader("🎨 視覺主題")
    selected_theme = st.selectbox(
        "風格選擇", list(THEMES.keys()), index=0, key="theme_selector"
    )

    st.divider()
    if st.button("🚪 登出系統", use_container_width=True):
      st.session_state.logged_in = False
      st.session_state.user_role = ""
      st.session_state.user_name = ""
      st.session_state.must_change_password = False
      st.rerun()
else:
  selected_theme = "全黑夜間"
  menu_option = "📝 開始解題"

t = THEMES[selected_theme]

# CSS 注入
st.markdown(
    f"""
<style>
    .stApp {{ background-color: {t["bg"]} !important; color: {t["text"]} !important; }}
    section[data-testid="stSidebar"] {{ background-color: {t["sidebar_bg"]} !important; border-right: 1px solid {t["border"]} !important; }}
    p, span, h1, h2, h3, h4, h5, h6, label, div {{ color: {t["text"]} !important; }}
    
    div.stButton > button {{
        background-color: {t["primary"]} !important;
        color: #FFFFFF !important;
        border: 1px solid {t["primary"]} !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        transition: all 0.2s ease-in-out !important;
    }}
    div.stButton > button * {{ color: #FFFFFF !important; }}
    div.stButton > button:hover {{
        background-color: {t["primary_hover"]} !important;
        border-color: {t["primary_hover"]} !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
        transform: translateY(-1px);
    }}
    
    input, textarea, div[data-baseweb="input"] > div {{
        background-color: {t["input_bg"]} !important;
        color: {t["input_text"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 6px !important;
    }}
    div[data-baseweb="select"] > div, ul[role="listbox"] li {{
        background-color: {t["card_bg"]} !important;
        color: {t["text"]} !important;
        border-color: {t["border"]} !important;
    }}
    div[data-testid="stExpander"] {{
        background-color: {t["card_bg"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
    }}
    
    .ai-card-gemini {{
        background-color: {t["card_gemini"]};
        border: 1px solid #2B4C7E;
        border-radius: 10px;
        padding: 16px;
        margin-top: 10px;
    }}
    .ai-card-openai {{
        background-color: {t["card_openai"]};
        border: 1px solid #235D43;
        border-radius: 10px;
        padding: 16px;
        margin-top: 10px;
    }}
    .step-number {{
        background-color: {t["primary"]};
        color: #FFFFFF !important;
        border-radius: 50%; width: 28px; height: 28px;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 14px; margin-right: 10px;
    }}
    .step-header {{ display: flex; align-items: center; font-size: 18px; font-weight: 700; color: {t["text"]}; margin-bottom: 8px; }}
</style>
""",
    unsafe_allow_html=True,
)

# --- 登入控制 ---
if not st.session_state.logged_in:
  st.title("🔑 A.lab 登入系統")
  st.caption("請輸入您的姓名/帳號與密碼")
  input_user = st.text_input("姓名 / 管理員帳號")
  input_password = st.text_input("密碼", type="password")

  if st.button("登入", use_container_width=True):
    if input_user == ADMIN_USER and input_password == ADMIN_PASSWORD:
      st.session_state.logged_in = True
      st.session_state.user_role = "admin"
      st.session_state.user_name = "系統管理員"
      st.rerun()
    elif (
        input_user in st.session_state.users_db
        and st.session_state.users_db[input_user]["password"] == input_password
    ):
      st.session_state.logged_in = True
      st.session_state.user_role = "user"
      st.session_state.user_name = input_user
      st.session_state.must_change_password = st.session_state.users_db[
          input_user
      ]["first_login"]
      st.rerun()
    else:
      st.error("❌ 帳號或密碼錯誤！")
  st.stop()

# --- 強制變更密碼 ---
if st.session_state.must_change_password:
  st.warning("🔒 首次登入請先修改預設密碼！")
  pwd1 = st.text_input("請輸入新密碼", type="password")
  pwd2 = st.text_input("再次確認新密碼", type="password")

  if st.button("確認更新密碼", use_container_width=True):
    if not pwd1 or pwd1 != pwd2 or pwd1 == DEFAULT_USER_PASSWORD:
      st.error("密碼不符合規則或二次輸入不一致！")
    else:
      u_name = st.session_state.user_name
      st.session_state.users_db[u_name]["password"] = pwd1
      st.session_state.users_db[u_name]["first_login"] = False
      st.session_state.must_change_password = False
      save_config_from_session()
      st.success("🎉 密碼修改成功！")
      st.rerun()
  st.stop()

# --- 頁首狀態 ---
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
    st.progress(
        min(1.0, used / limit),
        text=f"📊 今日剩餘額度：{remains}/{limit} 題 (已用 {used} 題)",
    )

st.divider()

# ==========================================
# 2. AI 引擎與 Prompt (加入自動退避與模型維護)
# ==========================================
GEMINI_API_KEY = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
OPENAI_API_KEY = str(st.secrets.get("OPENAI_API_KEY", "")).strip()


def build_system_prompt(mode="full"):
  mode_instruction = ""
  if mode == "hint":
    mode_instruction = """
    【特別指令 - 引導模式】：
    - 請【不要】直接給出答案選項（ans 請填寫 "提示模式"）。
    - 著重給出 2~3 個思考切入點、關鍵公式或考點陷阱，引導學生自主思考。
    """
  else:
    mode_instruction = """
    【特別指令 - 完整解析模式】：
    - ans 請給出明確的正確選項（如 A、B、C 或 D）。
    - reasoning 請包含：觀念說明、逐項選項剖析與結論。
    """

  return f"""
你是一位嚴謹的臺灣國中自然科會考名師（熟悉翰林、康軒、南一課綱）。
請分析使用者提供的題目，並嚴格只回傳以下 JSON 格式（不要寫任何 Markdown codeblock 標籤）：

{{
  "ans": "正確答案選項或提示模式",
  "reasoning": "詳細解析或思考提示"
}}

注意事項：
1. 必須使用臺灣國中課綱標準名詞（如：排水集氣法、電流熱效應、凸透鏡成像等）。
2. 理化與數學公式請盡量使用 LaTeX 語法格式化（如 $V = I \\times R$ 或 $\\text{{H}}_2\\text{{O}}$）。
{mode_instruction}
"""


def extract_text_from_images(
    image_list: list,
    model_name: str,
    extra_info: str = "",
    max_retries: int = 3,
) -> str:
  if not GEMINI_API_KEY:
    return "[圖片辨識失敗]: 未設定 GEMINI_API_KEY"

  ocr_prompt = (
      "請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明："
      f" {extra_info}"
  )
  clean_model = sanitize_model_name(model_name)
  client = genai.Client(api_key=GEMINI_API_KEY)

  for attempt in range(max_retries):
    try:
      response = client.models.generate_content(
          model=clean_model, contents=image_list + [ocr_prompt]
      )
      return (
          response.text.strip()
          if response and response.text
          else "[圖片解析空白]"
      )
    except APIError as e:
      err_str = str(e)
      if (
          "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
      ) and attempt < max_retries - 1:
        time.sleep((2**attempt) + random.uniform(0.5, 1.5))
        continue
      return f"[圖片辨識失敗]: {err_str}"
    except Exception as e:
      return f"[圖片辨識失敗]: {str(e)}"


def call_gemini(question_text, mode, model_name, max_retries: int = 3):
  if not GEMINI_API_KEY:
    return json.dumps(
        {"ans": "未設定 Key", "reasoning": "未設定 GEMINI_API_KEY。"},
        ensure_ascii=False,
    )

  clean_model = sanitize_model_name(model_name)
  client = genai.Client(api_key=GEMINI_API_KEY)
  prompt = f"{build_system_prompt(mode)}\n\n題目：{question_text}"

  for attempt in range(max_retries):
    try:
      response = client.models.generate_content(
          model=clean_model, contents=prompt
      )
      return response.text if response and response.text else "{}"
    except APIError as e:
      err_str = str(e)
      if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
        if attempt < max_retries - 1:
          time.sleep((2**attempt) + random.uniform(0.5, 1.5))
          continue
        return json.dumps(
            {"ans": "失敗", "reasoning": "⚠️ 觸發 API 配額限制 (429)，請稍後再試。"},
            ensure_ascii=False,
        )
      elif "404" in err_str or "NOT_FOUND" in err_str:
        return json.dumps(
            {
                "ans": "失敗",
                "reasoning": (
                    f"404 錯誤：模型 `{clean_model}` 無法存取，請至管理員頁面切換最新模型。"
                ),
            },
            ensure_ascii=False,
        )
      else:
        return json.dumps(
            {"ans": "失敗", "reasoning": f"Gemini 呼叫失敗: {err_str}"},
            ensure_ascii=False,
        )
    except Exception as e:
      return json.dumps(
          {"ans": "失敗", "reasoning": f"Gemini 呼叫失敗: {str(e)}"},
          ensure_ascii=False,
      )


def call_chatgpt(question_text, mode, model_name):
  if not OPENAI_API_KEY:
    return json.dumps(
        {"ans": "未設定 Key", "reasoning": "未設定 OPENAI_API_KEY。"},
        ensure_ascii=False,
    )
  try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_system_prompt(mode)},
            {"role": "user", "content": f"題目：{question_text}"},
        ],
    )
    return response.choices[0].message.content
  except Exception as e:
    return json.dumps(
        {"ans": "失敗", "reasoning": f"ChatGPT 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def parse_ai_json(raw_text):
  try:
    clean_text = (
        raw_text.strip().replace("```json", "").replace("```", "").strip()
    )
    data = json.loads(clean_text)
    return data.get("ans", "未知").strip(), data.get("reasoning", "無解析內容")
  except Exception:
    return "格式解析失敗", raw_text


# ==========================================
# 3. 頁面分流與功能渲染
# ==========================================

# ⚙️ 系統管理後台
if menu_option == "⚙️ 系統管理":
  st.title("⚙️ 管理員控制後台")

  st.subheader("➕ 新增使用者帳號")
  col_u1, col_u2 = st.columns([3, 1])
  new_username = col_u1.text_input(
      "學生/使用者姓名", placeholder="例如：李小明", key="add_user_input"
  )
  if col_u2.button("➕ 建立帳號"):
    if new_username.strip():
      u_name_clean = new_username.strip()
      if u_name_clean in st.session_state.users_db:
        st.error("⚠️ 該使用者姓名已存在！")
      else:
        st.session_state.users_db[u_name_clean] = {
            "password": DEFAULT_USER_PASSWORD,
            "first_login": True,
            "used_today": 0,
        }
        save_config_from_session()
        st.success(f"🎉 已成功建立帳號：{u_name_clean} (預設密碼：2580)")
        st.rerun()

  st.divider()

  st.subheader("📚 科目管理")
  col_s1, col_s2 = st.columns([3, 1])
  new_sub = col_s1.text_input(
      "新增科目", placeholder="例如：地科", key="add_sub_input"
  )
  if col_s2.button("➕ 新增"):
    if new_sub.strip() and new_sub not in st.session_state.subjects:
      st.session_state.subjects.append(new_sub.strip())
      save_config_from_session()
      st.success(f"已新增：{new_sub}")
      st.rerun()

  del_sub = st.selectbox(
      "刪除科目", ["請選擇"] + st.session_state.subjects
  )
  if st.button("🗑️ 刪除科目") and del_sub != "請選擇":
    st.session_state.subjects.remove(del_sub)
    save_config_from_session()
    st.rerun()

  st.divider()
  st.subheader("🎯 每日額度設定")
  new_limit = st.number_input(
      "使用者每日上限",
      min_value=1,
      max_value=100,
      value=st.session_state.daily_limit,
  )
  if st.button("更新額度上限"):
    st.session_state.daily_limit = new_limit
    save_config_from_session()
    st.success("額度已更新！")

  st.divider()
  st.subheader("📋 使用者帳號管理")
  for u_name, info in list(st.session_state.users_db.items()):
    col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 2, 1])
    col_a.write(f"**{u_name}**")
    col_b.write(f"已用: `{info.get('used_today', 0)}` 題")
    if col_c.button("🔄 重置題數", key=f"reset_{u_name}"):
      st.session_state.users_db[u_name]["used_today"] = 0
      save_config_from_session()
      st.toast("已重置題數")
      st.rerun()
    if col_d.button("🔑 重設密碼", key=f"pwd_{u_name}"):
      st.session_state.users_db[u_name]["password"] = DEFAULT_USER_PASSWORD
      st.session_state.users_db[u_name]["first_login"] = True
      save_config_from_session()
      st.toast("已重置為預設密碼 2580")
    if col_e.button("🗑️", key=f"del_{u_name}"):
      del st.session_state.users_db[u_name]
      save_config_from_session()
      st.rerun()

# 🐛 錯誤回報頁面
elif menu_option == "🐛 使用者錯誤回報":
  st.title("🐛 錯誤回報管理")
  reports = st.session_state.bug_reports
  if not reports:
    st.info("目前沒有任何錯誤回報！")
  else:
    for idx, item in enumerate(reversed(reports)):
      real_idx = len(reports) - 1 - idx
      with st.expander(
          f"📌 [{item['time']}] 回報人：{item['user']} | 狀態：{item.get('status', '待處理')}"
      ):
        st.write(f"**問題描述**：{item['description']}")
        if st.button("刪除此紀錄", key=f"del_bug_{real_idx}"):
          st.session_state.bug_reports.pop(real_idx)
          save_config_from_session()
          st.rerun()

# 📚 解題紀錄頁面 + 錯題本匯出功能
elif menu_option in ["📚 我的解題紀錄", "📚 所有人解題紀錄"]:
  st.title("📚 解題紀錄與會考錯題集")

  logs = (
      st.session_state.history_logs
      if st.session_state.user_role == "admin"
      else [
          log
          for log in st.session_state.history_logs
          if log["user"] == st.session_state.user_name
      ]
  )

  if not logs:
    st.info("尚無任何解題紀錄！")
  else:
    st.subheader("📥 匯出個人錯題本")
    col_exp1, col_exp2 = st.columns(2)

    md_content = "# 📖 國中自然科會考錯題複習集\n\n"
    for idx, item in enumerate(logs, 1):
      md_content += f"## 第 {idx} 題 [{item['subject']}]\n"
      md_content += f"- **發問時間**：{item['time']}\n"
      md_content += f"- **解題模式/答案**：{item['ans']}\n"
      md_content += f"- **補充說明**：{item['extra_info'] or '無'}\n\n"
      md_content += f"### 💡 觀念解析：\n{item['reasoning']}\n\n---\n\n"

    col_exp1.download_button(
        label="📝 下載錯題本 (Markdown 格式)",
        data=md_content.encode("utf-8"),
        file_name=f"會考錯題本_{st.session_state.user_name}.md",
        mime="text/markdown",
        use_container_width=True,
    )

    df_logs = pd.DataFrame(logs)
    csv_data = df_logs.to_csv(index=False).encode("utf-8-sig")
    col_exp2.download_button(
        label="📊 下載紀錄表 (CSV 格式)",
        data=csv_data,
        file_name=f"解題紀錄_{st.session_state.user_name}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()

    for item in reversed(logs):
      with st.expander(
          f"📌 [{item['time']}] {item['subject']} - 答案：{item['ans']}"
      ):
        st.write(f"**提問人**：{item['user']}")
        st.write(f"**補充說明**：{item['extra_info'] or '無'}")
        st.markdown(f"**解析內容**：\n{item['reasoning']}")

# 📝 開始解題頁面 (核心功能)
elif menu_option == "📝 開始解題":
  st.title("🧪 自然科解題實驗室")
  st.caption("拆解步驟，訂正錯誤，清晰脈絡，梳理思路")
  st.divider()

  # 步驟 1：圖片上傳與裁剪
  st.markdown(
      '<div class="step-header"><span'
      ' class="step-number">1</span>上傳題目圖片</div>',
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

  # 步驟 2：設定題型與解題模式
  st.markdown(
      '<div class="step-header"><span'
      ' class="step-number">2</span>設定題目與模式</div>',
      unsafe_allow_html=True,
  )

  col_m1, col_m2 = st.columns(2)
  subject = col_m1.selectbox("科目", st.session_state.subjects)

  solve_mode = col_m2.radio(
      "解題模式",
      ["🎯 完整解析 (直接給答案)", "💡 引導模式 (給提示不給答案)"],
      help=(
          "「引導模式」不會直接給答案，會提供關鍵思考切入點，幫助你練出會考真本事！"
      ),
  )
  mode_key = "hint" if "引導模式" in solve_mode else "full"

  extra_info = st.text_input(
      "補充敘述（選填）", placeholder="例如：想特別問 C 選項"
  )

  if st.button("🚀 開始解題", use_container_width=True):
    can_submit = True
    if not st.session_state.enable_gemini and not st.session_state.enable_openai:
      can_submit = False
      st.error("⚠️ 管理員已停用所有 AI 模型！")

    if st.session_state.user_role == "user" and can_submit:
      u_name = st.session_state.user_name
      if (
          st.session_state.users_db[u_name].get("used_today", 0)
          >= st.session_state.daily_limit
      ):
        can_submit = False
        st.error("⚠️ 今日額度已用完，請明日再試！")

    if can_submit:
      final_images = [
          st.session_state.cropped_images[i]
          for i in range(len(uploaded_files))
          if i in st.session_state.cropped_images
      ]
      if not final_images:
        st.warning("請先上傳至少一張題目圖片！")
      else:
        # 扣額度
        if st.session_state.user_role == "user":
          st.session_state.users_db[st.session_state.user_name][
              "used_today"
          ] += 1
          save_config_from_session()

        # 抓取目前選取的 model 名稱傳給子執行緒
        gemini_model = st.session_state.selected_gemini_model
        openai_model = st.session_state.selected_openai_model

        with st.status(
            "🚀 正在進行 AI 解析與平行驗證...", expanded=True
        ):
          st.write("🔍 **步驟 1/2**：進行 Gemini 多圖視覺 OCR 辨識...")
          q_text = extract_text_from_images(
              final_images, gemini_model, extra_info
          )

          st.write(
              "🤖 **步驟 2/2**：啟動雙 AI 模組進行平行邏輯推理..."
          )

          g_raw, c_raw = "", ""
          with ThreadPoolExecutor(max_workers=2) as executor:
            future_g = (
                executor.submit(call_gemini, q_text, mode_key, gemini_model)
                if st.session_state.enable_gemini
                else None
            )
            future_c = (
                executor.submit(call_chatgpt, q_text, mode_key, openai_model)
                if st.session_state.enable_openai
                else None
            )

            if future_g:
              g_raw = future_g.result()
            if future_c:
              c_raw = future_c.result()

          g_ans, g_reason = (
              parse_ai_json(g_raw)
              if st.session_state.enable_gemini
              else ("未啟用", "未啟用")
          )
          c_ans, c_reason = (
              parse_ai_json(c_raw)
              if st.session_state.enable_openai
              else ("未啟用", "未啟用")
          )

          # 紀錄至歷史
          main_ans = g_ans if st.session_state.enable_gemini else c_ans
          main_reason = (
              g_reason if st.session_state.enable_gemini else c_reason
          )
          st.session_state.history_logs.append({
              "user": st.session_state.user_name,
              "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "subject": subject,
              "ans": main_ans,
              "reasoning": main_reason,
              "extra_info": extra_info,
          })

        # --- 渲染解答結果 ---
        st.divider()
        st.markdown(
            '<div class="step-header"><span'
            ' class="step-number">3</span>觀念解析與交叉驗證</div>',
            unsafe_allow_html=True,
        )

        if mode_key == "full":
          valid_ans = [
              a
              for a in [g_ans, c_ans]
              if a not in ["未啟用", "失敗", "未設定 Key", "格式解析失敗"]
          ]
          if len(set(valid_ans)) == 1 and valid_ans:
            st.success(f"✅ **AI 驗證答案一致：【 {valid_ans[0]} 】**")
          elif len(set(valid_ans)) > 1:
            st.warning(
                f"⚠️ **AI 答案存在分歧！** (Gemini: {g_ans} | ChatGPT: {c_ans})"
            )
        else:
          st.info(
              "💡 **目前為【引導模式】，請閱讀以下關鍵提示後試著自己解答！**"
          )

        # 兩欄顏色卡片渲染
        cols = st.columns(
            sum([
                st.session_state.enable_gemini,
                st.session_state.enable_openai,
            ])
        )
        c_idx = 0

        if st.session_state.enable_gemini:
          with cols[c_idx]:
            ans_html = (
                f"<p><b>答案</b>：<code"
                f' style="font-size:18px;">{g_ans}</code></p><hr'
                f' style="border-color:{t["border"]};">'
                if mode_key == "full"
                else ""
            )
            st.markdown(
                f"""<div class="ai-card-gemini">
              <h3 style="color:#7EA6E0 !important;">🤖 Gemini ({sanitize_model_name(gemini_model)})</h3>
              {ans_html}
              <div>{g_reason}</div>
            </div>""",
                unsafe_allow_html=True,
            )
            c_idx += 1

        if st.session_state.enable_openai:
          with cols[c_idx]:
            ans_html = (
                f"<p><b>答案</b>：<code"
                f' style="font-size:18px;">{c_ans}</code></p><hr'
                f' style="border-color:{t["border"]};">'
                if mode_key == "full"
                else ""
            )
            st.markdown(
                f"""<div class="ai-card-openai">
              <h3 style="color:#63E6BE !important;">🟢 ChatGPT ({openai_model})</h3>
              {ans_html}
              <div>{c_reason}</div>
            </div>""",
                unsafe_allow_html=True,
            )

  # 錯誤回報 Drawer
  st.divider()
  with st.expander("🚨 解析有誤或系統異常？點此回報"):
    bug_desc = st.text_area("說明問題或錯誤內容")
    if st.button("📤 送出回報") and bug_desc.strip():
      st.session_state.bug_reports.append({
          "user": st.session_state.user_name,
          "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "description": bug_desc.strip(),
          "status": "待處理",
      })
      save_config_from_session()
      st.success("回報已送出！")
