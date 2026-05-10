import cv2
import time

from src.ai_core.detector import Detector
from src.ai_core.stream_utils import display

from src.backend.state.camera_state import (
    is_running,
    is_active
)

class CameraManager:
    def __init__(self, source):
        self.cap = cv2.VideoCapture(source)
        self.is_running = False
    
    def gen_frames(self):
        while True:
            success, frame = self.cap.read()
            
            if not is_running:
                time.sleep(0.1)
                continue
            
            if not success:
                break
                
            if is_active:
                results = self.detector.detect(frame)
                output_frame = results[0].plot()
                yield display(output_frame)
            else:
                yield display(frame)
