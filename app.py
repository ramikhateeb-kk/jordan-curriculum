"""
app.py - واجهة تطبيق رفيق المنهاج الأردني المطور (Streamlit App)
تتضمن التحسينات الثلاثة:
1. التنسيق السليم والاتجاه LTR للغة الإنجليزية
2. التخلص من الأسطر الفارغة في نتائج كتاب الأنشطة
3. الحل والشرح الذكي للأسئلة مع التحقق المنهجي المعتمد
"""

import streamlit as st
from config import APP_NAME
from catalog import get_catalog
from explain_ctx import explain_question_solution
from english_docs import format_english_explanation_html
from rag import search_activity_book, sanitize_text_whitespace

st.set_page_config(
    page_title=APP_NAME,
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Jordanian Curriculum UI & LTR/RTL support
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
    }
    .ltr-box {
        direction: ltr !important;
        text-align: left !important;
        font-family: 'Inter', system-ui, sans-serif !important;
    }
    .rtl-box {
        direction: rtl !important;
        text-align: right !important;
    }
    .clean-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

catalog = get_catalog()

# Sidebar: Grade and Semester selection
with st.sidebar:
    st.image("https://images.unsplash.com/photo-1546410531-bb4caa6b424d?w=300&q=80", use_container_width=True)
    st.title("منهاج الأردن الذكي")
    st.caption("المعلم ورفيق الحلول لكتب الطالب وكراسات الأنشطة")
    
    selected_grade = st.selectbox("اختر الصف الدراسي:", catalog["grades"], index=3)
    selected_semester = st.radio("الفصل الدراسي:", ["الفصل الأول", "الفصل الثاني"], index=0)
    
    st.markdown("---")
    st.info("💡 **توجيهات النظام المحدثة:**\n- يتم عرض شروحات اللغة الإنجليزية بنظام LTR تلقائياً لمنع تشوه النصوص.\n- تم إلغاء الأسطر الفارغة في كراسة الأنشطة.\n- يتم حل كافة أسئلة المنهاج بالذكاء الاصطناعي دون إظهار تعذر الإجابة إلا للأسئلة الخارجة تماماً عن المادة.")

# Main Application Tabs
tab1, tab2, tab3 = st.tabs([
    "🔍 اشرح لي حل السؤال (المعلم الذكي)",
    "📖 كتاب الأنشطة والتمارين (بدون أسطر فارغة)",
    "🗺️ شجرة المنهاج والتحقق المنهجي"
])

# ---------------- Tab 1: Question Explainer ----------------
with tab1:
    st.header("اشرح لي حل السؤال في المنهاج")
    st.write("حدد المادة ورقم الصفحة والسؤال للحصول على الشرح الكامل والحل المعتمد:")

    col_sub, col_book = st.columns(2)
    with col_sub:
        subject_names = [s["name"] for s in catalog["subjects"]]
        selected_subject_name = st.selectbox("المادة الدراسية:", subject_names, index=0)
        is_eng = "English" in selected_subject_name or "الإنجليزية" in selected_subject_name

    with col_book:
        selected_book = st.selectbox("نوع الكتاب:", catalog["book_types"], index=0)

    col_p, col_q, col_txt = st.columns([1, 1, 3])
    with col_p:
        page_num = st.text_input("رقم الصفحة:", value="18")
    with col_q:
        q_num = st.text_input("رقم السؤال:", value="2")
    with col_txt:
        q_text = st.text_input("نص أو موضوع السؤال (اختياري):", value="")

    # Quick test case button
    if st.button("🧪 تجربة سريعة: سؤال دورة الماء في التاريخ (فحص عدم الصلة)"):
        st.session_state["test_subj"] = "التاريخ"
        st.session_state["test_text"] = "دورة الماء في الطبيعة"

    if st.button("✨ اشرح لي حل السؤال الآن", type="primary", use_container_width=True):
        with st.spinner("جاري فحص المنهاج والبحث عن إجابة السؤال بالذكاء الاصطناعي..."):
            res = explain_question_solution(
                grade=selected_grade,
                subject=selected_subject_name,
                book_type=selected_book,
                page_number=page_num,
                question_number=q_num,
                question_text=q_text
            )

            # Case A: Irrelevant out-of-scope query
            if not res.get("is_relevant", True):
                st.warning(res.get("message", "تنبيه منهجي: السؤال غير وارد في منهاج هذه المادة."))
                if res.get("suggested_subject"):
                    st.info(f"💡 المادة المقترحة للحل: {res['suggested_subject']}")
            else:
                st.success("تم استخراج وشرح الحل بنجاح من المنهاج المعتمد!")
                
                # Check direction (LTR for English)
                if res.get("is_english"):
                    st.markdown("#### English Solution & Explanation (LTR Mode):")
                    st.markdown(format_english_explanation_html(res.get("solution_text", "")), unsafe_allow_html=True)
                else:
                    st.markdown("#### الحل والشرح النموذجي المعتمد:")
                    st.markdown(f"""
                    <div dir="rtl" class="clean-card" style="line-height: 1.8;">
                        {res.get('solution_text', '').replace('\n', '<br>')}
                    </div>
                    """, unsafe_allow_html=True)


# ---------------- Tab 2: Activity Book ----------------
with tab2:
    st.header("كتاب الأنشطة والتمارين (خالٍ من الأسطر الفارغة)")
    st.write("ابحث في كراسة التمارين واحصل على بطاقات منظمة ومباشرة:")

    act_query = st.text_input("ابحث عن موضوع السؤال أو القاعدة أو رقم الصفحة:", value="Past Simple")
    
    if st.button("بحث في كتاب الأنشطة", key="act_search_btn"):
        with st.spinner("جاري تنظيف الفراغات ومسح تمارين كتاب الأنشطة..."):
            act_results = search_activity_book(selected_grade, selected_subject_name, act_query)
            
            if not act_results:
                st.info("لم يتم العثور على أنشطة مطابقة.")
            else:
                for act in act_results:
                    st.markdown(f"""
                    <div class="clean-card">
                        <span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: bold;">{act['unit']}</span>
                        <span style="background: #e2e8f0; color: #334155; padding: 2px 8px; border-radius: 6px; font-size: 12px; margin-right: 5px;">{act['exercise']} - صفحة {act['page']}</span>
                        <h4 style="margin-top: 10px;">{act['title']}</h4>
                        <div style="background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #cbd5e1; margin: 8px 0;" dir="{'ltr' if is_eng else 'rtl'}">
                            <strong>نص النشاط:</strong><br>{act['prompt']}
                        </div>
                        <div style="background: #ecfdf5; padding: 12px; border-radius: 8px; border: 1px solid #a7f3d0; margin: 8px 0;" dir="{'ltr' if is_eng else 'rtl'}">
                            <strong style="color: #065f46;">الحل النموذجي:</strong><br>{act['solution']}
                        </div>
                        <small style="color: #64748b;">المرجع بكتاب الطالب: {act['student_book_ref']}</small>
                    </div>
                    """, unsafe_allow_html=True)


# ---------------- Tab 3: Curriculum Map ----------------
with tab3:
    st.header("شجرة المنهاج وقواعد التحقق المنهجي")
    st.info("""
    **الضابط المنهجي الصارم:**
    - لا تظهر رسالة عدم وجود إجابة إذا كان السؤال متعلقاً بالمادة المحددة.
    - تظهر رسالة التنبيه فقط إذا كان السؤال خارج المنهاج كلياً:
      - ❌ سؤال الطالب عن **دورة الماء** في مادة **التاريخ** -> يظهر تنبيه بعدم الصلة والتوجيه إلى العلوم.
      - ✅ سؤال الطالب عن **حل سؤال صفحة 18** في **اللغة الإنجليزية أو الرياضيات** -> يقوم الذكاء الاصطناعي بالحل فوراً.
    """)
