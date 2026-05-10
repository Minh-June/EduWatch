import streamlit as st
from pathlib import Path
import sqlite3

class Buildings
    def getBuildingName(name):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        building_name = cursor.execute("""
            SELECT name FROM Buildings
            WHERE ten_toa = ?
        """, (name,))
        conn.commit()
        conn.close()
        return building_name

    def addBuildings():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO buildings (name)
            VALUES (?)
        """, (name,))
        conn.commit()
        conn.close()

