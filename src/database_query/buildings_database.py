from src.utils.database_connection import connect_database, disconnect_database
import sqlite3

def getBuildingName(name):
    cursor = connect_database()
    building_name = cursor.execute("""
        SELECT name FROM Buildings
        WHERE ten_toa = ?
    """, (name,))
    disconnect_database()
    return building_name

def insertBuildings(name):
    cursor = connect_database()
    cursor.execute("""
        INSERT INTO buildings (name)
        VALUES (?)
    """, (name,))
    disconnect_database()

