import hmac
import pandas as pd
import streamlit as st
import catalog
import prompts as prompt_store

st.set_page_config(page_title="برومتات التقييم", page_icon="🧠", layout="wide")
st.markdown("""<style>html,body,.stApp,[data-testid="stMarkdownContainer"]{direction:rtl;text-align:right}textarea,input{direction:rtl;text-align:right}</style>""", unsafe_allow_html=True)
st.title("🧠 إدارة برومتات توليد الأسئلة")
st.caption("يُحفظ برومت مستقل لكل مبحث وصف وفصل. عند توليد سؤال في «قيّمني» يسترجع النظام البرومت المطابق تلقائيًا.")

admin_pw = catalog.secret("ADMIN_PASSWORD")
if not admin_pw:
    st.error("لم تُضبط كلمة مرور المشرف. أضف ADMIN_PASSWORD إلى Secrets.")
    st.stop()
if not st.session_state.get("admin_ok"):
    entered = st.text_input("كلمة مرور مدير النظام", type="password")
    if st.button("دخول"):
        if hmac.compare_digest(entered.encode(), str(admin_pw).encode()):
            st.session_state["admin_ok"] = True
            st.rerun()
        st.error("كلمة المرور غير صحيحة.")
    st.stop()

try:
    books = [b for b in catalog.list_books() if not b.get("parent_slug")]
    rows = prompt_store.list_prompts()
except Exception as e:
    st.error(f"تعذّرت قراءة برومتات التقييم: {e}")
    if catalog.backend_name() == "supabase":
        st.warning("إذا كان جدول assessment_prompts غير موجود، نفّذ ملف supabase_assessment_prompts.sql مرة واحدة من Supabase → SQL Editor.")
    st.stop()

if rows:
    st.subheader("البرومتات المحفوظة")
    st.dataframe([{"المبحث": r["subject"], "الصف": r["grade"], "الفصل": r.get("semester", 1),
                   "الحالة": "مفعّل" if r.get("active", True) else "موقوف",
                   "عدد الأحرف": len(r.get("prompt", ""))} for r in rows], hide_index=True, use_container_width=True)
else:
    st.info("لا توجد برومتات محفوظة بعد. أضف برومتًا أدناه.")

st.subheader("إضافة برومت أو تعديله")
subjects = sorted({b["subject"] for b in books})
subject_options = subjects or ["English Language"]
subject = st.selectbox("المبحث", subject_options, index=next((i for i,x in enumerate(subject_options) if "english" in x.lower() or "إنجليز" in x), 0))
c1, c2 = st.columns(2)
grade = c1.selectbox("الصف", list(range(1, 13)), index=10, format_func=lambda x: f"الصف {x}")
semester = c2.selectbox("الفصل الدراسي", [1, 2], format_func=lambda x: "الأول" if x == 1 else "الثاني")
matched = next((r for r in rows if str(r.get("subject", "")).casefold() == subject.casefold() and int(r["grade"]) == int(grade) and int(r.get("semester", 1)) == int(semester)), None)
if matched:
    default_prompt = matched.get("prompt", "")
elif int(grade) == 11 and ("english" in subject.lower() or "إنجليز" in subject or "انجليز" in subject):
    default_prompt = prompt_store.DEFAULT_EN_G11_PROMPT
else:
    default_prompt = "أنت خبير في إعداد أسئلة تقويمية وفق المنهاج الأردني. استخدم فقط محتوى الدرس المرفق، والتزم بنوع السؤال المناسب للمبحث، ولا تخترع مصادر أو أرقام صفحات. أعد JSON فقط وفق المخطط الذي يرسله النظام."

prompt_text = st.text_area("البرومت الكامل", value=default_prompt, height=520, key=f"prompt_{subject}_{grade}_{semester}_{matched.get('id') if matched else 'new'}")
active = st.checkbox("تفعيل هذا البرومت", value=matched.get("active", True) if matched else True)
if st.button("💾 حفظ البرومت", type="primary"):
    try:
        saved = prompt_store.save_prompt(subject, grade, semester, prompt_text, active)
        st.success(f"تم حفظ برومت {subject} — الصف {grade} — الفصل {semester}.")
        st.rerun()
    except Exception as e:
        st.error(f"تعذّر حفظ البرومت: {e}")

with st.expander("📝 تعليمات إعداد البرومت"):
    st.markdown("""
- حدّد نوع السؤال حسب **محتوى الدرس الفعلي** وليس عنوانه فقط.
- دروس القراءة تنتج أسئلة فهم مقروء قصيرة.
- دروس الكتابة الحرة تنتج مهمة كتابة فعلية ونموذج إجابة وسلم تصحيح، وليس اختيارًا من متعدد.
- دروس القواعد والمفردات والوظائف اللغوية المركّزة تنتج اختيارًا من متعدد بأربعة خيارات.
- عند الربط بين كتاب الطالب وكتاب الأنشطة، لا تنسب معلومة أو صفحة إلى الكتاب الخطأ.
- لا تخترع أرقام صفحات، وأعد JSON مطابقًا للمخطط الذي يطلبه النظام.
    """)
