from pathlib import Path
from typing import Any

from src.utils.config import YOLO_MODEL_PATH


CLASS_NAMES = {
    0: "Ngủ gật",
    1: "Cúi người sâu",
    2: "Rời vị trí",
    3: "Sử dụng điện thoại",
    4: "Quay bài/Trao đổi",
    5: "Đứng dậy",
    6: "Đọc tài liệu",
    7: "Di chuyển",
}


class EduWatchDetector:
    """YOLO detector wrapper. The real model is loaded later when weights are ready."""

    def __init__(self, model_path: str | Path = YOLO_MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        self.model: Any | None = None
        self.available = False

    def load(self) -> bool:
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(self.model_path))
            self.available = True
            return True
        except Exception:
            self.model = None
            self.available = False
            return False

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            return []

        if self.model is None and not self.load():
            return []

        results = self.model(frame, imgsz=640)
        detections: list[dict[str, Any]] = []
        for result in results:
            for box in getattr(result, "boxes", []):
                cls_id = int(box.cls[0]) if getattr(box, "cls", None) is not None else -1
                confidence = float(box.conf[0]) if getattr(box, "conf", None) is not None else 0.0
                detections.append(
                    {
                        "class_id": cls_id,
                        "label": CLASS_NAMES.get(cls_id, f"Vi phạm #{cls_id}"),
                        "confidence": confidence,
                        "box": box.xyxy[0].tolist(),
                    }
                )
        return detections


Detector = EduWatchDetector
