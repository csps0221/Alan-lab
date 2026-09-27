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
import streamlit.components.v1 as components

# 時區設定
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

def get_taipei_now_str():
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_taipei_today_str():
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")

# ==========================================
# 0. 資料庫與設定檔機制
# ==========================================
CONFIG_FILE = "config.json"
FILE_LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "daily_limit": 15,
    "selected_gemini_model": "gemini-3.1-pro",
    "selected_openai_model": "gpt-4o-mini",
    "enable_gemini": True,
    "enable_openai": True,
    "theme_color": "dark_blue",
    "subjects": ["化學", "理化", "生物", "地科", "數學", "其他"],
    "bug_reports": [],
    "history_logs": [],
    "login_logs": [],
    "users_db": {
        "Alan2580": {
            "password": "csps106121",
            "class_name": "系統管理員",
            "role": "admin",
            "first_login": False,
            "used_today": 0,
            "total_used": 0,
            "custom_limit": 99999,
        },
    },
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        try:
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        except Exception:
            return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for key, val in DEFAULT_CONFIG.items():
                if key not in cfg:
                    cfg[key] = val
            return cfg
    except Exception:
        return DEFAULT_CONFIG

def save_config(config_data):
    with FILE_LOCK:
        temp_file = f"{CONFIG_FILE}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, CONFIG_FILE)
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)

def save_config_from_session():
    config_data = {
        "daily_limit": st.session_state.daily_limit,
        "selected_gemini_model": st.session_state.selected_gemini_model,
        "selected_openai_model": st.session_state.selected_openai_model,
        "enable_gemini": st.session_state.enable_gemini,
        "enable_openai": st.session_state.enable_openai,
        "theme_color": st.session_state.theme_color,
        "subjects": st.session_state.subjects,
        "bug_reports": st.session_state.bug_reports,
        "history_logs": st.session_state.history_logs,
        "login_logs": st.session_state.login_logs,
        "users_db": st.session_state.users_db,
    }
    save_config(config_data)

def compress_and_to_b64(img: Image.Image, max_size=(1024, 1024), quality=75) -> str:
    """自動將圖片轉換格式、縮放並進行 JPEG 壓縮"""
    img_copy = img.copy()
    if img_copy.mode in ("RGBA", "P"):
        img_copy = img_copy.convert("RGB")
    img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffered = BytesIO()
    img_copy.save(buffered, format="JPEG", quality=quality)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# ==========================================
# 1. 頁面初始化與多色彩樣式
# ==========================================
st.set_page_config(page_title="A.lab | 解題實驗室", page_icon="🧪", layout="centered")

config = load_config()

if "history_logs" not in st.session_state:
    st.session_state.history_logs = config.get("history_logs", [])
if "login_logs" not in st.session_state:
    st.session_state.login_logs = config.get("login_logs", [])
if "daily_limit" not in st.session_state:
    st.session_state.daily_limit = config.get("daily_limit", 15)
if "users_db" not in st.session_state:
    st.session_state.users_db = config.get("users_db", DEFAULT_CONFIG["users_db"])
if "subjects" not in st.session_state:
    st.session_state.subjects = config.get("subjects", DEFAULT_CONFIG["subjects"])
if "bug_reports" not in st.session_state:
    st.session_state.bug_reports = config.get("bug_reports", [])
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "home"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "must_change_pwd" not in st.session_state:
    st.session_state.must_change_pwd = False
if "selected_gemini_model" not in st.session_state:
    st.session_state.selected_gemini_model = config.get("selected_gemini_model", "gemini-3.1-pro")
if "selected_openai_model" not in st.session_state:
    st.session_state.selected_openai_model = config.get("selected_openai_model", "gpt-4o-mini")
if "enable_gemini" not in st.session_state:
    st.session_state.enable_gemini = config.get("enable_gemini", True)
if "enable_openai" not in st.session_state:
    st.session_state.enable_openai = config.get("enable_openai", True)
if "theme_color" not in st.session_state:
    st.session_state.theme_color = config.get("theme_color", "dark_blue")

GEMINI_API_KEY = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
OPENAI_API_KEY = str(st.secrets.get("OPENAI_API_KEY", "")).strip()

THEME_PALETTES = {
    "dark_blue": {
        "bg": "#0D1117",
        "card_bg": "linear-gradient(135deg, #161B22 0%, #0D1117 100%)",
        "card_border": "#30363D",
        "primary_btn": "linear-gradient(135deg, #38BDF8 0%, #0284C7 100%)",
        "btn_text": "#FFFFFF",
        "highlight": "#38BDF8",
        "badge_bg": "#1F2937",
    },
    "emerald": {
        "bg": "#064E3B",
        "card_bg": "linear-gradient(135deg, #065F46 0%, #022C22 100%)",
        "card_border": "#059669",
        "primary_btn": "linear-gradient(135deg, #34D399 0%, #059669 100%)",
        "btn_text": "#FFFFFF",
        "highlight": "#6EE7B7",
        "badge_bg": "#064E3B",
    },
    "purple": {
        "bg": "#2E1065",
        "card_bg": "linear-gradient(135deg, #3B0764 0%, #1E1B4B 100%)",
        "card_border": "#7C3AED",
        "primary_btn": "linear-gradient(135deg, #C084FC 0%, #7E22CE 100%)",
        "btn_text": "#FFFFFF",
        "highlight": "#E9D5FF",
        "badge_bg": "#4C1D95",
    },
    "sunset_orange": {
        "bg": "#431407",
        "card_bg": "linear-gradient(135deg, #7C2D12 0%, #292524 100%)",
        "card_border": "#EA580C",
        "primary_btn": "linear-gradient(135deg, #FB923C 0%, #C2410C 100%)",
        "btn_text": "#FFFFFF",
        "highlight": "#FFEDD5",
        "badge_bg": "#7C2D12",
    },
    "sakura_pink": {
        "bg": "#500724",
        "card_bg": "linear-gradient(135deg, #831843 0%, #310E17 100%)",
        "card_border": "#DB2777",
        "primary_btn": "linear-gradient(135deg, #F472B6 0%, #BE185D 100%)",
        "btn_text": "#FFFFFF",
        "highlight": "#FCE7F3",
        "badge_bg": "#831843",
    },
}

current_theme = THEME_PALETTES.get(st.session_state.theme_color, THEME_PALETTES["dark_blue"])

st.markdown(
    f"""
    <style>
    @media (prefers-color-scheme: dark), (prefers-color-scheme: light) {{
        .stApp {{
            background-color: {current_theme["bg"]} !important;
            color: #F8FAFC !important;
        }}
    }}
    header[data-testid="stHeader"] {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    .custom-card {{
        background: {current_theme["card_bg"]} !important;
        border: 1.5px solid {current_theme["card_border"]} !important;
        border-radius: 16px !important;
        padding: 16px !important;
        margin-bottom: 12px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
        color: #F8FAFC !important;
    }}
    .admin-stat-card {{
        background: {current_theme["card_bg"]} !important;
        border: 1px solid {current_theme["card_border"]} !important;
        border-radius: 12px !important;
        padding: 12px 14px !important;
        text-align: center;
    }}
    .admin-stat-num {{
        font-size: 22px !important;
        font-weight: 800 !important;
        color: {current_theme["highlight"]} !important;
    }}
    .admin-stat-label {{
        font-size: 11px !important;
        color: #94A3B8 !important;
        margin-top: 2px;
    }}
    .top-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: {current_theme["card_bg"]} !important;
        border: 1.5px solid {current_theme["card_border"]} !important;
        border-radius: 16px;
        padding: 12px 16px;
        margin-bottom: 14px;
    }}
    .header-title {{
        font-size: 17px !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
    }}
    .header-sub {{
        font-size: 11px !important;
        color: #94A3B8 !important;
    }}
    .user-avatar {{
        width: 42px;
        height: 42px;
        background: {current_theme["primary_btn"]} !important;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        font-weight: bold;
        color: #FFFFFF !important;
    }}
    .quota-badge {{
        background-color: {current_theme["badge_bg"]} !important;
        border: 1px solid {current_theme["card_border"]} !important;
        border-radius: 12px;
        padding: 6px 12px;
        text-align: right;
    }}
    .step-number {{
        display: inline-block;
        width: 22px;
        height: 22px;
        background: {current_theme["primary_btn"]} !important;
        color: #FFFFFF !important;
        border-radius: 6px;
        text-align: center;
        line-height: 22px;
        font-size: 12px;
        font-weight: bold;
        margin-right: 6px;
    }}
    div.stButton > button {{
        background: {current_theme["primary_btn"]} !important;
        color: {current_theme["btn_text"]} !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
        padding: 8px 14px !important;
        transition: all 0.2s ease-in-out !important;
    }}
    div.stButton > button:hover {{
        filter: brightness(1.15) !important;
        box-shadow: 0 0 12px {current_theme["highlight"]} !important;
    }}
    div.stButton > button p {{ color: {current_theme["btn_text"]} !important; }}
    .secondary-btn div.stButton > button {{
        background: #1E293B !important;
        border: 1px solid {current_theme["card_border"]} !important;
    }}
    .secondary-btn div.stButton > button p {{ color: #CBD5E1 !important; }}
    input, textarea, div[data-baseweb="input"] > div {{
        background-color: #0F172A !important;
        color: #F8FAFC !important;
        border: 1px solid {current_theme["card_border"]} !important;
        border-radius: 10px !important;
    }}
    label {{ color: #F8FAFC !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 2. 登入邏輯 (含重設/修改密碼保護)
# ==========================================
if not st.session_state.logged_in:
    st.markdown(
        """
        <div class="top-header" style="justify-content: center; text-align: center; margin-top: 20px;">
            <div>
                <div style="font-size: 36px; margin-bottom: 8px;">🧪</div>
                <div class="header-title" style="font-size: 22px;">A.lab | 解題實驗室</div>
                <div class="header-sub">Science Lab Solution Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # 第一次登入/密碼遭重設時強制修改密碼
    if st.session_state.must_change_pwd:
        with st.container():
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown("### 初次登入/密碼重設 - 請修改密碼")
            st.info("為了您的帳號安全，初次登入或重設密碼後請設定新密碼！")
            new_pwd = st.text_input("輸入新密碼", type="password", placeholder="請輸入新密碼")
            confirm_pwd = st.text_input("確認新密碼", type="password", placeholder="請再次輸入新密碼")
            
            if st.button("確認修改並登入", use_container_width=True):
                if not new_pwd:
                    st.error("新密碼不可為空白！")
                elif new_pwd != confirm_pwd:
                    st.error("兩次輸入的密碼不一致，請重新確認！")
                else:
                    user_n = st.session_state.temp_user
                    st.session_state.users_db[user_n]["password"] = new_pwd
                    st.session_state.users_db[user_n]["first_login"] = False
                    st.session_state.logged_in = True
                    st.session_state.must_change_pwd = False
                    st.session_state.user_name = user_n
                    st.session_state.user_role = st.session_state.users_db[user_n].get("role", "user")
                    st.session_state.login_logs.append({"user": user_n, "time": get_taipei_now_str()})
                    save_config_from_session()
                    st.success("密碼修改成功！正在進入系統...")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            st.stop()
            
    # 一般登入介面
    with st.container():
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("### 使用者登入")
        input_username = st.text_input("帳號", placeholder="請輸入帳號")
        input_password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
        
        if st.button("登入系統", use_container_width=True):
            users = st.session_state.users_db
            if input_username in users and users[input_username]["password"] == input_password:
                if users[input_username].get("first_login", True):
                    st.session_state.must_change_pwd = True
                    st.session_state.temp_user = input_username
                    st.rerun()
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_name = input_username
                    st.session_state.user_role = users[input_username].get("role", "user")
                    st.session_state.login_logs.append({"user": input_username, "time": get_taipei_now_str()})
                    save_config_from_session()
                    st.toast(f"歡迎回來，{input_username}！", icon="👋")
                    st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新確認！")
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()

# ==========================================
# 3. AI 核心邏輯
# ==========================================
def build_system_prompt(subject: str = "通用"):
    return f"""你是一位專業嚴謹的【{subject}】領域萬能 AI 導師。
請針對使用者提出的問題(無論是文字敘述或圖片題目)進行【{subject}】領域精準解答與深度邏輯剖析。
請嚴格回傳JSON格式(不要包裹在 markdown codeblock 中):
{{
  "ans": "正確答案選項或簡短最終結果",
  "reasoning": "步驟清晰、邏輯嚴謹的詳細觀念推導過程"
}}
遇到公式請使用標準 LaTeX 語法(如 $E=mc^{2}$)。請以繁體中文回答。"""

def extract_text_from_images(image_list: list, extra_info: str = "", subject: str = "通用") -> str:
    if not GEMINI_API_KEY or not image_list or not st.session_state.enable_gemini:
        return ""
    ocr_prompt = f"這是一道【{subject}】科目的題目。請詳細轉錄圖片中的所有題目文字、選項與公式。補充文字描述:\n{extra_info}"
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=st.session_state.selected_gemini_model, 
            contents=image_list + [ocr_prompt]
        )
        return response.text.strip() if response and response.text else ""
    except Exception as e:
        return f"[圖片辨識說明]: {str(e)}"

def call_ai_solver(question_text, subject="通用", retries=2):
    if not st.session_state.enable_gemini and not st.session_state.enable_openai:
        return "服務已關閉", "管理員目前已關閉所有 AI 解題服務系統。"
    if not GEMINI_API_KEY and not OPENAI_API_KEY:
        return "未設定 API Key", "請在 secrets.toml 中設定 API Key。"
        
    sys_prompt = build_system_prompt(subject)
    prompt = f"{sys_prompt}\n\n【{subject}】題目需求與描述:\n{question_text}"
    
    for attempt in range(retries + 1):
        try:
            if GEMINI_API_KEY and st.session_state.enable_gemini:
                client = genai.Client(api_key=GEMINI_API_KEY)
                resp = client.models.generate_content(
                    model=st.session_state.selected_gemini_model, contents=prompt
                )
                raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)
                return data.get("ans", "無解答"), data.get("reasoning", "無解析內容")
                
            if OPENAI_API_KEY and st.session_state.enable_openai:
                client = OpenAI(api_key=OPENAI_API_KEY)
                resp = client.chat.completions.create(
                    model=st.session_state.selected_openai_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"【{subject}】題目需求與描述:\n{question_text}"},
                    ],
                )
                data = json.loads(resp.choices[0].message.content)
                return data.get("ans", "無解答"), data.get("reasoning", "無解析內容")
        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(1)
                continue
            return "解析格式錯誤", "AI 回傳格式不符 JSON 規範，請重試一次。"
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            return "解析失敗", f"呼叫 AI 時發生錯誤: {str(e)}"
    return "解析失敗", "無法存取 AI 模型或相關服務連線逾時。"

# ==========================================
# 4. 主介面 Header 與用戶資訊卡片
# ==========================================
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(
        """
        <div class="top-header" style="margin-bottom: 0px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">🧪</span>
                <div>
                    <div class="header-title">A.lab | 解題實驗室</div>
                    <div class="header-sub">Science Lab Platform</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_h2:
    theme_choice = st.selectbox(
        "主題色彩",
        options=["dark_blue", "emerald", "purple", "sunset_orange", "sakura_pink"],
        format_func=lambda x: {
            "dark_blue": "深藍",
            "emerald": "翡翠綠",
            "purple": "夢幻紫",
            "sunset_orange": "熾焰橘",
            "sakura_pink": "櫻花粉",
        }[x],
        index=["dark_blue", "emerald", "purple", "sunset_orange", "sakura_pink"].index(st.session_state.theme_color),
        label_visibility="collapsed",
    )
    if theme_choice != st.session_state.theme_color:
        st.session_state.theme_color = theme_choice
        save_config_from_session()
        st.rerun()

st.write("")
user_name = st.session_state.user_name
user_info = st.session_state.users_db.get(user_name, {"class_name": "學生", "used_today": 0, "custom_limit": 15})
class_name = user_info.get("class_name", "學生")
used_today = user_info.get("used_today", 0)
limit = user_info.get("custom_limit") or 15
remains = max(0, limit - used_today) if st.session_state.user_role != "admin" else "無限"

col_head1, col_head2 = st.columns([3, 2])
with col_head1:
    st.markdown(
        f"""
        <div class="custom-card" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="user-avatar">{user_name[0]}</div>
                <div>
                    <div style="font-size: 17px; font-weight: bold; color: #FFFFFF;">{user_name}</div>
                    <div style="font-size: 11px; color: #94A3B8;">{class_name}</div>
                </div>
            </div>
            <div class="quota-badge">
                <div style="font-size: 10px; color: #94A3B8;">題數狀態</div>
                <div style="font-size: 11px; color: #CBD5E1;">今日剩餘 <span style="font-size: 18px; font-weight: bold; color: #FFFFFF;">{remains}</span> 題</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_head2:
    st.markdown('<div class="secondary-btn" style="margin-top: 4px; display: flex; gap: 4px;">', unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("修改密碼", use_container_width=True):
            st.session_state.show_change_pwd_dialog = True
    with col_btn2:
        if st.button("登出", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 主動修改密碼 Dialog
if st.session_state.get("show_change_pwd_dialog", False):
    @st.dialog("修改個人密碼")
    def change_user_password_dialog():
        st.write("請輸入目前密碼與新密碼：")
        old_p = st.text_input("原密碼", type="password", key="dialog_old_p")
        new_p = st.text_input("新密碼", type="password", key="dialog_new_p")
        conf_p = st.text_input("確認新密碼", type="password", key="dialog_conf_p")
        
        if st.button("儲存新密碼", use_container_width=True):
            current_real_p = st.session_state.users_db[user_name].get("password")
            if old_p != current_real_p:
                st.error("原密碼輸入不正確！")
            elif not new_p:
                st.error("新密碼不可為空白！")
            elif new_p != conf_p:
                st.error("兩次輸入的新密碼不一致！")
            else:
                st.session_state.users_db[user_name]["password"] = new_p
                save_config_from_session()
                st.success("密碼成功修改！")
                st.session_state.show_change_pwd_dialog = False
                st.rerun()
    change_user_password_dialog()

st.write("")
is_admin = st.session_state.get("user_role") == "admin"
cols = st.columns(4 if is_admin else 3)
if cols[0].button("首頁", use_container_width=True):
    st.session_state.active_tab = "home"
    st.rerun()
if cols[1].button("最新解析", use_container_width=True):
    st.session_state.active_tab = "analysis"
    st.rerun()
if cols[2].button("解題紀錄", use_container_width=True):
    st.session_state.active_tab = "history"
    st.rerun()
if is_admin and cols[3].button("後台", use_container_width=True):
    st.session_state.active_tab = "admin"
    st.rerun()

st.divider()

# ==========================================
# 5. 頁面分流邏輯
# ==========================================

# --- TAB 1: 首頁 ---
if st.session_state.active_tab == "home":
    st.markdown(
        """
        <div style="font-size: 15px; font-weight: bold; color: #FFFFFF; margin-bottom: 8px;">
            <span class="step-number">1</span> 輸入文字題目或上傳圖片
        </div>
        """,
        unsafe_allow_html=True,
    )
    text_question = st.text_area(
        "文字題目描述(可直接貼上題目文字、觀念問題)",
        placeholder="例如:請幫我解釋氧化還原反應中,氧化劑與還原劑的判斷方式...",
        height=120,
    )
    uploaded_files = st.file_uploader(
        "上傳題目圖片(選填,可1~5張)", type=["png", "jpg", "jpeg"], accept_multiple_files=True
    )
    cropped_images = []
    if uploaded_files:
        st.markdown("#### 圖片裁切預覽")
        for i, f in enumerate(uploaded_files):
            img = Image.open(f)
            st.write(f"圖片{i+1}:")
            cropped_img = st_cropper(
                img, realtime_update=True, box_color=current_theme["highlight"], aspect_ratio=None, key=f"crop_{i}"
            )
            cropped_images.append(cropped_img)

    st.markdown(
        """
        <div style="font-size: 15px; font-weight: bold; color: #FFFFFF; margin-top: 16px; margin-bottom: 8px;">
            <span class="step-number">2</span> 設定科目與額外資訊
        </div>
        """,
        unsafe_allow_html=True,
    )
    selected_subject = st.selectbox("選擇題目科目", st.session_state.subjects, index=0)
    ref_answer = st.text_input("標準參考答案(選填)", placeholder="例如 B、ACD、2.5 mol...")

    col_b1, col_b2 = st.columns([3, 1])
    submit_btn = col_b1.button("開始解題", use_container_width=True)
    with col_b2:
        st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
        clear_btn = st.button("清除", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if submit_btn:
        if isinstance(remains, int) and remains <= 0:
            st.error("今日解題額度已用完，請明日再試！")
        elif not uploaded_files and not text_question.strip():
            st.warning("請輸入文字題目或上傳題目圖片！")
        else:
            with st.spinner(f"A.lab AI 正在針對【{selected_subject}】進行分析與解題中..."):
                images_to_process = (
                    cropped_images
                    if cropped_images
                    else ([Image.open(f) for f in uploaded_files] if uploaded_files else [])
                )
                ocr_text = (
                    extract_text_from_images(images_to_process, text_question, subject=selected_subject)
                    if images_to_process
                    else ""
                )

                combined_question = ""
                if text_question.strip():
                    combined_question += f"使用者文字題目/補充:\n{text_question.strip()}\n\n"
                if ocr_text:
                    combined_question += f"圖片題目辨識內容:\n{ocr_text}"

                ans, reasoning = call_ai_solver(combined_question, subject=selected_subject)
                images_b64 = [compress_and_to_b64(img) for img in images_to_process]

                new_record = {
                    "id": str(time.time()),
                    "user": user_name,
                    "time": get_taipei_now_str(),
                    "subject": selected_subject,
                    "ref_answer": ref_answer or "無",
                    "note": text_question or "無",
                    "ans": ans,
                    "reasoning": reasoning,
                    "images_b64": images_b64,
                    "admin_feedback": {
                        "status": "pending",
                        "comment": "",
                    },
                }
                st.session_state.history_logs.append(new_record)
                st.session_state.latest_analysis = new_record
                user_info["used_today"] += 1
                save_config_from_session()
                st.toast("解題完成！", icon="🎉")
                st.session_state.active_tab = "analysis"
                st.rerun()

# --- TAB 2: 解析結果 (個人隱私保護) ---
elif st.session_state.active_tab == "analysis":
    st.markdown("### 最新解題觀念解析")
    latest = st.session_state.get("latest_analysis")
    
    # 確保學生僅能查看屬於自己的最新解析紀錄
    if latest and (latest.get("user") == user_name or is_admin):
        res = latest
        feedback = res.get("admin_feedback", {})
        status = feedback.get("status", "pending")
        comment = feedback.get("comment", "")

        status_badge = ""
        if status == "correct":
            status_badge = "<span style='background:#059669; color:white; padding:2px 8px; border-radius:6px; font-size:12px;'>管理員審核: 正確</span>"
        elif status == "incorrect":
            status_badge = "<span style='background:#DC2626; color:white; padding:2px 8px; border-radius:6px; font-size:12px;'>管理員審核: 需再加強</span>"

        st.markdown(
            f"""
            <div class="custom-card">
                <div style="display: flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                    <div style="color: {current_theme['highlight']}; font-weight: bold; font-size: 16px;">[{res['subject']}] 觀念拆解與解答</div>
                    <div>{status_badge}</div>
                </div>
                <div style="font-size: 13px; color: #94A3B8; margin-bottom: 6px;">標準參考答案: <b style="color:#FFFFFF;">{res['ref_answer']}</b> | AI 答案: <b style="color:{current_theme['highlight']};">{res['ans']}</b></div>
                <div style="font-size: 14px; line-height: 1.6; color: #F8FAFC; white-space: pre-line; margin-top: 10px;">
                    <b>觀念推導過程:</b>\n{res['reasoning']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if comment:
            st.markdown(
                f"""
                <div class="custom-card" style="border-color: #F59E0B !important;">
                    <div style="color: #F59E0B; font-weight: bold; font-size: 14px; margin-bottom: 4px;">管理員點評與觀念加強:</div>
                    <div style="font-size: 13px; color: #F8FAFC;">{comment}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("目前尚無最新的解題結果，請至「首頁」輸入或上傳題目。")

# --- TAB 3: 我的解題紀錄 (個人隱私隔離) ---
elif st.session_state.active_tab == "history":
    st.markdown("### 我的解題紀錄")
    search_kw = st.text_input("搜尋關鍵字", placeholder="搜尋答案、題目文字、解析內容...", label_visibility="collapsed")
    
    # 隱私保護過濾：一般學生僅能檢視自己的解題紀錄，管理員可審視全部
    logs = [l for l in st.session_state.history_logs if l.get("user") == user_name or is_admin]

    if search_kw:
        logs = [l for l in logs if search_kw.lower() in str(l).lower()]

    st.caption(f"共 {len(logs)} 筆紀錄")

    if not logs:
        st.info("尚無解題紀錄！")
    else:
        for idx, item in enumerate(reversed(logs)):
            img_count = len(item.get("images_b64", []))
            feedback = item.get("admin_feedback", {})
            status = feedback.get("status", "pending")

            tag_html = ""
            if status == "correct":
                tag_html = "<span style='color:#34D399; font-size: 11px; margin-left:6px;'>[已核可]</span>"
            elif status == "incorrect":
                tag_html = "<span style='color:#F87171; font-size: 11px; margin-left: 6px;'>[! 需加強]</span>"

            st.markdown(
                f"""
                <div class="custom-card" style="display: flex; gap: 12px; align-items: flex-start;">
                    <div style="width: 65px; height: 65px; background: #1E293B; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #94A3B8;">
                        {f'{img_count}張' if img_count > 0 else '文字'}
                    </div>
                    <div style="flex: 1;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: bold; color: #FFFFFF; font-size: 14px;">{item['subject']} ({item['user']}){tag_html}</span>
                            <span style="font-size: 11px; color: #64748B;">{item['time']}</span>
                        </div>
                        <div style="font-size: 13px; color: #CBD5E1; margin-top: 3px;">答案: {item.get('ans', '無')}</div>
                        <div style="font-size: 11px; color: #94A3B8; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                            {item.get('note', '') if item.get('note') != '無' else item.get('reasoning', '')}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# --- TAB 4: 後台管理員系統 ---
elif st.session_state.active_tab == "admin":
    if not is_admin:
        st.error("存取被拒絕: 您沒有進入後台管理系統的權限！")
        if st.button("返回首頁"):
            st.session_state.active_tab = "home"
            st.rerun()
        st.stop()

    all_logs = st.session_state.history_logs
    total_logs_cnt = len(all_logs)
    reviewed_logs = [l for l in all_logs if l.get("admin_feedback", {}).get("status") in ["correct", "incorrect"]]
    correct_cnt = sum(1 for l in reviewed_logs if l.get("admin_feedback", {}).get("status") == "correct")
    accuracy_rate = (correct_cnt / len(reviewed_logs) * 100) if reviewed_logs else 0.0

    st.markdown("<h3 style='margin-bottom: 12px;'>🧪 A.lab 後台管理系統</h3>", unsafe_allow_html=True)

    total_users_cnt = len(st.session_state.users_db)
    ai_status = "正常" if (st.session_state.enable_gemini or st.session_state.enable_openai) else "停用"

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.markdown(
            f'<div class="admin-stat-card"><div class="admin-stat-num">{total_users_cnt}</div><div class="admin-stat-label">註冊使用者</div></div>',
            unsafe_allow_html=True,
        )
    with m_col2:
        st.markdown(
            f'<div class="admin-stat-card"><div class="admin-stat-num">{total_logs_cnt}</div><div class="admin-stat-label">累積解題量</div></div>',
            unsafe_allow_html=True,
        )
    with m_col3:
        st.markdown(
            f'<div class="admin-stat-card"><div class="admin-stat-num">{accuracy_rate:.1f}%</div><div class="admin-stat-label">解答正確率({len(reviewed_logs)}筆已審)</div></div>',
            unsafe_allow_html=True,
        )
    with m_col4:
        st.markdown(
            f'<div class="admin-stat-card"><div class="admin-stat-num" style="font-size:16px;">{ai_status}</div><div class="admin-stat-label">AI引擎狀態</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    admin_tab1, admin_tab2, admin_tab3, admin_tab4, admin_tab5 = st.tabs(
        ["使用者與權限", "科目管理", "解題點評與歷史紀錄", "AI 模型設定", "Bug回報"]
    )

    # 1. 使用者管理與密碼重設
    with admin_tab1:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### 帳號總覽與狀態")
        user_rows = []
        for uname, udata in st.session_state.users_db.items():
            user_rows.append(
                {
                    "帳號": uname,
                    "身分類別": udata.get("class_name", "學生"),
                    "權限角色": "管理員" if udata.get("role") == "admin" else "一般使用者",
                    "今日已用": f"{udata.get('used_today', 0)}題",
                    "每日額度上限": f"{udata.get('custom_limit', 15)}題",
                    "首次登入狀態": "待修改密碼" if udata.get("first_login") else "已修改密碼",
                }
            )
        st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        col_add, col_reset, col_del = st.columns(3)
        # + 新增學生帳號
        with col_add:
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown("#### 新增學生帳號")
            new_username = st.text_input("輸入新學生帳號", key="new_u_name", placeholder="例如:張小明")
            new_password = st.text_input("預設密碼", value="2580", type="password", key="new_u_pwd")
            new_limit = st.number_input("每日解題額度", min_value=1, max_value=99999, value=15, key="new_u_limit")
            if st.button("新增帳號", use_container_width=True):
                new_username = new_username.strip()
                if not new_username:
                    st.error("請輸入學生帳號！")
                elif new_username in st.session_state.users_db:
                    st.error(f"帳號 `{new_username}` 已經存在！")
                else:
                    st.session_state.users_db[new_username] = {
                        "password": new_password,
                        "class_name": "學生",
                        "role": "user",
                        "first_login": True,
                        "used_today": 0,
                        "total_used": 0,
                        "custom_limit": new_limit,
                    }
                    save_config_from_session()
                    st.success(f"成功新增學生: {new_username}！")
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # 🔑 重設學生密碼 (新增管理員安全重設機制)
        with col_reset:
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown("#### 重設學生密碼")
            resetable_users = [u for u, d in st.session_state.users_db.items() if d.get("role") != "admin"]
            if resetable_users:
                target_reset_u = st.selectbox("選擇要重設密碼的學生", resetable_users, key="reset_u_select")
                st.caption("重設後密碼將還原為 `2580`，且該學生下次登入需強制修改密碼。")
                if st.button("確認重設密碼", use_container_width=True):
                    st.session_state.users_db[target_reset_u]["password"] = "2580"
                    st.session_state.users_db[target_reset_u]["first_login"] = True
                    save_config_from_session()
                    st.success(f"已成功將 {target_reset_u} 的密碼重設為 2580！")
                    st.rerun()
            else:
                st.info("目前沒有可供重設的一般學生帳號。")
            st.markdown('</div>', unsafe_allow_html=True)

        # X 刪除學生帳號
        with col_del:
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown("#### 刪除學生帳號")
            deletable_users = [
                u for u, d in st.session_state.users_db.items()
                if u != st.session_state.user_name and d.get("role") != "admin"
            ]
            if deletable_users:
                user_to_delete = st.selectbox("選擇要刪除的學生帳號", deletable_users)
                if st.button("確定刪除帳號", use_container_width=True):
                    del st.session_state.users_db[user_to_delete]
                    save_config_from_session()
                    st.warning(f"已成功刪除學生帳號: {user_to_delete}")
                    st.rerun()
            else:
                st.info("目前沒有可供刪除的一般學生帳號。")
            st.markdown('</div>', unsafe_allow_html=True)

        # 額度調整
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### 解題額度調整機制")
        st.markdown("**1. 快速批量統一設定(全體一般使用者)**")
        col_all1, col_all2 = st.columns([3, 1])
        all_limit_val = col_all1.number_input("設定每日統一解題上限(題)", min_value=1, max_value=99999, value=15, key="all_limit_input")
        if col_all2.button("套用至全體", use_container_width=True):
            for u_name, u_data in st.session_state.users_db.items():
                if u_data.get("role") != "admin":
                    u_data["custom_limit"] = all_limit_val
            save_config_from_session()
            st.success(f"已將所有一般使用者的每日上限調至 {all_limit_val} 題！")
            st.rerun()

        st.divider()
        st.markdown("**2. 單一指定帳號獨立調整**")
        selected_user = st.selectbox("選擇要修改的帳號", list(st.session_state.users_db.keys()))
        current_u_limit = int(st.session_state.users_db[selected_user].get("custom_limit", 15))
        col_single1, col_single2 = st.columns([3, 1])
        new_limit = col_single1.number_input(f"設定 {selected_user} 的每日解題額度", min_value=1, max_value=99999, value=current_u_limit, key="custom_limit_input")
        if col_single2.button("儲存個別設定", use_container_width=True):
            st.session_state.users_db[selected_user]["custom_limit"] = new_limit
            save_config_from_session()
            st.success(f"已更新 {selected_user} 的每日額度為 {new_limit} 題！")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. 科目管理
    with admin_tab2:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### 系統科目類別管理")
        st.write("在此處新增或移除解題科目選單，修改後學生前端會同步更新，AI 也會根據所選科目採用對應專業解題模式。")
        st.markdown("**目前系統已啟用的科目列表:**")
        subject_tags = " ".join([f"`{s}`" for s in st.session_state.subjects])
        st.markdown(f"> {subject_tags}")
        st.divider()

        col_sub_add, col_sub_del = st.columns(2)
        with col_sub_add:
            st.markdown("##### 新增科目")
            new_subject_name = st.text_input("輸入新科目名稱", placeholder="例如:物理、歷史、英文...", key="new_sub_input")
            if st.button("新增科目", use_container_width=True):
                new_sub_clean = new_subject_name.strip()
                if not new_sub_clean:
                    st.error("請輸入科目名稱！")
                elif new_sub_clean in st.session_state.subjects:
                    st.error(f"科目 `{new_sub_clean}` 已經存在！")
                else:
                    st.session_state.subjects.append(new_sub_clean)
                    save_config_from_session()
                    st.success(f"成功新增科目: {new_sub_clean}！")
                    st.rerun()

        with col_sub_del:
            st.markdown("##### 刪除科目")
            if len(st.session_state.subjects) > 1:
                del_subject_target = st.selectbox("選擇要刪除的科目", st.session_state.subjects, key="del_sub_select")
                if st.button("確定刪除科目", use_container_width=True):
                    st.session_state.subjects.remove(del_subject_target)
                    save_config_from_session()
                    st.warning(f"已成功刪除科目: {del_subject_target}")
                    st.rerun()
            else:
                st.info("系統至少需保留一種科目，無法再刪除。")
        st.markdown('</div>', unsafe_allow_html=True)

    # 3. 全站紀錄與管理員點評
    with admin_tab3:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### 學生題目巡檢與管理員點評")
        if not all_logs:
            st.info("目前尚無任何解題紀錄。")
        else:
            filter_col1, filter_col2 = st.columns([1, 2])
            user_list = ["全部使用者"] + list(st.session_state.users_db.keys())
            selected_filter_user = filter_col1.selectbox("過濾使用者帳號", user_list)
            search_query = filter_col2.text_input("關鍵字過濾", placeholder="輸入題目內容、答案或觀念關鍵字...")

            filtered_logs = all_logs
            if selected_filter_user != "全部使用者":
                filtered_logs = [l for l in filtered_logs if l.get("user") == selected_filter_user]
            if search_query:
                filtered_logs = [l for l in filtered_logs if search_query.lower() in str(l).lower()]

            st.caption(f"符合條件的紀錄共 {len(filtered_logs)} 筆")
            table_data = []
            for item in reversed(filtered_logs):
                fb_status = item.get("admin_feedback", {}).get("status", "pending")
                status_str = "未審核"
                if fb_status == "correct":
                    status_str = "正確"
                elif fb_status == "incorrect":
                    status_str = "需加強"

                table_data.append(
                    {
                        "時間": item.get("time", "未知"),
                        "使用者": item.get("user", "未知"),
                        "科目": item.get("subject", "未定"),
                        "AI答案": item.get("ans", "無"),
                        "管理員審核": status_str,
                        "題目/文字備註": item.get("note", "無"),
                    }
                )
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if all_logs and filtered_logs:
            st.markdown("#### 審核點評與答對率計算")
            for idx, log in enumerate(reversed(filtered_logs)):
                log_id = log.get("id", f"log_{idx}")
                feedback = log.get("admin_feedback", {"status": "pending", "comment": ""})

                with st.expander(f"[{log.get('time')}] {log.get('user')} - {log.get('subject')} (AI答案: {log.get('ans')})"):
                    st.markdown(f"**發問學生:** `{log.get('user')}` | **科目:** `{log.get('subject')}` | **提問時間:** `{log.get('time')}`")
                    st.markdown(f"**標註參考答案:** {log.get('ref_answer')}")
                    st.markdown(f"**題目文字描述:**\n{log.get('note')}")
                    st.markdown(f"**AI 答案:** `{log.get('ans')}`")
                    st.markdown(f"**觀念詳細推導解析:**\n{log.get('reasoning')}")

                    if log.get("images_b64"):
                        st.write("上傳題目原圖:")
                        img_cols = st.columns(min(len(log["images_b64"]), 3))
                        for i, img_b64 in enumerate(log["images_b64"]):
                            try:
                                img_bytes = base64.b64decode(img_b64)
                                img_cols[i % 3].image(img_bytes, caption=f"圖片{i+1}", use_column_width=True)
                            except Exception:
                                pass

                    st.divider()
                    st.markdown("##### 管理員點評區(將計入正確率統計)")
                    c_col1, c_col2 = st.columns([1, 2])
                    current_status = feedback.get("status", "pending")
                    status_idx = 0
                    if current_status == "correct":
                        status_idx = 1
                    elif current_status == "incorrect":
                        status_idx = 2

                    new_status_choice = c_col1.radio(
                        "AI 解題正確度評定",
                        options=["pending", "correct", "incorrect"],
                        format_func=lambda x: {"pending": "待審核", "correct": "回答正確", "incorrect": "回答錯誤/需補強"}[x],
                        index=status_idx,
                        key=f"status_radio_{log_id}",
                    )

                    new_comment = c_col2.text_area(
                        "正確回應與觀念再加強補充",
                        value=feedback.get("comment", ""),
                        placeholder="請輸入給學生的觀念補充、錯誤更正或學習建議...",
                        key=f"comment_text_{log_id}",
                        height=100,
                    )

                    if st.button("儲存點評評語", key=f"save_fb_{log_id}"):
                        log["admin_feedback"] = {
                            "status": new_status_choice,
                            "comment": new_comment,
                        }
                        save_config_from_session()
                        st.toast("點評已儲存並成功更新統計！", icon="💾")
                        st.rerun()

    # 4. AI 模型設定
    with admin_tab4:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### AI 模型引擎開關與模型切換")
        col_ai1, col_ai2 = st.columns(2)

        gemini_options = ["gemini-3.1-pro", "gemini-3.6-flash", "gemini-2.5-pro", "gemini-2.5-flash"]
        current_gemini = st.session_state.selected_gemini_model
        gemini_idx = gemini_options.index(current_gemini) if current_gemini in gemini_options else 0

        with col_ai1:
            st.markdown("##### Google Gemini")
            st.session_state.enable_gemini = st.toggle("啟用 Gemini AI 解題引擎", value=st.session_state.enable_gemini)
            st.session_state.selected_gemini_model = st.selectbox(
                "Gemini 模型選擇",
                options=gemini_options,
                index=gemini_idx,
                help="Gemini 3.1 Pro 擁有極佳的複雜邏輯推導與 Agent 解題能力",
            )

        openai_options = ["gpt-4o-mini", "gpt-4o", "o3-mini"]
        current_openai = st.session_state.selected_openai_model
        openai_idx = openai_options.index(current_openai) if current_openai in openai_options else 0

        with col_ai2:
            st.markdown("##### OpenAI GPT")
            st.session_state.enable_openai = st.toggle("啟用 OpenAI 解題引擎", value=st.session_state.enable_openai)
            st.session_state.selected_openai_model = st.selectbox(
                "OpenAI 模型選擇", options=openai_options, index=openai_idx
            )

        st.write("")
        if st.button("儲存 AI 模型設定", use_container_width=True):
            save_config_from_session()
            st.success("已成功儲存 AI 模型設定與服務狀態！")
        st.markdown('</div>', unsafe_allow_html=True)

    # 5. Bug 回報
    with admin_tab5:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("#### 使用者 Bug 與建議回報監控")
        reports = st.session_state.bug_reports
        if not reports:
            st.info("目前沒有任何待處理的問題回報！")
        else:
            for i, rep in enumerate(reports):
                st.markdown(f"**回報 #{i+1}**")
                st.json(rep)
        st.markdown('</div>', unsafe_allow_html=True)
