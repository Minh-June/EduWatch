from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data_model" / "eduwatch.db"

def connect_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    return cursor

def disconnect_database()
    conn.commit()
    conn.close()
