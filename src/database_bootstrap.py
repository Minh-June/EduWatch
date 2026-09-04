import hashlib
import sqlite3
from pathlib import Path

from src.utils.config import AI_MODEL_DIR, DATA_DIR, DB_PATH


ROLE_ADMIN = 0
ROLE_TEACHER = 1
ROLE_GUARD = 2

ROLES = {
    ROLE_ADMIN: "Admin",
    ROLE_TEACHER: "Giảng viên/Giám thị",
    ROLE_GUARD: "Bảo vệ/Kỹ thuật",
}

CAMERA_POSITIONS = [
    "Cửa chính",
    "Bàn giáo viên",
    "Cuối lớp",
    "Cửa phụ",
    "Toàn cảnh 360/Fish-eye",
]
BUILDINGS = [
    "Giảng đường Nguyễn Đăng",
    "Giảng đường A",
    "Giảng đường B",
    "Giảng đường E",
    "Tòa nhà trung tâm",
]
ROOMS = ["ND.202", "ND.206", "P.101", "A.204", "B.301"]
VIOLATION_TYPES = [
    ("Ngủ gật", 0, "Trung bình"),
    ("Cúi người sâu", 0, "Nghiêm trọng"),
    ("Rời vị trí", 0, "Nghiêm trọng"),
    ("Sử dụng điện thoại", 0, "Nghiêm trọng"),
    ("Quay bài/Trao đổi", 0, "Nghiêm trọng"),
    ("Đứng dậy", 0, "Trung bình"),
    ("Đọc tài liệu", 0, "Nghiêm trọng"),
    ("Di chuyển", 0, "Trung bình"),
    ("Ngủ gật", 1, "Nghiêm trọng"),
    ("Cúi người sâu", 1, "Nghiêm trọng"),
    ("Rời vị trí", 1, "Nghiêm trọng"),
    ("Sử dụng điện thoại", 1, "Nghiêm trọng"),
    ("Quay bài/Trao đổi", 1, "Nghiêm trọng"),
    ("Đứng dậy", 1, "Nghiêm trọng"),
    ("Đọc tài liệu", 1, "Nghiêm trọng"),
    ("Di chuyển", 1, "Nghiêm trọng"),
]
SAMPLE_VIOLATIONS = [
    ("VNUA-2901", "Sử dụng điện thoại", "2024-05-24 10:45:00", 0.94, 1),
    ("VNUA-2895", "Quay bài/Trao đổi", "2024-05-24 09:12:00", 0.82, 1),
    ("VNUA-2882", "Phá hoại cơ sở vật chất", "2024-05-24 08:30:00", 0.65, 0),
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for folder in ["avatars", "video", "captures", "reports"]:
        (DATA_DIR / folder).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    dataset_dir = AI_MODEL_DIR / "datasets" / "eduwatch_yolo"
    with connect() as conn:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ma_nguoi_dung TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role INTEGER NOT NULL,
                ho_ten TEXT NOT NULL,
                ngay_sinh TEXT,
                gioi_tinh TEXT,
                email TEXT UNIQUE,
                so_dien_thoai TEXT,
                anh_dai_dien TEXT DEFAULT 'data/avatars/vnua_logo.jpg',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status INTEGER DEFAULT 1
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ten_toa TEXT UNIQUE NOT NULL,
                is_deleted INTEGER DEFAULT 0,
                status INTEGER DEFAULT 1
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building_id INTEGER,
                ten_phong TEXT NOT NULL,
                monitor_mode INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                status INTEGER DEFAULT 1,
                FOREIGN KEY(building_id) REFERENCES Buildings(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER,
                vi_tri_goc TEXT NOT NULL,
                video_source TEXT,
                status INTEGER DEFAULT 1,
                is_deleted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(room_id) REFERENCES Rooms(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Violation_Logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER,
                loai_vi_pham TEXT NOT NULL,
                thoi_gian DATETIME,
                image_path TEXT,
                confidence REAL,
                is_confirmed INTEGER DEFAULT 0,
                mode INTEGER DEFAULT 0,
                teacher_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(camera_id) REFERENCES Cameras(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS System_Requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                loai_yeu_cau TEXT,
                noi_dung TEXT,
                trang_thai INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_until TEXT,
                FOREIGN KEY(user_id) REFERENCES Users(id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Violation_Types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ten_vi_pham TEXT NOT NULL,
                mode INTEGER NOT NULL,
                muc_do TEXT DEFAULT 'Trung bình',
                is_active INTEGER DEFAULT 1,
                UNIQUE(ten_vi_pham, mode)
            )
            """
        )
        c.execute("CREATE TABLE IF NOT EXISTS Subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, ten_mon TEXT UNIQUE, ma_mon TEXT, khoa_vien TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS Faculties (id INTEGER PRIMARY KEY AUTOINCREMENT, ten_khoa TEXT UNIQUE)")
        c.execute("CREATE TABLE IF NOT EXISTS Classes (id INTEGER PRIMARY KEY AUTOINCREMENT, ten_lop TEXT UNIQUE, faculty_id INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS Students (id INTEGER PRIMARY KEY AUTOINCREMENT, ma_sinh_vien TEXT UNIQUE, ho_ten TEXT, class_id INTEGER, faculty_id INTEGER)")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS Exam_Schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                room_id INTEGER,
                teacher_id INTEGER,
                exam_date TEXT,
                start_time TEXT,
                end_time TEXT,
                shift_name TEXT,
                schedule_type TEXT DEFAULT 'exam'
            )
            """
        )
        c.execute("CREATE TABLE IF NOT EXISTS Exam_Reports (id INTEGER PRIMARY KEY AUTOINCREMENT, report_code TEXT UNIQUE, schedule_id INTEGER, teacher_id INTEGER, pdf_path TEXT, excel_path TEXT, teacher_notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS AI_Models (id INTEGER PRIMARY KEY AUTOINCREMENT, model_name TEXT, model_type TEXT DEFAULT 'YOLO', model_path TEXT, dataset_path TEXT, accuracy REAL, map_score REAL, is_active INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS Training_Jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, job_name TEXT, model_type TEXT DEFAULT 'YOLO', dataset_path TEXT, target_classes TEXT, status TEXT DEFAULT 'Chờ huấn luyện', progress INTEGER DEFAULT 0, loss REAL, accuracy REAL, map_score REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS System_Settings (id INTEGER PRIMARY KEY AUTOINCREMENT, setting_key TEXT UNIQUE, setting_value TEXT)")

        def columns(table: str) -> set[str]:
            return {row["name"] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}

        def add_column(table: str, column: str, ddl: str) -> None:
            if column not in columns(table):
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

        add_column("Users", "ma_nguoi_dung", "TEXT")
        add_column("Users", "anh_dai_dien", "TEXT DEFAULT 'data/avatars/vnua_logo.jpg'")
        add_column("Users", "status", "INTEGER DEFAULT 1")
        add_column("Buildings", "is_deleted", "INTEGER DEFAULT 0")
        add_column("Buildings", "status", "INTEGER DEFAULT 1")
        add_column("Rooms", "building_id", "INTEGER")
        add_column("Rooms", "is_deleted", "INTEGER DEFAULT 0")
        add_column("Rooms", "status", "INTEGER DEFAULT 1")
        add_column("Rooms", "monitor_mode", "INTEGER DEFAULT 0")
        add_column("Cameras", "video_source", "TEXT")
        add_column("Cameras", "is_deleted", "INTEGER DEFAULT 0")
        add_column("Cameras", "created_at", "TIMESTAMP")
        add_column("Cameras", "updated_at", "TIMESTAMP")
        add_column("Violation_Logs", "camera_id", "INTEGER")
        add_column("Violation_Logs", "loai_vi_pham", "TEXT")
        add_column("Violation_Logs", "thoi_gian", "DATETIME")
        add_column("Violation_Logs", "image_path", "TEXT")
        add_column("Violation_Logs", "confidence", "REAL")
        add_column("Violation_Logs", "is_confirmed", "INTEGER DEFAULT 0")
        add_column("Violation_Logs", "mode", "INTEGER DEFAULT 0")
        add_column("Violation_Logs", "teacher_note", "TEXT")
        add_column("System_Requests", "approved_until", "TEXT")

        c.execute(
            """
            UPDATE Users
            SET anh_dai_dien='data/avatars/vnua_logo.jpg'
            WHERE anh_dai_dien IS NULL
               OR anh_dai_dien=''
               OR anh_dai_dien='data/avatars/default.png'
            """
        )
        if "ma_giang_vien" in columns("Users"):
            c.execute("UPDATE Users SET ma_nguoi_dung = ma_giang_vien WHERE ma_nguoi_dung IS NULL OR ma_nguoi_dung = ''")
        if "source_url" in columns("Cameras"):
            c.execute("UPDATE Cameras SET video_source = source_url WHERE video_source IS NULL OR video_source = ''")
        c.execute(
            """
            UPDATE Cameras
            SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
            """
        )

        users = [
            ("AD001", hash_password("admin123"), ROLE_ADMIN, "Admin VNUA", "admin@vnua.edu.vn", "0900000001"),
            ("GV123", hash_password("gv123"), ROLE_TEACHER, "Nguyễn Văn A", "gv123@vnua.edu.vn", "0900000002"),
            ("BV001", hash_password("bv123"), ROLE_GUARD, "Bảo vệ Nguyễn Đăng", "bv001@vnua.edu.vn", "0900000003"),
        ]
        c.executemany(
            """
            INSERT OR IGNORE INTO Users
            (ma_nguoi_dung, password, role, ho_ten, email, so_dien_thoai)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            users,
        )

        for building in BUILDINGS:
            if not c.execute("SELECT id FROM Buildings WHERE ten_toa=?", (building,)).fetchone():
                c.execute("INSERT INTO Buildings (ten_toa, status) VALUES (?, 1)", (building,))

        for building in c.execute("SELECT id, ten_toa FROM Buildings WHERE COALESCE(is_deleted, 0)=0").fetchall():
            for room_name in ROOMS[:2]:
                exists = c.execute(
                    "SELECT id FROM Rooms WHERE building_id=? AND ten_phong=?",
                    (building["id"], room_name),
                ).fetchone()
                if not exists:
                    c.execute(
                        "INSERT INTO Rooms (building_id, ten_phong, status) VALUES (?, ?, 1)",
                        (building["id"], room_name),
                    )

        for room in c.execute("SELECT id, ten_phong FROM Rooms").fetchall():
            for index, position in enumerate(CAMERA_POSITIONS, start=1):
                source = (
                    f"rtsp://vnua.local/{room['ten_phong']}/cam{index}"
                    if index <= 4
                    else f"data/video/{room['ten_phong']}_360.mp4"
                )
                exists = c.execute(
                    "SELECT id FROM Cameras WHERE room_id=? AND vi_tri_goc=?",
                    (room["id"], position),
                ).fetchone()
                if not exists:
                    c.execute(
                        """
                        INSERT INTO Cameras (room_id, vi_tri_goc, video_source, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (room["id"], position, source, 1 if index != 4 else 0),
                    )

        c.executemany(
            "INSERT OR IGNORE INTO Violation_Types (ten_vi_pham, mode, muc_do) VALUES (?, ?, ?)",
            VIOLATION_TYPES,
        )

        first_camera = c.execute("SELECT id FROM Cameras LIMIT 1").fetchone()
        if first_camera:
            for code, name, time_text, confidence, mode in SAMPLE_VIOLATIONS:
                exists = c.execute(
                    "SELECT id FROM Violation_Logs WHERE loai_vi_pham=? AND thoi_gian=?",
                    (name, time_text),
                ).fetchone()
                if not exists:
                    c.execute(
                        """
                        INSERT INTO Violation_Logs
                        (camera_id, loai_vi_pham, thoi_gian, image_path, confidence, is_confirmed, mode)
                        VALUES (?, ?, ?, ?, ?, 0, ?)
                        """,
                        (first_camera["id"], name, time_text, f"data/captures/{code}.jpg", confidence, mode),
                    )

        c.execute(
            """
            INSERT OR IGNORE INTO AI_Models
            (model_name, model_type, model_path, dataset_path, accuracy, map_score, is_active)
            VALUES ('YOLO EduWatch v1', 'YOLO', 'AI_model/yolo_eduwatch.pt', ?, 0.985, 0.921, 1)
            """,
            (str(dataset_dir),),
        )
        conn.commit()


def default_page_for_role(role: int) -> str:
    if int(role) == ROLE_ADMIN:
        return "reports"
    if int(role) == ROLE_GUARD:
        return "security"
    return "monitoring"


def role_name(role: int) -> str:
    return ROLES.get(int(role), ROLES[ROLE_TEACHER])
