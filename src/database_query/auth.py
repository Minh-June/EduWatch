import hashlib
import sqlite3
from typing import Any

from src.utils.config import DB_PATH


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_by_code(ma_nguoi_dung: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM Users WHERE ma_nguoi_dung=? AND status=1",
            (ma_nguoi_dung,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_login(login: str) -> dict[str, Any] | None:
    value = login.strip()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM Users
            WHERE status=1
              AND (ma_nguoi_dung=? OR LOWER(email)=? OR so_dien_thoai=?)
            """,
            (value, value.lower(), value),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM Users WHERE id=? AND status=1", (user_id,)).fetchone()
        return dict(row) if row else None


def verify_login(login: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_login(login)
    if not user or user["password"] != hash_password(password):
        return None
    return user


def create_user(data: dict[str, Any]) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Users
            (ma_nguoi_dung, password, role, ho_ten, ngay_sinh, gioi_tinh, email, so_dien_thoai, anh_dai_dien, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["ma_nguoi_dung"],
                hash_password(data["password"]),
                data.get("role", 1),
                data["ho_ten"],
                data.get("ngay_sinh"),
                data.get("gioi_tinh"),
                data.get("email"),
                data.get("so_dien_thoai"),
                data.get("anh_dai_dien", "data/avatars/vnua_logo.jpg"),
                data.get("status", 1),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def email_exists(email: str, exclude_user_id: int | None = None) -> bool:
    query = "SELECT id FROM Users WHERE email=?"
    params: list[Any] = [email]
    if exclude_user_id is not None:
        query += " AND id != ?"
        params.append(exclude_user_id)
    with connect() as conn:
        return conn.execute(query, params).fetchone() is not None


def phone_exists(phone: str, exclude_user_id: int | None = None) -> bool:
    query = "SELECT id FROM Users WHERE so_dien_thoai=?"
    params: list[Any] = [phone]
    if exclude_user_id is not None:
        query += " AND id != ?"
        params.append(exclude_user_id)
    with connect() as conn:
        return conn.execute(query, params).fetchone() is not None


def update_profile(user_id: int, email: str, so_dien_thoai: str, anh_dai_dien: str | None = None) -> dict[str, Any] | None:
    with connect() as conn:
        if anh_dai_dien:
            conn.execute(
                "UPDATE Users SET email=?, so_dien_thoai=?, anh_dai_dien=? WHERE id=?",
                (email, so_dien_thoai, anh_dai_dien, user_id),
            )
        else:
            conn.execute(
                "UPDATE Users SET email=?, so_dien_thoai=? WHERE id=?",
                (email, so_dien_thoai, user_id),
            )
        conn.commit()
    return get_user_by_id(user_id)


def update_profile_contact(user_id: int, so_dien_thoai: str, anh_dai_dien: str | None = None) -> dict[str, Any] | None:
    with connect() as conn:
        if anh_dai_dien:
            conn.execute(
                "UPDATE Users SET so_dien_thoai=?, anh_dai_dien=? WHERE id=?",
                (so_dien_thoai, anh_dai_dien, user_id),
            )
        else:
            conn.execute(
                "UPDATE Users SET so_dien_thoai=? WHERE id=?",
                (so_dien_thoai, user_id),
            )
        conn.commit()
    return get_user_by_id(user_id)


def update_password(user_id: int, new_password: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE Users SET password=? WHERE id=?", (hash_password(new_password), user_id))
        conn.commit()


def list_users() -> list[dict[str, Any]]:
    with connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, ma_nguoi_dung, ho_ten, ngay_sinh, gioi_tinh, email, so_dien_thoai, role, status, created_at
                FROM Users
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        ]


def update_user_role(user_id: int, role: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Users SET role=? WHERE id=?", (int(role), int(user_id)))
        conn.commit()


def soft_delete_user(user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE Users SET status=0 WHERE id=?", (int(user_id),))
        conn.commit()
