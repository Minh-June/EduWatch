import cv2
import time
import hashlib
import sqlite3
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from connect_camera import gen_frames
from ultralytics import YOLO

router = APIRouter()

latest_detections = []
last_detect_time = {}
COOLDOWN = 5

@router.get("/video")
def video_feed():
    return StreamingResponse(
        gen_frames(latest_detections, last_detect_time),
        media_type='multipart/x-mixed-replace; boundary=frame')

@router.get("/detections")       
def detections():
    data = list(latest_detections)
    return data

@router.post("/start")
def start_camera():
    global is_running
    is_running = True
    return {"status": "started"}

@router.post("/stop")
def stop_camera():
    global is_running
    is_running = False
    return {"status": "stopped"}

@router.post("/model/start")
def activate():
    global is_active
    is_active = True
    return {"predict": "started"}

@router.post("/model/stop")
def deactivate():
    global is_active
    is_active = False
    return {"predict": "stopped"}

