import sqlite3

def get_user_by_email(self, email):
    conn = sqlite3.connect("eduwatch.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, email, password, role
        FROM Users
        WHERE email = ?
    """, (email,))

    user = cursor.fetchone()

    conn.close()

    return user

