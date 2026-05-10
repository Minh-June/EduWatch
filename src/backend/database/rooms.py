import streamlit as st
def addRooms():
    @st.dialog("Thêm phòng")
    rooms_name = st.text_input("Rooms")
    
    if st.button("Submit"):
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?,?,?)
        """, (name))
