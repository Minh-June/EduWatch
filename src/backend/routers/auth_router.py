from fastapi import APIRouter

from src.backend.database.login_data import LoginData
from src.backend.services.login_services import login_service

router = APIRouter()

@router.post("/login")
def login(data: LoginData):
    return login_service(data)
