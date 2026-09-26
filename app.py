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

# =========================================================
# 0. 資料庫與設定檔機制
# =========================================================
CONFIG_FILE = "config.json"
FILE_LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "daily_limit": 15,
    "selected_gemini_model": "gemini-3.6-flash",
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
        "蕭翊倫": {
            "password": "2580",
            "class_name": "學生",
            "role": "user",
            "first_login": False,
            "used_today": 0,
            "total_used": 0,
            "custom_limit": 15,
        },
        "測試使用者": {
            "password": "2580",
            "class_name": "學生",
            "role": "user",
            "first_login": False,
            "used_today": 0,
            "total_used": 0,
            "custom_limit": 15,
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
        except Exception as e:
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

def pil_to_base64(img: Image.Image) -> str:
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# =========================================================
# 1. 頁面初始化與動態介面主題樣式
# =========================================================
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
if "selected_gemini_model" not in st.session_state:
    st.session_state.selected_gemini_model = config.get("selected_gemini_model", "gemini-3.6-flash")
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

# 多款介面主題配色定義
THEME_PALETTES = {
    "dark_blue": {
        "bg": "#11151A",
        "card_bg": "linear-gradient(145deg, #181E24, #13171C)",
        "card_border": "#28323D",
        "primary_btn": "linear-gradient(180deg, #DCE6F2 0%, #B8C7D9 100%)",
        "highlight": "#38BDF8",
    },
    "emerald": {
        "bg": "#0B1914",
        "card_bg": "linear-gradient(145deg, #132720, #0E1F19)",
        "card_border": "#1F3E33",
        "primary_btn": "linear-gradient(180deg, #D1FAE5 0%, #A7F3D0 100%)",
        "highlight": "#34D399",
    },
    "purple": {
        "bg": "#14111A",
        "card_bg": "linear-gradient(145deg, #201A28, #181320)",
        "card_border": "#352B42",
        "primary_btn": "linear-gradient(180deg, #EDE9FE 0%, #DDD6FE 100%)",
        "highlight": "#C084FC",
    },
}

current_theme = THEME_PALETTES.get(st.session_state.theme_color, THEME_PALETTES["dark_blue"])

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {current_theme["bg"]} !important;
        color: #E2E8F0 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    
    header[data-testid="stHeader"] {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    
    .custom-card {{
        background: {current_theme["card_bg"]};
        border: 1px solid {current_theme["card_border"]};
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }}
    
    .top-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: {current_theme["card_bg"]};
        border: 1px solid {current_theme["card_border"]};
        border-radius: 16px;
        padding: 12px 16px;
        margin-bottom: 14px;
    }}
    .header-title {{
        font-size: 16px;
        font-weight: 700;
        color: #FFFFFF;
    }}
    .header-sub {{
        font-size: 11px;
        color: #8A99AD;
    }}
    
    .user-avatar {{
        width: 42px;
        height: 42px;
        background-color: #2D3748;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        font-weight: bold;
        color: #E2E8F0;
    }}
    .quota-badge {{
        background-color: #1A232E;
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 6px 12px;
        text-align: right;
    }}
    
    .step-number {{
        display: inline-block;
        width: 20px;
        height: 20px;
        background-color: #28323D;
        color: #FFFFFF;
        border-radius: 5px;
        text-align: center;
        line-height: 20px;
        font-size: 11px;
        font-weight: bold;
        margin-right: 6px;
    }}

    div.stButton > button {{
        background: {current_theme["primary_btn"]} !important;
        color: #0F172A !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
        padding: 8px 14px !important;
        transition: all 0.2s ease-in-out !important;
    }}
    div.stButton > button:hover {{
        background: #FFFFFF !important;
        box-shadow: 0 0 10px rgba(255, 255, 255, 0.25) !important;
    }}
    div.stButton > button p {{ color: #0F172A !important; }}

    .secondary-btn div.stButton > button {{
        background: #1C242C !important;
        border: 1px solid {current_theme["card_border"]} !important;
    }}
    .secondary-btn div.stButton > button p {{ color: #94A3B8 !important; }}

    input, textarea, div[data-baseweb="input"] > div {{
        background-color: #13171C !important;
        color: #F1F5F9 !important;
        border: 1px solid {current_theme["card_border"]} !important;
        border-radius: 10px !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# 2. 登入介面邏輯
# =========================================================
if not st.session_state.logged_in:
    st.markdown(
        """
        <div class="top-header" style="justify-content: center; text-align: center; margin-top: 20px;">
            <div>
                <div style="font-size: 32px; margin-bottom: 8px;">🧪</div>
                <div class="header-title" style="font-size: 20px;">A.lab | 解題實驗室</div>
                <div class="header-sub">Science Lab Solution Platform</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("### 🔑 使用者登入")
        input_username = st.text_input("帳號", placeholder="請輸入帳號")
        input_password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
        
        if st.button("登入系統", use_container_width=True):
            users = st.session_state.users_db
            if input_username in users and users[input_username]["password"] == input_password:
                st.session_state.logged_in = True
                st.session_state.user_name = input_username
                st.session_state.user_role = users[input_username].get("role", "user")
                st.session_state.login_logs.append({"user": input_username, "time": get_taipei_now_str()})
                save_config_from_session()
                st.toast(f"🎉 歡迎回來，{input_username}！", icon="✅")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新確認！")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# =========================================================
# 3. AI 核心邏輯
# =========================================================
def build_system_prompt():
    return """你是一位專業嚴謹的萬能AI導師。
請針對使用者上傳的題目進行精準解答與深度邏輯剖析。
請嚴格回傳JSON格式(不要包裹在 markdown codeblock 中):
{
  "ans": "正確答案選項或簡短最終結果",
  "reasoning": "步驟清晰、邏輯嚴謹的詳細觀念推導過程"
}
遇到公式請使用標準 LaTeX 語法(如 $E=mc^2$)。請以繁體中文回答。"""

def extract_text_from_images(image_list: list, extra_info: str = "") -> str:
    if not GEMINI_API_KEY or not image_list or not st.session_state.enable_gemini:
        return ""
    ocr_prompt = f"請詳細轉錄圖片中的所有題目文字、選項與公式。補充說明: {extra_info}"
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=st.session_state.selected_gemini_model, contents=image_list + [ocr_prompt]
        )
        return response.text.strip() if response and response.text else ""
    except Exception as e:
        return f"[圖片辨識說明]: {str(e)}"

def call_ai_solver(question_text):
    if not st.session_state.enable_gemini and not st.session_state.enable_openai:
        return "服務已關閉", "管理員目前已關閉所有 AI 解題服務系統。"

    if not GEMINI_API_KEY and not OPENAI_API_KEY:
        return "未設定 API Key", "請在 secrets.toml 中設定 API Key。"
    
    prompt = f"{build_system_prompt()}\n\n題目:{question_text}"
    
    if GEMINI_API_KEY and st.session_state.enable_gemini:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=st.session_state.selected_gemini_model, contents=prompt
            )
            raw = resp.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            return data.get("ans", "未知"), data.get("reasoning", "無解析內容")
        except Exception:
            pass

    if OPENAI_API_KEY and st.session_state.enable_openai:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=st.session_state.selected_openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": f"題目:{question_text}"},
                ],
            )
            data = json.loads(resp.choices[0].message.content)
            return data.get("ans", "未知"), data.get("reasoning", "無解析內容")
        except Exception as e:
            return "解析失敗", str(e)
            
    return "解析失敗", "無法存取 AI 模型或相關服務未啟用"

# =========================================================
# 4. 主介面 Header 與用戶資訊卡片
# =========================================================
col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.markdown(
        """
        <div class="top-header" style="margin-bottom: 0px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 22px;">🧪</span>
                <div>
                    <div class="header-title">A.lab | 解題實驗室</div>
                    <div class="header-sub">Science Lab</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_h2:
    theme_choice = st.selectbox(
        "主題色彩",
        options=["dark_blue", "emerald", "purple"],
        format_func=lambda x: {"dark_blue": "🌌 藍", "emerald": "🌲 綠", "purple": "🔮 紫"}[x],
        index=["dark_blue", "emerald", "purple"].index(st.session_state.theme_color),
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

col_head1, col_head2 = st.columns([4, 1])
with col_head1:
    st.markdown(
        f"""
        <div class="custom-card" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="user-avatar">{user_name[0]}</div>
                <div>
                    <div style="font-size: 17px; font-weight: bold; color: #FFFFFF;">{user_name}</div>
                    <div style="font-size: 11px; color: #8A99AD;">{class_name}</div>
                </div>
            </div>
            <div class="quota-badge">
                <div style="font-size: 10px; color: #8A99AD;">題數狀態</div>
                <div style="font-size: 11px; color: #CBD5E1;">今日剩餘 <span style="font-size: 18px; font-weight: bold; color: #FFFFFF;">{remains}</span> 題</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_head2:
    st.markdown('<div class="secondary-btn" style="margin-top: 8px;">', unsafe_allow_html=True)
    if st.button("登出", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# 導覽分頁按鈕（僅對管理者顯示後台按鈕）
is_admin = st.session_state.get("user_role") == "admin"
cols = st.columns(4 if is_admin else 3)

if cols[0].button("🏠 首頁", use_container_width=True):
    st.session_state.active_tab = "home"
    st.rerun()
if cols[1].button("✨ 最新解析", use_container_width=True):
    st.session_state.active_tab = "analysis"
    st.rerun()
if cols[2].button("📋 解題紀錄", use_container_width=True):
    st.session_state.active_tab = "history"
    st.rerun()
if is_admin and cols[3].button("⚙️ 後台", use_container_width=True):
    st.session_state.active_tab = "admin"
    st.rerun()

st.divider()

# =========================================================
# 5. 頁面分流邏輯
# =========================================================

# --- TAB 1: 首頁 (上傳與裁切) ---
if st.session_state.active_tab == "home":
    st.markdown(
        """
        <div style="font-size: 15px; font-weight: bold; color: #FFFFFF; margin-bottom: 8px;">
            <span class="step-number">1</span> 上傳與裁切題目圖片
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    uploaded_files = st.file_uploader(
        "選擇題目圖片（可上傳 1~5 張）",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    cropped_images = []
    if uploaded_files:
        st.markdown("#### ✂️ 圖片裁切預覽")
        for i, f in enumerate(uploaded_files):
            img = Image.open(f)
            st.write(f"圖片 {i+1}:")
            cropped_img = st_cropper(img, realtime_update=True, box_color="#38BDF8", aspect_ratio=None, key=f"crop_{i}")
            cropped_images.append(cropped_img)

    st.markdown(
        """
        <div style="font-size: 15px; font-weight: bold; color: #FFFFFF; margin-top: 16px; margin-bottom: 8px;">
            <span class="step-number">2</span> 設定題目資訊
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    selected_subject = st.selectbox("科目", st.session_state.subjects, index=0)
    ref_answer = st.text_input("標準參考答案 選填", placeholder="例如 B、ACD、2.5 mol...")
    extra_note = st.text_input("補充敘述 選填", placeholder="有需要再補充，例如：想特別問 C 選項")

    col_b1, col_b2 = st.columns([3, 1])
    submit_btn = col_b1.button("開始解題", use_container_width=True)
    with col_b2:
        st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
        clear_btn = st.button("清除題目", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if submit_btn:
        if isinstance(remains, int) and remains <= 0:
            st.error("今日解題額度已用完，請明日再試！")
        elif not uploaded_files and not extra_note:
            st.warning("請上傳題目圖片或填寫補充敘述！")
        else:
            with st.spinner("🌀 A.lab AI 正在分析與解題中..."):
                images_to_process = cropped_images if cropped_images else ([Image.open(f) for f in uploaded_files] if uploaded_files else [])
                ocr_text = extract_text_from_images(images_to_process, extra_note)
                combined_question = f"補充敘述: {extra_note}\n\n圖片題目辨識內容:\n{ocr_text}" if ocr_text else extra_note

                ans, reasoning = call_ai_solver(combined_question)
                images_b64 = [pil_to_base64(img) for img in images_to_process]

                new_record = {
                    "user": user_name,
                    "time": get_taipei_now_str(),
                    "subject": selected_subject,
                    "ref_answer": ref_answer or "無",
                    "note": extra_note or "無",
                    "ans": ans,
                    "reasoning": reasoning,
                    "images_b64": images_b64,
                }
                
                st.session_state.history_logs.append(new_record)
                st.session_state.latest_analysis = new_record
                user_info["used_today"] += 1
                save_config_from_session()
                st.toast("✅ 解題完成！", icon="🎉")
                st.session_state.active_tab = "analysis"
                st.rerun()

# --- TAB 2: 解析結果 ---
elif st.session_state.active_tab == "analysis":
    st.markdown("### ✨ 最新解題觀念解析")
    if "latest_analysis" in st.session_state and st.session_state.latest_analysis:
        res = st.session_state.latest_analysis
        st.markdown(
            f"""
            <div class="custom-card">
                <div style="color: {current_theme['highlight']}; font-weight: bold; margin-bottom: 6px;">[{res['subject']}] 觀念拆解與解答</div>
                <div style="font-size: 13px; color: #94A3B8; margin-bottom: 6px;">標準參考答案: <b style="color:#FFFFFF;">{res['ref_answer']}</b> | AI 答案: <b style="color:{current_theme['highlight']};">{res['ans']}</b></div>
                <div style="font-size: 14px; line-height: 1.6; color: #F8FAFC; white-space: pre-line; margin-top: 10px;">
                <b>觀念推導過程:</b>\n{res['reasoning']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("目前尚無最新的解題結果，請至「首頁」上傳題目。")

# --- TAB 3: 我的解題紀錄 ---
elif st.session_state.active_tab == "history":
    st.markdown("### 📋 我的解題紀錄")
    search_kw = st.text_input("搜尋關鍵字", placeholder="搜尋答案、題目補充、解析內容...", label_visibility="collapsed")
    
    logs = [l for l in st.session_state.history_logs if l.get("user") == user_name or is_admin]
    if search_kw:
        logs = [l for l in logs if search_kw.lower() in str(l).lower()]

    st.caption(f"共 {len(logs)} 筆紀錄")

    if not logs:
        st.info("尚無解題紀錄！")
    else:
        for idx, item in enumerate(reversed(logs)):
            img_count = len(item.get("images_b64", []))
            st.markdown(
                f"""
                <div class="custom-card" style="display: flex; gap: 12px; align-items: flex-start;">
                    <div style="width: 65px; height: 65px; background: #222B35; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #8A99AD;">
                        { f'📷 {img_count}張' if img_count > 0 else '📝 文字' }
                    </div>
                    <div style="flex: 1;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: bold; color: #FFFFFF; font-size: 14px;">{item['subject']} ({item['user']})</span>
                            <span style="font-size: 11px; color: #64748B;">{item['time']}</span>
                        </div>
                        <div style="font-size: 13px; color: #CBD5E1; margin-top: 3px;">答案: {item.get('ans', '無')}</div>
                        <div style="font-size: 11px; color: #8A99AD; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                            {item.get('reasoning', '')}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# --- TAB 4: 後台管理員系統 (非 admin 禁止進入) ---
elif st.session_state.active_tab == "admin":
    if not is_admin:
        st.error("⛔ 存取被拒絕：您沒有進入後台管理系統的權限！")
        if st.button("返回首頁"):
            st.session_state.active_tab = "home"
            st.rerun()
        st.stop()

    st.markdown("### ⚙️ A.lab 後台管理系統")
    admin_tab1, admin_tab2, admin_tab3 = st.tabs(["👥 使用者列表與權限設定", "🤖 AI 模型設定", "🐞 Bug 回報處理"])
    
    with admin_tab1:
        st.write("#### 使用者列表與權限設定")
        user_df = pd.DataFrame.from_dict(st.session_state.users_db, orient="index")
        
        column_translation = {
            "password": "密碼",
            "class_name": "班別/類別",
            "role": "權限角色",
            "first_login": "首次登入",
            "used_today": "今日已用",
            "total_used": "累積使用",
            "custom_limit": "每日額度",
        }
        translated_df = user_df.rename(columns=column_translation)
        translated_df.index.name = "帳號"
        st.dataframe(translated_df, use_container_width=True)
        
        st.divider()
        st.write("#### ⚡ 快速一鍵修改使用者題數額度")
        
        # 1. 全體一鍵修改
        st.markdown("**1. 全體使用者一鍵重設**")
        col_all1, col_all2 = st.columns([3, 1])
        all_limit_val = col_all1.number_input("設定所有一般使用者題數", min_value=1, max_value=99999, value=15, key="all_limit_input")
        if col_all2.button("一鍵套用全體", use_container_width=True):
            for u_name, u_data in st.session_state.users_db.items():
                if u_data.get("role") != "admin":
                    u_data["custom_limit"] = all_limit_val
            save_config_from_session()
            st.success(f"已成功將所有非管理員使用者的每日額度統一修改為 {all_limit_val} 題！")
            st.rerun()

        # 2. 單一使用者點擊修改
        st.markdown("**2. 單一使用者快速點擊修改**")
        selected_user = st.selectbox("選擇要修改的使用者", list(st.session_state.users_db.keys()))
        current_u_limit = int(st.session_state.users_db[selected_user].get("custom_limit", 15))
        st.caption(f"目前額度：{current_u_limit} 題")
        
        btn_cols = st.columns(4)
        if btn_cols[0].button("一鍵設為 15 題", use_container_width=True):
            st.session_state.users_db[selected_user]["custom_limit"] = 15
            save_config_from_session()
            st.toast(f"已修改 {selected_user} 額度為 15 題！", icon="✅")
            st.rerun()
        if btn_cols[1].button("一鍵設為 30 題", use_container_width=True):
            st.session_state.users_db[selected_user]["custom_limit"] = 30
            save_config_from_session()
            st.toast(f"已修改 {selected_user} 額度為 30 題！", icon="✅")
            st.rerun()
        if btn_cols[2].button("一鍵設為 50 題", use_container_width=True):
            st.session_state.users_db[selected_user]["custom_limit"] = 50
            save_config_from_session()
            st.toast(f"已修改 {selected_user} 額度為 50 題！", icon="✅")
            st.rerun()
        if btn_cols[3].button("一鍵設為 無限(99999)", use_container_width=True):
            st.session_state.users_db[selected_user]["custom_limit"] = 99999
            save_config_from_session()
            st.toast(f"已修改 {selected_user} 額度為無限！", icon="✅")
            st.rerun()

        st.write("或手動輸入題數：")
        new_limit = st.number_input("自訂題數", min_value=1, max_value=99999, value=current_u_limit, key="custom_limit_input")
        if st.button("儲存自訂題數"):
            st.session_state.users_db[selected_user]["custom_limit"] = new_limit
            save_config_from_session()
            st.success(f"已成功修改 {selected_user} 的每日額度為 {new_limit} 題！")
            st.rerun()

    with admin_tab2:
        st.write("#### AI 模型管理與開關設定")
        
        col_ai1, col_ai2 = st.columns(2)
        with col_ai1:
            st.session_state.enable_gemini = st.toggle("啟用 Gemini AI 引擎", value=st.session_state.enable_gemini)
            st.session_state.selected_gemini_model = st.text_input("Gemini 模型名稱", value=st.session_state.selected_gemini_model)
        
        with col_ai2:
            st.session_state.enable_openai = st.toggle("啟用 OpenAI AI 引擎", value=st.session_state.enable_openai)
            st.session_state.selected_openai_model = st.text_input("OpenAI 模型名稱", value=st.session_state.selected_openai_model)

        if st.button("儲存 AI 設定"):
            save_config_from_session()
            st.success("AI 模型設定與服務開關儲存成功！")

    with admin_tab3:
        st.write("#### 使用者回報紀錄")
        st.write(st.session_state.bug_reports)
