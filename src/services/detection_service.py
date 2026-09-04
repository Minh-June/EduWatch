from datetime import datetime
from typing import Any

from src.ai_core.alert_manager import push_role_alert, save_capture, severity_for
from src.ai_core.camera_manager import CameraManager, CameraSource, infer_source_type
from src.ai_core.detector import EduWatchDetector
from src.database_query.cameras import get_camera
from src.database_query.logs import create_violation_log


class DetectionService:
    def __init__(self) -> None:
        self.detector = EduWatchDetector()
        self.managers: dict[int, CameraManager] = {}

    def camera_manager(self, camera: dict) -> CameraManager:
        camera_id = int(camera["id"])
        source = camera.get("video_source") or ""
        if camera_id not in self.managers:
            self.managers[camera_id] = CameraManager(
                CameraSource(
                    source_type=infer_source_type(source),
                    value=source,
                    room_code=camera.get("ten_phong") or "",
                    camera_position=camera.get("vi_tri_goc") or "",
                )
            )
        return self.managers[camera_id]

    def read_frame(self, camera: dict) -> Any:
        return self.camera_manager(camera).read()

    def snapshot_jpeg(self, camera_id: int) -> bytes | None:
        camera = get_camera(camera_id)
        if not camera:
            return None
        frame = self.read_frame(camera)
        if frame is None:
            return None
        try:
            import cv2

            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                return buffer.tobytes()
        except Exception:
            return None
        return None

    def detect_once(self, camera_id: int, mode: int, min_confidence: float = 0.55) -> list[dict]:
        camera = get_camera(camera_id)
        if not camera:
            return []

        frame = self.read_frame(camera)
        detections = [
            detection
            for detection in self.detector.detect(frame)
            if float(detection.get("confidence", 0)) >= min_confidence
        ]
        created: list[dict] = []
        for detection in detections:
            label = detection.get("label") or "Vi phạm AI"
            image_path = save_capture(camera_id, frame, label)
            log_id = create_violation_log(
                camera_id=camera_id,
                loai_vi_pham=label,
                thoi_gian=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                image_path=image_path,
                confidence=float(detection.get("confidence", 0)),
                mode=mode,
            )
            severity = severity_for(label, mode)
            context = f"{camera.get('ten_toa') or ''} - {camera.get('ten_phong') or ''} - {camera.get('vi_tri_goc') or 'Camera'}"
            recipient_count = push_role_alert(label, context, severity)
            created.append(
                {
                    "log_id": log_id,
                    "label": label,
                    "severity": severity,
                    "image_path": image_path,
                    "recipient_count": recipient_count,
                    "sound": severity == "Nghiêm trọng",
                }
            )
        return created

    def stop_all(self) -> None:
        for manager in self.managers.values():
            manager.stop()
        self.managers.clear()


detection_service = DetectionService()


def detect_camera_once(camera_id: int, mode: int, min_confidence: float = 0.55) -> list[dict]:
    return detection_service.detect_once(camera_id, mode, min_confidence)


def camera_snapshot_jpeg(camera_id: int) -> bytes | None:
    return detection_service.snapshot_jpeg(camera_id)
