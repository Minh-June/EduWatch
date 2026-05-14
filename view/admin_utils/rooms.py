import streamlit as st
def addRooms():
    @st.dialog("Thêm phòng")
    rooms_name = ui.input("Rooms")
    
    if ui.button("Submit"):
        insertRooms(rooms_name)
