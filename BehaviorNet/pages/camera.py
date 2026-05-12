import streamlit as st
import numpy as np
import sqlite3
import cv2

from ultralytics import YOLO
from modules import controller as ctr

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "model" / "database.db"

st.set_page_config(layout="wide")
col1, col2, col3 = st.columns([1, 2, 1])
model = YOLO("model/yolov8n.pt")

def start(number):
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        results = model(frame)
        frame = results[number].plot()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        FRAME_WINDOW.image(frame, use_container_width=True)
    cap.release()

with col1:
    hall = st.selectbox(
        "Giảng đường:",
        ("A", "B", "Nguyễn Đăng"),
    )
    camera = st.radio(
        "Góc quay:",
        key = "camera",
        options = ["1", "2", "3", "4"],
    )
    play = st.checkbox("Phát")
with col2:
    FRAME_WINDOW = st.image([])
    cap = cv2.VideoCapture(0)
    if play:
        match camera:
            case "1":
                start(0)
            case "2":
                start(0)
            case "3":
                start(0)
            case "4":
                start(0)
                

   
