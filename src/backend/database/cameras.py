import streamlit as st

def addCamera():
    @st.dialog("Thêm camera")
    camera_name = st.text_input("Camera")
    camera_angle = st.text_input("Angle")
    camera_source = st.text_input("Source")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (cemera_name))

