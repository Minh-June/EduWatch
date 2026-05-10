import streamlit as st
from pages.dashboard import show_dashboard

def show_sidebar():
    with st.sidebar:
        selected = option_menu(
            "EduWatch VNUA", [
                "Giám sát trực tiếp",
                "Nhật ký vi phạm", 
                "Trang báo cáo", 
                'Settings'
                ],
            icons = [
                'camera-video', 
                'journal', 
                'bar-chart', 
                'gear'
                ], 
            menu_icon="cast", 
            default_index=1
        )
        ctn = st.container()
        with ctn:
            email = st.session_state.get("email")
            st.subheader("Ten dang nhap")
            st.write(email)
        )
    if selected == "Giám sát trực tiếp":
        show_dashboard()
    elif selected == "Trang báo cáo":
        st.title("Trang báo cáo")

    elif selected == "Settings":
        st.title("Cài đặt hệ thống")
