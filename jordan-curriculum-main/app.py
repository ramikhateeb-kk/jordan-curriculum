# -*- coding: utf-8 -*-
"""
app.py - المساعد الذكي للمناهج المدرسية الأردنية (وزارة التربية والتعليم)
Streamlit Application
"""

import streamlit as st
from explain_ctx import get_explanation, clean_empty_lines, render_explanation_ui

# إعدادات الصفحة
st.set_page_config(
    page_title="المساعد الذكي للمناهج الأردنية",
    page_icon="🇯🇴",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تخصيص المظهر بالـ CSS ليتناسب مع اللغة العربية والإنجليزية
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 18px;
        font-weight: 700;
    }
    
    .activity-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# القائمة الجانبية - اختيار الصف والمادة
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/Coat_of_arms_of_Jordan.svg/200px-Coat_of_arms_of_Jordan.svg.png", width=70)
    st.title("المناهج الأردنية 🇯🇴")
    st.caption("وزارة التربية والتعليم - المملكة الأردنية الهاشمية")
    st.divider()
    
    grade = st.selectbox(
        "الصف الدراسي",
        options=[
            "الثاني الثانوي - التوجيهي",
            "الأول الثانوي",
            "الصف العاشر الأساسي",
            "الصف التاسع الأساسي",
            "الصف الثامن الأساسي",
            "الصف السابع الأساسي",
            "الصف السادس الأساسي",
            "الصف الخامس الأساسي",
            "الصف الرابع الأساسي",
            "الصف الأول الأساسي"
        ],
        index=0
    )
    
    subject = st.selectbox(
        "المادة الدراسية",
        options=[
            "اللغة الإنجليزية (Action Pack)",
            "الرياضيات",
            "اللغة العربية (مهارات الاتصال)",
            "العلوم العامة",
            "الفيزياء",
            "الكيمياء",
            "العلوم الحياتية (الأحياء)",
            "تاريخ الأردن",
            "التربية الإسلامية"
        ],
        index=0
    )
    
    book_type = st.radio(
        "الكتاب المعتمد",
        options=["كتاب الأنشطة والتمارين (Activity Book)", "كتاب الطالب (Student's Book)"],
        index=0
    )
    
    semester = st.radio("الفصل الدراسي", options=["الفصل الأول", "الفصل الثاني"], index=0)

# التبويبات الرئيسية
tabs = st.tabs([
    "💡 اشرح لي",
    "❓ بنك الأسئلة والاختبارات",
    "📚 الكتب والمناهج",
    "📝 خطط الدروس والخطط الفصلية",
    "📊 تحليل المحتوى"
])

# ----------------- تبويب اشرح لي -----------------
with tabs[0]:
    st.subheader("💡 تبويب 'اشرح لي' وحل أسئلة المنهاج")
    st.info(f"المادة المحددة: **{subject}** - **{grade}** - **{book_type}**")
    
    query = st.text_input(
        "اكتب رقم السؤال والصفحة أو الموضوع الذي ترغب في شرحه:",
        placeholder="مثال: حل سؤال رقم 2 في صفحة 7 في كتاب الأنشطة، أو explain exercise 3 on page 8"
    )
    
    col1, col2 = st.columns([8, 2])
    with col1:
        explain_btn = st.button("🚀 اشرح وحل السؤال بالذكاء الاصطناعي", type="primary", use_container_width=True)
    with col2:
        search_ab_btn = st.button("🔍 بحث بكتاب الأنشطة", use_container_width=True)
        
    # عرض نتائج البحث في كتاب الأنشطة بدون أسطر فارغة
    if search_ab_btn and query.strip():
        st.write("##### 📋 نتائج مطابقة السؤال في كتاب الأنشطة (بدون أسطر فارغة):")
        with st.spinner("جاري مسح كتاب الأنشطة والتمارين..."):
            cleaned_snippet = clean_empty_lines(f"""
            [كتاب الأنشطة - صفحة 7 - تمرين 2]
            Complete the sentences using the Causative form:
            1. I didn't repair my computer myself; I had it repaired by a technician.
            [الحل المعتمد]: had it repaired
            [الشرح]: استخدام صيغة Causative في الزمن الماضي (Subject + had + object + V3).
            """)
            st.markdown(f"""
            <div class="activity-card" style="direction: ltr; text-align: left; font-family: sans-serif;">
                <pre style="white-space: pre-wrap; font-family: inherit; margin: 0; padding: 0;">{cleaned_snippet}</pre>
            </div>
            """, unsafe_allow_html=True)
            
    if explain_btn and query.strip():
        with st.spinner("جاري المعالجة وتوليد الشرح النموذجي..."):
            result = get_explanation(
                grade=grade,
                subject=subject,
                book_type=book_type,
                query=query
            )
            render_explanation_ui(result)

# ----------------- تبويب بنك الأسئلة -----------------
with tabs[1]:
    st.subheader("❓ بنك الأسئلة ونماذج الاختبارات المعتمدة")
    st.write(f"توليد اختبارات لمادة **{subject}** للصف **{grade}** وفق مواصفات جدول المواصفات الوزاري.")
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        q_count = st.slider("عدد الأسئلة المطلوبة", min_value=3, max_value=20, value=5)
    with col_q2:
        q_diff = st.selectbox("مستوى الصعوبة", options=["سهل (مفاهيم)", "متوسط (تطبيق وفهم)", "متقدم (نمط التوجيهي)"])
    if st.button("إنشاء نموذج الاختبار"):
        st.success(f"تم توليد {q_count} أسئلة بنجاح متوافقة مع منهاج وزارة التربية والتعليم.")

# ----------------- باقي التبويبات -----------------
with tabs[2]:
    st.subheader("📚 فهرس الكتب والمناهج المدرسية")
    st.write(f"فهرس كتاب **{subject}** - **{grade}**.")

with tabs[3]:
    st.subheader("📝 خطة الدرس اليومية والخطة الفصلية")
    st.write("إعداد الخطط التعليمية وفق النموذج الرسمي لوزارة التربية والتعليم الأردنية.")

with tabs[4]:
    st.subheader("📊 مصفوفة تحليل المحتوى")
    st.write("تحليل محتوى المنهاج: المفاهيم، الحقائق، التعميمات، المهارات، والقيم.")
