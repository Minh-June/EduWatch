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
        
        for box in results[0].boxes:
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = self.model.names[cls_id]
            if conf > 0.8:
                last_time = last_detect_time.get(label, 0)
                current_time = time.time()
                if current_time - last_time > COOLDOWN:
                    detection = {
                        "label": label,
                        "confidence": conf
                    }
                    
                    latest_detections.append(detection)
                    last_detect_time[label] = current_time
        return results


