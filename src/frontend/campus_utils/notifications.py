import streamlit as st
from pathlib import Path
import requests

BASE_DIR = Path(__file__).resolve().parent
js_path = BASE_DIR / "script.js"

with open(js_path, "r") as f:
    js_code = f.read()

def get_message():
    st.components.v1.html(
        f"""
        <div id="alerts"></div>
        <script>
            {js_code}
        </script>
        """
    )

