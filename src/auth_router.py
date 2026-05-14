from fastapi import APIRouter
from pydantic import BaseModel


@router.post("/login")
def login():
    try:
        conn = sqlite3.connect("eduwatch.db")
	    cursor = conn.cursor()
        
        input_hash = hashlib.sha256(
            data.password.encode()
        ).hexdigest()        
        
        cursor.execute("""
            SELECT id, email, password, role FROM Users
            WHERE email = ?
        """, (data.email,))
        user = cursor.fetchone()
        conn.close()
        
        stored_hash = user[2]
        if input_hash == stored_hash:
            return {
                "success": True,
                "email": user[1]
                "role": user[3]
            }
        else:
            return {
                "success": False,
                "message": "Wrong password"
            }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

