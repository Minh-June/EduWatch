import sqlite3
import streamlit as st

@st.dialog("Thêm tòa nhà")
def addBuildings():
    buildings_name = st.text_input("Buildings")

    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?)
        """, (name))

@st.dialog("Thêm camera")
def addCamera():
    camera_name = st.text_input("Camera")
    camera_angle = st.text_input("Angle")
    camera_source = st.text_input("Source")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (cemera_name))
        
@st.dialog("Thêm phòng")
def addRooms():
    rooms_name = st.text_input("Rooms")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (name))

@st.dialog("Cập nhật tòa nhà")
def updateBuildings():
    buildings_name = st.text_input("Buildings")

    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?)
        """, (name))

@st.dialog("Cập nhật camera")
def updateCamera():
    camera_name = st.text_input("Camera")
    camera_angle = st.text_input("Angle")
    camera_source = st.text_input("Source")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (cemera_name))
        
@st.dialog("Cập nhật phòng")
def updateRooms():
    rooms_name = st.text_input("Rooms")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (name))


