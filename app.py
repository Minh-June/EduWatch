import streamlit as st
from pages.sign_in import show_sign_in
from pages.dashboard import show_dashboard
#from src.frontend.dashboard import show_dashboard

if "page" not in st.session_state:
    st.session_state["page"] = "login"
    
if st.session_state["page"] == "login":
    show_sign_in()
    
elif st.session_state["page"] == "dashboard":
    show_sidebar()
