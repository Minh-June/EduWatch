from datetime import date, time
from typing import Any

try:
    import streamlit as st
except Exception:  # pragma: no cover - lets this service be imported outside Streamlit.
    st = None

from src.database_query.auth import connect
from src.database_query.logs import confirm_violation as _confirm_violation
from src.database_query.logs import mark_false_ai as _mark_false_ai


STATUS_MAP = {
    "Tất cả": "all",
    "Chờ xác nhận": 0,
    "Đã xác nhận": 1,
    "Đã duyệt": 1,
    "Báo sai AI": -1,
    "AI báo sai": -1,
}

MODE_MAP = {
    "Tất cả": "all",
    "Phòng thường": 0,
    "Phòng thi": 1,
}


def _build_datetime(value: date | None, clock: time | None = None, end: bool = False) -> str | None:
    if not isinstance(value, date):
        return None
    if isinstance(clock, time):
        clock_text = clock.strftime("%H:%M:%S")
    else:
        clock_text = "23:59:59" if end else "00:00:00"
    return f"{value.isoformat()} {clock_text}"


def _where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    query = str(filters.get("query") or "").strip()
    if query:
        keyword = f"%{query}%"
        clauses.append(
            """
            (
                CAST(v.id AS TEXT) LIKE ?
                OR v.loai_vi_pham LIKE ?
                OR c.vi_tri_goc LIKE ?
                OR r.ten_phong LIKE ?
                OR b.ten_toa LIKE ?
            )
            """
        )
        params.extend([keyword, keyword, keyword, keyword, keyword])

    for key, column in {
        "building_id": "b.id",
        "room_id": "r.id",
        "camera_id": "c.id",
    }.items():
        value = filters.get(key)
        if value not in (None, "", "all"):
            clauses.append(f"{column}=?")
            params.append(int(value))

    mode = filters.get("mode", "all")
    if mode != "all":
        clauses.append("v.mode=?")
        params.append(int(mode))

    status = filters.get("status", "all")
    if status != "all":
        clauses.append("COALESCE(v.is_confirmed, 0)=?")
        params.append(int(status))

    violation_type = filters.get("violation_type", "all")
    if violation_type != "all":
        clauses.append("v.loai_vi_pham=?")
        params.append(str(violation_type))

    if filters.get("start_at"):
        clauses.append("COALESCE(v.created_at, v.thoi_gian) >= ?")
        params.append(filters["start_at"])

    if filters.get("end_at"):
        clauses.append("COALESCE(v.created_at, v.thoi_gian) <= ?")
        params.append(filters["end_at"])

    if filters.get("min_confidence") not in (None, "", 0, 0.0):
        clauses.append("COALESCE(v.confidence, 0) >= ?")
        params.append(float(filters["min_confidence"]))

    if filters.get("max_confidence") not in (None, ""):
        clauses.append("COALESCE(v.confidence, 0) <= ?")
        params.append(float(filters["max_confidence"]))

    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", params)


def database_has_violation_logs() -> bool:
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM Violation_Logs LIMIT 1").fetchone()
        return row is not None


def latest_violation_date() -> date | None:
    """Return the newest real log date for useful initial filters."""
    with connect() as conn:
        row = conn.execute(
            "SELECT MAX(COALESCE(created_at, thoi_gian)) AS latest FROM Violation_Logs"
        ).fetchone()
    raw = (dict(row) if row else {}).get("latest")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def sample_violation_logs() -> list[dict[str, Any]]:
    return [
        {
            "id": "sample-1",
            "camera_id": None,
            "loai_vi_pham": "Sử dụng điện thoại",
            "thoi_gian": "2026-07-08 08:20:00",
            "created_at": "2026-07-08 08:20:00",
            "image_path": "",
            "confidence": 0.94,
            "is_confirmed": 0,
            "mode": 0,
            "teacher_note": "Dữ liệu mẫu fallback khi database chưa có log.",
            "vi_tri_goc": "Camera cửa lớp",
            "ten_phong": "P.101",
            "ten_toa": "Nhà A",
            "is_sample": True,
        },
        {
            "id": "sample-2",
            "camera_id": None,
            "loai_vi_pham": "Ngủ gật",
            "thoi_gian": "2026-07-08 09:05:00",
            "created_at": "2026-07-08 09:05:00",
            "image_path": "",
            "confidence": 0.87,
            "is_confirmed": 1,
            "mode": 1,
            "teacher_note": "Dữ liệu mẫu fallback khi database chưa có log.",
            "vi_tri_goc": "Camera cuối phòng",
            "ten_phong": "P.204",
            "ten_toa": "Nhà B",
            "is_sample": True,
        },
    ]


def list_violation_logs(filters: dict[str, Any], limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    where, params = _where(filters)
    params.extend([int(limit), int(offset)])
    with connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT v.*, c.vi_tri_goc, r.ten_phong, b.ten_toa
                FROM Violation_Logs v
                LEFT JOIN Cameras c ON c.id = v.camera_id
                LEFT JOIN Rooms r ON r.id = c.room_id
                LEFT JOIN Buildings b ON b.id = r.building_id
                {where}
                ORDER BY COALESCE(v.created_at, v.thoi_gian) DESC, v.id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        ]
    return rows


def count_violation_logs(filters: dict[str, Any]) -> int:
    where, params = _where(filters)
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM Violation_Logs v
            LEFT JOIN Cameras c ON c.id = v.camera_id
            LEFT JOIN Rooms r ON r.id = c.room_id
            LEFT JOIN Buildings b ON b.id = r.building_id
            {where}
            """,
            params,
        ).fetchone()
    return int((dict(row) if row else {}).get("total") or 0)


def summarize_violation_logs(filters: dict[str, Any]) -> dict[str, int]:
    """Return status totals with one parameterized aggregate query."""
    where, params = _where(filters)
    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN COALESCE(v.is_confirmed, 0) = 0 THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN COALESCE(v.is_confirmed, 0) = 1 THEN 1 ELSE 0 END) AS confirmed,
                SUM(CASE WHEN COALESCE(v.is_confirmed, 0) = -1 THEN 1 ELSE 0 END) AS false_ai
            FROM Violation_Logs v
            LEFT JOIN Cameras c ON c.id = v.camera_id
            LEFT JOIN Rooms r ON r.id = c.room_id
            LEFT JOIN Buildings b ON b.id = r.building_id
            {where}
            """,
            params,
        ).fetchone()
    values = dict(row) if row else {}
    return {key: int(values.get(key) or 0) for key in ("total", "pending", "confirmed", "false_ai")}


def get_violation_detail(violation_id: str | int) -> dict[str, Any] | None:
    if str(violation_id).startswith("sample-"):
        return next((row for row in sample_violation_logs() if row["id"] == str(violation_id)), None)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT v.*, c.vi_tri_goc, r.ten_phong, b.ten_toa
            FROM Violation_Logs v
            LEFT JOIN Cameras c ON c.id = v.camera_id
            LEFT JOIN Rooms r ON r.id = c.room_id
            LEFT JOIN Buildings b ON b.id = r.building_id
            WHERE v.id=?
            """,
            (int(violation_id),),
        ).fetchone()
    return dict(row) if row else None


def confirm_violation(violation_id: str | int, user_id: str | None = None) -> None:
    note = f"confirmed_by={user_id}" if user_id else ""
    _confirm_violation(int(violation_id), note)


def mark_false_alarm(violation_id: str | int, user_id: str | None = None) -> None:
    _mark_false_ai(int(violation_id))


def build_violation_filters_from_state() -> dict[str, Any]:
    state = st.session_state if st is not None else {}
    return {
        "query": state.get("logs_search_query", ""),
        "building_id": state.get("logs_selected_building_id"),
        "room_id": state.get("logs_selected_room_id"),
        "camera_id": state.get("logs_selected_camera_id"),
        "mode": MODE_MAP.get(state.get("logs_selected_mode", "Tất cả"), "all"),
        "status": STATUS_MAP.get(state.get("logs_selected_status", "Chờ xác nhận"), "all"),
        "violation_type": state.get("logs_selected_violation_type_value", "all"),
        "start_at": _build_datetime(
            state.get("logs_start_date"),
            state.get("logs_start_time"),
            end=False,
        ),
        "end_at": _build_datetime(
            state.get("logs_end_date"),
            state.get("logs_end_time"),
            end=True,
        ),
    }
