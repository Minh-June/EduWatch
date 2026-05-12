import streamlit as st
from pathlib import Path
import sqlite3
import sys
import os
from modules import controller as ctr

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "model" / "database.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()


tab1, tab2, tab3, tab4 = st.tabs(["Camera", "Rooms", "Buildings", "Users"])

    with tab1:
        #CRUD bảng camera 
        if st.button("Thêm camera"):
        ctr.addCamera()
        if st.button("Cập nhật camera"):
        ctr.updateCamera()            
    #if st.button("Xóa phòng"):
    #Truy vấn bảng camera
    camera_table = cursor.execute("""
        SELECT * FROM camera
    """)
    st.table(camera_table)
with tab2:
    #CRUD bảng phòng
    if st.button("Thêm phòng"):
        ctr.addRooms()
    if st.button("Cập nhật phòng"):
        ctr.updateRooms()            
    #if st.button("Xóa phòng"):    
    #Truy vấn bảng phòng
    rooms_table = cursor.execute("""
            SELECT * FROM rooms
    """)
    st.table(rooms_table)
with tab3:
    if st.button("Thêm tòa nhà"):
        ctr.addCamera()
    if st.button("Cập nhật tòa nhà"):
        ctr.updateCamera()            
    #if st.button("Xóa phòng"):
        #ctr.addBuildings()
                
    buildings_table = cursor.execute("""
        SELECT * FROM buildings
    """)
    st.table(buildings_table)
with tab4:
    users_table = cursor.execute("""
        SELECT * FROM users
    """)
    st.table(users_table)
        
#elif st.session_state.shared_data == "Professor":
#    log_table = cursor.execute("""
#        SELECT * FROM violation_logs
#    """)
conn.commit()
conn.close()
