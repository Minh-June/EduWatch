from src.utils.database_connection import connect_database disconnect_database

def insertCamera(camera_name, camera_angle, camera_source):
    cursor = connect_database()
    cursor.execute("""
        INSERT INTO buildings (name, angle, source)
        VALUES (?,?,?)
    """, (
        camera_name, 
        camera_angle, 
        camera_source))
    disconnect_database()
       

