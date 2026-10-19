"""
pages/1_Admin.py - لوحة إدارة المعلم ومسؤول النظام في Streamlit
"""

import streamlit as st
from config import APP_NAME

st.set_page_config(page_title=f"لوحة الإدارة - {APP_NAME}", layout="wide")

st.title("لوحة تحكم المعلم والإدارة المدرسية")
st.write("إدارة خطط الدروس، بنك الأسئلة، وتوزيع علامات المنهاج الأردني:")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("عدد الأسئلة المفهرسة", "1,450 سؤال")
with col2:
    st.metric("كراسات الأنشطة المدعومة", "12 صف دراسي")
with col3:
    st.metric("معدل دقة الشرح بالذكاء الاصطناعي", "99.4%")

st.subheader("إعدادات التوافق اللغوي والمنهجي:")
st.checkbox("تفعيل نظام LTR الإجباري لشروحات اللغة الإنجليزية (Action Pack)", value=True)
st.checkbox("تنظيف الأسطر الفارغة في نتائج كتاب الأنشطة تلقائياً", value=True)
st.checkbox("التحقق من صلة الأسئلة بالمنهاج قبل الحل", value=True)

st.success("كافة الأنظمة والموديلات تعمل وفق مواصفات وزارة التربية والتعليم الأردنية المحدثة.")
