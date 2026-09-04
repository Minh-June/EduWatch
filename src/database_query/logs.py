from src.database_query.auth import connect


def list_violation_logs(
    include_false_ai: bool = False,
    room_id: int | None = None,
    camera_id: int | None = None,
    mode: int | None = None,
    limit: int = 100,
):
    clauses = []
    params: list[object] = []
    if not include_false_ai:
        clauses.append("v.is_confirmed != -1")
    if room_id is not None:
        clauses.append("c.room_id=?")
        params.append(room_id)
    if camera_id is not None:
        clauses.append("v.camera_id=?")
        params.append(camera_id)
    if mode is not None:
        clauses.append("v.mode=?")
        params.append(mode)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT v.*, c.vi_tri_goc, r.ten_phong, b.ten_toa
                FROM Violation_Logs v
                LEFT JOIN Cameras c ON c.id = v.camera_id
                LEFT JOIN Rooms r ON r.id = c.room_id
                LEFT JOIN Buildings b ON b.id = r.building_id
                {where}
                ORDER BY v.created_at DESC, v.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        ]


def create_violation_log(
    camera_id: int,
    loai_vi_pham: str,
    thoi_gian: str,
    image_path: str,
    confidence: float,
    mode: int,
) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Violation_Logs
            (camera_id, loai_vi_pham, thoi_gian, image_path, confidence, is_confirmed, mode)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (camera_id, loai_vi_pham, thoi_gian, image_path, confidence, mode),
        )
        conn.commit()
        return int(cursor.lastrowid)


def confirm_violation(log_id: int, teacher_note: str = "") -> None:
    with connect() as conn:
        conn.execute("UPDATE Violation_Logs SET is_confirmed=1, teacher_note=? WHERE id=?", (teacher_note, log_id))
        conn.commit()


def mark_false_ai(log_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Violation_Logs SET is_confirmed=-1 WHERE id=?", (log_id,))
        conn.commit()


def delete_violation_log(log_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM Violation_Logs WHERE id=?", (log_id,))
        conn.commit()
