from streamlit_option_menu import option_menu
from src.frontend.campus_utils.camera import connect_camera, start_camera, activate_camera
from src.frontend.campus_utils.notifications import get_message
import streamlit as st

#with open("style.css") as f:

#    st.markdown(
#        f"<style>{f.read()}</style>",
#        unsafe_allow_html=True
#    )

# --- initstate ---
def show_dashboard():
    ctn1 = st.container()
    ctn2 = st.container()
    with ctn1:
        st.write("Tong quan")               
    with ctn2:
        col1, col2 = st.columns([2, 1])
        with col1:
            ctn1 = st.container()
            ctn2 = st.container()
            with ctn1:
                st.title("Camera stream")
                connect_camera()
            with ctn2:
                btn = st.button("Start / Stop")
                model_active = st.toggle("Activate Model")
                if btn:
                    start_camera()
                if model_active != st.session_state.get(
                    "last_model_state", False):
                    activate_camera(model_active)
        with col2:
            st.subheader("NHẬT KÝ VI PHẠM MỚI NHẤT")
            get_message()
