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
        "primary": "#E53E3E",
        "card": "#121212",
        "sub_text": "#CCCCCC",
        "sidebar_bg": "#121212",
    },
    "清霧白": {
        "bg": "#F8F9FA",
        "text": "#1A1A1A",
        "primary": "#E53E3E",
        "card": "#FFFFFF",
        "sub_text": "#718096",
        "sidebar_bg": "#EDF2F7",
    },
    "燕麥米": {
        "bg": "#F4F1EA",
        "text": "#3D3A36",
        "primary": "#E53E3E",
        "card": "#FAF8F5",
        "sub_text": "#8A837A",
        "sidebar_bg": "#EBE5DF",
    },
    "森林綠": {
        "bg": "#E8F0EC",
        "text": "#1C3326",
        "primary": "#E53E3E",
        "card": "#F2F7F4",
        "sub_text": "#5C7869",
        "sidebar_bg": "#D5E3DB",
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
            menu_options = [
                "⚙️ 系統管理",
                "📝 開始解題",
                "📚 所有人解題紀錄",
            ]
        else:
            menu_options = ["📝 開始解題", "📚 我的解題紀錄"]

        menu_option = st.radio(
            "功能導航", menu_options, index=0, label_visibility="collapsed"
        )

        st.divider()
        st.subheader("🎨 視覺主題設定")
        selected_theme = st.selectbox(
            "選擇主題配色", list(THEMES.keys()), index=0
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

t = THEMES[selected_theme]

# 全局 CSS 注入與樣式整合
st.markdown(
    f"""
<style>
    .stApp {{
        background-color: {t["bg"]} !important;
        color: {t["text"]} !important;
    }}
    section[data-testid="stSidebar"] {{
        background-color: {t["sidebar_bg"]} !important;
    }}
    p, span, h1, h2, h3, h4, h5, h6, label, div {{
        color: {t["text"]} !important;
    }}
    div.stButton > button,
    button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-primary"] {{
        background-color: #E53E3E !important;
        color: #FFFFFF !important;
        border-color: #E53E3E !important;
        font-weight: bold !important;
        border-radius: 6px !important;
    }}
    div.stButton > button *, button * {{
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }}
    div.stButton > button:hover,
    div.stButton > button:focus,
    div.stButton > button:active {{
        background-color: #C53030 !important;
        border-color: #C53030 !important;
        color: #FFFFFF !important;
        box-shadow: none !important;
    }}
    input, textarea, div[data-baseweb="input"] > div {{
        background-color: #1E3A8A !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border-color: #1E3A8A !important;
    }}
    div[data-baseweb="select"] > div,
    div[data-baseweb="popover"] *,
    ul[role="listbox"] li {{
        background-color: {t["card"]} !important;
        color: {t["text"]} !important;
        border-color: {t["sub_text"]} !important;
    }}
    .step-number {{
        background-color: #E53E3E;
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
            and st.session_state.users_db[input_user]["password"]
            == input_password
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
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "").strip()
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", "").strip()

SYSTEM_PROMPT = """
你是一位嚴謹的考題解析專家。請分析使用者提供的題目，並嚴格只回傳以下 JSON 格式（不要包含任何 Markdown 標記，直接輸出 JSON 內容）：
{
  "ans": "正確答案選項（例如 A、B、C 或 D，若是非選擇題請給出簡短最終答案）",
  "reasoning": "詳細的解題步驟與觀念說明"
}
"""


def extract_text_from_images(image_list: list, extra_info: str = "") -> str:
    if not GEMINI_API_KEY:
        return "[圖片辨識失敗]: 請先在 Streamlit Secrets 設定 GEMINI_API_KEY"
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        ocr_prompt = (
            f"請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明：{extra_info}"
        )
        contents = image_list + [ocr_prompt]
        response = client.models.generate_content(
            model="gemini-1.5-flash", contents=contents
        )
        return response.text.strip()
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
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"{SYSTEM_PROMPT}\n\n題目：{question_text}",
        )
        return response.text
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
            {"ans": "失敗", "reasoning": f"ChatGPT API 呼叫失敗: {str(e)}"},
            ensure_ascii=False,
        )


def call_claude(question_text):
    if not CLAUDE_API_KEY:
        return json.dumps(
            {
                "ans": "未設定 Key",
                "reasoning": "未在 Secrets 中設定 CLAUDE_API_KEY。",
            },
            ensure_ascii=False,
        )
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
            {"ans": "失敗", "reasoning": f"Claude API 呼叫失敗: {str(e)}"},
            ensure_ascii=False,
        )


def parse_ai_json(raw_text):
    try:
        clean_text = (
            raw_text.strip()
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )
        data = json.loads(clean_text)
        ans = data.get("ans", "未知").strip().upper()
        reasoning = data.get("reasoning", "無解析內容")
        return ans, reasoning
    except:
        return "格式解析失敗", raw_text


# ==========================================
# 3. 頁面渲染分流
# ==========================================

# 👑 獨立頁面 1：管理員後台控制頁面
if menu_option == "⚙️ 系統管理":
    st.title("⚙️ 管理員控制後台")
    st.caption("調整系統設定與檢視使用者狀態")

    st.subheader("🎯 每日提問額度設定")
    new_limit = st.number_input(
        "全站使用者每日預設可提問數",
        min_value=1,
        max_value=100,
        value=st.session_state.daily_limit,
    )
    if st.button("更新預設每日題數上限"):
        st.session_state.daily_limit = new_limit
        st.success(f"已將每日提問上限更新為：{new_limit} 題")
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
            st.success(
                f"已成功新增使用者：{new_name}（預設密碼：{new_pass}）"
            )
            st.rerun()
        else:
            st.warning("請填寫姓名與預設密碼！")

    st.divider()
    st.subheader("📋 目前使用者名單與狀態管理")

    for u_name, info in list(st.session_state.users_db.items()):
        col_a, col_b, col_c, col_d, col_e = st.columns([2, 2, 2, 2, 1])
        col_a.write(f"**姓名**：{u_name}")

        used = info.get("used_today", 0)
        col_b.write(
            f"**今日使用**：`{used}/{st.session_state.daily_limit}` 題"
        )

        if col_c.button("🔄 重置題數", key=f"reset_limit_{u_name}"):
            st.session_state.users_db[u_name]["used_today"] = 0
            st.toast(f"已重置 {u_name} 今日已用題數為 0！")
            st.rerun()

        if col_d.button("🔑 還原密碼", key=f"reset_pwd_{u_name}"):
            st.session_state.users_db[u_name]["password"] = (
                DEFAULT_USER_PASSWORD
            )
            st.session_state.users_db[u_name]["first_login"] = True
            st.toast(
                f"已將 {u_name} 的密碼重置為 {DEFAULT_USER_PASSWORD}！"
            )
            st.rerun()

        if col_e.button("🗑️", key=f"del_{u_name}"):
            del st.session_state.users_db[u_name]
            st.toast(f"已刪除 {u_name}")
            st.rerun()

# 📚 頁面 2：解題紀錄頁面 (附帶科目與使用者雙重篩選功能)
elif menu_option in ["📚 我的解題紀錄", "📚 所有人解題紀錄"]:
    title_text = (
        "📚 全站解題紀錄"
        if st.session_state.user_role == "admin"
        else "📚 我的解題紀錄"
    )
    st.title(title_text)
    st.caption("歷次檢索與解析紀錄匯總")
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
        st.subheader("🔍 條件篩選")
        filter_col1, filter_col2 = st.columns(2)

        available_users = ["全部使用者"] + list(
            set([log["user"] for log in base_logs])
        )
        available_subjects = ["全部科目"] + list(
            set([log["subject"] for log in base_logs])
        )

        with filter_col1:
            selected_user_filter = (
                st.selectbox("選擇使用者", available_users)
                if st.session_state.user_role == "admin"
                else st.session_state.user_name
            )

        with filter_col2:
            selected_subject_filter = st.selectbox(
                "選擇科目", available_subjects
            )

        filtered_logs = base_logs
        if selected_user_filter != "全部使用者":
            filtered_logs = [
                log
                for log in filtered_logs
                if log["user"] == selected_user_filter
            ]
        if selected_subject_filter != "全部科目":
            filtered_logs = [
                log
                for log in filtered_logs
                if log["subject"] == selected_subject_filter
            ]

        st.caption(f"共找到 **{len(filtered_logs)}** 筆符合條件的紀錄")
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

# 📝 頁面 3：開始解題頁面 (管理員與一般使用者皆會儲存紀錄)
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
            tabs = st.tabs(
                [f"圖片 {i+1}" for i in range(len(uploaded_files))]
            )
            for idx, file in enumerate(uploaded_files):
                with tabs[idx]:
                    raw_img = Image.open(file)
                    cropped_img = st_cropper(
                        raw_img,
                        realtime_update=True,
                        box_color="#E53E3E",
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

    subject = st.selectbox("科目", ["理化", "生物", "地科", "數學", "其他"])
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
    <div class="step-header"><span class="step-number">3</span>觀念解析與 AI 三重驗證</div>
    <div class="sub-text">答案 ➔ 觀念解析 ➔ 多模態選項比對</div>
    """,
        unsafe_allow_html=True,
    )

    if start_btn:
        can_submit = True

        if st.session_state.user_role == "user":
            u_name = st.session_state.user_name
            used = st.session_state.users_db[u_name].get("used_today", 0)
            limit = st.session_state.daily_limit
            if used >= limit:
                can_submit = False
                st.error(
                    f"⚠️ 您今日的提問額度（{limit}"
                    " 題）已用完！請明日再試或聯繫管理員重置。"
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

                with st.status(
                    "🚀 實驗室正在解析題目與進行 AI 比對...", expanded=True
                ) as status:
                    st.write("🔍 **步驟 1**：Gemini 多圖視覺 OCR 辨識中...")
                    q_text = extract_text_from_images(final_images, extra_info)

                    st.write(
                        "🤖 **步驟 2**：Gemini x ChatGPT x Claude"
                        " 三方平行交叉驗證中..."
                    )
                    g_raw = call_gemini(q_text)
                    c_raw = call_chatgpt(q_text)
                    cl_raw = call_claude(q_text)

                    g_ans, g_reason = parse_ai_json(g_raw)
                    c_ans, c_reason = parse_ai_json(c_raw)
                    cl_ans, cl_reason = parse_ai_json(cl_raw)

                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state.history_logs.append({
                        "user": st.session_state.user_name,
                        "time": now_str,
                        "subject": subject,
                        "ans": g_ans,
                        "reasoning": g_reason,
                        "extra_info": extra_info,
                    })

                    status.update(label="🎉 解析完成！", state="complete")

                # 檢查可用的 AI 答案比對
                valid_answers = [
                    ans
                    for ans in [g_ans, c_ans, cl_ans]
                    if ans not in ["未設定 KEY", "失敗", "格式解析失敗", "未知"]
                ]

                if valid_answers and len(set(valid_answers)) == 1:
                    st.success(
                        f"✅ **AI 驗證答案一致：【 {valid_answers[0]} 】**"
                    )
                elif valid_answers:
                    st.warning(
                        f"⚠️ **AI 答案存在分歧！** (Gemini: {g_ans} | ChatGPT:"
                        f" {c_ans} | Claude: {cl_ans})"
                    )
                else:
                    st.error(
                        "❌ 無法取得有效答案，請檢查 Secrets 中的 API Key"
                        " 是否正確。"
                    )

                res_col1, res_col2, res_col3 = st.columns(3)
                with res_col1:
                    st.subheader("🤖 Gemini")
                    st.write(f"**答案**：`{g_ans}`")
                    st.write(g_reason)
                with res_col2:
                    st.subheader("🟢 ChatGPT")
                    st.write(f"**答案**：`{c_ans}`")
                    st.write(c_reason)
                with res_col3:
                    st.subheader("🟣 Claude")
                    st.write(f"**答案**：`{cl_ans}`")
                    st.write(cl_reason)
    else:
        st.info(
            "尚未產生題目詳解，完成上方步驟並點擊「開始解題」後，解析會顯示在這裡。"
        )
