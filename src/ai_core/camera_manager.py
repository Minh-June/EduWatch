from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class CameraSource:
    source_type: str
    value: str
    room_code: str = ""
    camera_position: str = ""


class CameraManager:
    """Small OpenCV-backed camera stream manager for RTSP/IP, webcam, and video files."""

    def __init__(self, source: CameraSource) -> None:
        self.source = source
        self.running = False
        self.capture: Any | None = None

    def start(self) -> bool:
        try:
            import cv2
        except Exception:
            self.running = False
            return False

        value: str | int = self.source.value
        if self.source.source_type == "webcam":
            value = int(self.source.value or 0)
        elif self.source.source_type == "video":
            value = str(Path(self.source.value))

        self.capture = cv2.VideoCapture(value)
        self.running = bool(self.capture and self.capture.isOpened())
        return self.running

    def stop(self) -> None:
        if self.capture is not None:
            self.capture.release()
        self.capture = None
        self.running = False

    def read(self):
        if self.capture is None and not self.start():
            return None
        ok, frame = self.capture.read()
        if not ok:
            if self.source.source_type == "video" and self.capture is not None:
                self.capture.set(1, 0)
                ok, frame = self.capture.read()
            if not ok:
                return None
        return frame

    def frames(self) -> Iterator[Any]:
        self.running = True
        if self.capture is None and not self.start():
            return
        while self.running:
            frame = self.read()
            if frame is None:
                break
            yield frame


def infer_source_type(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized.startswith(("rtsp://", "http://", "https://")):
        return "rtsp"
    if normalized.isdigit():
        return "webcam"
    return "video"
