from src.database_query.auth import connect


def list_cameras(room_id: int | None = None):
    if room_id is None:
        query = "SELECT * FROM Cameras WHERE COALESCE(is_deleted, 0)=0"
        params: tuple[object, ...] = ()
    else:
        query = "SELECT * FROM Cameras WHERE room_id=? AND COALESCE(is_deleted, 0)=0"
        params = (room_id,)
    with connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def list_cameras_with_location(room_id: int | None = None):
    params: tuple[object, ...] = ()
    where = ""
    if room_id is not None:
        where = "WHERE c.room_id=? AND COALESCE(c.is_deleted, 0)=0"
        params = (room_id,)
    else:
        where = "WHERE COALESCE(c.is_deleted, 0)=0"
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT c.*, r.ten_phong, b.ten_toa, b.id AS building_id
                FROM Cameras c
                LEFT JOIN Rooms r ON r.id = c.room_id
                LEFT JOIN Buildings b ON b.id = r.building_id
                {where}
                ORDER BY b.ten_toa, r.ten_phong, c.vi_tri_goc
                """,
                params,
            ).fetchall()
        ]


def get_camera(camera_id: int):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT c.*, r.ten_phong, b.ten_toa, b.id AS building_id
            FROM Cameras c
            LEFT JOIN Rooms r ON r.id = c.room_id
            LEFT JOIN Buildings b ON b.id = r.building_id
            WHERE c.id=?
            """,
            (camera_id,),
        ).fetchone()
        return dict(row) if row else None


def add_camera(room_id: int, vi_tri_goc: str, video_source: str, status: int = 1) -> int:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO Cameras (room_id, vi_tri_goc, video_source, status) VALUES (?, ?, ?, ?)",
            (room_id, vi_tri_goc, video_source, status),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_camera_status(camera_id: int, status: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Cameras SET status=? WHERE id=?", (status, camera_id))
        conn.commit()


def update_camera(camera_id: int, room_id: int, vi_tri_goc: str, video_source: str, status: int = 1) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE Cameras
            SET room_id=?, vi_tri_goc=?, video_source=?, status=?
            WHERE id=?
            """,
            (room_id, vi_tri_goc, video_source, status, camera_id),
        )
        conn.commit()


def delete_camera(camera_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Cameras SET is_deleted=1, status=0 WHERE id=?", (camera_id,))
        conn.commit()


def camera_is_used(camera_id: int) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM Violation_Logs WHERE camera_id=? LIMIT 1", (int(camera_id),)).fetchone()
        return row is not None
