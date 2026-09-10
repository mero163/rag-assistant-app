import streamlit as st
import requests
import time

# Page Configuration
st.set_page_config(
    page_title="المساعد القانوني المصري",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium RTL Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
    }
    
    /* Title Header */
    .main-header {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 2rem;
        border-radius: 16px;
        border: 1px solid #334155;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        margin-bottom: 2rem;
        text-align: center;
    }
    
    .main-header h1 {
        color: #38bdf8;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }
    
    .main-header p {
        color: #94a3b8;
        font-size: 1.1rem;
    }
    
    /* Source Badges */
    .article-badge {
        display: inline-block;
        background-color: #0284c7;
        color: #ffffff;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.875rem;
        margin: 0.25rem;
    }
    
    .source-card {
        background-color: #1e293b;
        border-right: 4px solid #38bdf8;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    
    .source-title {
        color: #38bdf8;
        font-weight: 700;
        font-size: 1rem;
    }
    
    .source-meta {
        color: #64748b;
        font-size: 0.85rem;
        margin-bottom: 0.5rem;
    }
    
    .source-content {
        color: #cbd5e1;
        font-size: 0.95rem;
        line-height: 1.6;
    }

    .stButton button {
        width: 100%;
        background-color: #0284c7;
        color: white;
        font-weight: 700;
        border-radius: 8px;
        border: none;
        padding: 0.6rem 1rem;
        transition: all 0.3s ease;
    }
    
    .stButton button:hover {
        background-color: #0369a1;
        box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# Configuration settings
BACKEND_URL_INPUT = st.sidebar.text_input("رابط الـ Backend API", value="http://127.0.0.1:8000")
BACKEND_URL = BACKEND_URL_INPUT.strip().rstrip("/")

# Function to check backend health with retry fallback
def get_backend_health():
    urls_to_try = [
        f"{BACKEND_URL}/health",
        f"{BACKEND_URL}/api/health",
        "http://127.0.0.1:8000/health",
        "http://localhost:8000/health"
    ]
    for url in urls_to_try:
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception:
            continue
    return None

# Sidebar Controls
st.sidebar.markdown("### ⚙️ إعدادات النظام")
health_data = get_backend_health()

if health_data and health_data.get("status") in ["healthy", "online"]:
    st.sidebar.success("🟢 الاتصال بالـ Backend نشط")
    st.sidebar.markdown(f"**عدد القطع المفهرسة:** `{health_data.get('total_chunks', 0)}`")
    st.sidebar.markdown(f"**نموذج التضمين:** `{health_data.get('embedding_model', 'BAAI/bge-m3')}`")
else:
    st.sidebar.error("🔴 متعذر الاتصال بالـ Backend (تأكد من تشغيل uvicorn backend.main:app)")

st.sidebar.markdown("---")

selected_model = st.sidebar.selectbox(
    "نموذج الذكاء الاصطناعي (LLM):",
    options=["qwen2.5:7b", "qwen2.5:3b", "aya-expanse:8b", "mistral:latest"],
    index=0
)

top_k = st.sidebar.slider("عدد المواد القانونية المسترجعة (Top-K):", min_value=1, max_value=10, value=5)

if st.sidebar.button("🔄 إعادة فهرسة المستندات"):
    with st.spinner("جاري إعادة فهرسة المستندات..."):
        try:
            res = requests.post(f"{BACKEND_URL}/reindex", timeout=120)
            if res.status_code == 200:
                st.sidebar.success("✅ تمت الفهرسة بنجاح!")
                st.rerun()
            else:
                st.sidebar.error("❌ فشلت الفهرسة")
        except Exception as e:
            st.sidebar.error(f"خطأ: {e}")

# Header
st.markdown("""
<div class="main-header">
    <h1>⚖️ المساعد القانوني المصري الذكي</h1>
    <p>نظام استرجاع وإجابة قائم على RAG مدعوم بالتشريعات المصرية (الدستور، قانون العقوبات، المرور، والعمل)</p>
</div>
""", unsafe_allow_html=True)

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Quick Sample Questions
st.markdown("##### 💡 أسئلة مقترحة للاختبار:")
col1, col2, col3, col4 = st.columns(4)

sample_q = None
if col1.button("📌 ما هي اللغة الرسمية للدولة؟"):
    sample_q = "ما هي اللغة الرسمية للدولة؟"
if col2.button("🚗 عقوبة السير عكس الاتجاه؟"):
    sample_q = "ما هي عقوبة السير عكس الاتجاه؟"
if col3.button("💼 إجازة العامل السنوية؟"):
    sample_q = "كم تبلغ إجازة العامل السنوية؟"
if col4.button("📜 المصدر الرئيسي للتشريع؟"):
    sample_q = "ما هو المصدر الرئيسي للتشريع؟"

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            with st.expander("📚 النصوص والمواد القانونية المسترجعة"):
                for idx, src in enumerate(message["sources"]):
                    st.markdown(f"""
                    <div class="source-card">
                        <div class="source-title">📄 {src['law_title']} - مادة ({src['article_number']})</div>
                        <div class="source-meta">نسبة الصلة: {int(src['score'] * 100)}%</div>
                        <div class="source-content">{src['content']}</div>
                    </div>
                    """, unsafe_allow_html=True)

# Chat Input Logic
user_input = st.chat_input("اكتب سؤالك القانوني هنا...")
prompt_to_process = sample_q if sample_q else user_input

if prompt_to_process:
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt_to_process})
    with st.chat_message("user"):
        st.markdown(prompt_to_process)

    # Process RAG Request
    with st.chat_message("assistant"):
        with st.spinner("جاري البحث في التشريعات القانونية وتوليد الإجابة..."):
            try:
                payload = {
                    "question": prompt_to_process,
                    "top_k": top_k,
                    "model_name": selected_model
                }
                response = requests.post(f"{BACKEND_URL}/query", json=payload, timeout=90)
                
                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("answer", "لم يتم الحصول على إجابة.")
                    sources = data.get("sources", [])
                    art_nums = data.get("article_numbers", [])
                    exec_time = data.get("processing_time_sec", 0.0)

                    # Append Article Badges if present
                    full_display_answer = answer
                    if art_nums:
                        badges_html = " ".join([f"<span class='article-badge'>مادة {num}</span>" for num in art_nums])
                        full_display_answer += f"\n\n**📌 أرقام المواد المستند إليها:**\n\n{badges_html}"

                    full_display_answer += f"\n\n_<small>⏱️ زمن المعالجة: {exec_time} ثانية</small>_"

                    st.markdown(full_display_answer, unsafe_allow_html=True)

                    if sources:
                        with st.expander("📚 النصوص والمواد القانونية المسترجعة"):
                            for src in sources:
                                st.markdown(f"""
                                <div class="source-card">
                                    <div class="source-title">📄 {src['law_title']} - مادة ({src['article_number']})</div>
                                    <div class="source-meta">نسبة الصلة: {int(src['score'] * 100)}%</div>
                                    <div class="source-content">{src['content']}</div>
                                </div>
                                """, unsafe_allow_html=True)

                    # Save to state
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_display_answer,
                        "sources": sources
                    })

                else:
                    st.error(f"❌ حدث خطأ من الـ Backend: {response.text}")
            except Exception as e:
                st.error(f"❌ تعذر الاتصال بالسيرفر: {e}")
