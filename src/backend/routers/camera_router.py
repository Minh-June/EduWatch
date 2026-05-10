from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import src.backend.state.camera_state as state

from src.ai_core.camera_manager import CameraManager

router = APIRouter()

camera_manager = CameraManager(0)

@router.get("/video")
def video_feed():
    return StreamingResponse(
        camera_manager.gen_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get("/detections")
def detections():
    return list(state.latest_detections)

@router.post("/start")
def start_camera():
    state.is_running = True
    return {"status": "started"}

@router.post("/stop")
def stop_camera():
    state.is_running = False
    return {"status": "stopped"}

@router.post("/model/start")
def activate():
    state.is_active = True
    return {"predict": "started"}

@router.post("/model/stop")
def deactivate():
    state.is_active = False
    return {"predict": "stopped"}
