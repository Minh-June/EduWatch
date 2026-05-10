from fastapi import FastAPI
from fastapi import APIRouter
from src.backend.routers.auth_router import router as auth_router
from src.backend.routers.camera_router import router as camera_router
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(camera_router)

