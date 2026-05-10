import hashlib
from src.backend.database.auth import get_user_by_email
from src.backend.database.login_data import LoginData

def login_service(data):
    user = get_user_by_email(data.email)
    if user is None:
        return {
            "success": False,
            "message": "User not found"
        }

    input_hash = hashlib.sha256(
        data.password.encode()
    ).hexdigest()

    stored_hash = user[2]
    
    if input_hash != stored_hash:
        return {
            "success": False,
            "message": "Wrong password"
        }
    return {
        "success": True,
        "email": user[1],
        "role": user[3]
    }
