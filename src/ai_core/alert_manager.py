from datetime import datetime
from pathlib import Path
from typing import Any

from src.database_query.auth import connect
from src.utils.config import BASE_DIR, CAPTURE_DIR


SEVERITY_BY_NAME = {
    "Ngủ gật": "Trung bình",
    "Cúi người sâu": "Nghiêm trọng",
    "Rời vị trí": "Nghiêm trọng",
    "Sử dụng điện thoại": "Nghiêm trọng",
    "Quay bài/Trao đổi": "Nghiêm trọng",
    "Đứng dậy": "Trung bình",
    "Đọc tài liệu": "Nghiêm trọng",
    "Di chuyển": "Trung bình",
}


def save_alert_placeholder(alert_id: str) -> str:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CAPTURE_DIR / f"{alert_id}.txt"
    path.write_text("placeholder capture", encoding="utf-8")
    return str(path)


def save_capture(camera_id: int, frame: Any, label: str) -> str:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(ch if ch.isalnum() else "_" for ch in label)[:40]
    path = CAPTURE_DIR / f"cam_{camera_id}_{safe_label}_{timestamp}.jpg"
    try:
        import cv2

        if frame is not None and cv2.imwrite(str(path), frame):
            return str(path.relative_to(BASE_DIR))
    except Exception:
        pass

    fallback = path.with_suffix(".txt")
    fallback.write_text(
        f"camera_id={camera_id}\nlabel={label}\ncaptured_at={datetime.now().isoformat(timespec='seconds')}",
        encoding="utf-8",
    )
    return str(fallback.relative_to(BASE_DIR))


def severity_for(label: str, mode: int) -> str:
    if mode == 1:
        return "Nghiêm trọng"
    return SEVERITY_BY_NAME.get(label, "Trung bình")


def alert_roles_for(severity: str) -> list[int]:
    if severity == "Nghiêm trọng":
        return [0, 1, 2]
    return [0, 1]


def push_role_alert(label: str, context: str, severity: str) -> int:
    roles = alert_roles_for(severity)
    placeholders = ",".join("?" for _ in roles)
    with connect() as conn:
        recipients = conn.execute(
            f"SELECT id FROM Users WHERE status=1 AND role IN ({placeholders})",
            roles,
        ).fetchall()
        for recipient in recipients:
            conn.execute(
                """
                INSERT INTO System_Requests (user_id, loai_yeu_cau, noi_dung, trang_thai)
                VALUES (?, ?, ?, 3)
                """,
                (
                    recipient["id"],
                    "Cảnh báo AI",
                    f"{severity} - {context}: {label}",
                ),
            )
        conn.commit()
        return len(recipients)
