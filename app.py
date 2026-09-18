import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
import os
import random
import threading
import time
from zoneinfo import ZoneInfo
from google import genai
from google.genai.errors import APIError
from openai import OpenAI
import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_cropper import st_cropper
# 引入 Streamlit 元件庫以存取 LocalStorage
import streamlit.components.v1 as components

# 定義台北標準時間(UTC+8)取得函數
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

def get_taipei_now_str():
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_taipei_today_str():
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")

def get_taipei_today_date():
    return datetime.now(TAIPEI_TZ).date()

# =========================================================
# 0. 安全的設定檔與紀錄存取機制(Json 本地資料庫)
# =========================================================
CONFIG_FILE = "config.json"
FILE_LOCK = threading.Lock()
DEFAULT_CONFIG = {
    "daily_limit": 5,
    "selected_gemini_model": "gemini-3.6-flash",
    "selected_openai_model": "gpt-4o-mini",
    "enable_gemini": True,
    "enable_openai": True,
    "subjects": ["理化", "生物", "地科", "數學", "其他"],
    "bug_reports": [],
    "history_logs": [],
    "login_logs": [],
    "users_db": {
        "王小明": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
            "total_used": 0,
            "custom_limit": None,
        },
        "測試使用者": {
            "password": "2580",
            "first_login": True,
            "used_today": 0,
            "total_used": 0,
            "custom_limit": None,
        },
    },
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        try:
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        except Exception as e:
            st.error(f"建立預設設定檔失敗: {e}")
            return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for key, val in DEFAULT_CONFIG.items():
            if key not in cfg:
                cfg[key] = val
        if "users_db" in cfg:
            for u_info in cfg["users_db"].values():
                if "total_used" not in u_info:
                    u_info["total_used"] = u_info.get("used_today", 0)
                if "custom_limit" not in u_info:
                    u_info["custom_limit"] = None
        return cfg
    except Exception as e:
        st.error(f"載入設定檔失敗,已還原為預設設定: {e}")
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
        "history_logs": st.session_state.history_logs,
        "login_logs": st.session_state.login_logs,
        "users_db": st.session_state.users_db,
    }
    save_config(config_data)

def record_login(user_name, role):
    """記錄使用者登入歷史(以台北標準時間寫入)"""
    log_entry = {
        "user": user_name,
        "role": role,
        "timestamp": get_taipei_now_str(),
        "date": get_taipei_today_str(),
    }
    st.session_state.login_logs.append(log_entry)
    save_config_from_session()

def sanitize_model_name(model_name: str) -> str:
    clean = str(model_name).replace("models/", "").strip()
    deprecated_map = {
        "gemini-1.5-flash": "gemini-3.6-flash",
        "gemini-1.5-pro": "gemini-3.6-flash",
        "gemini-2.0-flash": "gemini-3.6-flash",
        "gemini-2.5-flash": "gemini-3.6-flash",
        "gemini-2.5-pro": "gemini-3.6-flash",
    }
    return deprecated_map.get(clean, clean)

def pil_to_base64(img: Image.Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# =========================================================
# 1. 系統初始化與 LocalStorage/URL 防重整登出機制
# =========================================================
st.set_page_config(page_title="A.lab 全能解題實驗室", page_icon="📚 ", layout="centered")
config = load_config()

# --- Session 初始化
if "history_logs" not in st.session_state:
    st.session_state.history_logs = config.get("history_logs", [])
if "login_logs" not in st.session_state:
    st.session_state.login_logs = config.get("login_logs", [])
if "daily_limit" not in st.session_state:
    st.session_state.daily_limit = config.get("daily_limit", 5)
if "users_db" not in st.session_state:
    st.session_state.users_db = config.get("users_db", DEFAULT_CONFIG["users_db"])
if "subjects" not in st.session_state:
    st.session_state.subjects = config.get("subjects", DEFAULT_CONFIG["subjects"])
if "bug_reports" not in st.session_state:
    st.session_state.bug_reports = config.get("bug_reports", [])

ADMIN_USER = "Alan2580"
ADMIN_PASSWORD = "csps106121"
DEFAULT_USER_PASSWORD = "2580"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "must_change_password" not in st.session_state:
    st.session_state.must_change_password = False

# 讀取 URL 參數
st_query = st.query_params

# 若 Session 未記錄登入，先從 URL 參數防重整自動恢復
if not st.session_state.logged_in:
    if "auto_user" in st_query and "auto_role" in st_query:
        param_user = st_query["auto_user"]
        param_role = st_query["auto_role"]
        if param_role == "admin" and param_user == ADMIN_USER:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.user_name = "系統管理員"
        elif param_user in st.session_state.users_db:
            st.session_state.logged_in = True
            st.session_state.user_role = "user"
            st.session_state.user_name = param_user
            st.session_state.must_change_password = st.session_state.users_db[param_user].get("first_login", False)

# 前端 JS: 若 LocalStorage 存在記錄但 URL 沒有參數，自動寫入 URL 恢復
js_restore_session = """
<script>
const storedUser = localStorage.getItem('alab_user');
const storedRole = localStorage.getItem('alab_role');
const urlParams = new URLSearchParams(window.location.search);
if (storedUser && storedRole && !urlParams.has('auto_user')) {
    urlParams.set('auto_user', storedUser);
    urlParams.set('auto_role', storedRole);
    window.location.search = urlParams.toString();
}
</script>
"""
components.html(js_restore_session, height=0, width=0)

THEMES = {
    "櫻花粉": {
        "bg": "#FFF5F7",
        "sidebar_bg": "#FFE6EA",
        "card_bg": "#FFFFFF",
        "text": "#5A3A42",
        "sub_text": "#D87093",
        "primary": "#FFB7C5",
        "primary_hover": "#FF94A8",
        "input_bg": "#FFFFFF",
        "input_text": "#5A3A42",
        "border": "#FFCAD4",
    },
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
    "森林綠": {
        "bg": "#0D1F17",
        "sidebar_bg": "#132A20",
        "card_bg": "#1B382B",
        "text": "#E8F5E9",
        "sub_text": "#A5D6A7",
        "primary": "#2E7D32",
        "primary_hover": "#1B5E20",
        "input_bg": "#132A20",
        "input_text": "#FFFFFF",
        "border": "#2E4F3E",
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
}

MODEL_OPTIONS = {
    "Gemini": ["gemini-3.6-flash"],
    "ChatGPT": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
}

init_gemini_model = sanitize_model_name(config.get("selected_gemini_model", "gemini-3.6-flash"))
if init_gemini_model not in MODEL_OPTIONS["Gemini"]:
    init_gemini_model = "gemini-3.6-flash"

if "selected_gemini_model" not in st.session_state:
    st.session_state.selected_gemini_model = init_gemini_model
if "selected_openai_model" not in st.session_state:
    st.session_state.selected_openai_model = config.get("selected_openai_model", "gpt-4o-mini")
if "enable_gemini" not in st.session_state:
    st.session_state.enable_gemini = config.get("enable_gemini", True)
if "enable_openai" not in st.session_state:
    st.session_state.enable_openai = config.get("enable_openai", True)

selected_theme = "櫻花粉"

# --- 側邊欄 ---
if st.session_state.logged_in:
    with st.sidebar:
        st.title("📚 選單")
        st.write(f"當前登入：**{st.session_state.user_name}**")
        st.divider()
        menu_options = (
            ["系統管理", "使用者上線紀錄", "使用者錯誤回報", "開始解題", "所有人解題紀錄"]
            if st.session_state.user_role == "admin"
            else ["開始解題", "我的解題紀錄"]
        )
        menu_option = st.radio("功能導航", menu_options, index=0, label_visibility="collapsed")
        
        if st.session_state.user_role == "admin":
            st.divider()
            st.subheader("AI 模型控制")
            g_chk = st.checkbox("啟用 Gemini 模型", value=st.session_state.enable_gemini)
            if g_chk != st.session_state.enable_gemini:
                st.session_state.enable_gemini = g_chk
                save_config_from_session()
            if st.session_state.enable_gemini:
                current_g_model = sanitize_model_name(st.session_state.selected_gemini_model)
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

            o_chk = st.checkbox("啟用 ChatGPT 模型", value=st.session_state.enable_openai)
            if o_chk != st.session_state.enable_openai:
                st.session_state.enable_openai = o_chk
                save_config_from_session()
            if st.session_state.enable_openai:
                o_sel = st.selectbox(
                    "ChatGPT 版本",
                    MODEL_OPTIONS["ChatGPT"],
                    index=MODEL_OPTIONS["ChatGPT"].index(st.session_state.selected_openai_model),
                )
                if o_sel != st.session_state.selected_openai_model:
                    st.session_state.selected_openai_model = o_sel
                    save_config_from_session()

        st.divider()
        st.subheader("視覺主題")
        selected_theme = st.selectbox("風格選擇", list(THEMES.keys()), index=0, key="theme_selector")
        st.divider()
        if st.button("登出系統", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.must_change_password = False
            st.query_params.clear() # 清空 URL 參數
            
            js_logout = """
            <script>
            localStorage.removeItem('alab_user');
            localStorage.removeItem('alab_role');
            window.location.href = window.location.pathname;
            </script>
            """
            components.html(js_logout, height=0, width=0)
            st.rerun()
else:
    menu_option = "開始解題"

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
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
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
    </style>
    """,
    unsafe_allow_html=True,
)

# --- 登入控制 ---
if not st.session_state.logged_in:
    st.title("📚 A.lab 登入系統")
    st.caption("請輸入您的姓名/帳號與密碼")
    input_user = st.text_input("姓名/管理員帳號")
    input_password = st.text_input("密碼", type="password")
    if st.button("登入", use_container_width=True):
        if input_user == ADMIN_USER and input_password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.user_name = "系統管理員"
            record_login("系統管理員", "admin")
            
            # 將登入標記寫入 URL 參數以支援刷新不登出
            st.query_params["auto_user"] = ADMIN_USER
            st.query_params["auto_role"] = "admin"
            
            js_save = f"""
            <script>
            localStorage.setItem('alab_user', '{ADMIN_USER}');
            localStorage.setItem('alab_role', 'admin');
            </script>
            """
            components.html(js_save, height=0, width=0)
            st.rerun()
        elif (
            input_user in st.session_state.users_db
            and st.session_state.users_db[input_user]["password"] == input_password
        ):
            st.session_state.logged_in = True
            st.session_state.user_role = "user"
            st.session_state.user_name = input_user
            st.session_state.must_change_password = st.session_state.users_db[input_user]["first_login"]
            record_login(input_user, "user")
            
            # 將登入標記寫入 URL 參數以支援刷新不登出
            st.query_params["auto_user"] = input_user
            st.query_params["auto_role"] = "user"
            
            js_save = f"""
            <script>
            localStorage.setItem('alab_user', '{input_user}');
            localStorage.setItem('alab_role', 'user');
            </script>
            """
            components.html(js_save, height=0, width=0)
            st.rerun()
        else:
            st.error("帳號或密碼錯誤!")
    st.stop()

# --- 強制變更密碼 ---
if st.session_state.must_change_password:
    st.warning("首次登入請先修改預設密碼!")
    pwd1 = st.text_input("請輸入新密碼", type="password")
    pwd2 = st.text_input("再次確認新密碼", type="password")
    if st.button("確認更新密碼", use_container_width=True):
        if not pwd1 or pwd1 != pwd2 or pwd1 == DEFAULT_USER_PASSWORD:
            st.error("密碼不符合規則或二次輸入不一致!")
        else:
            u_name = st.session_state.user_name
            st.session_state.users_db[u_name]["password"] = pwd1
            st.session_state.users_db[u_name]["first_login"] = False
            st.session_state.must_change_password = False
            save_config_from_session()
            st.success("密碼修改成功!")
            st.rerun()
    st.stop()

# --- 頁首狀態 ---
top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    role_label = "管理員(無限次數)" if st.session_state.user_role == "admin" else "使用者"
    st.write(f"當前使用者：**{st.session_state.user_name}** ({role_label})")
    if st.session_state.user_role == "user":
        user_info = st.session_state.users_db.get(st.session_state.user_name, {"used_today": 0, "total_used": 0})
        used = user_info.get("used_today", 0)
        limit = user_info.get("custom_limit") or st.session_state.daily_limit
        remains = max(0, limit - used)
        st.progress(
            min(1.0, used / limit) if limit > 0 else 1.0,
            text=(
                f"今日額度: {remains}/{limit}題(已用{used}題) | "
                f"累計總發問: {user_info.get('total_used', 0)}題"
            ),
        )
st.divider()

# =========================================================
# 2. AI 引擎與 System Prompt
# =========================================================
GEMINI_API_KEY = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
OPENAI_API_KEY = str(st.secrets.get("OPENAI_API_KEY", "")).strip()

def build_system_prompt(mode="full"):
    mode_instruction = (
        """
【特別指令-引導模式】:
- 請【不要】直接給出最終答案(ans 請填寫"提示模式")。
- 著重提供關鍵觀念、解題切入點、公式推導方向或邏輯陷阱,引導使用者自行推理。
"""
        if mode == "hint"
        else """
【特別指令-完整解析模式】:
- ans 請給出明確答案(若為選擇題請給選項如 A/B/C/D; 若為問答或計算題請簡短寫出最終答案數字/結果)。
- reasoning 請包含完整的邏輯推導過程、觀念說明與結論。
"""
    )
    return f"""
你是一位博學多聞、邏輯嚴謹的萬能 AI 導師。
無論使用者提出任何學科、領域、難度或類型的題目(涵蓋科學、數學、程式設計、人文、語言、通用知識等),只要是可以解答的問題,你都必須全力進行解答與剖析。
請嚴格只回傳以下 JSON 格式(絕對不要寫任何 Markdown codeblock 標籤如 ```json ... ```):
{{
    "ans": "正確答案選項、最終結果或提示模式",
    "reasoning": "詳細解析或思考提示"
}}
注意事項:
1. 請以流暢專業的繁體中文回答。
2. 遇到數學、物理、化學公式時,請使用標準 LaTeX 語法格式化(例如 $E=mc^2$ 或 $f(x) = \\int x dx$)。
{mode_instruction}
"""

def extract_text_from_images(image_list: list, model_name: str, extra_info: str = "", max_retries: int = 3) -> str:
    if not GEMINI_API_KEY:
        return "[圖片辨識失敗]: 未設定 GEMINI_API_KEY"
    ocr_prompt = f"請將這幾張圖片中的題目、題目文字、公式或選項進行完整精準的轉錄與辨識。補充說明: {extra_info}"
    clean_model = sanitize_model_name(model_name)
    client = genai.Client(api_key=GEMINI_API_KEY)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=clean_model, contents=image_list + [ocr_prompt]
            )
            return response.text.strip() if response and response.text else "[圖片解析空白]"
        except APIError as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                time.sleep((2**attempt) + random.uniform(0.5, 1.5))
                continue
            return f"[圖片辨識失敗]: {err_str}"
        except Exception as e:
            return f"[圖片辨識失敗]: {str(e)}"

def call_gemini(question_text, mode, model_name, max_retries: int = 3):
    if not GEMINI_API_KEY:
        return json.dumps({"ans": "未設定 Key", "reasoning": "未設定 GEMINI_API_KEY"}, ensure_ascii=False)
    clean_model = sanitize_model_name(model_name)
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"{build_system_prompt(mode)}\n\n題目:{question_text}"
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=clean_model, contents=prompt)
            return response.text if response and response.text else "{}"
        except APIError as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if attempt < max_retries - 1:
                    time.sleep((2**attempt) + random.uniform(0.5, 1.5))
                    continue
                return json.dumps({"ans": "失敗", "reasoning": "!觸發 API 配額限制(429),請稍後再試。"}, ensure_ascii=False)
            elif "404" in err_str or "NOT_FOUND" in err_str:
                return json.dumps(
                    {"ans": "失敗", "reasoning": f"404 錯誤:模型 `{clean_model}` 無法存取,請至管理員頁面切換最新模型。"},
                    ensure_ascii=False,
                )
            else:
                return json.dumps({"ans": "失敗", "reasoning": f"Gemini 呼叫失敗: {err_str}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ans": "失敗", "reasoning": f"Gemini 呼叫失敗: {str(e)}"}, ensure_ascii=False)

def call_chatgpt(question_text, mode, model_name):
    if not OPENAI_API_KEY:
        return json.dumps({"ans": "未設定 Key", "reasoning": "未設定 OPENAI_API_KEY"}, ensure_ascii=False)
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": build_system_prompt(mode)},
                {"role": "user", "content": f"題目:{question_text}"},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        return json.dumps({"ans": "失敗", "reasoning": f"ChatGPT 呼叫失敗: {str(e)}"}, ensure_ascii=False)

def parse_ai_json(raw_text):
    try:
        clean_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return data.get("ans", "未知").strip(), data.get("reasoning", "無解析內容")
    except Exception:
        return "格式解析失敗", raw_text

# =========================================================
# 3. 頁面分流與功能渲染
# =========================================================
# 系統管理後台
if menu_option == "系統管理":
    st.title("⚙️ 管理員控制後台")
    st.subheader("👤 新增使用者帳號")
    col_u1, col_u2 = st.columns([3, 1])
    new_username = col_u1.text_input("學生/使用者姓名", placeholder="例如:李小明", key="add_user_input")
    if col_u2.button("➕ 建立帳號"):
        if new_username.strip():
            u_name_clean = new_username.strip()
            if u_name_clean in st.session_state.users_db:
                st.error("! 該使用者姓名已存在!")
            else:
                st.session_state.users_db[u_name_clean] = {
                    "password": DEFAULT_USER_PASSWORD,
                    "first_login": True,
                    "used_today": 0,
                    "total_used": 0,
                    "custom_limit": None,
                }
                save_config_from_session()
                st.success(f"已成功建立帳號: {u_name_clean} (預設密碼: 2580)")
                st.rerun()
    st.divider()

    st.subheader("📚 分類與科目管理")
    col_s1, col_s2 = st.columns([3, 1])
    new_sub = col_s1.text_input("新增主題/科目", placeholder="例如:微積分、程式語言", key="add_sub_input")
    if col_s2.button("新增"):
        if new_sub.strip() and new_sub not in st.session_state.subjects:
            st.session_state.subjects.append(new_sub.strip())
            save_config_from_session()
            st.success(f"已新增: {new_sub}")
            st.rerun()

    del_sub = st.selectbox("刪除科目", ["請選擇"] + st.session_state.subjects)
    if st.button("刪除科目") and del_sub != "請選擇":
        st.session_state.subjects.remove(del_sub)
        save_config_from_session()
        st.rerun()

    st.divider()
    st.subheader("🔢 預設每日額度設定")
    new_limit = st.number_input(
        "全域使用者預設每日上限",
        min_value=1,
        max_value=500,
        value=st.session_state.daily_limit,
    )
    if st.button("更新預設上限"):
        st.session_state.daily_limit = new_limit
        save_config_from_session()
        st.success("全域預設額度已更新!")

    st.divider()
    st.subheader("👥 使用者帳號與題數管理")
    for u_name, info in list(st.session_state.users_db.items()):
        used_today = info.get("used_today", 0)
        total_used = info.get("total_used", 0)
        eff_limit = info.get("custom_limit") or st.session_state.daily_limit
        with st.expander(f"👤 {u_name} | 今日已用: {used_today}/{eff_limit}題 | 累計提問: {total_used}題"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**密碼狀態**: {'預設密碼(需變更)' if info.get('first_login') else '已自訂密碼'}")
                st.write(f"**今日使用次數**: `{used_today}`題")
                st.write(f"**建號至今累計**: `{total_used}`題")
            with col_b:
                custom_limit_val = st.number_input(
                    "個別指定今日發問上限(留空/維持全域上限)",
                    min_value=0,
                    max_value=1000,
                    value=int(eff_limit),
                    key=f"limit_in_{u_name}",
                )
                if st.button("儲存該生獨立額度", key=f"save_limit_{u_name}"):
                    st.session_state.users_db[u_name]["custom_limit"] = custom_limit_val
                    save_config_from_session()
                    st.success(f"已將 {u_name} 的上限修改為 {custom_limit_val} 題")
                    st.rerun()

            st.divider()
            btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
            if btn_c1.button("修改名字", key=f"edit_{u_name}"):
                st.session_state[f"editing_user_{u_name}"] = True
            if btn_c2.button("重置今日次數", key=f"reset_count_{u_name}"):
                st.session_state.users_db[u_name]["used_today"] = 0
                save_config_from_session()
                st.toast(f"已重置 {u_name} 的今日發問次數!")
                st.rerun()
            if btn_c3.button("重置密碼", key=f"reset_pwd_{u_name}"):
                st.session_state.users_db[u_name]["password"] = DEFAULT_USER_PASSWORD
                st.session_state.users_db[u_name]["first_login"] = True
                save_config_from_session()
                st.toast(f"已將 {u_name} 的密碼重置為預設密碼(2580)!")
                st.rerun()
            if btn_c4.button("刪除帳號", key=f"del_{u_name}"):
                del st.session_state.users_db[u_name]
                save_config_from_session()
                st.rerun()

            if st.session_state.get(f"editing_user_{u_name}", False):
                with st.form(key=f"rename_form_{u_name}"):
                    new_name_val = st.text_input("輸入新名字", value=u_name)
                    submit_rename = st.form_submit_button("確認修改")
                    if submit_rename:
                        new_name_clean = new_name_val.strip()
                        if not new_name_clean:
                            st.error("名字不能為空白!")
                        elif new_name_clean in st.session_state.users_db and new_name_clean != u_name:
                            st.error("此名字已被其他帳號使用!")
                        else:
                            st.session_state.users_db[new_name_clean] = st.session_state.users_db.pop(u_name)
                            for log in st.session_state.history_logs:
                                if log.get("user") == u_name:
                                    log["user"] = new_name_clean
                            for bug in st.session_state.bug_reports:
                                if bug.get("user") == u_name:
                                    bug["user"] = new_name_clean
                            for login in st.session_state.login_logs:
                                if login.get("user") == u_name:
                                    login["user"] = new_name_clean
                            st.session_state[f"editing_user_{u_name}"] = False
                            save_config_from_session()
                            st.success(f"帳號名字已更新為: {new_name_clean}")
                            st.rerun()

# 使用者上線紀錄頁面
elif menu_option == "使用者上線紀錄":
    st.title("📈 使用者登入與上線次數查詢")
    today_date = get_taipei_today_date()
    selected_date = st.date_input("📅 選擇要查詢的日期", value=today_date)
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    st.divider()

    if selected_date > today_date:
        st.warning("! 未來日期無法查詢! 請選擇今日(含)以前的日期。")
    else:
        login_logs = st.session_state.login_logs
        filtered_logs = [log for log in login_logs if log.get("date") == selected_date_str]
        st.subheader(f"📅 日期: {selected_date_str} 統計概覽")
        if not filtered_logs:
            st.info(f"在 {selected_date_str} 沒有任何登入紀錄!")
        else:
            total_logins = len(filtered_logs)
            df_filtered = pd.DataFrame(filtered_logs)
            user_counts = df_filtered["user"].value_counts().reset_index()
            user_counts.columns = ["使用者名稱", "登入/上線次數"]

            m_col1, m_col2 = st.columns(2)
            m_col1.metric("當日總上線人次", f"{total_logins} 次")
            m_col2.metric("當日不重複上線人數", f"{len(user_counts)} 人")
            st.divider()

            st.subheader("🏆 各使用者上線次數排行榜")
            st.dataframe(user_counts, use_container_width=True)
            st.divider()

            st.subheader("🕒 當日詳細上線時間軸記錄")
            for log in reversed(filtered_logs):
                st.text(
                    f"[{log['timestamp']}] 使用者: {log['user']} ({'管理員' if log['role']=='admin' else '學生'}) 登入系統"
                )

# 錯誤回報頁面
elif menu_option == "使用者錯誤回報":
    st.title("🐞 錯誤回報管理")
    reports = st.session_state.bug_reports
    if not reports:
        st.info("目前沒有任何錯誤回報!")
    else:
        for idx, item in enumerate(reversed(reports)):
            real_idx = len(reports) - 1 - idx
            with st.expander(f"[{item['time']}] 回報人: {item['user']} | 狀態: {item.get('status', '待處理')}"):
                st.write(f"**問題描述**: {item['description']}")
                if item.get("related_question"):
                    st.info(f"**關聯題目與解答**:\n{item['related_question']}")
                if st.button("刪除此紀錄", key=f"del_bug_{real_idx}"):
                    st.session_state.bug_reports.pop(real_idx)
                    save_config_from_session()
                    st.rerun()

# 解題紀錄頁面
elif menu_option in ["我的解題紀錄", "所有人解題紀錄"]:
    st.title("📖 解題紀錄與錯題本")
    logs = (
        st.session_state.history_logs
        if st.session_state.user_role == "admin"
        else [log for log in st.session_state.history_logs if log.get("user") == st.session_state.user_name]
    )
    if not logs:
        st.info("尚無任何解題紀錄!")
    else:
        st.subheader("📥 匯出個人解答集/錯題本")
        col_exp1, col_exp2 = st.columns(2)

        md_content = "# 個人解題與錯題複習集\n\n"
        for idx, item in enumerate(logs, 1):
            md_content += f"## 第 {idx} 題 [{item['subject']}]\n"
            md_content += f"- **提問人**: {item.get('user', '未知')}\n"
            md_content += f"- **發問時間**: {item['time']}\n"
            md_content += f"- **題目文字與內容**: {item.get('question_text', '無')}\n"
            md_content += f"- **解題模式/答案**: {item['ans']}\n"
            md_content += f"- **補充說明**: {item.get('extra_info', '無') or '無'}\n\n"
            md_content += f"### 觀念解析:\n{item['reasoning']}\n\n---\n\n"

        col_exp1.download_button(
            label="下載錯題本 (Markdown 格式)",
            data=md_content.encode("utf-8"),
            file_name=f"個人錯題本_{st.session_state.user_name}.md",
            mime="text/markdown",
            use_container_width=True,
        )

        df_logs = pd.DataFrame(logs)
        csv_data = df_logs.to_csv(index=False).encode("utf-8-sig")
        col_exp2.download_button(
            label="下載紀錄表 (CSV 格式)",
            data=csv_data,
            file_name=f"解題紀錄_{st.session_state.user_name}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.divider()

        for item in reversed(logs):
            with st.expander(f"[{item['time']}] {item.get('user', '未知')} - {item['subject']} - 答案: {item['ans']}"):
                st.write(f"**提問人**: {item.get('user', '未知')}")
                st.write(f"**補充說明**: {item.get('extra_info', '無') or '無'}")
                st.markdown(f"**完整題目與辨識內容**:\n```text\n{item.get('question_text', '無文字內容')}\n```")
                images_b64 = item.get("images_b64", [])
                if images_b64:
                    st.write("**提問時上傳的圖片:**")
                    img_cols = st.columns(min(len(images_b64), 3))
                    for b_idx, b64_str in enumerate(images_b64):
                        with img_cols[b_idx % 3]:
                            try:
                                img_data = base64.b64decode(b64_str)
                                st.image(img_data, use_container_width=True)
                            except Exception:
                                st.write("圖片載入失敗")
                st.markdown(f"**AI 解析內容**:\n{item['reasoning']}")

# 開始解題頁面 (核心功能)
elif menu_option == "開始解題":
    st.title("🌸 全能解題實驗室")
    st.caption("支援全學科、各類型問題: 拆解步驟, 清晰脈絡, 精準解答")
    st.divider()

    st.markdown('### 1. 輸入題目內容')
    input_text_question = st.text_area(
        "題目文字描述(可直接貼上文字、題目、程式碼或問題)",
        placeholder="請在此輸入你想要發問或解答的任何問題...",
        height=120,
    )
    uploaded_files = st.file_uploader(
        "上傳題目圖片(可選,最多6張)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if "cropped_images" not in st.session_state:
        st.session_state.cropped_images = {}

    if uploaded_files:
        if len(uploaded_files) > 6:
            st.error("! 最多上傳 6 張圖片!")
        else:
            tabs = st.tabs([f"圖片 {i+1}" for i in range(len(uploaded_files))])
            for idx, file in enumerate(uploaded_files):
                with tabs[idx]:
                    st.divider()
                    raw_img = Image.open(file)
                    cropped_img = st_cropper(
                        raw_img,
                        realtime_update=True,
                        box_color=t["primary"],
                        key=f"crop_{idx}",
                    )
                    st.session_state.cropped_images[idx] = cropped_img

    st.markdown('### 2. 設定主題與模式')
    col_m1, col_m2 = st.columns(2)
    subject = col_m1.selectbox("領域/科目", st.session_state.subjects)
    solve_mode = col_m2.radio(
        "解題模式",
        ["完整解析(直接給答案)", "引導模式(給提示不給答案)"],
        help="「引導模式」不會直接給出最終結果,會提供解題方向與思維提示。",
    )
    mode_key = "hint" if "引導模式" in solve_mode else "full"

    extra_info = st.text_input("補充敘述(選填)", placeholder="例如:請著重說明第二步的推導 logic")

    if st.button("🚀 開始解題", use_container_width=True):
        can_submit = True
        if not st.session_state.enable_gemini and not st.session_state.enable_openai:
            can_submit = False
            st.error("! 管理員已停用所有 AI 模型!")

        if st.session_state.user_role == "user" and can_submit:
            u_name = st.session_state.user_name
            u_info = st.session_state.users_db.get(u_name, {})
            used_today = u_info.get("used_today", 0)
            eff_limit = u_info.get("custom_limit") or st.session_state.daily_limit
            if used_today >= eff_limit:
                can_submit = False
                st.error(f"! 今日額度已用完 ({used_today}/{eff_limit}題), 請明日再試或聯絡管理員增加額度!")

        has_text = bool(input_text_question.strip())
        final_images = (
            [st.session_state.cropped_images[i] for i in range(len(uploaded_files)) if i in st.session_state.cropped_images]
            if uploaded_files
            else []
        )
        has_images = bool(final_images)

        if not has_text and not has_images:
            can_submit = False
            st.warning("請至少輸入題目文字或上傳一張題目圖片!")

        if can_submit:
            if st.session_state.user_role == "user":
                u_name = st.session_state.user_name
                st.session_state.users_db[u_name]["used_today"] = (
                    st.session_state.users_db[u_name].get("used_today", 0) + 1
                )
                st.session_state.users_db[u_name]["total_used"] = (
                    st.session_state.users_db[u_name].get("total_used", 0) + 1
                )

            gemini_model = st.session_state.selected_gemini_model
            openai_model = st.session_state.selected_openai_model

            with st.status("正在進行 AI 解析與平行驗證...", expanded=True):
                full_question_text = ""
                if has_images:
                    st.write("🔍 **步驟 1/2**: 進行 Gemini 多圖視覺 OCR 辨識...")
                    ocr_extracted = extract_text_from_images(final_images, gemini_model, extra_info)
                    if has_text:
                        full_question_text = (
                            f"【使用者文字輸入】:\n{input_text_question.strip()}\n\n【圖片辨識內容】:\n{ocr_extracted}"
                        )
                    else:
                        full_question_text = ocr_extracted
                else:
                    st.write("📝 **步驟 1/2**: 處理文字題目...")
                    full_question_text = input_text_question.strip()

                st.write("🧠 **步驟 2/2**: 啟動雙 AI 模組進行平行邏輯推理...")
                g_raw, c_raw = "", ""
                with ThreadPoolExecutor(max_workers=2) as executor:
                    future_g = (
                        executor.submit(call_gemini, full_question_text, mode_key, gemini_model)
                        if st.session_state.enable_gemini
                        else None
                    )
                    future_c = (
                        executor.submit(call_chatgpt, full_question_text, mode_key, openai_model)
                        if st.session_state.enable_openai
                        else None
                    )

                    if future_g:
                        g_raw = future_g.result()
                    if future_c:
                        c_raw = future_c.result()

                g_ans, g_reason = parse_ai_json(g_raw) if st.session_state.enable_gemini else ("未啟用", "未啟用")
                c_ans, c_reason = parse_ai_json(c_raw) if st.session_state.enable_openai else ("未啟用", "未啟用")

                main_ans = g_ans if st.session_state.enable_gemini else c_ans
                main_reason = g_reason if st.session_state.enable_gemini else c_reason

                images_b64 = [pil_to_base64(img) for img in final_images]
                latest_log = {
                    "user": st.session_state.user_name,
                    "time": get_taipei_now_str(),
                    "subject": subject,
                    "ans": main_ans,
                    "reasoning": main_reason,
                    "question_text": full_question_text,
                    "images_b64": images_b64,
                    "extra_info": extra_info,
                }
                st.session_state.history_logs.append(latest_log)
                st.session_state.latest_result = latest_log
                save_config_from_session()

    # --- 渲染解答結果與問題回報區塊 ---
    if "latest_result" in st.session_state and st.session_state.latest_result:
        res = st.session_state.latest_result
        st.divider()
        st.markdown('### 3. 觀念解析與交叉驗證')
        st.markdown(f"**題目主題**: `{res['subject']}` | **解答結果**: `{res['ans']}`")
        st.markdown(f"**詳細解析:**\n{res['reasoning']}")
        st.divider()

        with st.expander("對此題解答有疑問? 點此進行問題回報"):
            bug_desc = st.text_area("請描述您發現的問題(例如: 答案算錯、解析不清楚、圖片辨識有誤)", key="latest_bug_desc")
            if st.button("送出錯誤回報"):
                if bug_desc.strip():
                    st.session_state.bug_reports.append(
                        {
                            "user": st.session_state.user_name,
                            "time": get_taipei_now_str(),
                            "description": bug_desc.strip(),
                            "related_question": (
                                f"[{res['subject']}] 答案: {res['ans']}\n"
                                f"題目內容: {res['question_text']}"
                            ),
                            "status": "待處理",
                        }
                    )
                    save_config_from_session()
                    st.success("問題回報已成功送出! 管理員將會進行審核。")
                else:
                    st.warning("請先輸入問題描述再送出。")
