import streamlit as st
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "eduwatch.db"

def addBuildings():
    @st.dialog("Thêm tòa nhà")
    buildings_name = st.text_input("Buildings")
    

def removeBuildings():
    @st.dialog("Xóa tòa nhà")

def updateBuildings():
    @st.dialog("Cập nhật tòa nhà")


