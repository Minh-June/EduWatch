import time
from ultralytics import YOLO
from src.backend.state.camera_state import (
    latest_detections,
    last_detect_time,
    COOLDOWN
)

class Detector:
    def __init__(self, model_path):
        self.model = YOLO(model_path)

    def detect_object(self, frame):
        results = self.model(frame, imgsz=320)
        return results


