import streamlit as st
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "model" / "database.db"

st.title("Đăng nhập tài khoản")
username = st.text_input("Email hoac Username:")
password = st.text_input("Password:", type = "password")
sign_in = st.button("Đăng nhập")

def signin(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users
        WHERE username = ? AND password = ?
    """, (username, password))

    user = cursor.fetchone()
    conn.close()

    return user is not None

if sign_in:
    if signin(username, password):
        st.switch_page("pages/dataviewer.py")
    else:
        st.error("Sai thông tin")

if st.button("Đăng ký"):
    st.switch_page("pages/sign_up.py")
