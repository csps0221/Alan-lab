import streamlit as st
import json
import os
from PIL import Image
from streamlit_cropper import st_cropper
from google import genai
from openai import OpenAI
from anthropic import Anthropic

# ==========================================
# 0. 管理員與學生帳號資料庫 (Session State 儲存)
# ==========================================
st.set_page_config(page_title="H.H. Science Lab 解題實驗室", layout="centered")

# 設定固定管理員帳號密碼 (可自行修改)
ADMIN_USER = "admin"
ADMIN_PASSWORD = "adminpassword123"

# 初始化學生帳號資料庫
if "students_db" not in st.session_state:
    st.session_state.students_db = st.secrets.get("STUDENTS", {
        "王小明": "123456",
        "張小華": "654321",
        "測試學生": "1111"
    })

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""  # "admin" 或 "student"
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

# --- 登入頁面 ---
if not st.session_state.logged_in:
    st.title("🔑 H.H. Science Lab 登入系統")
    st.caption("請輸入您的姓名/帳號與密碼")
    
    input_user = st.text_input("姓名 / 管理員帳號")
    input_password = st.text_input("密碼", type="password")
    
    if st.button("登入", type="primary", use_container_width=True):
        # 1. 驗證是否為管理員
        if input_user == ADMIN_USER and input_password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
            st.session_state.user_role = "admin"
            st.session_state.user_name = "系統管理員"
            st.success("歡迎管理者登入！")
            st.rerun()
        # 2. 驗證是否為學生
        elif input_user in st.session_state.students_db and st.session_state.students_db[input_user] == input_password:
            st.session_state.logged_in = True
            st.session_state.user_role = "student"
            st.session_state.user_name = input_user
            st.success(f"歡迎 {input_user} 同學登入！")
            st.rerun()
        else:
            st.error("❌ 帳號或密碼錯誤！")
    st.stop()

# --- 頂部狀態列 ---
top_col1, top_col2 = st.columns([4, 1])
with top_col1:
    role_label = "👑 管理員" if st.session_state.user_role == "admin" else "🎓 學生"
    st.write(f"當前使用者：**{st.session_state.user_name}** ({role_label})")
with top_col2:
    if st.button("登出"):
        st.session_state.logged_in = False
        st.session_state.user_role = ""
        st.session_state.user_name = ""
        st.rerun()

st.divider()

# ==========================================
# 👑 管理員專屬後台：新增/刪除學生帳號
# ==========================================
if st.session_state.user_role == "admin":
    with st.expander("⚙️ 管理員選單：學生帳號管理", expanded=True):
        st.subheader("➕ 新增學生帳號")
        new_name = st.text_input("學生姓名", key="new_s_name")
        new_pass = st.text_input("設定密碼", key="new_s_pass")
        if st.button("新增/更新學生帳號"):
            if new_name and new_pass:
                st.session_state.students_db[new_name] = new_pass
                st.success(f"已成功新增/更新學生：{new_name}")
                st.rerun()
            else:
                st.warning("請填寫完整的姓名與密碼！")
        
        st.divider()
        st.subheader("📋 目前學生名單")
        for s_name, s_pass in list(st.session_state.students_db.items()):
            col_a, col_b, col_c = st.columns([2, 2, 1])
            col_a.write(f"**姓名**：{s_name}")
            col_b.write(f"**密碼**：`{s_pass}`")
            if col_c.button("刪除", key=f"del_{s_name}"):
                del st.session_state.students_db[s_name]
                st.toast(f"已刪除 {s_name}")
                st.rerun()

    st.divider()

# ==========================================
# 1. API Key 設定
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

# ==========================================
# 2. 自訂質感 CSS
# ==========================================
st.markdown("""
<style>
    .main { background-color: #F8F9FA; }
    .step-number {
        background-color: #1A1A1A;
        color: #FFFFFF;
        border-radius: 50%;
        width: 28px;
        height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 14px;
        margin-right: 10px;
    }
    .step-header {
        display: flex;
        align-items: center;
        font-size: 18px;
        font-weight: 700;
        color: #1A1A1A;
        margin-bottom: 8px;
    }
    .sub-text {
        color: #8E8E93;
        font-size: 13px;
        margin-left: 38px;
        margin-top: -6px;
        margin-bottom: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 核心邏輯 (OCR 與 API 呼叫)
# ==========================================
def extract_text_from_images(image_list: list, extra_info: str = "") -> str:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        ocr_prompt = f"請將這幾張圖片中的考題文字完整、精準轉錄（包含題目與選項）。補充說明：{extra_info}"
        contents = image_list + [ocr_prompt]
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents
        )
        return response.text.strip()
    except Exception as e:
        return f"[圖片辨識失敗]: {str(e)}"

def call_gemini(question_text):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{SYSTEM_PROMPT}\n\n題目：{question_text}"
        )
        return response.text
    except Exception as e:
        return json.dumps({"ans": "錯誤", "reasoning": f"Gemini API 呼叫失敗: {str(e)}"}, ensure_ascii=False)

def call_chatgpt(question_text):
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"題目：{question_text}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return json.dumps({"ans": "錯誤", "reasoning": f"ChatGPT API 呼叫失敗: {str(e)}"}, ensure_ascii=False)

def call_claude(question_text):
    try:
        client = Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"題目：{question_text}"}
            ]
        )
        return response.content[0].text
    except Exception as e:
        return json.dumps({"ans": "錯誤", "reasoning": f"Claude API 呼叫失敗: {str(e)}"}, ensure_ascii=False)

def parse_ai_json(raw_text):
    try:
        clean_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        ans = data.get("ans", "未知").strip().upper()
        reasoning = data.get("reasoning", "無解析內容")
        return ans, reasoning
    except:
        return "格式解析失敗", raw_text

# ==========================================
# 4. 主介面渲染 (解題實驗室)
# ==========================================
st.caption("H.H. SCIENCE LAB")
st.title("自然科解題實驗室")
st.caption("拆解步驟，訂正錯誤，清晰脈絡，梳理思路")
st.divider()

# --- 步驟 1：上傳題目圖片 ---
st.markdown("""
<div class="step-header"><span class="step-number">1</span>上傳題目圖片</div>
<div class="sub-text">可上傳 1~6 張，題目與解答皆可上傳</div>
""", unsafe_allow_html=True)

uploaded_files = st.file_uploader("", type=["png", "jpg", "jpeg"], accept_multiple_files=True, label_visibility="collapsed")

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
                cropped_img = st_cropper(raw_img, realtime_update=True, box_color='#000000', key=f"crop_{idx}")
                st.session_state.cropped_images[idx] = cropped_img

st.divider()

# --- 步驟 2：設定題目資訊 ---
st.markdown("""
<div class="step-header"><span class="step-number">2</span>設定題目資訊</div>
<div class="sub-text">科目、參考答案與補充敘述</div>
""", unsafe_allow_html=True)

subject = st.selectbox("科目", ["理化", "生物", "地科", "數學", "其他"])
std_answer = st.text_input("標準參考答案（選填）", placeholder="例如 B、ACD、2.5 mol...")
extra_info = st.text_input("補充敘述（選填）", placeholder="有需要再補充，例如：想特別問 C 選項")

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    start_btn = st.button("開始解題", type="primary", use_container_width=True)
with col_btn2:
    clear_btn = st.button("清除目前題目", use_container_width=True)

st.divider()

# --- 步驟 3：觀念解析 ---
st.markdown("""
<div class="step-header"><span class="step-number">3</span>觀念解析與 AI 三重驗證</div>
<div class="sub-text">答案 ➔ 觀念解析 ➔ 多模態選項比對</div>
""", unsafe_allow_html=True)

if start_btn:
    final_images = [st.session_state.cropped_images[i] for i in range(len(uploaded_files)) if i in st.session_state.cropped_images] if uploaded_files else []
    
    if not final_images:
        st.warning("請先上傳至少一張題目圖片！")
    else:
        with st.status("🚀 實驗室正在解析題目與進行 AI 比對...", expanded=True) as status:
            st.write("🔍 **步驟 1**：Gemini 多圖視覺 OCR 辨識中...")
            q_text = extract_text_from_images(final_images, extra_info)
            
            st.write("🤖 **步驟 2**：Gemini x ChatGPT x Claude 三方平行交叉驗證中...")
            g_raw = call_gemini(q_text)
            c_raw = call_chatgpt(q_text)
            cl_raw = call_claude(q_text)
            
            g_ans, g_reason = parse_ai_json(g_raw)
            c_ans, c_reason = parse_ai_json(c_raw)
            cl_ans, cl_reason = parse_ai_json(cl_raw)
            
            status.update(label="🎉 解析完成！", state="complete")
        
        if g_ans == c_ans == cl_ans:
            st.success(f"✅ **三家 AI 答案完全一致：【 {g_ans} 】**")
        else:
            st.warning(f"⚠️ **三家 AI 答案存在分歧！** (Gemini: {g_ans} | ChatGPT: {c_ans} | Claude: {cl_ans})")
            
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
    st.info("尚未產生題目詳解，完成上方步驟並點擊「開始解題」後，解析會顯示在這裡。")