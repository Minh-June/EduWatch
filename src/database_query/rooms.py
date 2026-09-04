from src.database_query.auth import connect


def list_rooms(building_id: int | None = None, include_deleted: bool = False):
    clauses = []
    params: list[object] = []
    if building_id is not None:
        clauses.append("building_id=?")
        params.append(building_id)
    if not include_deleted:
        clauses.append("is_deleted=0")
        clauses.append("COALESCE(status, 1)=1")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM Rooms{where} ORDER BY ten_phong", params).fetchall()]


def get_room(room_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM Rooms WHERE id=?", (room_id,)).fetchone()
        return dict(row) if row else None


def add_room(building_id: int, ten_phong: str) -> int:
    with connect() as conn:
        cursor = conn.execute("INSERT INTO Rooms (building_id, ten_phong, status) VALUES (?, ?, 1)", (building_id, ten_phong))
        conn.commit()
        return int(cursor.lastrowid)


def update_room(room_id: int, building_id: int, ten_phong: str, status: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE Rooms SET building_id=?, ten_phong=?, status=? WHERE id=?",
            (int(building_id), ten_phong, int(status), int(room_id)),
        )
        conn.commit()


def set_room_status(room_id: int, status: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Rooms SET status=? WHERE id=?", (int(status), int(room_id)))
        conn.commit()


def room_is_used(room_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM Cameras c
            LEFT JOIN Violation_Logs v ON v.camera_id = c.id
            WHERE c.room_id=? AND (c.id IS NOT NULL OR v.id IS NOT NULL)
            LIMIT 1
            """,
            (int(room_id),),
        ).fetchone()
        return row is not None


def soft_delete_room(room_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Rooms SET is_deleted=1, status=0 WHERE id=?", (room_id,))
        conn.commit()


def update_room_monitor_mode(room_id: int, monitor_mode: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Rooms SET monitor_mode=? WHERE id=?", (int(monitor_mode), room_id))
        conn.commit()
