import streamlit as st
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "eduwatch.db"

def getRooms():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    rooms_table = cursor.execute("""
        SELECT * FROM Rooms
    """)
    return rooms_table

def addRooms():
    cursor.execute("""
        INSERT INTO buildings (name)
        VALUES (?,?,?)
    """, (name))

def updateRooms():
    cursor.execute("""
        INSERT INTO buildings (name)
        VALUES (?,?,?)
    """, (name))
    conn.commit()
    conn.close()
