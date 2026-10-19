"""
auth_ui.py - واجهة تسجيل الدخول والتحقق للمستخدمين في Streamlit
"""

import streamlit as st
from accounts import authenticate_user

def render_auth_sidebar():
    """
    عرض شريط تسجيل الدخول في Streamlit
    """
    if "user" not in st.session_state:
        st.session_state["user"] = None

    if st.session_state["user"]:
        user = st.session_state["user"]
        st.sidebar.success(f"مرحباً، {user.get('name', 'المستخدم')}")
        st.sidebar.caption(f"الدور: {user.get('role', 'طالب')} | المدرسة: {user.get('school', 'وزارة التربية')}")
        if st.sidebar.button("تسجيل الخروج"):
            st.session_state["user"] = None
            st.rerun()
    else:
        st.sidebar.subheader("تسجيل الدخول")
        email = st.sidebar.text_input("البريد الإلكتروني:", value="teacher@moe.edu.jo")
        password = st.sidebar.text_input("كلمة المرور:", type="password", value="123456")
        if st.sidebar.button("دخول المنصة", type="primary"):
            user = authenticate_user(email, password)
            if user:
                st.session_state["user"] = user
                st.sidebar.success("تم تسجيل الدخول بنجاح")
                st.rerun()
            else:
                st.sidebar.error("بيانات الدخول غير صحيحة")
