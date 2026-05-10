import cv2
import time
from ultralytics import YOLO
from detect_services import detect_object

def display(frame):
    _, buffer = cv2.imencode('.jpg', frame)
    frame_bytes = buffer.tobytes()

    return (
        b'--frame\r\n'
        b'Content-Type: image/jpeg\r\n\r\n' +
        frame_bytes +
        b'\r\n'
    )


def gen_frames(
        latest_detections, 
        last_detect_time,
        is_running,
        is_active
    ):
    try:
        while True:
            # Doc camera
            success, frame = cap.read()

            if not is_running:
                time.sleep(0.1)
                continue

            if not success: break

            if is_active:
                detect_object(frame)
                
                # Ve khung len hinh
                output_frame = results[0].plot()
                yield display(output_frame)
            else:
                output_frame = frame
                yield display(output_frame)
