import streamlit as st
import requests

def connect_camera():
    st.components.v1.html("""
        <img
            src="http://localhost:8000/video"
            style="
                width:100%;
                height:auto;
                border-radius:10px;
            "
        >
    """,height=600)

def start_camera():
    if "camera_running" not in st.session_state:
        st.session_state.camera_running = False
    st.session_state.camera_running = (
        not st.session_state.camera_running)

    if st.session_state.camera_running:
        requests.post("http://localhost:8000/start")
    else:
        requests.post("http://localhost:8000/stop")

def activate_camera(model_active):
    st.session_state.last_model_state = (model_active)

    if model_active:
        requests.post("http://localhost:8000/model/start")
    else:
        requests.post("http://localhost:8000/model/stop")


