from src.utils.database_connection import connect_database
import sqlite3

def getRooms():
    cursor = connect_database()
    cursor.execute("""
        SELECT * FROM Rooms
    """)
    disconnect_database()
    

def insertRooms(name):    
    cursor = connect_database()
    cursor.execute("""
        INSERT INTO buildings (name)
        VALUES (?,?,?)
    """, (name))
    disconnect_database()

def updateRooms():
    disconnect_database()
    cursor.execute("""
        INSERT INTO buildings (name)
        VALUES (?,?,?)
    """, (name))
    disconnect_database()
