import streamlit as st
import sqlite3
import re
import sys
import string
import collections
from pathlib import Path
from src.frontend.dashboard import show_dashboard
def show_sign_up():
    BASE_DIR = Path(__file__).resolve().parent.parent
    DB_PATH = BASE_DIR / "model" / "database.db"

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("EduWatch VNUA")
        st.markdown("""
        <header>
            <h2>Chào mừng đến với hệ thống <br> AI quản trị số học tập</h2>
        </header>
        <body>
            <p>Tham gia cộng đồng giảng viên tại <br> 
            học viện Nông Nghiệp Việt Nam để <br> 
            quản lý và theo dõi tiến độ đào tạo <br> 
            hiệu quả hơn</p>
        </body>
        """, unsafe_allow_html = True)
    with col2:
        st.subheader("Đăng ký tài khoản")
        c1, c2 = st.columns([1, 1])
        with c1:
            username = st.text_input("Username:")
            gender = st.selectbox("Giới tính", ["Nam", "Nữ", "Khác"])
            date = st.date_input("Ngày sinh")
        with c2:
            email = st.text_input("Email")
            phone = st.text_input("Số điện thoại")
            password = st.text_input("Password:", type = "password")
            check_password = st.text_input("Retype password:", type = "password")
            role = st.selectbox(
                "Vai trò:",
            ("Professor", "Supervisory", "Admin"),
            )
        sign_up = st.button("Đăng ký tài khoản")
    
    if sign_up:
        if signup(username, password, check_password):
            show_dashboard()
        else:
            st.error("Sai tên đăng nhập hoặc mật khẩu không đạt yêu cầu")
