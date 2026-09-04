from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "eduwatch.db"
CAPTURE_DIR = DATA_DIR / "captures"
VIDEO_DIR = DATA_DIR / "video"
AVATAR_DIR = DATA_DIR / "avatars"
AI_MODEL_DIR = BASE_DIR / "AI_model"
YOLO_MODEL_PATH = AI_MODEL_DIR / "yolo_eduwatch.pt"
BRAND_GREEN = "#37BD74"

