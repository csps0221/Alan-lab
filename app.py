import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
import os
import threading

from google import genai
from openai import OpenAI
import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_cropper import st_cropper

# ==========================================
# 0. 安全的設定檔存取機制 (Json 本地資料庫)
# ==========================================
CONFIG_FILE = "config.json"
FILE_LOCK = threading.Lock()  # 避免併發寫入檔案衝突

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
  """安全載入設定檔"""
  if not os.path.exists(CONFIG_FILE):
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      cfg = json.load(f)
      # 補全可能缺失的鍵值
      for key, val in DEFAULT_CONFIG.items():
        if key not in cfg:
          cfg[key] = val
      return cfg
  except Exception as e:
    st.error(f"載入設定檔失敗，已還原為預設設定: {e}")
    return DEFAULT_CONFIG


def save_config(config_data):
  """原子化寫入 json 檔案，防止檔案毀損"""
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
  """將 Session 狀態同步儲存至 json 檔案"""
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


def image_to_base64(pil_img):
  buffered = BytesIO()
  pil_img.save(buffered, format="JPEG")
  return base64.b64encode(buffered.getvalue()).decode("utf-8")


def base64_to_image(b64_str):
  img_data = base64.b64decode(b64_str)
  return Image.open(BytesIO(img_data))


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

MODEL_OPTIONS = {
    "Gemini": [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "ChatGPT": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
}

# --- Session 狀態初始化 ---
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

# 帳號設定
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
        g_sel = st.selectbox(
            "Gemini 版本",
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
    
    .ai-card {{
        background-color: {t["card_bg"]};
        border: 1px solid {t["border"]};
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
    .sub-text {{ color: {t["sub_text"]} !important; font-size: 13px; margin-left: 38px; margin-top: -6px; margin-bottom: 14px; }}
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
# 2. AI 引擎與平行呼叫核心邏輯
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
  """優化後的 Gemini 多圖 OCR 辨識"""
  if not GEMINI_API_KEY:
    return "[圖片辨識失敗]: 未設定 GEMINI_API_KEY"

  ocr_prompt = (
      "請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明："
      f" {extra_info}"
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

    for model_name in models_to_try:
      try:
        response = client.models.generate_content(
            model=model_name, contents=image_list + [ocr_prompt]
        )
        if response and response.text:
          return response.text.strip()
      except Exception:
        continue
    return "[圖片辨識失敗]: 所有備用模型皆無法解析圖片"
  except Exception as e:
    return f"[圖片辨識失敗]: {str(e)}"


def call_gemini(question_text):
  if not GEMINI_API_KEY:
    return json.dumps(
        {"ans": "未設定 Key", "reasoning": "未設定 GEMINI_API_KEY。"},
        ensure_ascii=False,
    )
  try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    clean_model = st.session_state.selected_gemini_model.replace("models/", "")
    response = client.models.generate_content(
        model=clean_model, contents=f"{SYSTEM_PROMPT}\n\n題目：{question_text}"
    )
    return response.text if response and response.text else "{}"
  except Exception as e:
    return json.dumps(
        {"ans": "失敗", "reasoning": f"Gemini 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def call_chatgpt(question_text):
  if not OPENAI_API_KEY:
    return json.dumps(
        {"ans": "未設定 Key", "reasoning": "未設定 OPENAI_API_KEY。"},
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
        {"ans": "失敗", "reasoning": f"ChatGPT 呼叫失敗: {str(e)}"},
        ensure_ascii=False,
    )


def parse_ai_json(raw_text):
  try:
    clean_text = (
        raw_text.strip().replace("```json", "").replace("```", "").strip()
    )
    data = json.loads(clean_text)
    return data.get("ans", "未知").strip().upper(), data.get(
        "reasoning", "無解析內容"
    )
  except Exception:
    return "格式解析失敗", raw_text


# ==========================================
# 3. 頁面分流與功能渲染
# ==========================================

# ⚙️ 系統管理後台
if menu_option == "⚙️ 系統管理":
  st.title("⚙️ 管理員控制後台")

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
    col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
    col_a.write(f"**{u_name}**")
    col_b.write(f"已用: `{info.get('used_today', 0)}` 題")
    if col_c.button("🔄 重置題數", key=f"reset_{u_name}"):
      st.session_state.users_db[u_name]["used_today"] = 0
      save_config_from_session()
      st.toast("已重置題數")
      st.rerun()
    if col_d.button("🗑️", key=f"del_{u_name}"):
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
        if item.get("image_b64"):
          st.image(
              base64_to_image(item["image_b64"]), use_container_width=True
          )
        if st.button("刪除此紀錄", key=f"del_bug_{real_idx}"):
          st.session_state.bug_reports.pop(real_idx)
          save_config_from_session()
          st.rerun()

# 📚 解題紀錄頁面
elif menu_option in ["📚 我的解題紀錄", "📚 所有人解題紀錄"]:
  st.title("📚 解題紀錄匯總")
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
    st.info("尚無任何紀錄！")
  else:
    for item in reversed(logs):
      with st.expander(
          f"📌 [{item['time']}] {item['subject']} - 答案：{item['ans']}"
      ):
        st.write(f"**提問人**：{item['user']}")
        st.write(f"**補充說明**：{item['extra_info'] or '無'}")
        st.write(f"**解析**：\n{item['reasoning']}")

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

  # 步驟 2：設定題型資訊
  st.markdown(
      '<div class="step-header"><span'
      ' class="step-number">2</span>設定題目資訊</div>',
      unsafe_allow_html=True,
  )
  subject = st.selectbox("科目", st.session_state.subjects)
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
        # 扣除額度
        if st.session_state.user_role == "user":
          st.session_state.users_db[st.session_state.user_name][
              "used_today"
          ] += 1
          save_config_from_session()

        with st.status("🚀 正在進行 AI 解析與平行驗證...", expanded=True):
          st.write("🔍 **步驟 1/2**：進行 Gemini 多圖視覺 OCR 辨識...")
          q_text = extract_text_from_images(final_images, extra_info)

          st.write("🤖 **步驟 2/2**：啟動雙 AI 模組進行平行邏輯推理...")

          # 🔥 關鍵效能優化：使用 ThreadPoolExecutor 併發呼叫 AI
          g_raw, c_raw = "", ""
          with ThreadPoolExecutor(max_workers=2) as executor:
            future_g = (
                executor.submit(call_gemini, q_text)
                if st.session_state.enable_gemini
                else None
            )
            future_c = (
                executor.submit(call_chatgpt, q_text)
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

        # 比對答案
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

        # 兩欄呈現解析
        cols = st.columns(
            sum([
                st.session_state.enable_gemini,
                st.session_state.enable_openai,
            ])
        )
        c_idx = 0

        if st.session_state.enable_gemini:
          with cols[c_idx]:
            st.markdown(
                f"""<div class="ai-card">
              <h3>🤖 Gemini ({st.session_state.selected_gemini_model})</h3>
              <p><b>答案</b>：<code style="font-size:18px;">{g_ans}</code></p>
              <hr style="border-color:{t["border"]};">
              <p>{g_reason}</p>
            </div>""",
                unsafe_allow_html=True,
            )
            c_idx += 1

        if st.session_state.enable_openai:
          with cols[c_idx]:
            st.markdown(
                f"""<div class="ai-card">
              <h3>🟢 ChatGPT ({st.session_state.selected_openai_model})</h3>
              <p><b>答案</b>：<code style="font-size:18px;">{c_ans}</code></p>
              <hr style="border-color:{t["border"]};">
              <p>{c_reason}</p>
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
          "image_b64": "",
          "status": "待處理",
      })
      save_config_from_session()
      st.success("回報已送出！")
