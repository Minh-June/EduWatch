import sqlite3

conn = sqlite3.connect("database.db")
conn.execute("PRAGMA foreign_keys = ON")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buildings_id INTEGER,
    name TEXT UNIQUE,
    FOREIGN KEY (buildings_id) REFERENCES buildings(id)
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS camera (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rooms_id INTEGER,
    name TEXT UNIQUE,
    angle TEXT UNIQUE,
    source TEXT,
    FOREIGN KEY (rooms_id) REFERENCES rooms(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS violation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER,
    name TEXT UNIQUE,
    source TEXT,
    confidence REAL,
    FOREIGN KEY (camera_id) REFERENCES camera(id)
)
""")

conn.commit()
conn.close()
