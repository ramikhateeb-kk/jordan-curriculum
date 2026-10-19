# -*- coding: utf-8 -*-
"""accounts.py & auth_ui.py - إدارة حسابات المعلمين والطلبة وتسجيل الدخول"""
import streamlit as st

def render_login_ui():
    st.sidebar.markdown("### 🔐 حساب المستخدم")
    st.sidebar.info("مسجل كـ: معلم / مشرف تربوي")
