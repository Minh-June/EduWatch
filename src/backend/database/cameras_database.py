import streamlit as st
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "eduwatch.db"
class Camera:
    camera_name
    camera_angle
    camera_source
    def addCamera(
                camera_name, 
                camera_angle, 
                camera_source):
        cursor.execute("""
            INSERT INTO buildings (name, angle, source)
            VALUES (?,?,?)
        """, (
            camera_name, 
            camera_angle, 
            camera_source))
       

