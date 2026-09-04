from src.database_query.auth import connect


def list_buildings(include_deleted: bool = False):
    query = "SELECT * FROM Buildings" if include_deleted else "SELECT * FROM Buildings WHERE is_deleted=0 AND COALESCE(status, 1)=1"
    query += " ORDER BY ten_toa"
    with connect() as conn:
        return [dict(row) for row in conn.execute(query).fetchall()]


def add_building(ten_toa: str) -> int:
    with connect() as conn:
        cursor = conn.execute("INSERT INTO Buildings (ten_toa, status) VALUES (?, 1)", (ten_toa,))
        conn.commit()
        return int(cursor.lastrowid)


def update_building(building_id: int, ten_toa: str, status: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE Buildings SET ten_toa=?, status=? WHERE id=?",
            (ten_toa, int(status), int(building_id)),
        )
        conn.commit()


def set_building_status(building_id: int, status: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Buildings SET status=? WHERE id=?", (int(status), int(building_id)))
        conn.commit()


def building_is_used(building_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM Rooms r
            LEFT JOIN Cameras c ON c.room_id = r.id
            LEFT JOIN Violation_Logs v ON v.camera_id = c.id
            WHERE r.building_id=? AND (c.id IS NOT NULL OR v.id IS NOT NULL)
            LIMIT 1
            """,
            (int(building_id),),
        ).fetchone()
        return row is not None


def soft_delete_building(building_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Buildings SET is_deleted=1, status=0 WHERE id=?", (building_id,))
        conn.commit()
