import io
import base64
import logging
import math
import secrets
import re
import uuid
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

LOGGER = logging.getLogger(__name__)

from src.components.camera_dblclick import create_camera_dblclick_bridge
from src.database_bootstrap import (
    ROLE_ADMIN,
    ROLE_GUARD,
    ROLE_TEACHER,
    connect as db_connect,
    default_page_for_role,
    ensure_schema,
    role_name,
)
from src.database_query.auth import (
    create_user,
    email_exists,
    get_user_by_login,
    get_user_by_code,
    get_user_by_id,
    list_users,
    phone_exists,
    soft_delete_user,
    update_password,
    update_profile_contact,
    update_user_role,
    verify_login,
)
from src.database_query.buildings import (
    add_building,
    list_buildings,
    set_building_status,
    soft_delete_building,
    update_building,
)
from src.database_query.cameras import (
    add_camera,
    camera_is_used,
    delete_camera,
    get_camera,
    list_cameras,
    update_camera,
    update_camera_status,
)
from src.database_query.logs import confirm_violation, mark_false_ai
from src.database_query.rooms import (
    add_room,
    get_room,
    list_rooms,
    set_room_status,
    soft_delete_room,
    update_room,
    update_room_monitor_mode,
)
from src.services.violation_log_service import (
    confirm_violation as service_confirm_violation,
    count_violation_logs as service_count_violation_logs,
    get_violation_detail as service_get_violation_detail,
    list_violation_logs as service_list_violation_logs,
    summarize_violation_logs as service_summarize_violation_logs,
    mark_false_alarm as service_mark_false_alarm,
)
from src.utils.config import AVATAR_DIR, BASE_DIR, DATA_DIR


camera_dblclick_bridge = create_camera_dblclick_bridge()

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def to_vietnam_time(value: object) -> datetime | None:
    """Normalize database/display timestamps without double-adding seven hours.

    EduWatch currently writes naive timestamps with ``datetime.now()``. Those
    values are therefore interpreted as Vietnam local time; aware values are
    converted normally and ISO values ending in Z are treated as UTC.
    """
    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else None
    if parsed is None:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=VIETNAM_TZ)
    return parsed.astimezone(VIETNAM_TZ)


PRIMARY = "#37BD74"
PRIMARY_HOVER = "#2e9f62"
DANGER = "#e8286b"
DANGER_HOVER = "#ad1457"
SURFACE = "#f6f8fb"
TEXT = "#16211c"
DEFAULT_AVATAR = DATA_DIR / "avatars" / "vnua_logo.jpg"
LOGIN_COVER_CANDIDATES = [
    DATA_DIR / "avatars" / "ảnh bìa đăng nhập.jpg",
    DATA_DIR / "avatars" / "bìa đăng nhập.jpg",
]
AUTH_LOGO_SVG = """
<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">
    <path fill="currentColor" d="M32 8 4 22l28 14 23-11.5V42h5V22L32 8Z"/>
    <path fill="currentColor" d="M17 33.5V44c0 4.8 6.7 9 15 9s15-4.2 15-9V33.5L32 41 17 33.5Z"/>
</svg>
"""
REPORT_DIR = DATA_DIR / "reports"
PAGE_ALIASES = {"dashboard": "monitoring", "admin": "reports", "schedule": "monitoring"}
PAGE_LABELS = {
    "monitoring": "Giám sát trực tiếp",
    "violations": "Nhật ký vi phạm",
    "reports": "Thống kê báo cáo",
    "buildings": "Quản lý tòa nhà/phòng/camera",
    "users": "Quản lý người dùng",
    "profile": "Hồ sơ cá nhân",
    "settings": "Hồ sơ cá nhân",
    "security": "Giám sát an ninh",
    "device-status": "Trạng thái thiết bị",
    "incidents": "Sự cố",
    "exam-report": "Báo cáo phòng thi",
}
PAGE_ICONS = {
    "monitoring": "🎥",
    "violations": "🕘",
    "reports": "📊",
    "buildings": "🏢",
    "users": "👥",
    "profile": "👤",
    "settings": "⚙️",
    "security": "🛡️",
    "device-status": "📡",
    "incidents": "🚨",
    "exam-report": "📝",
}


st.set_page_config(page_title="EduWatch VNUA", layout="wide", initial_sidebar_state="expanded")


def inject_global_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --ew-primary: {PRIMARY};
            --ew-primary-hover: {PRIMARY_HOVER};
            --ew-danger: {DANGER};
            --ew-surface: {SURFACE};
            --ew-text: {TEXT};
            --ew-line: #e5ecf2;
            --ew-soft: #eef8f2;
            --ew-soft-strong: #dff4e7;
            --ew-muted: #6d7a8b;
            --ew-shadow: 0 18px 40px rgba(18, 38, 63, 0.08);
        }}
        html, body, [class*="css"]  {{
            font-family: "Segoe UI", "Trebuchet MS", sans-serif;
            color: var(--ew-text);
        }}
        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(55,189,116,.12), transparent 24%),
                radial-gradient(circle at bottom right, rgba(55,189,116,.08), transparent 18%),
                linear-gradient(180deg, #fbfdfc 0%, var(--ew-surface) 100%);
        }}
        section[data-testid="stSidebar"] {{
            width: 280px !important;
            min-width: 280px !important;
            max-width: 280px !important;
            background: #eef8f1;
            border-right: 1px solid #dff2e6;
        }}
        section[data-testid="stSidebar"] > div:first-child {{
            width: 280px !important;
            padding: 64px 30px 28px !important;
            background: #eef8f1;
        }}
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
            gap: 0;
        }}
        .block-container {{
            padding-top: 1.1rem;
            padding-bottom: 2.2rem;
            max-width: 1440px;
        }}
        .stApp header[data-testid="stHeader"] {{
            background: transparent;
        }}
        [data-testid="collapsedControl"] {{
            margin-top: .8rem;
        }}
        .ew-page-header {{
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:1rem;
            margin-bottom: 1.2rem;
        }}
        .ew-title {{
            font-size: 3.15rem;
            font-weight: 800;
            letter-spacing: -.02em;
            line-height: 1.02;
            margin-bottom: .25rem;
        }}
        .ew-subtitle {{
            color: var(--ew-muted);
            margin-bottom: 0;
            max-width: 860px;
            font-size: 1.07rem;
        }}
        .ew-user-chip {{
            background:#fff;
            border:1px solid var(--ew-line);
            border-radius:16px;
            padding:.9rem 1rem;
            box-shadow: var(--ew-shadow);
            min-width: 220px;
        }}
        .ew-user-chip strong {{
            display:block;
            font-size:1rem;
            margin-bottom:.2rem;
        }}
        .ew-user-chip span {{
            color:var(--ew-muted);
            font-size:.92rem;
        }}
        .ew-card {{
            background: rgba(255,255,255,.98);
            border: 1px solid var(--ew-line);
            border-radius: 16px;
            padding: 1.15rem 1.25rem;
            box-shadow: var(--ew-shadow);
        }}
        .ew-metric {{
            background: #fff;
            border: 1px solid var(--ew-line);
            border-radius: 16px;
            padding: 1.1rem 1.15rem;
            min-height: 108px;
            box-shadow: var(--ew-shadow);
        }}
        .ew-metric-label {{
            color: var(--ew-muted);
            font-size: .82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .04em;
        }}
        .ew-metric-value {{
            color: var(--ew-primary);
            font-size: 1.9rem;
            font-weight: 800;
            margin-top: .35rem;
            line-height: 1.15;
        }}
        .ew-status-ok, .ew-status-bad, .ew-status-warn {{
            display: inline-block;
            padding: .28rem .7rem;
            border-radius: 999px;
            font-size: .78rem;
            font-weight: 700;
        }}
        .ew-status-ok {{
            color: #12653a;
            background: #dff6e8;
        }}
        .ew-status-bad {{
            color: #9d174d;
            background: #ffe3ef;
        }}
        .ew-status-warn {{
            color: #92400e;
            background: #fff3d6;
        }}
        .stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div,
        .stDateInput [data-baseweb="input"] > div, .stTimeInput [data-baseweb="input"] > div {{
            border-radius: 14px !important;
            min-height: 48px !important;
            border: 1px solid #dfe6ee !important;
            background: #f2f5f8 !important;
            box-shadow: none !important;
        }}
        .stTextArea textarea {{
            min-height: 120px !important;
        }}
        .stTextInput label, .stTextArea label, .stSelectbox label, .stDateInput label, .stTimeInput label {{
            font-weight: 700 !important;
        }}
        body:not(:has(.locations-page)) .stButton > button, .stDownloadButton > button {{
            border-radius: 14px;
            border: 1px solid {PRIMARY};
            background: {PRIMARY};
            color: white;
            font-weight: 700;
            min-height: 44px;
            box-shadow: 0 8px 18px rgba(55,189,116,.26);
        }}
        body:not(:has(.locations-page)) .stButton > button:hover, .stDownloadButton > button:hover {{
            background: {PRIMARY_HOVER};
            border-color: {PRIMARY_HOVER};
            color: white;
        }}
        .ew-btn-danger + div button {{
            background: {DANGER} !important;
            border-color: {DANGER} !important;
            color: #fff !important;
            box-shadow: 0 8px 18px rgba(232,40,107,.24) !important;
        }}
        .ew-btn-danger + div button:hover {{
            background: {DANGER_HOVER} !important;
            border-color: {DANGER_HOVER} !important;
            color: #fff !important;
        }}
        .ew-btn-outline + div button {{
            background: #fff !important;
            border-color: {PRIMARY} !important;
            color: {PRIMARY} !important;
            box-shadow: none !important;
        }}
        .ew-btn-outline + div button:hover {{
            background: {PRIMARY} !important;
            border-color: {PRIMARY} !important;
            color: #fff !important;
        }}
        .ew-danger button {{
            background: {DANGER} !important;
            border-color: {DANGER} !important;
        }}
        .profile-page,
        .profile-main-card-marker,
        .profile-password-card-marker,
        .profile-upload-widget,
        .profile-save-button-marker,
        .profile-password-button-marker {{
            display: block;
            height: 0;
            overflow: hidden;
        }}
        body:has(.profile-page) [data-testid="stMainBlockContainer"] {{
            justify-content: flex-start !important;
            align-items: flex-start !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }}
        body:has(.profile-page) .block-container {{
            max-width: 960px !important;
            width: min(960px, calc(100vw - 360px)) !important;
            margin-left: 0 !important;
            margin-right: auto !important;
            padding: 40px 32px 80px 32px !important;
            align-self: flex-start !important;
            justify-self: start !important;
        }}
        .profile-title {{
            font-size: 42px;
            font-weight: 900;
            color: #17201b;
            line-height: 1.1;
            margin: 30px 0 0;
        }}
        .profile-subtitle {{
            color: #64748b;
            font-size: 16px;
            margin-top: 8px;
            margin-bottom: 32px;
        }}
        body:has(.profile-page) .profile-main-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-main-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-main-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.profile-page) .profile-password-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-password-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-password-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #fff;
            border: 0 !important;
            border-radius: 24px;
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
            padding: 34px;
            overflow: visible;
        }}
        body:has(.profile-page) .profile-password-card-marker + div,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-password-card-marker) + [data-testid="stElementContainer"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-password-card-marker) + [data-testid="element-container"] {{
            margin-top: 28px;
        }}
        body:has(.profile-page) .profile-main-card-marker + div,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-main-card-marker) + [data-testid="stElementContainer"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-main-card-marker) + [data-testid="element-container"],
        body:has(.profile-page) .profile-password-card-marker + div,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-password-card-marker) + [data-testid="stElementContainer"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-password-card-marker) + [data-testid="element-container"] {{
            max-width: 960px !important;
            margin-left: 0 !important;
            margin-right: auto !important;
        }}
        .profile-left {{
            text-align: center;
        }}
        .profile-avatar {{
            width: 124px;
            height: 124px;
            border-radius: 999px;
            object-fit: cover;
            border: 6px solid #e8f8ed;
            display: block;
            margin: 0 auto;
        }}
        .profile-name {{
            margin-top: 24px;
            font-size: 22px;
            font-weight: 900;
            color: #0f172a;
        }}
        .profile-code {{
            margin-top: 8px;
            color: #64748b;
            font-size: 14px;
        }}
        .profile-role-badge {{
            display: inline-block;
            margin-top: 16px;
            background: #37BD74;
            color: #fff;
            border-radius: 6px;
            padding: 3px 12px;
            font-size: 13px;
            font-weight: 800;
        }}
        .profile-upload-box {{
            margin-top: 20px;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 8px 18px rgba(15,23,42,0.16);
            text-align: left;
            background: #fff;
        }}
        .profile-upload-head {{
            background: #37BD74;
            color: #fff;
            padding: 10px 12px;
            font-weight: 800;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .profile-upload-plus {{
            font-size: 22px;
            line-height: 1;
            font-weight: 900;
        }}
        .profile-upload-progress {{
            color: rgba(255,255,255,.92);
            font-size: 12px;
            margin-top: 2px;
            font-weight: 600;
        }}
        body:has(.profile-page) .profile-upload-widget + div [data-testid="stFileUploader"],
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-upload-widget) + [data-testid="stElementContainer"] [data-testid="stFileUploader"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-upload-widget) + [data-testid="element-container"] [data-testid="stFileUploader"] {{
            margin: 0;
            border-radius: 0 0 6px 6px;
            background: #fff;
            min-height: 72px;
            padding: 0;
        }}
        body:has(.profile-page) .profile-upload-widget + div [data-testid="stFileUploader"] label,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-upload-widget) + [data-testid="stElementContainer"] [data-testid="stFileUploader"] label,
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-upload-widget) + [data-testid="element-container"] [data-testid="stFileUploader"] label {{
            display: none !important;
        }}
        body:has(.profile-page) .profile-upload-widget + div [data-testid="stFileUploaderDropzone"],
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-upload-widget) + [data-testid="stElementContainer"] [data-testid="stFileUploaderDropzone"],
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-upload-widget) + [data-testid="element-container"] [data-testid="stFileUploaderDropzone"] {{
            border: 0 !important;
            background: #fff !important;
            min-height: 72px;
            padding: 10px 12px;
        }}
        .profile-field {{
            border: 1px dashed #cbd5e1;
            border-radius: 4px;
            padding: 12px 14px;
            margin-bottom: 14px;
            background: #fff;
        }}
        .profile-field-label {{
            color: #64748b;
            font-size: 14px;
        }}
        .profile-field-value {{
            color: #111827;
            font-size: 16px;
            margin-top: 4px;
            font-weight: 600;
        }}
        .profile-phone-label {{
            color: #64748b;
            font-size: 14px;
            margin: 0 0 6px;
        }}
        body:has(.profile-page) .profile-phone-field + div .stTextInput label {{
            display: none !important;
        }}
        body:has(.profile-page) .profile-phone-field + div .stTextInput input {{
            background: #fff !important;
            border: 1px dashed #cbd5e1 !important;
            border-radius: 4px !important;
            min-height: 52px !important;
            color: #111827 !important;
            font-size: 16px !important;
            box-shadow: none !important;
        }}
        .profile-section-title {{
            font-size: 24px;
            font-weight: 900;
            color: #111827;
            margin-bottom: 22px;
        }}
        body:has(.profile-page) .profile-save-button-marker + div button,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-save-button-marker) + [data-testid="stElementContainer"] button,
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-save-button-marker) + [data-testid="element-container"] button,
        body:has(.profile-page) .profile-password-button-marker + div .stFormSubmitButton > button,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-password-button-marker) + [data-testid="stElementContainer"] .stFormSubmitButton > button,
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-password-button-marker) + [data-testid="element-container"] .stFormSubmitButton > button {{
            width: auto !important;
            min-width: 178px !important;
            background: #37BD74 !important;
            border-color: #37BD74 !important;
            color: #fff !important;
            border-radius: 8px !important;
            font-weight: 800 !important;
            padding: 10px 18px !important;
            box-shadow: 0 8px 18px rgba(55,189,116,.24) !important;
        }}
        body:has(.profile-page) .profile-save-button-marker + div button:hover,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-save-button-marker) + [data-testid="stElementContainer"] button:hover,
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-save-button-marker) + [data-testid="element-container"] button:hover,
        body:has(.profile-page) .profile-password-button-marker + div .stFormSubmitButton > button:hover,
        body:has(.profile-page) [data-testid="stElementContainer"]:has(.profile-password-button-marker) + [data-testid="stElementContainer"] .stFormSubmitButton > button:hover,
        body:has(.profile-page) [data-testid="element-container"]:has(.profile-password-button-marker) + [data-testid="element-container"] .stFormSubmitButton > button:hover {{
            background: #2e9f62 !important;
            border-color: #2e9f62 !important;
            color: #fff !important;
        }}
        .reports-page,
        .reports-search-marker,
        .reports-filter-card-marker,
        .reports-filter-date-marker,
        .reports-filter-button-marker,
        .reports-pdf-button-marker,
        .reports-excel-button-marker {{
            display: block;
            height: 0;
            overflow: hidden;
        }}
        body:has(.reports-page) [data-testid="stMainBlockContainer"] {{
            justify-content: flex-start !important;
            align-items: flex-start !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }}
        body:has(.reports-page) .block-container {{
            max-width: 1120px !important;
            width: min(1120px, calc(100vw - 352px)) !important;
            margin-left: 0 !important;
            margin-right: auto !important;
            padding: 30px 28px 72px 28px !important;
            align-self: flex-start !important;
            justify-self: start !important;
        }}
        body:has(.reports-page) .reports-search-marker + div .stTextInput label,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-marker) + [data-testid="stElementContainer"] .stTextInput label,
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-search-marker) + [data-testid="element-container"] .stTextInput label {{
            display: none !important;
        }}
        body:has(.reports-page) .reports-search-marker + div .stTextInput input,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-search-marker) + [data-testid="element-container"] .stTextInput input {{
            height: 48px !important;
            min-height: 48px !important;
            border-radius: 999px !important;
            background: #fff !important;
            border: 1px solid #e4ece7 !important;
            box-shadow: 0 8px 24px rgba(15,23,42,.05) !important;
            padding-left: 20px !important;
            color: #334155 !important;
        }}
        .reports-top-nav {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 22px;
            min-height: 48px;
            color: #64748b;
            font-size: 15px;
            font-weight: 800;
        }}
        .reports-tab-active {{
            color: #37BD74;
            border-bottom: 3px solid #37BD74;
            padding-bottom: 9px;
        }}
        .reports-system-badge {{
            background: #e8f8ee;
            color: #37BD74;
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 900;
        }}
        .reports-icon {{
            width: 38px;
            height: 38px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #fff;
            color: #64748b;
            box-shadow: 0 8px 22px rgba(15,23,42,.05);
        }}
        .reports-title {{
            color: #37BD74;
            font-size: 42px;
            line-height: 1.1;
            font-weight: 900;
            margin: 24px 0 22px;
        }}
        .reports-actions {{
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 12px;
            margin-top: 20px;
        }}
        .reports-summary-card {{
            background: #fff;
            border-radius: 20px;
            padding: 28px 30px;
            min-height: 128px;
            box-shadow: 0 12px 34px rgba(15,23,42,.055);
            border: 1px solid #eef3ef;
        }}
        .reports-summary-label {{
            color: #8ca09a;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
        }}
        .reports-summary-value {{
            color: #37BD74;
            font-size: 28px;
            font-weight: 900;
            margin-top: 16px;
            line-height: 1.18;
        }}
        body:has(.reports-page) .reports-filter-card-marker + div,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-card-marker) + [data-testid="stElementContainer"],
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-filter-card-marker) + [data-testid="element-container"] {{
            margin-top: 22px;
        }}
        body:has(.reports-page) .reports-filter-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-filter-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #fff;
            border: 1px solid #eef3ef;
            border-radius: 20px;
            padding: 22px 24px;
            box-shadow: 0 12px 34px rgba(15,23,42,.05);
        }}
        body:has(.reports-page) .reports-filter-date-marker + div .stDateInput label,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-date-marker) + [data-testid="stElementContainer"] .stDateInput label,
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-filter-date-marker) + [data-testid="element-container"] .stDateInput label {{
            display: none !important;
        }}
        body:has(.reports-page) .reports-filter-date-marker + div .stDateInput [data-baseweb="input"] > div,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-date-marker) + [data-testid="stElementContainer"] .stDateInput [data-baseweb="input"] > div,
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-filter-date-marker) + [data-testid="element-container"] .stDateInput [data-baseweb="input"] > div {{
            background: #fff !important;
            border: 1px solid #e1e8e3 !important;
            border-radius: 12px !important;
            min-height: 48px !important;
            box-shadow: none !important;
        }}
        body:has(.reports-page) .reports-filter-button-marker + div button,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-button-marker) + [data-testid="stElementContainer"] button,
        body:has(.reports-page) [data-testid="element-container"]:has(.reports-filter-button-marker) + [data-testid="element-container"] button {{
            min-height: 48px !important;
            border-radius: 10px !important;
            background: #37BD74 !important;
            border-color: #37BD74 !important;
            color: #fff !important;
            font-weight: 900 !important;
            padding: 10px 22px !important;
            box-shadow: 0 10px 22px rgba(55,189,116,.22) !important;
        }}
        body:has(.reports-page) .reports-pdf-button-marker + div .stDownloadButton > button,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-pdf-button-marker) + [data-testid="stElementContainer"] .stDownloadButton > button {{
            min-height: 44px !important;
            border-radius: 10px !important;
            background: #37BD74 !important;
            border-color: #37BD74 !important;
            color: #fff !important;
            font-weight: 900 !important;
            padding: 9px 18px !important;
            box-shadow: 0 10px 22px rgba(55,189,116,.18) !important;
        }}
        body:has(.reports-page) .reports-excel-button-marker + div .stDownloadButton > button,
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-excel-button-marker) + [data-testid="stElementContainer"] .stDownloadButton > button {{
            min-height: 44px !important;
            border-radius: 10px !important;
            background: #fff !important;
            border-color: #37BD74 !important;
            color: #37BD74 !important;
            font-weight: 900 !important;
            padding: 9px 18px !important;
            box-shadow: none !important;
        }}
        .reports-table-card {{
            margin-top: 22px;
            background: #fff;
            border-radius: 22px;
            overflow: hidden;
            border: 1px solid #eef3ef;
            box-shadow: 0 12px 34px rgba(15,23,42,.055);
        }}
        .reports-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 15px;
        }}
        .reports-table th {{
            background: #f6faf7;
            color: #17201b;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: .03em;
            text-align: left;
            padding: 18px 22px;
            border-bottom: 1px solid #e8efe9;
        }}
        .reports-table td {{
            color: #334155;
            font-weight: 700;
            padding: 18px 22px;
            border-bottom: 1px solid #eef3ef;
        }}
        .reports-table tr:last-child td {{
            border-bottom: 0;
        }}
        .sidebar-brand {{
            color: #2f9e44 !important;
            font-size: 32px !important;
            font-weight: 900 !important;
            line-height: 1.12 !important;
            margin-bottom: 10px !important;
        }}
        .sidebar-role-label {{
            color: #94a3b8 !important;
            font-size: 14px !important;
            font-weight: 900 !important;
            letter-spacing: .10em !important;
            text-transform: uppercase !important;
            margin-bottom: 112px !important;
        }}
        .sidebar-menu-spacer {{
            height: 0;
        }}
        .sidebar-nav-marker,
        .sidebar-logout-marker {{
            display: block;
            height: 0;
            overflow: hidden;
            margin: 0;
            padding: 0;
        }}
        [data-testid="stSidebar"] .stButton > button {{
            background: transparent !important;
            border: 1px solid transparent !important;
            box-shadow: none !important;
            color: #334155 !important;
            min-height: 62px !important;
            justify-content: flex-start !important;
            padding: 16px 18px !important;
            border-radius: 18px !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            text-align: left !important;
            white-space: nowrap !important;
        }}
        [data-testid="stSidebar"] .stButton > button p {{
            color: inherit !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            white-space: nowrap !important;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{
            background: #e6f6ec !important;
            border-color: #d7f0df !important;
            color: #334155 !important;
        }}
        .sidebar-nav-marker + div[data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"],
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-nav-marker) + div[data-testid="stButton"],
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] {{
            margin-bottom: 42px !important;
        }}
        .sidebar-nav-marker + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-nav-marker) + div[data-testid="stButton"] button,
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button {{
            width: 100% !important;
            min-height: 62px !important;
            justify-content: flex-start !important;
            padding: 16px 18px !important;
            border-radius: 18px !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            white-space: nowrap;
            text-align: left !important;
            overflow: visible !important;
        }}
        .sidebar-nav-marker + div[data-testid="stButton"] button p,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-nav-marker) + div[data-testid="stButton"] button p,
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p {{
            color: inherit !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            white-space: nowrap !important;
        }}
        .sidebar-nav-marker.active + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-nav-marker.active) + div[data-testid="stButton"] button,
        div:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button {{
            background: #37BD74 !important;
            border-color: #37BD74 !important;
            color: #fff !important;
            font-weight: 900 !important;
            box-shadow: 0 16px 34px rgba(55, 189, 116, .28) !important;
        }}
        .sidebar-nav-marker.active + div[data-testid="stButton"] button p,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button p,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-nav-marker.active) + div[data-testid="stButton"] button p,
        div:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button p {{
            color: #fff !important;
            font-weight: 900 !important;
        }}
        .sidebar-footer-spacer {{
            height: 150px;
        }}
        .sidebar-user-card {{
            width: 100%;
            min-height: 96px;
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 16px 18px;
            border-radius: 24px;
            border: 1px solid #d9efe0;
            background: #f8fffb;
            box-sizing: border-box;
            overflow: hidden;
            pointer-events: none;
        }}
        .sidebar-user-avatar {{
            width: 56px;
            height: 56px;
            border-radius: 999px;
            object-fit: cover;
            flex: 0 0 56px;
        }}
        .sidebar-user-meta {{
            min-width: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .sidebar-user-code {{
            color: #58a83f;
            font-size: 24px;
            font-weight: 900;
            line-height: 1.05;
            white-space: nowrap;
        }}
        .sidebar-user-name {{
            color: #6b7a99;
            font-size: 18px;
            font-weight: 500;
            line-height: 1.2;
            margin-top: 4px;
            white-space: nowrap;
        }}
        .sidebar-user-card-click {{
            display: none !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"],
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div[data-testid="stButton"],
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"],
        div:has(> div[data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div:has(div[data-testid="stButton"]),
        div:has(.sidebar-user-card-click) + div:has(div[data-testid="stButton"]) {{
            width: 100% !important;
            height: 96px !important;
            margin-top: -96px !important;
            margin-bottom: 0 !important;
            position: relative !important;
            z-index: 20 !important;
            pointer-events: auto !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div[data-testid="stButton"] button,
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"] button,
        div:has(> div[data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button,
        div:has(.sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button {{
            width: 100% !important;
            height: 96px !important;
            min-height: 96px !important;
            border-radius: 22px !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: transparent !important;
            padding: 0 !important;
            text-align: left !important;
            justify-content: flex-start !important;
            position: relative !important;
            overflow: hidden !important;
            cursor: pointer !important;
            pointer-events: auto !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"] button:hover,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button:hover,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div[data-testid="stButton"] button:hover,
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"] button:hover,
        div:has(> div[data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button:hover,
        div:has(.sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button:hover {{
            background: transparent !important;
            border: none !important;
            color: transparent !important;
            box-shadow: none !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"] button p,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button p,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div[data-testid="stButton"] button p,
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"] button p,
        div:has(> div[data-testid="stMarkdownContainer"] .sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button p,
        div:has(.sidebar-user-card-click) + div:has(div[data-testid="stButton"]) div[data-testid="stButton"] button p {{
            display: none !important;
        }}
        .sidebar-logout-marker + div[data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"],
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-logout-marker) + div[data-testid="stButton"],
        div:has(.sidebar-logout-marker) + div[data-testid="stButton"] {{
            margin-top: 26px !important;
        }}
        .sidebar-logout-marker + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] button,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-logout-marker) + div[data-testid="stButton"] button,
        div:has(.sidebar-logout-marker) + div[data-testid="stButton"] button {{
            width: 100% !important;
            min-height: 52px !important;
            justify-content: flex-start !important;
            padding: 10px 12px !important;
            border-radius: 14px;
            background: transparent !important;
            border-color: transparent !important;
            color: #58c06a !important;
            font-size: 22px !important;
            font-weight: 900 !important;
        }}
        .sidebar-logout-marker + div[data-testid="stButton"] button:hover,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] button:hover,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-logout-marker) + div[data-testid="stButton"] button:hover,
        div:has(.sidebar-logout-marker) + div[data-testid="stButton"] button:hover {{
            background: #e8f8ee !important;
            color: #58c06a !important;
        }}
        .sidebar-logout-marker + div[data-testid="stButton"] button p,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] button p,
        div:has(> [data-testid="stMarkdownContainer"] .sidebar-logout-marker) + div[data-testid="stButton"] button p,
        div:has(.sidebar-logout-marker) + div[data-testid="stButton"] button p {{
            color: inherit !important;
            font-size: 22px !important;
            font-weight: 900 !important;
        }}
        .ew-camera-box {{
            background: #fff;
            border: 1px solid var(--ew-line);
            border-radius: 18px;
            overflow: hidden;
            padding: .9rem;
            min-height: 320px;
            box-shadow: var(--ew-shadow);
        }}
        .ew-camera-box.alert {{
            border: 2px solid var(--ew-danger);
            box-shadow: 0 18px 36px rgba(232,40,107,.14);
        }}
        .ew-camera-head {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:.75rem;
            margin-bottom:.75rem;
        }}
        .ew-camera-title {{
            font-weight: 800;
            font-size:1rem;
        }}
        .ew-camera-frame {{
            border-radius: 16px;
            overflow:hidden;
            min-height:220px;
            background: linear-gradient(180deg, #f4f7f9 0%, #e8edf3 100%);
            border: 1px solid #e4e9ef;
        }}
        .ew-empty-camera {{
            display:flex;
            align-items:center;
            justify-content:center;
            min-height:220px;
            color:#6a7b72;
            font-weight:700;
            text-align:center;
            padding: 1rem;
        }}
        .ew-camera-meta {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:.75rem;
            margin-top:.75rem;
            color:var(--ew-muted);
            font-size:.92rem;
        }}
        .auth-page,
        .auth-login-page,
        .auth-register-page {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-page) section[data-testid="stSidebar"],
        body:has(.auth-page) header[data-testid="stHeader"] {{
            display:none;
        }}
        body:has(.auth-page) .block-container {{
            max-width: 1720px;
            min-height: 100vh;
            padding: 1.65rem 3.15rem 2rem 3.15rem;
        }}
        body:has(.auth-signin) .block-container {{
            max-width: 1480px !important;
            min-height: 100vh !important;
            margin-left: auto !important;
            margin-right: auto !important;
            padding: 40px 64px !important;
        }}
        body:has(.auth-page) .stApp {{
            background:#f4f8f5;
        }}
        body:has(.auth-page) [data-testid="stForm"] {{
            border:0;
            padding:0;
        }}
        body:has(.auth-signin) [data-testid="stHorizontalBlock"]:has(.auth-login-left) {{
            width: min(1480px, 100%) !important;
            min-height: calc(100vh - 80px);
            align-items:center;
            gap: 90px !important;
            justify-content:center !important;
            margin:0 auto !important;
        }}
        .auth-login-left {{
            max-width: 710px;
            padding-left: 0;
        }}
        .auth-login-brand {{
            padding: 0 0 .1rem 0;
            margin-bottom:0 !important;
        }}
        .auth-logo-row {{
            display:flex;
            align-items:center;
            gap:16px;
            margin-bottom:34px;
        }}
        body:has(.auth-signin) .auth-login-left .auth-logo-row {{
            margin-bottom:44px !important;
        }}
        .auth-logo-icon {{
            width:58px;
            height:58px;
            border-radius:14px;
            display:flex;
            align-items:center;
            justify-content:center;
            background:#63C174;
            color:#fff;
            box-shadow:0 14px 28px rgba(99,193,116,.24);
        }}
        .auth-logo-icon svg {{
            width:32px;
            height:32px;
            display:block;
        }}
        .auth-brand {{
            color:#63C174;
            font-size:1.72rem;
            line-height:1;
            font-weight:900;
        }}
        .auth-hero-heading {{
            margin:0 0 24px 0;
            color:#1F2A44;
            font-size:clamp(54px, 4.35vw, 76px);
            font-weight:900;
            line-height:1.05;
            letter-spacing:0;
        }}
        .auth-hero-green {{
            display:block;
            color:#63C174;
        }}
        .auth-hero-desc {{
            margin:0 0 32px 0;
            max-width:640px;
            color:#263247;
            font-size:1.18rem;
            line-height:1.4;
            font-weight:650;
        }}
        .auth-campus-card {{
            max-width: 710px;
        }}
        body:has(.auth-signin) .auth-image-target + div img {{
            width:100%;
            height:100% !important;
            display:block;
            object-fit:cover !important;
            border-radius:18px;
        }}
        body:has(.auth-signin) .auth-image-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            height:440px !important;
            padding:12px;
            border-radius:22px;
            border:1px solid #E7EAF0;
            background:#fff;
            box-shadow:0 18px 46px rgba(31,42,68,.08);
            overflow:hidden;
            max-width: 710px;
        }}
        body:has(.auth-signin) .auth-image-target + div [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.auth-signin) .auth-image-target + div [data-testid="stImage"],
        body:has(.auth-signin) .auth-image-target + div figure {{
            height:100% !important;
        }}
        .auth-title {{
            margin:0;
            color:#5cc878;
            font-size:2rem;
            font-weight:800;
            text-align:center;
            letter-spacing:0;
        }}
        body:has(.auth-signin) .auth-title {{
            color:#63C174;
            font-size:1.85rem;
            font-weight:900;
        }}
        .auth-subtitle {{
            margin:16px 0 44px 0;
            text-align:center;
            color:#1F2A44;
            font-size:1.08rem;
            font-weight:700;
        }}
        .auth-divider {{
            display:flex;
            align-items:center;
            justify-content:center;
            gap:14px;
            color:#98a2b3;
            font-size:.88rem;
            font-weight:800;
            margin:1.65rem 0 1.65rem 0;
        }}
        .auth-divider::before, .auth-divider::after {{
            content:"";
            height:1px;
            flex:1;
            background:#e5e7eb;
        }}
        .auth-hint {{
            color:#63C174;
            font-weight:800;
            text-align:left;
            margin:.1rem 0 1.4rem 0;
            font-size:.95rem;
        }}
        .auth-login-card {{
            display:block;
        }}
        body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            width:520px !important;
            max-width:520px;
            min-height:700px !important;
            margin:0 auto;
            padding:58px 56px !important;
            border-radius:30px;
            border:0;
            background:#fff;
            box-shadow:0 20px 58px rgba(31,42,68,.10);
            display:flex !important;
            flex-direction:column !important;
            justify-content:center !important;
        }}
        body:has(.auth-signin) .auth-forgot-link-trigger + div button,
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-forgot-link-trigger) + [data-testid="stElementContainer"] button,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-forgot-link-trigger) + [data-testid="element-container"] button {{
            width:auto !important;
            min-height:auto !important;
            height:auto !important;
            padding:0 !important;
            border:none !important;
            background:transparent !important;
            box-shadow:none !important;
            color:#63C174 !important;
            font-size:.95rem !important;
            font-weight:900 !important;
            justify-content:flex-start !important;
            margin:.05rem 0 1.4rem 0 !important;
        }}
        body:has(.auth-signin) .auth-forgot-link-trigger + div button p,
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-forgot-link-trigger) + [data-testid="stElementContainer"] button p,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-forgot-link-trigger) + [data-testid="element-container"] button p {{
            color:inherit !important;
            font-size:.95rem !important;
            font-weight:900 !important;
        }}
        body:has(.auth-recovery) .block-container {{
            max-width: 100% !important;
            min-height: 100vh !important;
            padding: 0 !important;
        }}
        body:has(.auth-recovery) .stApp {{
            background:#f8fbfa;
        }}
        body:has(.auth-recovery):not(:has(.auth-reset)) .block-container {{
            padding:44px 70px 18px 70px !important;
        }}
        body:has(.auth-recovery):not(:has(.auth-reset)) [data-testid="stHorizontalBlock"]:has(.recovery-left) {{
            width:min(1180px, 100%) !important;
            min-height:calc(100vh - 62px);
            margin:0 auto !important;
            align-items:flex-start;
            gap:104px !important;
        }}
        .recovery-left {{
            max-width:520px;
            padding-top:42px;
        }}
        .recovery-logo {{
            display:flex;
            align-items:center;
            gap:11px;
            margin-bottom:38px;
            color:#2f8b52;
            font-size:20px;
            font-weight:900;
        }}
        .recovery-logo .auth-logo-icon {{
            width:29px;
            height:29px;
            border-radius:8px;
            box-shadow:none;
        }}
        .recovery-logo .auth-logo-icon svg {{
            width:18px;
            height:18px;
        }}
        .recovery-title {{
            margin:0 0 18px 0;
            color:#182031;
            font-size:42px;
            line-height:1.08;
            font-weight:900;
            letter-spacing:0;
        }}
        .recovery-title span {{
            display:block;
            color:#5ec777;
        }}
        .recovery-copy {{
            width:430px;
            margin:0 0 36px 0;
            color:#667085;
            font-size:15px;
            line-height:1.45;
            font-weight:700;
        }}
        .recovery-image {{
            width:540px;
            height:180px;
            border-radius:22px;
            overflow:hidden;
            box-shadow:0 26px 44px rgba(23,39,53,.22);
            position:relative;
        }}
        .recovery-image img {{
            width:100%;
            height:100%;
            display:block;
            object-fit:cover;
        }}
        .recovery-image-caption {{
            position:absolute;
            left:24px;
            bottom:22px;
            color:#fff;
            font-size:12px;
            line-height:1.22;
            font-weight:800;
            text-shadow:0 2px 8px rgba(0,0,0,.35);
        }}
        body:has(.auth-otp) .recovery-left {{
            padding-top:0;
        }}
        body:has(.auth-otp) .recovery-logo {{
            margin-bottom:44px;
        }}
        body:has(.auth-otp) .recovery-title {{
            margin-bottom:22px;
            font-size:43px;
        }}
        body:has(.auth-otp) .recovery-copy {{
            width:438px;
            margin-bottom:24px;
            line-height:1.55;
        }}
        body:has(.auth-otp) .recovery-image {{
            width:498px;
            height:168px;
            border-radius:18px;
        }}
        .recovery-card-anchor {{
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-recovery) .recovery-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
            width:528px !important;
            max-width:528px;
            min-height:342px;
            margin:110px 0 0 auto;
            padding:52px 48px 42px 48px !important;
            border:0;
            border-radius:26px;
            background:#fff;
            box-shadow:0 28px 58px rgba(31,42,68,.10);
        }}
        body:has(.auth-otp) .recovery-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
            width:456px !important;
            max-width:456px;
            min-height:386px;
            margin-top:70px;
            padding:42px 42px 36px 42px !important;
        }}
        .recovery-card-title {{
            margin:0 0 16px 0;
            color:#58bd70;
            font-size:26px;
            line-height:1.05;
            text-align:center;
            font-weight:900;
            letter-spacing:0;
        }}
        .recovery-card-desc {{
            max-width:330px;
            margin:0 auto 34px auto;
            color:#7a8291;
            font-size:13px;
            line-height:1.35;
            text-align:center;
            font-weight:700;
        }}
        body:has(.auth-recovery) .stTextInput label {{
            color:#394155 !important;
            font-size:13px !important;
            line-height:1 !important;
            font-weight:900 !important;
            margin-bottom:9px !important;
        }}
        body:has(.auth-recovery) .stTextInput input {{
            min-height:58px !important;
            border-radius:12px !important;
            background:#f2f4f4 !important;
            color:#1f2937 !important;
            font-size:14px !important;
            font-weight:700 !important;
            padding:0 17px !important;
        }}
        body:has(.auth-recovery) .stTextInput input::placeholder {{
            color:#c1c8c5 !important;
            opacity:1 !important;
        }}
        body:has(.auth-recovery) .stTextInput {{
            margin-bottom:24px !important;
        }}
        body:has(.auth-recovery) .stFormSubmitButton > button {{
            min-height:66px !important;
            border-radius:10px !important;
            border:0 !important;
            background:#5BBE72 !important;
            color:#fff !important;
            font-size:18px !important;
            font-weight:900 !important;
            box-shadow:0 12px 20px rgba(48,151,76,.24) !important;
        }}
        body:has(.auth-recovery) .stFormSubmitButton > button:hover {{
            background:#50af66 !important;
            color:#fff !important;
        }}
        .recovery-small-link-row {{
            margin-top:28px;
            color:#8b95a5;
            text-align:center;
            font-size:13px;
            font-weight:700;
        }}
        .recovery-small-link-row strong {{
            color:#2f8b52;
            font-weight:900;
        }}
        .recovery-secure-line {{
            display:flex;
            align-items:center;
            justify-content:center;
            gap:22px;
            margin-top:42px;
            color:#c5ccc9;
            font-size:10px;
            font-weight:900;
            letter-spacing:.08em;
        }}
        .recovery-secure-line::before,
        .recovery-secure-line::after {{
            content:"";
            width:64px;
            height:1px;
            background:#edf0ee;
        }}
        .recovery-footer {{
            position:fixed;
            left:0;
            right:0;
            bottom:17px;
            color:#a9b0b8;
            text-align:center;
            font-size:11px;
            font-weight:700;
        }}
        .recovery-inline-link {{
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-recovery) .recovery-inline-link + div button,
        body:has(.auth-recovery) [data-testid="stElementContainer"]:has(.recovery-inline-link) + [data-testid="stElementContainer"] button,
        body:has(.auth-recovery) [data-testid="element-container"]:has(.recovery-inline-link) + [data-testid="element-container"] button {{
            min-height:auto !important;
            height:auto !important;
            width:auto !important;
            margin:0 auto !important;
            padding:0 !important;
            border:none !important;
            background:transparent !important;
            box-shadow:none !important;
            color:#2f8b52 !important;
            font-size:13px !important;
            font-weight:900 !important;
        }}
        body:has(.auth-recovery) .recovery-inline-link + div button p,
        body:has(.auth-recovery) [data-testid="stElementContainer"]:has(.recovery-inline-link) + [data-testid="stElementContainer"] button p,
        body:has(.auth-recovery) [data-testid="element-container"]:has(.recovery-inline-link) + [data-testid="element-container"] button p {{
            color:inherit !important;
            font-size:13px !important;
            font-weight:900 !important;
        }}
        .otp-input-row {{
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) {{
            gap:12px !important;
            margin-bottom:26px;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) [data-testid="column"] {{
            min-width:0 !important;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) .stTextInput {{
            margin-bottom:0 !important;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) input {{
            width:42px !important;
            min-height:48px !important;
            border-radius:10px !important;
            padding:0 !important;
            text-align:center !important;
            font-size:22px !important;
            font-weight:900 !important;
            color:#5d6676 !important;
        }}
        body:has(.auth-otp) .stFormSubmitButton > button {{
            min-height:64px !important;
            font-size:17px !important;
            border-radius:10px !important;
        }}
        .otp-resend {{
            margin:28px 0 8px 0;
            color:#8b95a5;
            text-align:center;
            font-size:13px;
            font-weight:700;
        }}
        .otp-resend span {{
            color:#2f8b52;
            font-weight:900;
        }}
        body:has(.auth-reset) .stApp {{
            background:#f7f7fc;
        }}
        body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) {{
            min-height:100vh;
            gap:0 !important;
            align-items:stretch;
        }}
        body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) > div[data-testid="column"] {{
            padding:0 !important;
        }}
        .reset-left-panel {{
            min-height:100vh;
            position:relative;
            display:flex;
            align-items:flex-end;
            padding:0 0 116px 88px;
            color:#fff;
            background-size:cover;
            background-position:center;
            overflow:hidden;
        }}
        .reset-left-panel::before {{
            content:"";
            position:absolute;
            inset:0;
            background:rgba(13,82,37,.78);
        }}
        .reset-left-content {{
            position:relative;
            width:460px;
        }}
        .reset-brand {{
            display:flex;
            align-items:center;
            gap:12px;
            margin-bottom:36px;
            font-size:20px;
            font-weight:900;
        }}
        .reset-brand .auth-logo-icon {{
            width:42px;
            height:42px;
            border-radius:10px;
            background:#fff;
            color:#2c9b58;
            box-shadow:none;
        }}
        .reset-brand .auth-logo-icon svg {{
            width:25px;
            height:25px;
        }}
        .reset-title {{
            margin:0 0 24px 0;
            font-size:32px;
            line-height:1.12;
            font-weight:900;
            letter-spacing:0;
        }}
        .reset-copy {{
            width:405px;
            margin:0 0 42px 0;
            font-size:14px;
            line-height:1.45;
            font-weight:800;
        }}
        .reset-divider {{
            width:360px;
            height:1px;
            background:rgba(255,255,255,.2);
            margin-bottom:28px;
        }}
        .reset-join {{
            display:flex;
            align-items:center;
            gap:14px;
            font-size:12px;
            font-weight:800;
        }}
        .reset-bubbles {{
            display:flex;
            width:74px;
        }}
        .reset-bubbles span {{
            width:28px;
            height:28px;
            border-radius:999px;
            background:#e9fff0;
            border:1px solid rgba(255,255,255,.75);
            margin-left:-7px;
        }}
        .reset-bubbles span:first-child {{
            margin-left:0;
        }}
        .reset-bubbles span:nth-child(2) {{
            background:#d7ffe1;
        }}
        .reset-bubbles span:nth-child(3) {{
            background:#70cf84;
        }}
        .reset-card-anchor {{
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-reset) .reset-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
            width:492px !important;
            max-width:492px;
            min-height:365px;
            margin:196px auto 0 auto;
            padding:52px 50px 40px 50px !important;
            border:0;
            border-radius:22px;
            background:#fff;
            box-shadow:0 26px 56px rgba(31,42,68,.08);
        }}
        body:has(.auth-reset) .recovery-card-title {{
            color:#111827;
            font-size:24px;
            margin-bottom:18px;
        }}
        body:has(.auth-reset) .recovery-card-desc {{
            margin-bottom:26px;
            font-size:13px;
        }}
        body:has(.auth-reset) .stTextInput label {{
            color:#1f2937 !important;
            font-size:13px !important;
            font-weight:900 !important;
            margin-bottom:8px !important;
        }}
        body:has(.auth-reset) .stTextInput input {{
            min-height:50px !important;
            border-radius:9px !important;
            background:#f3f5f5 !important;
            font-size:13px !important;
            padding-left:14px !important;
        }}
        body:has(.auth-reset) .stTextInput:has(input[type="password"]) button {{
            background:transparent !important;
            color:#16211c !important;
            margin-right:6px !important;
        }}
        body:has(.auth-reset) .stTextInput {{
            margin-bottom:18px !important;
        }}
        body:has(.auth-reset) .stFormSubmitButton > button {{
            min-height:54px !important;
            border-radius:10px !important;
            font-size:13px !important;
            font-weight:900 !important;
            background:#5BBE72 !important;
            border:0 !important;
            box-shadow:0 10px 18px rgba(48,151,76,.18) !important;
        }}
        body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left) {{
            max-width: 1320px;
            min-height: min(820px, calc(100vh - 40px));
            margin: 0 auto;
            align-items:stretch;
            gap:0 !important;
            border-radius:24px;
            background:#fff;
            box-shadow:0 18px 55px rgba(15,23,42,.10);
            overflow:hidden;
        }}
        body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left) > div[data-testid="column"] {{
            padding:0 !important;
        }}
        .auth-register-left {{
            position:relative;
            overflow:hidden;
            height:100%;
            min-height:820px;
            border-radius:24px 0 0 24px;
            background:linear-gradient(180deg,#73c76c 0%, #3f8644 100%);
            color:#fff;
            padding:56px 48px;
        }}
        .auth-register-left .auth-logo-row {{
            gap:16px;
            margin-bottom:74px;
        }}
        .auth-register-left .auth-brand {{
            color:#fff;
            font-size:1.75rem;
        }}
        .auth-register-left .auth-logo-icon {{
            width:48px;
            height:48px;
            border-radius:0;
            background:transparent;
            box-shadow:none;
        }}
        .auth-register-left .auth-logo-icon svg {{
            width:44px;
            height:44px;
        }}
        .auth-register-heading {{
            margin:0 0 2.15rem 0;
            max-width:390px;
            font-size:3.35rem;
            font-weight:800;
            line-height:1.12;
            letter-spacing:0;
        }}
        .auth-register-copy {{
            max-width:390px;
            color:rgba(255,255,255,.92);
            font-size:1.36rem;
            line-height:1.7;
            font-weight:800;
        }}
        .auth-decor-circle {{
            position:absolute;
            border-radius:999px;
            background:rgba(255,255,255,.16);
            pointer-events:none;
        }}
        .auth-decor-circle.one {{
            width:146px;
            height:146px;
            right:-26px;
            bottom:80px;
        }}
        .auth-decor-circle.two {{
            width:108px;
            height:108px;
            right:106px;
            bottom:58px;
        }}
        .auth-decor-circle.three {{
            width:46px;
            height:46px;
            left:53%;
            bottom:150px;
        }}
        .auth-decor-circle.four {{
            width:44px;
            height:230px;
            left:51%;
            bottom:-12px;
            border-radius:24px;
        }}
        .auth-register-right {{
            display:block;
        }}
        body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            height:100%;
            margin:0;
            padding:5.25rem 4.6rem 3.15rem 4.6rem;
            border-radius:0 24px 24px 0;
            border:0;
            background:#fff;
            box-shadow:none;
        }}
        body:has(.auth-signup) .auth-title {{
            font-size:2.25rem;
            margin-bottom:3.35rem;
        }}
        body:has(.auth-page) .stTextInput input,
        body:has(.auth-page) .stSelectbox [data-baseweb="select"] > div,
        body:has(.auth-page) .stDateInput [data-baseweb="input"] > div {{
            width:100% !important;
            min-height:56px !important;
            border-radius:14px !important;
            border:0 !important;
            background:#eef3f1 !important;
            color:#0f172a !important;
            box-shadow:none !important;
        }}
        body:has(.auth-signin) .stTextInput input {{
            background:#EEF1F8 !important;
            min-height:54px !important;
            padding-left:18px !important;
            padding-right:18px !important;
        }}
        body:has(.auth-signin) .stTextInput:has(input[type="password"]) button {{
            background:#E3E7F0 !important;
            border-radius:12px !important;
            color:#64748b !important;
            margin-right:6px !important;
        }}
        body:has(.auth-page) .stTextInput label,
        body:has(.auth-page) .stSelectbox label,
        body:has(.auth-page) .stDateInput label {{
            color:#475569 !important;
            font-size:1.02rem !important;
            font-weight:800 !important;
            margin-bottom:.35rem !important;
        }}
        body:has(.auth-signin) .stTextInput label {{
            color:#111827 !important;
            font-size:1rem !important;
            font-weight:900 !important;
            margin-bottom:.28rem !important;
        }}
        body:has(.auth-page) .stTextInput,
        body:has(.auth-page) .stSelectbox,
        body:has(.auth-page) .stDateInput {{
            margin-bottom:1.15rem;
        }}
        body:has(.auth-signin) .stTextInput {{
            margin-bottom:.95rem;
        }}
        body:has(.auth-signup) .stTextInput,
        body:has(.auth-signup) .stSelectbox,
        body:has(.auth-signup) .stDateInput {{
            margin-bottom:1.75rem;
        }}
        body:has(.auth-page) .stButton > button,
        body:has(.auth-page) .stFormSubmitButton > button {{
            min-height:56px !important;
            border-radius:12px !important;
            border:1px solid #37BD74 !important;
            background:#37BD74 !important;
            color:#fff !important;
            font-size:1.15rem !important;
            font-weight:800 !important;
            box-shadow:0 12px 26px rgba(55,189,116,.30) !important;
        }}
        body:has(.auth-page) .stButton > button:hover,
        body:has(.auth-page) .stFormSubmitButton > button:hover {{
            background:#2e9f62 !important;
            border-color:#2e9f62 !important;
            color:#fff !important;
        }}
        body:has(.auth-signin) .stButton > button,
        body:has(.auth-signin) .stFormSubmitButton > button {{
            min-height:54px !important;
            border-radius:14px !important;
            border:1px solid #63C174 !important;
            background:#63C174 !important;
            color:#fff !important;
            font-size:1.05rem !important;
            font-weight:900 !important;
            box-shadow:0 12px 26px rgba(99,193,116,.28) !important;
        }}
        body:has(.auth-signin) .stButton > button:hover,
        body:has(.auth-signin) .stFormSubmitButton > button:hover {{
            background:#56af63 !important;
            border-color:#56af63 !important;
            color:#fff !important;
        }}
        body:has(.auth-page) .auth-outline-trigger + div button {{
            background:#fff !important;
            color:#37BD74 !important;
            border:2px solid #37BD74 !important;
            box-shadow:none !important;
        }}
        body:has(.auth-page) .auth-outline-trigger + div button:hover {{
            background:#37BD74 !important;
            color:#fff !important;
        }}
        body:has(.auth-signin) .auth-outline-trigger + div button {{
            background:#fff !important;
            color:#63C174 !important;
            border:2px solid #63C174 !important;
            box-shadow:none !important;
        }}
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-outline-trigger) + [data-testid="stElementContainer"] button,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-outline-trigger) + [data-testid="element-container"] button {{
            background:#fff !important;
            color:#63C174 !important;
            border:2px solid #63C174 !important;
            box-shadow:none !important;
        }}
        body:has(.auth-signin) .auth-outline-trigger + div button:hover {{
            background:#fff !important;
            color:#56af63 !important;
            border-color:#56af63 !important;
        }}
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-outline-trigger) + [data-testid="stElementContainer"] button:hover,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-outline-trigger) + [data-testid="element-container"] button:hover {{
            background:#fff !important;
            color:#56af63 !important;
            border-color:#56af63 !important;
        }}
        body:has(.auth-signin) .auth-outline-trigger + div button p,
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-outline-trigger) + [data-testid="stElementContainer"] button p,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-outline-trigger) + [data-testid="element-container"] button p {{
            color:inherit !important;
            font-weight:900 !important;
        }}
        body:has(.auth-recovery) .stTextInput label {{
            color:#394155 !important;
            font-size:13px !important;
            line-height:1 !important;
            font-weight:900 !important;
            margin-bottom:9px !important;
        }}
        body:has(.auth-recovery) .stTextInput input {{
            min-height:58px !important;
            border-radius:12px !important;
            background:#f2f4f4 !important;
            color:#1f2937 !important;
            font-size:14px !important;
            font-weight:700 !important;
            padding:0 17px !important;
        }}
        body:has(.auth-recovery) .stTextInput {{
            margin-bottom:24px !important;
        }}
        body:has(.auth-recovery) .stFormSubmitButton > button {{
            min-height:66px !important;
            border-radius:10px !important;
            border:0 !important;
            background:#5BBE72 !important;
            color:#fff !important;
            font-size:18px !important;
            font-weight:900 !important;
            box-shadow:0 12px 20px rgba(48,151,76,.24) !important;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) input {{
            width:42px !important;
            min-height:48px !important;
            border-radius:10px !important;
            padding:0 !important;
            text-align:center !important;
            font-size:22px !important;
            font-weight:900 !important;
        }}
        body:has(.auth-otp) .stFormSubmitButton > button {{
            min-height:64px !important;
            font-size:17px !important;
        }}
        body:has(.auth-reset) .stTextInput input {{
            min-height:50px !important;
            border-radius:9px !important;
            background:#f3f5f5 !important;
            font-size:13px !important;
            padding-left:14px !important;
        }}
        body:has(.auth-reset) .stTextInput {{
            margin-bottom:18px !important;
        }}
        body:has(.auth-reset) .stFormSubmitButton > button {{
            min-height:54px !important;
            border-radius:10px !important;
            font-size:13px !important;
        }}
        body:has(.auth-recovery) .recovery-inline-link + div button,
        body:has(.auth-recovery) [data-testid="stElementContainer"]:has(.recovery-inline-link) + [data-testid="stElementContainer"] button,
        body:has(.auth-recovery) [data-testid="element-container"]:has(.recovery-inline-link) + [data-testid="element-container"] button {{
            min-height:auto !important;
            height:auto !important;
            width:auto !important;
            margin:0 auto !important;
            padding:0 !important;
            border:none !important;
            background:transparent !important;
            box-shadow:none !important;
            color:#2f8b52 !important;
            font-size:13px !important;
            font-weight:900 !important;
        }}
        .auth-footer-link {{
            margin-top:1.75rem;
            text-align:center;
            color:#98a2b3;
            font-size:1.05rem;
            font-weight:800;
        }}
        .auth-footer-link span {{
            color:#37BD74;
        }}
        .signup-login-text {{
            color:#98a2b3;
            font-size:15px;
            font-weight:800;
            text-align:right;
            line-height:28px;
            white-space:nowrap;
        }}
        .signup-login-link {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.signup-login-text):has(.signup-login-link) {{
            gap:8px !important;
            align-items:center !important;
        }}
        body:has(.auth-signup) .signup-login-link + div button,
        body:has(.auth-signup) [data-testid="stElementContainer"]:has(.signup-login-link) + [data-testid="stElementContainer"] button,
        body:has(.auth-signup) [data-testid="element-container"]:has(.signup-login-link) + [data-testid="element-container"] button {{
            width:auto !important;
            min-height:auto !important;
            height:auto !important;
            padding:0 !important;
            border:none !important;
            background:transparent !important;
            box-shadow:none !important;
            color:#37BD74 !important;
            font-size:15px !important;
            font-weight:900 !important;
            justify-content:flex-start !important;
            white-space:nowrap !important;
        }}
        body:has(.auth-signup) .signup-login-link + div button:hover,
        body:has(.auth-signup) [data-testid="stElementContainer"]:has(.signup-login-link) + [data-testid="stElementContainer"] button:hover,
        body:has(.auth-signup) [data-testid="element-container"]:has(.signup-login-link) + [data-testid="element-container"] button:hover {{
            background:transparent !important;
            color:#2e9f62 !important;
            border:none !important;
            box-shadow:none !important;
        }}
        body:has(.auth-signup) .signup-login-link + div button p,
        body:has(.auth-signup) [data-testid="stElementContainer"]:has(.signup-login-link) + [data-testid="stElementContainer"] button p,
        body:has(.auth-signup) [data-testid="element-container"]:has(.signup-login-link) + [data-testid="element-container"] button p {{
            color:inherit !important;
            font-size:15px !important;
            font-weight:900 !important;
            white-space:nowrap !important;
        }}
        /* Auth responsive sizing override: keep all auth forms compact and consistent. */
        body:has(.auth-signin) .block-container,
        body:has(.auth-signup) .block-container,
        body:has(.auth-recovery) .block-container {{
            min-height:100vh !important;
            max-width:100% !important;
            padding:20px 36px !important;
            box-sizing:border-box !important;
        }}
        body:has(.auth-page) .stApp {{
            background:#f7fbf8 !important;
        }}
        body:has(.auth-signin) [data-testid="stHorizontalBlock"]:has(.auth-login-left),
        body:has(.auth-recovery):not(:has(.auth-reset)) [data-testid="stHorizontalBlock"]:has(.recovery-left) {{
            width:min(1160px, 100%) !important;
            min-height:calc(100vh - 40px) !important;
            gap:44px !important;
            align-items:center !important;
            justify-content:center !important;
            margin:0 auto !important;
        }}
        body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left) {{
            width:min(1100px, 100%) !important;
            max-width:1100px !important;
            min-height:auto !important;
            align-items:center !important;
            gap:40px !important;
            margin:0 auto !important;
            border-radius:0 !important;
            background:transparent !important;
            box-shadow:none !important;
            overflow:visible !important;
        }}
        body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) {{
            min-height:calc(100vh - 40px) !important;
            align-items:center !important;
        }}
        .auth-login-left,
        .recovery-left {{
            max-width:500px !important;
            padding-top:0 !important;
        }}
        .auth-login-brand {{
            margin-bottom:0 !important;
        }}
        body:has(.auth-signin) .auth-login-left .auth-logo-row,
        .recovery-logo {{
            margin-bottom:24px !important;
        }}
        .auth-logo-icon {{
            width:46px !important;
            height:46px !important;
            border-radius:12px !important;
        }}
        .auth-logo-icon svg {{
            width:27px !important;
            height:27px !important;
        }}
        .auth-brand {{
            font-size:1.35rem !important;
        }}
        .auth-hero-heading,
        .recovery-title {{
            font-size:clamp(34px, 3.6vw, 48px) !important;
            line-height:1.04 !important;
            margin:0 0 16px 0 !important;
        }}
        .auth-hero-desc,
        .recovery-copy {{
            width:auto !important;
            max-width:500px !important;
            font-size:clamp(14px, 1.25vw, 18px) !important;
            line-height:1.35 !important;
            margin:0 0 22px 0 !important;
        }}
        body:has(.auth-signin) .auth-image-target + div [data-testid="stVerticalBlockBorderWrapper"],
        .recovery-image {{
            height:310px !important;
            max-height:310px !important;
            max-width:500px !important;
            border-radius:16px !important;
            overflow:hidden !important;
        }}
        .recovery-image {{
            width:100% !important;
            box-shadow:0 20px 38px rgba(23,39,53,.16) !important;
        }}
        body:has(.auth-signup) .auth-register-left {{
            min-height:auto !important;
            height:auto !important;
            max-width:460px !important;
            padding:34px 36px !important;
            border-radius:22px !important;
        }}
        body:has(.auth-signup) .auth-register-heading {{
            font-size:clamp(28px, 2.6vw, 38px) !important;
            line-height:1.06 !important;
            margin:0 0 16px 0 !important;
        }}
        body:has(.auth-signup) .auth-register-copy {{
            font-size:15px !important;
            line-height:1.38 !important;
            max-width:390px !important;
        }}
        body:has(.auth-reset) .reset-left-panel {{
            min-height:calc(100vh - 40px) !important;
            padding:0 42px 54px 56px !important;
        }}
        body:has(.auth-reset) .reset-left-content {{
            width:min(390px, 100%) !important;
        }}
        body:has(.auth-reset) .reset-title {{
            font-size:27px !important;
            line-height:1.12 !important;
            margin-bottom:16px !important;
        }}
        body:has(.auth-reset) .reset-copy {{
            width:auto !important;
            font-size:13px !important;
            line-height:1.35 !important;
            margin-bottom:24px !important;
        }}
        body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.auth-recovery) .recovery-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.auth-reset) .reset-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
            width:440px !important;
            max-width:100% !important;
            min-height:auto !important;
            height:auto !important;
            margin:0 auto !important;
            padding:34px 36px !important;
            border-radius:22px !important;
            border:0 !important;
            background:#fff !important;
            box-shadow:0 18px 50px rgba(15,23,42,.10) !important;
            box-sizing:border-box !important;
        }}
        body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            justify-content:center !important;
        }}
        body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            max-height:calc(100vh - 40px) !important;
            overflow:auto !important;
        }}
        body:has(.auth-signin) .auth-title,
        body:has(.auth-signup) .auth-title,
        .recovery-card-title,
        body:has(.auth-reset) .recovery-card-title {{
            font-size:24px !important;
            line-height:1.15 !important;
            margin:0 0 8px 0 !important;
            font-weight:900 !important;
            color:#37BD74 !important;
            text-align:center !important;
        }}
        body:has(.auth-reset) .recovery-card-title {{
            color:#111827 !important;
        }}
        .auth-subtitle,
        .recovery-card-desc,
        body:has(.auth-reset) .recovery-card-desc {{
            max-width:100% !important;
            font-size:14px !important;
            line-height:1.35 !important;
            margin:0 auto 22px auto !important;
            text-align:center !important;
            color:#334155 !important;
            font-weight:700 !important;
        }}
        body:has(.auth-page) .stTextInput label,
        body:has(.auth-page) .stSelectbox label,
        body:has(.auth-page) .stDateInput label,
        body:has(.auth-recovery) .stTextInput label,
        body:has(.auth-reset) .stTextInput label {{
            font-size:14px !important;
            line-height:1.2 !important;
            font-weight:800 !important;
            color:#111827 !important;
            margin-bottom:6px !important;
        }}
        body:has(.auth-page) .stTextInput input,
        body:has(.auth-page) .stSelectbox [data-baseweb="select"] > div,
        body:has(.auth-page) .stDateInput [data-baseweb="input"] > div,
        body:has(.auth-recovery) .stTextInput input,
        body:has(.auth-reset) .stTextInput input {{
            min-height:44px !important;
            height:44px !important;
            border-radius:11px !important;
            font-size:14px !important;
            font-weight:700 !important;
            padding-left:16px !important;
            padding-right:16px !important;
        }}
        body:has(.auth-page) .stTextInput,
        body:has(.auth-page) .stSelectbox,
        body:has(.auth-page) .stDateInput,
        body:has(.auth-recovery) .stTextInput,
        body:has(.auth-reset) .stTextInput {{
            margin-bottom:14px !important;
        }}
        body:has(.auth-page) .stButton > button,
        body:has(.auth-page) .stFormSubmitButton > button,
        body:has(.auth-recovery) .stFormSubmitButton > button,
        body:has(.auth-reset) .stFormSubmitButton > button {{
            min-height:46px !important;
            height:46px !important;
            border-radius:11px !important;
            font-size:14px !important;
            font-weight:900 !important;
        }}
        .auth-divider {{
            margin:18px 0 !important;
        }}
        body:has(.auth-signin) .auth-forgot-link-trigger + div button,
        body:has(.auth-signin) [data-testid="stElementContainer"]:has(.auth-forgot-link-trigger) + [data-testid="stElementContainer"] button,
        body:has(.auth-signin) [data-testid="element-container"]:has(.auth-forgot-link-trigger) + [data-testid="element-container"] button {{
            margin:0 0 14px 0 !important;
            min-height:auto !important;
        }}
        .recovery-small-link-row,
        .otp-resend {{
            margin-top:16px !important;
            font-size:13px !important;
        }}
        .recovery-secure-line {{
            margin-top:22px !important;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) {{
            gap:8px !important;
            margin-bottom:18px !important;
        }}
        body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) input {{
            width:100% !important;
            min-height:44px !important;
            height:44px !important;
            padding:0 !important;
            text-align:center !important;
            font-size:18px !important;
            font-weight:900 !important;
        }}
        @media (max-width: 768px) {{
            body:has(.auth-signin) .block-container,
            body:has(.auth-signup) .block-container,
            body:has(.auth-recovery) .block-container {{
                min-height:100vh !important;
                padding:12px 12px !important;
            }}
            body:has(.auth-signin) [data-testid="stHorizontalBlock"]:has(.auth-login-left),
            body:has(.auth-recovery):not(:has(.auth-reset)) [data-testid="stHorizontalBlock"]:has(.recovery-left),
            body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left),
            body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) {{
                width:100% !important;
                display:block !important;
                min-height:auto !important;
                margin:0 auto !important;
            }}
            body:has(.auth-signin) [data-testid="stHorizontalBlock"]:has(.auth-login-left) > div[data-testid="column"],
            body:has(.auth-recovery) [data-testid="stHorizontalBlock"]:has(.recovery-left) > div[data-testid="column"],
            body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left) > div[data-testid="column"],
            body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) > div[data-testid="column"] {{
                width:100% !important;
                min-width:0 !important;
                padding:0 !important;
            }}
            .auth-login-left,
            .recovery-left,
            body:has(.auth-signup) .auth-register-left,
            body:has(.auth-reset) .reset-left-panel,
            body:has(.auth-signin) .auth-image-target + div {{
                display:none !important;
            }}
            body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-recovery) .recovery-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-reset) .reset-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
                width:100% !important;
                max-width:390px !important;
                padding:24px 18px !important;
                border-radius:18px !important;
                box-shadow:0 12px 32px rgba(15,23,42,.10) !important;
            }}
            body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
                max-height:none !important;
                overflow:visible !important;
            }}
            body:has(.auth-signin) .auth-title,
            body:has(.auth-signup) .auth-title,
            .recovery-card-title,
            body:has(.auth-reset) .recovery-card-title {{
                font-size:21px !important;
                line-height:1.18 !important;
                margin-bottom:8px !important;
            }}
            .auth-subtitle,
            .recovery-card-desc,
            body:has(.auth-reset) .recovery-card-desc {{
                font-size:13px !important;
                line-height:1.35 !important;
                margin-bottom:18px !important;
            }}
            body:has(.auth-page) .stTextInput label,
            body:has(.auth-page) .stSelectbox label,
            body:has(.auth-page) .stDateInput label {{
                font-size:14px !important;
            }}
            body:has(.auth-page) .stTextInput input,
            body:has(.auth-page) .stSelectbox [data-baseweb="select"] > div,
            body:has(.auth-page) .stDateInput [data-baseweb="input"] > div,
            body:has(.auth-recovery) .stTextInput input,
            body:has(.auth-reset) .stTextInput input {{
                min-height:42px !important;
                height:42px !important;
                font-size:13px !important;
            }}
            body:has(.auth-page) .stButton > button,
            body:has(.auth-page) .stFormSubmitButton > button,
            body:has(.auth-recovery) .stFormSubmitButton > button,
            body:has(.auth-reset) .stFormSubmitButton > button {{
                min-height:44px !important;
                height:44px !important;
                font-size:13px !important;
            }}
            body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) {{
                gap:5px !important;
            }}
            body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) input {{
                min-height:40px !important;
                height:40px !important;
                font-size:15px !important;
            }}
            .signup-login-text {{
                text-align:right !important;
                font-size:13px !important;
            }}
            body:has(.auth-signup) .signup-login-link + div button,
            body:has(.auth-signup) [data-testid="stElementContainer"]:has(.signup-login-link) + [data-testid="stElementContainer"] button,
            body:has(.auth-signup) [data-testid="element-container"]:has(.signup-login-link) + [data-testid="element-container"] button {{
                font-size:13px !important;
            }}
            .recovery-footer {{
                position:static !important;
                margin-top:18px !important;
            }}
        }}
        [data-testid="stDataFrame"] {{
            border: 1px solid var(--ew-line);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--ew-shadow);
            background:#fff;
        }}
        [data-testid="stDataFrame"] [role="columnheader"] {{
            background: #f8f1c9 !important;
            font-weight: 800 !important;
        }}
        .ew-section-card {{
            background:#fff;
            border:1px solid var(--ew-line);
            border-radius:16px;
            padding:1rem 1.2rem;
            box-shadow: var(--ew-shadow);
            margin-bottom: 1rem;
        }}
        .ew-filter-card {{
            background:#fff;
            border:1px solid var(--ew-line);
            border-radius:16px;
            padding:1rem 1.1rem .6rem 1.1rem;
            box-shadow: var(--ew-shadow);
            margin-bottom: 1rem;
        }}
        .content-card {{
            background:#fff;
            border:1px solid var(--ew-line);
            border-radius:16px;
            box-shadow: var(--ew-shadow);
            padding:1rem 1.15rem;
            margin-bottom:1rem;
        }}
        .stat-grid {{
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:20px;
            margin-bottom:1rem;
        }}
        .two-col-grid {{
            display:grid;
            grid-template-columns:minmax(0,1.4fr) minmax(300px,.85fr);
            gap:20px;
            align-items:start;
        }}
        .three-col-grid {{
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:20px;
            align-items:start;
        }}
        .camera-grid {{
            display:grid;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:20px;
        }}
        .filter-row {{
            display:grid;
            grid-template-columns:1.4fr 1fr 1fr 1fr .9fr;
            gap:16px;
            align-items:end;
        }}
        .admin-three-col {{
            display:grid;
            grid-template-columns:repeat(3,minmax(0,1fr));
            gap:20px;
            align-items:start;
        }}
        .side-panel {{
            background:#fff;
            border:1px solid var(--ew-line);
            border-radius:16px;
            box-shadow: var(--ew-shadow);
            padding:1rem 1.15rem;
            position:sticky;
            top:1rem;
        }}
        .ew-card-title {{
            font-size:1.15rem;
            font-weight:800;
            margin-bottom:.25rem;
        }}
        .ew-card-subtitle {{
            color:var(--ew-muted);
            font-size:.95rem;
            margin-bottom:.9rem;
        }}
        .ew-toolbar {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:1rem;
            margin-bottom:.85rem;
        }}
        .ew-actions-inline {{
            display:flex;
            align-items:center;
            gap:.55rem;
            flex-wrap:wrap;
        }}
        .ew-detail-stack {{
            display:flex;
            flex-direction:column;
            gap:.8rem;
        }}
        .ew-avatar-panel {{
            text-align:center;
            padding:1.35rem 1.1rem;
        }}
        .ew-avatar-ring {{
            display:inline-flex;
            align-items:center;
            justify-content:center;
            width:210px;
            height:210px;
            border-radius:50%;
            background:linear-gradient(180deg,#f2fbf5 0%, #e7f5eb 100%);
            border:1px solid #d9ebe0;
            margin-bottom:1rem;
        }}
        .ew-note {{
            color:var(--ew-muted);
            font-size:.93rem;
        }}
        .ew-spacer-sm {{
            height:.4rem;
        }}
        .ew-list-item {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:1rem;
            padding: 1rem 1.1rem;
            border:1px solid #edf1f5;
            border-radius:14px;
            background:#fbfcfd;
            margin-bottom:.8rem;
        }}
        body:has(.users-page) .stApp {{
            background:#f6faf7;
        }}
        body:has(.users-page) .block-container {{
            max-width: 1540px;
            padding-top: 2.1rem;
            padding-left: 2rem;
            padding-right: 2rem;
        }}
        body:has(.users-page) section[data-testid="stSidebar"] {{
            background:#f0fbf4;
            border-right:1px solid #dff2e6;
        }}
        body:has(.users-page) [data-testid="stSidebar"] .ew-sidebar-logo-badge {{
            display:none;
        }}
        body:has(.users-page) [data-testid="stSidebar"] .ew-sidebar-logo {{
            color:#269a4b;
        }}
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label {{
            border-radius:14px;
            padding:.95rem 1rem;
            font-weight:800;
            border:1px solid transparent;
            background:transparent;
            color:#334155;
        }}
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label > div:first-child,
        body:has(.users-page) [data-testid="stSidebar"] .stRadio input {{
            display:none !important;
        }}
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label[data-checked="true"],
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label:has(input:checked) {{
            background:#37BD74 !important;
            border-color:#37BD74 !important;
            color:#fff;
            box-shadow:0 12px 26px rgba(55,189,116,.22);
        }}
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label[data-checked="true"] p,
        body:has(.users-page) [data-testid="stSidebar"] .stRadio label:has(input:checked) p {{
            color:#fff !important;
            font-weight:900 !important;
        }}
        .users-page,
        .users-table-card-marker,
        .users-table-header-marker,
        .users-table-row-marker,
        .users-detail-link,
        .users-role-select,
        .users-delete-btn,
        .users-actions-cell {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        .users-title {{
            color:#37BD74;
            font-size:2.65rem;
            line-height:1.08;
            font-weight:900;
            margin:0;
        }}
        .users-subtitle {{
            color:#64748b;
            font-size:1.05rem;
            font-weight:600;
            margin:.4rem 0 1.8rem;
        }}
        body:has(.users-page) .users-table-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background:#fff;
            border:1px solid #dbe6db !important;
            border-radius:14px;
            box-shadow:0 14px 34px rgba(15, 23, 42, 0.07);
            overflow:hidden;
            padding:0;
            width:100%;
        }}
        body:has(.users-page) .users-table-card-marker + div [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] > div {{
            gap:0;
        }}
        body:has(.users-page) .users-table-header-marker + div [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] {{
            min-height:58px;
            align-items:stretch !important;
            background:#37BD74 !important;
            padding:0 !important;
            color:#fff !important;
            font-weight:900;
            gap:0 !important;
            border-bottom:1px solid #2fa865;
        }}
        body:has(.users-page) .users-table-row-marker + div [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] {{
            min-height:74px;
            align-items:stretch !important;
            padding:0 !important;
            border-bottom:1px solid #e5ece5;
            background:#fff;
            gap:0 !important;
        }}
        body:has(.users-page) .users-table-header-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) .users-table-row-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            display:flex !important;
            align-items:center !important;
            min-width:0 !important;
            padding:18px 16px !important;
            border-right:1px solid #e5ece5;
            overflow:hidden !important;
        }}
        body:has(.users-page) .users-table-header-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) .users-table-row-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {{
            border-right:0;
        }}
        body:has(.users-page) .users-table-header-marker + div [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) .users-table-header-marker + div [data-testid="stHorizontalBlock"] strong,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] strong,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="stHorizontalBlock"] strong {{
            color:#fff !important;
            font-size:16px !important;
            font-weight:900 !important;
            line-height:1.2 !important;
            margin:0 !important;
        }}
        body:has(.users-page) .users-table-row-marker + div [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p {{
            margin:0;
            color:#1f2937 !important;
            font-size:15px !important;
            line-height:1.25 !important;
        }}
        .users-name-cell,
        .users-role-cell {{
            color:#0f172a;
            font-weight:900;
        }}
        .users-muted-cell {{
            color:#0f172a;
            font-weight:500;
        }}
        .users-role-cell {{
            font-weight:800;
        }}
        .users-detail-link + div button,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-detail-link) + [data-testid="stElementContainer"] button,
        body:has(.users-page) [data-testid="element-container"]:has(.users-detail-link) + [data-testid="element-container"] button {{
            background:transparent !important;
            border:0 !important;
            box-shadow:none !important;
            color:#37BD74 !important;
            font-weight:800 !important;
            padding:0 !important;
            min-height:28px !important;
            justify-content:flex-start !important;
            font-size:15px !important;
        }}
        .users-role-select + div [data-baseweb="select"] > div,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-role-select) + [data-testid="stElementContainer"] [data-baseweb="select"] > div,
        body:has(.users-page) [data-testid="element-container"]:has(.users-role-select) + [data-testid="element-container"] [data-baseweb="select"] > div {{
            min-height:40px !important;
            border-radius:8px !important;
            background:#f9fbfa !important;
            border:1px solid #d7ded9 !important;
            box-shadow:none !important;
        }}
        body:has(.users-page) [data-testid="column"]:has(.users-actions-cell) [data-testid="stHorizontalBlock"] {{
            width:100% !important;
            align-items:center !important;
            gap:10px !important;
        }}
        body:has(.users-page) [data-testid="column"]:has(.users-actions-cell) [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width:0 !important;
            padding:0 !important;
        }}
        .users-delete-btn + div button,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-delete-btn) + [data-testid="stElementContainer"] button,
        body:has(.users-page) [data-testid="element-container"]:has(.users-delete-btn) + [data-testid="element-container"] button {{
            width:38px !important;
            min-width:38px !important;
            height:38px !important;
            min-height:38px !important;
            padding:0 !important;
            border-radius:999px !important;
            background:#e8286b !important;
            border-color:#e8286b !important;
            color:#fff !important;
            box-shadow:0 10px 24px rgba(232,40,107,.25) !important;
            font-size:1.15rem !important;
        }}
        .users-delete-btn + div button:disabled,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-delete-btn) + [data-testid="stElementContainer"] button:disabled,
        body:has(.users-page) [data-testid="element-container"]:has(.users-delete-btn) + [data-testid="element-container"] button:disabled {{
            opacity:.38 !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            min-height:58px !important;
            align-items:stretch !important;
            background:#37BD74 !important;
            padding:0 !important;
            gap:0 !important;
            border-bottom:1px solid #2fa865 !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            min-height:74px !important;
            align-items:stretch !important;
            background:#fff !important;
            padding:0 !important;
            gap:0 !important;
            border-bottom:1px solid #e5ece5 !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            display:flex !important;
            align-items:center !important;
            min-width:0 !important;
            padding:18px 16px !important;
            border-right:1px solid #e5ece5 !important;
            overflow:hidden !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {{
            border-right:0 !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] strong,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-header-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] strong {{
            color:#fff !important;
            font-size:16px !important;
            font-weight:900 !important;
            line-height:1.2 !important;
            margin:0 !important;
        }}
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p,
        body:has(.users-page) [data-testid="element-container"]:has(.users-table-row-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p {{
            color:#1f2937 !important;
            font-size:15px !important;
            line-height:1.25 !important;
            margin:0 !important;
        }}
        .users-detail-card {{
            margin-top:1rem;
            background:#fff;
            border:1px solid #e8eee9;
            border-radius:16px;
            padding:1rem 1.15rem;
            box-shadow:0 12px 28px rgba(15,23,42,.06);
        }}
        body:has(.locations-page) .stApp {{
            background:#f6faf7;
        }}
        body:has(.locations-page) .block-container {{
            max-width:none;
            padding-top:20px;
            padding-left:30px;
            padding-right:30px;
            padding-bottom:34px;
            overflow-x:hidden !important;
        }}
        .locations-page,
        .location-grid,
        .location-card-target,
        .location-card-content,
        .location-card-header-row,
        .location-list-content,
        .location-item-target,
        .location-add-btn,
        .icon-btn {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        .location-page-title {{
            color:#37BD74 !important;
            font-size:38px !important;
            line-height:1.1 !important;
            font-weight:900 !important;
            margin:0 0 6px 0 !important;
        }}
        .location-page-subtitle {{
            color:#64748b !important;
            font-size:16px !important;
            line-height:1.35 !important;
            font-weight:600 !important;
            margin:0 0 28px 0 !important;
        }}
        body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"] {{
            width:100% !important;
            display:grid !important;
            grid-template-columns:repeat(3, minmax(0, 1fr)) !important;
            gap:28px !important;
            align-items:stretch !important;
            overflow-x:hidden !important;
        }}
        body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width:0 !important;
            max-width:100% !important;
            overflow:visible !important;
        }}
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-grid),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-grid),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-content),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-content),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-header-row),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-header-row),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-list-content),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-list-content),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) {{
            height:0 !important;
            min-height:0 !important;
            margin:0 !important;
            padding:0 !important;
            overflow:hidden !important;
        }}
        body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background:#ffffff !important;
            border:1px solid #d8e0db !important;
            border-radius:22px !important;
            padding:22px !important;
            height:calc(100vh - 210px) !important;
            min-height:700px !important;
            box-sizing:border-box !important;
            overflow:hidden !important;
            box-shadow:none !important;
            display:flex !important;
            flex-direction:column !important;
        }}
        body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] > div {{
            height:100% !important;
            min-height:0 !important;
            display:flex !important;
            flex-direction:column !important;
            gap:0 !important;
        }}
        body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{
            height:100% !important;
            min-height:0 !important;
            display:flex !important;
            flex-direction:column !important;
            gap:0 !important;
        }}
        body:has(.locations-page) .location-card-header-row + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-header-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-header-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            flex:0 0 auto !important;
            width:100% !important;
            display:grid !important;
            grid-template-columns:minmax(0, 1fr) 132px !important;
            align-items:center !important;
            gap:16px !important;
            min-height:58px !important;
            height:58px !important;
            margin-bottom:18px !important;
            overflow:visible !important;
        }}
        body:has(.locations-page) .location-card-header-row + div [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-header-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-header-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] [data-testid="column"] {{
            min-width:0 !important;
            padding:0 !important;
            overflow:visible !important;
        }}
        .location-card-title {{
            display:block !important;
            color:#182033 !important;
            font-size:20px !important;
            line-height:1.2 !important;
            font-weight:800 !important;
            margin:0 !important;
            text-align:left !important;
            min-width:0 !important;
            overflow:visible !important;
            white-space:normal !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-add-btn) {{
            width:132px !important;
            min-width:132px !important;
            max-width:132px !important;
            justify-content:flex-end !important;
        }}
        .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            width:132px !important;
            min-width:132px !important;
            max-width:132px !important;
            height:48px !important;
            min-height:48px !important;
            padding:0 16px !important;
            border-radius:10px !important;
            background:#37BD74 !important;
            color:#ffffff !important;
            font-size:16px !important;
            font-weight:800 !important;
            border:none !important;
            box-shadow:0 6px 14px rgba(55,189,116,.25) !important;
            display:inline-flex !important;
            align-items:center !important;
            justify-content:center !important;
            white-space:nowrap !important;
        }}
        .location-add-btn + div button p,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button p,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button p {{
            color:#ffffff !important;
            font-size:16px !important;
            font-weight:800 !important;
            line-height:1 !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-list-content),
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] .location-list-content) {{
            flex:1 1 auto !important;
            width:100% !important;
            min-height:0 !important;
            display:flex !important;
            flex-direction:column !important;
            gap:14px !important;
            overflow-x:hidden !important;
            overflow-y:auto !important;
            max-height:none !important;
            padding:0 4px 0 0 !important;
            margin-top:4px !important;
            box-sizing:border-box !important;
        }}
        body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            width:100% !important;
            min-height:88px !important;
            display:grid !important;
            grid-template-columns:minmax(0, 1fr) 32px 32px 48px !important;
            align-items:center !important;
            column-gap:12px !important;
            padding:16px 18px !important;
            margin:0 !important;
            border-radius:18px !important;
            background:#f7f8fb !important;
            box-sizing:border-box !important;
            overflow:visible !important;
        }}
        body:has(.locations-page) .location-item-target.active + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target.active) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target.active) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target.active) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target.active) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            background:#eef8ef !important;
        }}
        body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] [data-testid="column"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] [data-testid="column"] {{
            display:flex !important;
            align-items:center !important;
            min-width:0 !important;
            max-width:none !important;
            padding:0 !important;
            overflow:visible !important;
        }}
        body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child {{
            width:100% !important;
            align-items:stretch !important;
            justify-content:center !important;
            text-align:left !important;
            overflow:hidden !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-item-content) {{
            position:relative !important;
            flex-direction:column !important;
            justify-content:flex-start !important;
            align-items:flex-start !important;
            overflow:hidden !important;
            text-align:left !important;
        }}
        .location-item-main,
        .location-item-content {{
            display:flex !important;
            flex-direction:column !important;
            justify-content:center !important;
            align-items:flex-start !important;
            gap:4px !important;
            min-width:0 !important;
            width:100% !important;
            text-align:left !important;
            overflow:hidden !important;
            padding:0 !important;
            margin:0 !important;
            color:#0f172a !important;
        }}
        .location-item-title,
        .location-item-name {{
            display:block !important;
            color:#182033 !important;
            font-size:18px !important;
            line-height:1.25 !important;
            font-weight:800 !important;
            margin:0 !important;
            padding:0 !important;
            text-align:left !important;
            white-space:normal !important;
            overflow-wrap:anywhere !important;
        }}
        .location-item-status,
        .location-item-meta {{
            display:block !important;
            color:#7a859f !important;
            font-size:15px !important;
            line-height:1.25 !important;
            font-weight:600 !important;
            margin:0 !important;
            padding:0 !important;
            text-align:left !important;
            white-space:normal !important;
        }}
        .location-item-url {{
            display:block !important;
            color:#9aa3b7 !important;
            font-size:14px !important;
            line-height:1.25 !important;
            font-weight:500 !important;
            margin:0 !important;
            padding:0 !important;
            text-align:left !important;
            white-space:normal !important;
            overflow-wrap:anywhere !important;
            word-break:break-word !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.icon-btn) {{
            justify-content:center !important;
            overflow:visible !important;
        }}
        .icon-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn) + [data-testid="element-container"] button {{
            width:28px !important;
            min-width:28px !important;
            max-width:28px !important;
            height:28px !important;
            min-height:28px !important;
            padding:0 !important;
            border-radius:6px !important;
            font-size:20px !important;
            background:transparent !important;
            color:#37BD74 !important;
            border:none !important;
            box-shadow:none !important;
            display:inline-flex !important;
            align-items:center !important;
            justify-content:center !important;
            overflow:visible !important;
        }}
        .icon-btn + div button p,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn) + [data-testid="stElementContainer"] button p,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn) + [data-testid="element-container"] button p {{
            color:#37BD74 !important;
            font-size:20px !important;
            line-height:1 !important;
        }}
        .icon-btn.delete + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn.delete) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn.delete) + [data-testid="element-container"] button {{
            width:40px !important;
            min-width:40px !important;
            max-width:40px !important;
            height:40px !important;
            min-height:40px !important;
            border-radius:50% !important;
            padding:0 !important;
            margin:0 !important;
            background:#e8286b !important;
            color:#ffffff !important;
            font-size:18px !important;
            border:none !important;
            box-shadow:0 8px 18px rgba(232,40,107,.22) !important;
            display:inline-flex !important;
            align-items:center !important;
            justify-content:center !important;
            overflow:visible !important;
        }}
        .icon-btn.delete + div button p,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn.delete) + [data-testid="stElementContainer"] button p,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn.delete) + [data-testid="element-container"] button p {{
            color:#ffffff !important;
            font-size:18px !important;
            line-height:1 !important;
        }}
        .empty-hint {{
            color:#64748b;
            font-size:15px;
            line-height:1.45;
            padding:.75rem 0 0;
        }}
        @media (max-width:1100px) {{
            body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"] {{
                grid-template-columns:1fr !important;
            }}
        }}
        body:has(.monitoring-page) .stApp {{
            background:#f6f8fb;
        }}
        body:has(.monitoring-page) .block-container {{
            max-width: 1500px;
            padding-top: 1.35rem;
        }}
        body:has(.monitoring-page) section[data-testid="stSidebar"] {{
            background:#f0fbf4;
            border-right:1px solid #dff2e6;
        }}
        body:has(.monitoring-page) [data-testid="stSidebar"] .ew-sidebar-brand {{
            border-bottom:0;
            margin-bottom:1.35rem;
        }}
        body:has(.monitoring-page) [data-testid="stSidebar"] .ew-sidebar-logo-badge {{
            display:none;
        }}
        body:has(.monitoring-page) [data-testid="stSidebar"] .ew-sidebar-logo {{
            color:#269a4b;
        }}
        body:has(.monitoring-page) [data-testid="stSidebar"] .stRadio label {{
            border-radius:14px;
            padding:.95rem 1rem;
            color:#52635d;
            font-weight:800;
        }}
        body:has(.monitoring-page) [data-testid="stSidebar"] .stRadio label[data-checked="true"] {{
            background:#5cc878;
            border-color:#5cc878;
            color:#fff;
            box-shadow:0 12px 26px rgba(55,189,116,.24);
        }}
        .monitoring-page {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        .monitoring-topbar {{
            display:grid;
            grid-template-columns:minmax(280px,1fr) auto;
            gap:24px;
            align-items:center;
            margin:0 0 1.35rem 0;
        }}
        .monitoring-title {{
            color:#18251f;
            font-size:1.35rem;
            font-weight:900;
            line-height:1.1;
        }}
        .monitoring-user {{
            color:#64748b;
            font-size:.92rem;
            font-weight:700;
            margin-top:.22rem;
        }}
        .monitoring-top-actions {{
            display:flex;
            align-items:center;
            gap:28px;
            color:#98a2b3;
            font-weight:900;
        }}
        .monitoring-tab-active {{
            color:#269a4b;
            border-bottom:2px solid #37BD74;
            padding-bottom:.75rem;
        }}
        .monitoring-filter-card {{
            background:transparent;
            margin-bottom:1.35rem;
        }}
        .monitoring-filter-row {{
            display:block;
        }}
        body:has(.monitoring-page) .monitoring-filter-row + div [data-testid="stHorizontalBlock"] {{
            align-items:end;
            gap:22px;
        }}
        body:has(.monitoring-page) .stSelectbox label,
        body:has(.monitoring-page) .stRadio label,
        body:has(.monitoring-page) .stToggle label {{
            color:#1f2a24 !important;
            font-weight:900 !important;
        }}
        body:has(.monitoring-page) .stSelectbox [data-baseweb="select"] > div,
        body:has(.monitoring-page) .stTextInput input {{
            min-height:54px !important;
            border:1px solid #d6ddd9 !important;
            border-radius:5px !important;
            background:#f9fbfa !important;
            box-shadow:none !important;
            font-size:1.05rem !important;
        }}
        body:has(.monitoring-page) .stRadio > div {{
            display:flex;
            gap:8px;
            padding:5px;
            border-radius:999px;
            background:#eef5f0;
        }}
        body:has(.monitoring-page) main .stRadio label {{
            border-radius:999px;
            padding:.62rem 1.6rem;
            border:0;
            color:#58bf74;
            background:transparent;
        }}
        body:has(.monitoring-page) main .stRadio label[data-checked="true"] {{
            background:#5cc878;
            color:#fff;
            box-shadow:0 10px 24px rgba(55,189,116,.22);
        }}
        .monitoring-main-grid {{
            display:block;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
            align-items:start;
            gap:24px;
        }}
        .camera-grid {{
            display:grid;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:20px;
        }}
        .camera-card {{
            position:relative;
            overflow:hidden;
            border-radius:20px;
            border:3px solid transparent;
            background:#111;
            box-shadow:0 18px 34px rgba(15,23,42,.11);
            min-height:278px;
            margin-bottom:.45rem;
        }}
        .camera-card.alert {{
            border-color:#e8286b;
            box-shadow:0 16px 36px rgba(232,40,107,.20);
        }}
        .camera-card.focused {{
            min-height:500px;
        }}
        .camera-card.thumb {{
            min-height:155px;
            border-radius:16px;
        }}
        .camera-preview {{
            position:absolute;
            inset:0;
            background-size:cover;
            background-position:center;
        }}
        .camera-placeholder {{
            position:absolute;
            inset:0;
            display:flex;
            align-items:center;
            justify-content:center;
            color:#eef2f7;
            font-weight:900;
            background:
                radial-gradient(circle at 42% 45%, rgba(255,255,255,.18), transparent 13%),
                linear-gradient(135deg,#8f733c 0%,#293f37 100%);
        }}
        .camera-header {{
            position:absolute;
            z-index:2;
            top:18px;
            left:18px;
            right:18px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
        }}
        .camera-name {{
            max-width:58%;
            padding:.55rem .85rem;
            border-radius:9px;
            background:rgba(0,0,0,.70);
            color:#fff;
            font-weight:900;
            font-size:.92rem;
        }}
        .camera-status-badge {{
            padding:.55rem .95rem;
            border-radius:9px;
            color:#fff;
            background:#5cc878;
            font-weight:900;
            font-size:.88rem;
        }}
        .camera-status-badge.offline {{
            background:#8b9491;
        }}
        .camera-status-badge.error {{
            background:#e8286b;
        }}
        .camera-detection-box {{
            position:absolute;
            z-index:2;
            top:34%;
            left:51%;
            width:32%;
            height:38%;
            transform:translateX(-14%);
            border:3px solid #cf183d;
            background:rgba(207,24,61,.66);
            color:#fff;
            display:flex;
            align-items:flex-start;
            justify-content:center;
            text-align:center;
            padding-top:1.05rem;
            font-weight:900;
            line-height:1.2;
        }}
        .camera-meta {{
            position:absolute;
            z-index:2;
            right:20px;
            bottom:18px;
            color:#fff;
            text-align:right;
            font-weight:900;
            text-shadow:0 1px 3px rgba(0,0,0,.65);
        }}
        .camera-focus-layout,
        .camera-focus-main {{
            display:block;
        }}
        .camera-thumb-row {{
            margin-top:14px;
        }}
        .camera-thumb-card {{
            display:block;
        }}
        .monitoring-side-panel-target {{
            display:block;
            height:0;
            overflow:hidden;
        }}
        .monitoring-side-panel,
        body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            background:#fff;
            border:0;
            border-radius:18px;
            padding:1.35rem 1.35rem 1.25rem;
            box-shadow:0 12px 32px rgba(15,23,42,.06);
            min-height:0;
            position:sticky;
            top:1rem;
        }}
        body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] > div {{
            gap:.75rem;
        }}
        .monitoring-side-title {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
            color:#18251f;
            font-size:1.05rem;
            font-weight:900;
            margin-bottom:1.35rem;
            text-transform:uppercase;
        }}
        .monitoring-side-dot {{
            width:10px;
            height:10px;
            border-radius:999px;
            background:#c4001a;
        }}
        .latest-violation-list {{
            max-height:560px;
            overflow-y:auto;
            padding-right:.2rem;
        }}
        .latest-violation-item {{
            background:#f1f3f2;
            border-radius:18px;
            padding:1.1rem 1rem 1.2rem;
            margin-bottom:1.2rem;
        }}
        .latest-violation-top {{
            display:flex;
            justify-content:space-between;
            gap:10px;
            color:#667085;
            font-weight:700;
            font-size:.88rem;
        }}
        .latest-violation-type {{
            color:#c5142f;
            font-weight:900;
            font-size:1.08rem;
            margin:.8rem 0 .65rem;
        }}
        .latest-violation-preview {{
            min-height:130px;
            border:2px solid #c5142f;
            border-radius:14px;
            background:#111;
            background-size:cover;
            background-position:center;
            position:relative;
            overflow:hidden;
        }}
        .latest-confidence {{
            position:absolute;
            left:16px;
            bottom:16px;
            padding:.45rem .8rem;
            border-radius:999px;
            background:#d32248;
            color:#fff;
            font-weight:900;
            font-size:.82rem;
        }}
        .camera-status-list {{
            display:flex;
            flex-direction:column;
            gap:.8rem;
        }}
        .camera-status-row {{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:14px;
            padding:1rem;
            border-radius:16px;
            background:#f6f8fb;
            border:1px solid #e6ece8;
            font-weight:800;
        }}
        .camera-status-row span:last-child {{
            padding:.35rem .7rem;
            border-radius:999px;
            color:#fff;
            background:#37BD74;
            font-size:.82rem;
        }}
        .camera-status-row.warn span:last-child {{
            background:#f59e0b;
        }}
        .camera-status-row.bad span:last-child {{
            background:#e8286b;
        }}
        .ew-field-grid {{
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .9rem;
        }}
        .ew-field {{
            border:1px dashed #d6dde6;
            border-radius:14px;
            padding: .95rem 1rem;
            background:#fff;
        }}
        .ew-field label {{
            display:block;
            color:var(--ew-muted);
            margin-bottom:.3rem;
        }}
        @media (max-width: 900px) {{
            section[data-testid="stSidebar"] {{
                min-width: auto !important;
            }}
            .block-container {{
                padding-top: .9rem;
            }}
            .ew-page-header {{
                flex-direction:column;
            }}
            .ew-title {{
                font-size: 2.25rem;
            }}
            .auth-hero-heading {{
                font-size:3.3rem;
            }}
            .auth-register-heading {{
                font-size:2.9rem;
                margin-top:1rem;
            }}
            .auth-register-left {{
                min-height:360px;
                padding:30px 24px;
            }}
            body:has(.auth-page) .block-container {{
                padding-top: .5rem;
            }}
            body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
                max-width:none;
                margin:0;
                padding:1.25rem;
            }}
            .ew-field-grid {{
                grid-template-columns: 1fr;
            }}
            .monitoring-topbar {{
                grid-template-columns:1fr;
            }}
            .camera-grid {{
                grid-template-columns:1fr;
            }}
            .camera-card,
            .camera-card.focused {{
                min-height:260px;
            }}
            .monitoring-side-panel {{
                min-height:auto;
                position:relative;
            }}
            .stat-grid, .two-col-grid, .three-col-grid, .filter-row, .admin-three-col {{
                grid-template-columns:1fr;
            }}
        }}
        @media (max-width: 768px) {{
            body:has(.auth-signin) .block-container,
            body:has(.auth-signup) .block-container,
            body:has(.auth-recovery) .block-container {{
                max-width:100% !important;
                min-height:100vh !important;
                padding:12px 12px !important;
            }}
            body:has(.auth-signin) [data-testid="stHorizontalBlock"]:has(.auth-login-left),
            body:has(.auth-recovery):not(:has(.auth-reset)) [data-testid="stHorizontalBlock"]:has(.recovery-left),
            body:has(.auth-signup) [data-testid="stHorizontalBlock"]:has(.auth-register-left),
            body:has(.auth-reset) [data-testid="stHorizontalBlock"]:has(.reset-left-panel) {{
                width:100% !important;
                display:block !important;
                min-height:auto !important;
                margin:0 auto !important;
                gap:0 !important;
            }}
            .auth-login-left,
            .recovery-left,
            body:has(.auth-signup) .auth-register-left,
            body:has(.auth-reset) .reset-left-panel,
            body:has(.auth-signin) .auth-image-target + div {{
                display:none !important;
            }}
            body:has(.auth-signin) .auth-login-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-signup) .auth-signup-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-recovery) .recovery-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.auth-reset) .reset-card-anchor + div [data-testid="stVerticalBlockBorderWrapper"] {{
                width:100% !important;
                max-width:390px !important;
                min-height:auto !important;
                margin:0 auto !important;
                padding:24px 18px !important;
                border-radius:18px !important;
            }}
            body:has(.auth-signin) .auth-title,
            body:has(.auth-signup) .auth-title,
            .recovery-card-title,
            body:has(.auth-reset) .recovery-card-title {{
                font-size:21px !important;
                line-height:1.18 !important;
                margin-bottom:8px !important;
            }}
            .auth-subtitle,
            .recovery-card-desc {{
                font-size:13px !important;
                line-height:1.35 !important;
                margin-bottom:18px !important;
            }}
            body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) {{
                gap:5px !important;
            }}
            body:has(.auth-otp) [data-testid="stHorizontalBlock"]:has(.otp-input-row) input {{
                min-height:40px !important;
                height:40px !important;
                font-size:15px !important;
            }}
        }}

        /* Responsive shell normalization: keep Streamlit full-width and prevent body-level horizontal drift. */
        :root {{
            --sidebar-width-desktop: 280px;
            --sidebar-width-laptop: 240px;
            --sidebar-width-tablet: 82px;
            --main-padding-desktop-x: 36px;
            --main-padding-desktop-y: 32px;
            --main-padding-laptop: 28px;
            --main-padding-tablet: 22px;
            --main-padding-mobile: 16px;
        }}
        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        main {{
            max-width: 100vw !important;
            overflow-x: hidden !important;
            box-sizing: border-box !important;
        }}
        .stApp {{
            background: #f6faf7;
        }}
        .block-container,
        body:has(.monitoring-page) .block-container,
        body:has(.reports-page) .block-container,
        body:has(.violations-page) .block-container,
        body:has(.locations-page) .block-container,
        body:has(.users-page) .block-container,
        body:has(.profile-page) .block-container {{
            max-width: none !important;
            width: 100% !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            padding: var(--main-padding-desktop-y) var(--main-padding-desktop-x) 48px !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
        }}
        [data-testid="stMainBlockContainer"],
        body:has(.monitoring-page) [data-testid="stMainBlockContainer"],
        body:has(.reports-page) [data-testid="stMainBlockContainer"],
        body:has(.violations-page) [data-testid="stMainBlockContainer"],
        body:has(.locations-page) [data-testid="stMainBlockContainer"],
        body:has(.users-page) [data-testid="stMainBlockContainer"],
        body:has(.profile-page) [data-testid="stMainBlockContainer"] {{
            width: 100% !important;
            max-width: 100% !important;
            justify-content: flex-start !important;
            align-items: stretch !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            overflow-x: hidden !important;
        }}
        section[data-testid="stSidebar"] {{
            width: var(--sidebar-width-desktop) !important;
            min-width: var(--sidebar-width-desktop) !important;
            max-width: var(--sidebar-width-desktop) !important;
            flex: 0 0 var(--sidebar-width-desktop) !important;
            overflow-x: hidden !important;
        }}
        section[data-testid="stSidebar"] > div:first-child {{
            width: var(--sidebar-width-desktop) !important;
            min-width: var(--sidebar-width-desktop) !important;
            max-width: var(--sidebar-width-desktop) !important;
            padding: 38px 22px 24px !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
        }}
        .sidebar-brand {{
            font-size: 28px !important;
            line-height: 1.08 !important;
            margin-bottom: 8px !important;
        }}
        .sidebar-brand-short {{
            display: none;
        }}
        .sidebar-role-label {{
            font-size: 12px !important;
            margin-bottom: 36px !important;
        }}
        [data-testid="stSidebar"] .stButton > button,
        .sidebar-nav-marker + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button,
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button {{
            min-height: 48px !important;
            padding: 11px 12px !important;
            border-radius: 14px !important;
            font-size: 15px !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        [data-testid="stSidebar"] .stButton > button p,
        .sidebar-nav-marker + div[data-testid="stButton"] button p,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p,
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p {{
            font-size: 15px !important;
            line-height: 1.15 !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        .sidebar-nav-marker + div[data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"],
        div:has(.sidebar-nav-marker) + div[data-testid="stButton"] {{
            margin-bottom: 10px !important;
        }}
        .sidebar-footer-spacer {{
            height: 28px !important;
        }}
        .sidebar-user-card {{
            min-height: 72px !important;
            padding: 12px !important;
            border-radius: 18px !important;
            gap: 10px !important;
        }}
        .sidebar-user-avatar {{
            width: 42px !important;
            height: 42px !important;
            flex-basis: 42px !important;
        }}
        .sidebar-user-code {{
            font-size: 15px !important;
        }}
        .sidebar-user-name {{
            font-size: 13px !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"],
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"],
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"] {{
            height: 72px !important;
            margin-top: -72px !important;
        }}
        .sidebar-user-card-click + div[data-testid="stButton"] button,
        div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button,
        div:has(.sidebar-user-card-click) + div[data-testid="stButton"] button {{
            height: 72px !important;
            min-height: 72px !important;
        }}
        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        .reports-table-card,
        .users-table-card,
        .users-detail-card,
        .ew-card {{
            max-width: 100% !important;
            overflow-x: auto !important;
            box-sizing: border-box !important;
        }}
        .locations-title,
        .location-page-title {{
            color: #58c878 !important;
            font-size: clamp(30px, 4vw, 46px) !important;
            letter-spacing: 0 !important;
        }}
        .locations-subtitle,
        .location-page-subtitle {{
            max-width: 860px !important;
            margin-bottom: 24px !important;
        }}
        body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"] {{
            grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
            gap: 24px !important;
            align-items: stretch !important;
            width: 100% !important;
        }}
        body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            border: 1px solid #dfe7e2 !important;
            border-radius: 22px !important;
            padding: 24px !important;
            height: auto !important;
            min-height: 640px !important;
            box-shadow: 0 18px 38px rgba(20, 43, 30, 0.07) !important;
        }}
        body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            grid-template-columns: minmax(0, 1fr) 34px 34px 44px !important;
            min-height: 82px !important;
            padding: 15px 16px !important;
            border-radius: 13px !important;
            background: #f8fafc !important;
            column-gap: 10px !important;
        }}
        .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            background: #5dc878 !important;
            border-color: #5dc878 !important;
        }}
        .icon-btn.delete + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn.delete) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn.delete) + [data-testid="element-container"] button {{
            background: #df2371 !important;
        }}
        @media (min-width: 1024px) and (max-width: 1279px) {{
            .block-container,
            body:has(.monitoring-page) .block-container,
            body:has(.reports-page) .block-container,
            body:has(.violations-page) .block-container,
            body:has(.locations-page) .block-container,
            body:has(.users-page) .block-container,
            body:has(.profile-page) .block-container {{
                padding: var(--main-padding-laptop) !important;
            }}
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div:first-child {{
                width: var(--sidebar-width-laptop) !important;
                min-width: var(--sidebar-width-laptop) !important;
                max-width: var(--sidebar-width-laptop) !important;
                flex-basis: var(--sidebar-width-laptop) !important;
            }}
            section[data-testid="stSidebar"] > div:first-child {{
                padding: 32px 18px 22px !important;
            }}
        }}
        @media (min-width: 768px) and (max-width: 1023px) {{
            .block-container,
            body:has(.monitoring-page) .block-container,
            body:has(.reports-page) .block-container,
            body:has(.violations-page) .block-container,
            body:has(.locations-page) .block-container,
            body:has(.users-page) .block-container,
            body:has(.profile-page) .block-container {{
                padding: var(--main-padding-tablet) !important;
            }}
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div:first-child {{
                width: var(--sidebar-width-tablet) !important;
                min-width: var(--sidebar-width-tablet) !important;
                max-width: var(--sidebar-width-tablet) !important;
                flex-basis: var(--sidebar-width-tablet) !important;
            }}
            section[data-testid="stSidebar"] > div:first-child {{
                padding: 24px 10px 18px !important;
            }}
            .sidebar-brand-full,
            .sidebar-role-label,
            .sidebar-user-meta {{
                display: none !important;
            }}
            .sidebar-brand-short {{
                display: block !important;
                text-align: center !important;
                font-size: 20px !important;
            }}
            [data-testid="stSidebar"] .stButton > button,
            .sidebar-nav-marker + div[data-testid="stButton"] button,
            div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button,
            div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button {{
                width: 54px !important;
                min-height: 48px !important;
                padding: 0 !important;
                justify-content: center !important;
                border-radius: 14px !important;
            }}
            [data-testid="stSidebar"] .stButton > button p,
            .sidebar-nav-marker + div[data-testid="stButton"] button p,
            div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p,
            div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p {{
                width: 24px !important;
                max-width: 24px !important;
                height: 24px !important;
                overflow: hidden !important;
                white-space: nowrap !important;
                font-size: 0 !important;
                line-height: 1 !important;
            }}
            [data-testid="stSidebar"] .stButton > button p::first-letter,
            .sidebar-nav-marker + div[data-testid="stButton"] button p::first-letter,
            div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p::first-letter,
            div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button p::first-letter {{
                font-size: 20px !important;
            }}
            .sidebar-user-card {{
                min-height: 54px !important;
                justify-content: center !important;
                padding: 6px !important;
            }}
            .sidebar-user-avatar {{
                width: 34px !important;
                height: 34px !important;
                flex-basis: 34px !important;
            }}
            body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"],
            .monitoring-topbar,
            .camera-grid,
            .ew-field-grid {{
                grid-template-columns: 1fr !important;
            }}
            body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
                min-height: 420px !important;
            }}
        }}
        @media (max-width: 767px) {{
            .block-container,
            body:has(.monitoring-page) .block-container,
            body:has(.reports-page) .block-container,
            body:has(.violations-page) .block-container,
            body:has(.locations-page) .block-container,
            body:has(.users-page) .block-container,
            body:has(.profile-page) .block-container {{
                width: 100vw !important;
                max-width: 100vw !important;
                padding: var(--main-padding-mobile) !important;
            }}
            section[data-testid="stSidebar"] {{
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                flex-basis: 0 !important;
                border-right: 0 !important;
                overflow: hidden !important;
            }}
            section[data-testid="stSidebar"] > div:first-child {{
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            }}
            [data-testid="collapsedControl"] {{
                display: flex !important;
                margin: 8px 0 0 8px !important;
            }}
            .ew-page-header,
            .monitoring-topbar,
            body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"],
            .camera-grid,
            .ew-field-grid {{
                grid-template-columns: 1fr !important;
                width: 100% !important;
            }}
            .location-page-title {{
                font-size: 30px !important;
            }}
            body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
                min-height: auto !important;
                padding: 18px !important;
            }}
            body:has(.locations-page) .location-card-header-row + div [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-header-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="element-container"]:has(.location-card-header-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                grid-template-columns: minmax(0, 1fr) 104px !important;
                gap: 10px !important;
            }}
            body:has(.locations-page) [data-testid="column"]:has(.location-add-btn),
            .location-add-btn + div button,
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
            body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
                width: 104px !important;
                min-width: 104px !important;
                max-width: 104px !important;
            }}
            body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                grid-template-columns: minmax(0, 1fr) 30px 30px 40px !important;
                column-gap: 7px !important;
                padding: 13px 12px !important;
            }}
        }}

        /* Pixel-focused custom report page. Streamlit widgets are kept only for state/export hooks. */
        .report-page,
        .report-topbar-marker,
        .report-export-row,
        .report-filter-card-marker,
        .report-filter-controls,
        .report-search-marker,
        .report-date-marker,
        .report-search-button-marker,
        .report-pdf-marker,
        .report-excel-marker {{
            display: block;
            height: 0;
            overflow: hidden;
        }}
        body:has(.report-page) .stApp {{
            background: #f6faf7 !important;
        }}
        body:has(.report-page) header[data-testid="stHeader"] {{
            display: none !important;
        }}
        body:has(.report-page) .block-container {{
            width: 100% !important;
            max-width: none !important;
            padding: 46px 48px 58px !important;
            overflow-x: hidden !important;
            box-sizing: border-box !important;
        }}
        .report-shell {{
            color: #111827;
            font-family: "Segoe UI", "Inter", Arial, sans-serif;
        }}
        body:has(.report-page) .report-topbar-marker + div [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: minmax(320px, 730px) minmax(360px, 1fr) !important;
            gap: 34px !important;
            align-items: center !important;
            margin-bottom: 38px !important;
        }}
        body:has(.report-page) .report-topbar-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width: 0 !important;
            padding: 0 !important;
        }}
        .report-top-nav {{
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 28px;
            color: #9aa0b4;
            font-size: 24px;
            font-weight: 900;
            white-space: nowrap;
        }}
        .report-tab-active {{
            color: #3fa652;
            padding-bottom: 14px;
            border-bottom: 3px solid #5fbe73;
        }}
        .report-system-badge {{
            background: #58ad50;
            color: #fff;
            padding: 8px 14px;
            border-radius: 7px;
            font-size: 22px;
            font-weight: 800;
        }}
        .report-nav-icon {{
            color: #687082;
            font-size: 23px;
            line-height: 1;
        }}
        body:has(.report-page) .report-search-marker + div .stTextInput label,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"] .stTextInput label,
        body:has(.report-page) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"] .stTextInput label {{
            display: none !important;
        }}
        body:has(.report-page) .report-search-marker + div .stTextInput input,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
        body:has(.report-page) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"] .stTextInput input {{
            height: 64px !important;
            min-height: 64px !important;
            border-radius: 999px !important;
            border: 0 !important;
            background: #e9eeee !important;
            box-shadow: none !important;
            padding-left: 74px !important;
            color: #6b7280 !important;
            font-size: 22px !important;
            font-weight: 500 !important;
        }}
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"],
        body:has(.report-page) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"] {{
            position: relative !important;
        }}
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"]::before,
        body:has(.report-page) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"]::before {{
            content: "⌕";
            position: absolute;
            left: 30px;
            top: 13px;
            z-index: 4;
            color: #75817c;
            font-size: 34px;
            line-height: 1;
        }}
        .report-title-row {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 28px;
            align-items: center;
            margin-bottom: 44px;
        }}
        .report-title {{
            color: #5fbe73;
            font-size: 52px;
            line-height: 1.05;
            font-weight: 900;
            letter-spacing: 0;
        }}
        body:has(.report-page) .report-title-row + div [data-testid="stHorizontalBlock"],
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-export-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.report-page) [data-testid="element-container"]:has(.report-export-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: 238px 202px !important;
            gap: 18px !important;
            justify-content: end !important;
            align-items: center !important;
        }}
        body:has(.report-page) .report-pdf-marker + div .stDownloadButton > button,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-pdf-marker) + [data-testid="stElementContainer"] .stDownloadButton > button,
        body:has(.report-page) [data-testid="element-container"]:has(.report-pdf-marker) + [data-testid="element-container"] .stDownloadButton > button {{
            height: 62px !important;
            min-height: 62px !important;
            width: 100% !important;
            border-radius: 5px !important;
            background: #5fbe73 !important;
            border: 2px solid #5fbe73 !important;
            color: #fff !important;
            box-shadow: 0 6px 12px rgba(17,24,39,.20) !important;
            font-size: 24px !important;
            font-weight: 900 !important;
        }}
        body:has(.report-page) .report-excel-marker + div .stDownloadButton > button,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-excel-marker) + [data-testid="stElementContainer"] .stDownloadButton > button,
        body:has(.report-page) [data-testid="element-container"]:has(.report-excel-marker) + [data-testid="element-container"] .stDownloadButton > button {{
            height: 62px !important;
            min-height: 62px !important;
            width: 100% !important;
            border-radius: 5px !important;
            background: #fff !important;
            border: 3px solid #5fbe73 !important;
            color: #5fbe73 !important;
            box-shadow: none !important;
            font-size: 24px !important;
            font-weight: 900 !important;
        }}
        .report-stat-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }}
        .report-stat-card {{
            background: #fff;
            border: 1px solid #dfe8e2;
            border-radius: 30px;
            min-height: 190px;
            padding: 40px 42px 32px;
            box-shadow: 0 22px 44px rgba(31,49,38,.06);
        }}
        .report-stat-label {{
            color: #697287;
            font-size: 23px;
            line-height: 1.2;
            font-weight: 900;
            text-transform: uppercase;
            margin-bottom: 22px;
        }}
        .report-stat-value {{
            color: #5fbe73;
            font-size: 42px;
            line-height: 1.1;
            font-weight: 900;
        }}
        .report-filter-card {{
            background: #fff;
            border: 1px solid #dfe8e2;
            border-radius: 30px;
            min-height: 132px;
            padding: 34px 40px;
            margin-bottom: 40px;
            box-shadow: 0 18px 42px rgba(31,49,38,.05);
            display: flex;
            align-items: center;
            gap: 24px;
        }}
        body:has(.report-page) .report-filter-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-filter-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.report-page) [data-testid="element-container"]:has(.report-filter-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #fff !important;
            border: 1px solid #dfe8e2 !important;
            border-radius: 30px !important;
            min-height: 132px !important;
            padding: 34px 40px !important;
            margin-bottom: 40px !important;
            box-shadow: 0 18px 42px rgba(31,49,38,.05) !important;
        }}
        body:has(.report-page) .report-filter-card-marker + div [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-filter-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.report-page) [data-testid="element-container"]:has(.report-filter-card-marker) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] > div {{
            gap: 0 !important;
        }}
        body:has(.report-page) .report-filter-card + div [data-testid="stHorizontalBlock"],
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-filter-controls) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.report-page) [data-testid="element-container"]:has(.report-filter-controls) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: 276px 230px minmax(0, 1fr) !important;
            gap: 24px !important;
            align-items: center !important;
        }}
        body:has(.report-page) .report-date-marker + div .stDateInput label,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-date-marker) + [data-testid="stElementContainer"] .stDateInput label,
        body:has(.report-page) [data-testid="element-container"]:has(.report-date-marker) + [data-testid="element-container"] .stDateInput label {{
            display: none !important;
        }}
        body:has(.report-page) .report-date-marker + div .stDateInput [data-baseweb="input"] > div,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-date-marker) + [data-testid="stElementContainer"] .stDateInput [data-baseweb="input"] > div,
        body:has(.report-page) [data-testid="element-container"]:has(.report-date-marker) + [data-testid="element-container"] .stDateInput [data-baseweb="input"] > div {{
            height: 68px !important;
            min-height: 68px !important;
            border-radius: 7px !important;
            border: 2px solid #bfc5c2 !important;
            background: #fff !important;
            box-shadow: none !important;
        }}
        body:has(.report-page) .report-search-button-marker + div button,
        body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-button-marker) + [data-testid="stElementContainer"] button,
        body:has(.report-page) [data-testid="element-container"]:has(.report-search-button-marker) + [data-testid="element-container"] button {{
            height: 62px !important;
            min-height: 62px !important;
            width: 230px !important;
            border-radius: 6px !important;
            background: #5fbe73 !important;
            border-color: #5fbe73 !important;
            color: #fff !important;
            font-size: 23px !important;
            font-weight: 900 !important;
            box-shadow: 0 6px 12px rgba(17,24,39,.20) !important;
        }}
        .report-table-card {{
            background: #fff;
            border: 1px solid #dfe8e2;
            border-radius: 30px;
            overflow: hidden;
            box-shadow: 0 18px 42px rgba(31,49,38,.05);
        }}
        .report-table-scroll {{
            width: 100%;
            overflow-x: auto;
        }}
        .report-table {{
            width: 100%;
            min-width: 920px;
            border-collapse: collapse;
            color: #061015;
            font-size: 25px;
        }}
        .report-table thead tr {{
            height: 72px;
            background: #f0f1f2;
        }}
        .report-table th {{
            padding: 20px 42px;
            text-align: left;
            font-size: 22px;
            line-height: 1.15;
            font-weight: 900;
            white-space: nowrap;
        }}
        .report-table tbody tr {{
            height: 82px;
            border-bottom: 1px solid #edf0ef;
        }}
        .report-table tbody tr:last-child {{
            border-bottom: 0;
        }}
        .report-table td {{
            padding: 18px 42px;
            font-weight: 500;
            line-height: 1.2;
        }}
        .report-table td:first-child,
        .report-table td:nth-child(3),
        .report-table td:nth-child(4) {{
            font-weight: 900;
        }}
        @media (max-width: 1200px) {{
            body:has(.report-page) .block-container {{
                padding: 32px 28px 46px !important;
            }}
            .report-topbar,
            .report-title-row {{
                grid-template-columns: 1fr;
                gap: 22px;
            }}
            .report-top-nav {{
                justify-content: flex-start;
                flex-wrap: wrap;
            }}
            body:has(.report-page) .report-title-row + div [data-testid="stHorizontalBlock"],
            body:has(.report-page) [data-testid="stElementContainer"]:has(.report-export-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.report-page) [data-testid="element-container"]:has(.report-export-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                justify-content: start !important;
            }}
        }}
        @media (max-width: 768px) {{
            body:has(.report-page) .block-container {{
                padding: 18px 14px 32px !important;
            }}
            .report-topbar,
            .report-title-row,
            .report-stat-grid {{
                grid-template-columns: 1fr;
            }}
            .report-title {{
                font-size: 36px;
            }}
            .report-top-nav {{
                gap: 14px;
                font-size: 17px;
            }}
            .report-system-badge {{
                font-size: 15px;
            }}
            body:has(.report-page) .report-search-marker + div .stTextInput input,
            body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
            body:has(.report-page) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"] .stTextInput input {{
                height: 56px !important;
                min-height: 56px !important;
                font-size: 16px !important;
                padding-left: 58px !important;
            }}
            body:has(.report-page) .report-title-row + div [data-testid="stHorizontalBlock"],
            body:has(.report-page) [data-testid="stElementContainer"]:has(.report-export-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {{
                grid-template-columns: 1fr 1fr !important;
                width: 100% !important;
            }}
            body:has(.report-page) .report-filter-card + div [data-testid="stHorizontalBlock"],
            body:has(.report-page) [data-testid="stElementContainer"]:has(.report-filter-controls) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {{
                grid-template-columns: 1fr !important;
            }}
            body:has(.report-page) .report-search-button-marker + div button,
            body:has(.report-page) [data-testid="stElementContainer"]:has(.report-search-button-marker) + [data-testid="stElementContainer"] button {{
                width: 100% !important;
            }}
            .report-stat-card {{
                min-height: 150px;
                padding: 28px;
            }}
            .report-stat-label {{
                font-size: 17px;
            }}
            .report-stat-value {{
                font-size: 30px;
            }}
            .report-table th,
            .report-table td {{
                padding-left: 22px;
                padding-right: 22px;
                font-size: 18px;
            }}
        }}

        /* EduWatch realtime dashboard: fixed viewport on desktop/laptop, scrollable function view on mobile. */
        .monitoring-mobile-actions {{
            display: block;
            height: 0;
            overflow: hidden;
        }}
        body:has(.monitoring-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] {{
            display: none !important;
        }}
        body:has(.monitoring-page) .block-container {{
            --edu-header-h: 58px;
            --edu-gap: 12px;
            --edu-right: 336px;
            height: 100vh !important;
            height: 100dvh !important;
            padding: 10px 14px !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) [data-testid="stVerticalBlock"] {{
            min-height: 0 !important;
        }}
        body:has(.monitoring-page) .monitoring-topbar {{
            min-height: var(--edu-header-h) !important;
            height: var(--edu-header-h) !important;
            margin: 0 0 var(--edu-gap) 0 !important;
            grid-template-columns: minmax(0, 1fr) auto !important;
            gap: 12px !important;
        }}
        body:has(.monitoring-page) .monitoring-title {{
            font-size: 1.1rem !important;
        }}
        body:has(.monitoring-page) .monitoring-user {{
            font-size: .82rem !important;
        }}
        body:has(.monitoring-page) .monitoring-top-actions {{
            gap: 16px !important;
            font-size: .86rem !important;
        }}
        body:has(.monitoring-page) .monitoring-filter-card {{
            margin-bottom: var(--edu-gap) !important;
        }}
        body:has(.monitoring-page) .monitoring-filter-row + div [data-testid="stHorizontalBlock"] {{
            gap: 10px !important;
            align-items: end !important;
        }}
        body:has(.monitoring-page) .stSelectbox label,
        body:has(.monitoring-page) .stRadio label,
        body:has(.monitoring-page) .stToggle label {{
            font-size: .78rem !important;
            line-height: 1.1 !important;
            margin-bottom: 2px !important;
        }}
        body:has(.monitoring-page) .stSelectbox [data-baseweb="select"] > div,
        body:has(.monitoring-page) .stTextInput input {{
            min-height: 42px !important;
            height: 42px !important;
            border-radius: 10px !important;
            font-size: .9rem !important;
        }}
        body:has(.monitoring-page) .stRadio > div {{
            min-height: 42px !important;
            padding: 4px !important;
        }}
        body:has(.monitoring-page) main .stRadio label {{
            min-height: 32px !important;
            padding: .42rem .85rem !important;
            font-size: .76rem !important;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) var(--edu-right) !important;
            gap: var(--edu-gap) !important;
            height: calc(100dvh - var(--edu-header-h) - 86px) !important;
            min-height: 0 !important;
            overflow: hidden !important;
            align-items: stretch !important;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            width: auto !important;
            min-width: 0 !important;
            height: 100% !important;
            min-height: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child > div,
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stVerticalBlock"] {{
            height: 100% !important;
            min-height: 0 !important;
            display: grid !important;
            grid-template-rows: repeat(2, minmax(0, 1fr)) !important;
            gap: var(--edu-gap) !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: var(--edu-gap) !important;
            min-height: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width: 0 !important;
            min-height: 0 !important;
            height: 100% !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .camera-card {{
            height: 100% !important;
            min-height: 0 !important;
            max-height: none !important;
            margin: 0 !important;
            border-radius: 18px !important;
            border-width: 2px !important;
            box-shadow: 0 12px 28px rgba(15,23,42,.10) !important;
        }}
        body:has(.monitoring-page) .camera-card.alert {{
            box-shadow: 0 14px 34px rgba(232,40,107,.24) !important;
        }}
        body:has(.monitoring-page) .camera-header {{
            top: 12px !important;
            left: 12px !important;
            right: 12px !important;
            gap: 8px !important;
        }}
        body:has(.monitoring-page) .camera-name {{
            max-width: 64% !important;
            padding: .4rem .62rem !important;
            font-size: .78rem !important;
        }}
        body:has(.monitoring-page) .camera-status-badge {{
            padding: .4rem .62rem !important;
            font-size: .72rem !important;
            white-space: nowrap !important;
        }}
        body:has(.monitoring-page) .camera-detection-box {{
            top: 34% !important;
            height: 34% !important;
            padding-top: .72rem !important;
            font-size: .86rem !important;
        }}
        body:has(.monitoring-page) .camera-meta {{
            right: 12px !important;
            bottom: 10px !important;
            font-size: .74rem !important;
        }}
        body:has(.monitoring-page) [data-testid="stElementContainer"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"],
        body:has(.monitoring-page) [data-testid="element-container"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] {{
            width: 108px !important;
            margin-top: -44px !important;
            margin-left: 12px !important;
            position: relative !important;
            z-index: 5 !important;
        }}
        body:has(.monitoring-page) [data-testid="stElementContainer"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] button,
        body:has(.monitoring-page) [data-testid="element-container"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] button {{
            min-height: 32px !important;
            height: 32px !important;
            border-radius: 999px !important;
            padding: 0 12px !important;
            font-size: .75rem !important;
            background: rgba(255,255,255,.88) !important;
            border-color: rgba(255,255,255,.78) !important;
            color: #111827 !important;
            box-shadow: 0 8px 18px rgba(0,0,0,.18) !important;
        }}
        body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            height: 100% !important;
            min-height: 0 !important;
            padding: 16px !important;
            border-radius: 18px !important;
            position: static !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] > div,
        body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {{
            height: 100% !important;
            min-height: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.monitoring-page) .monitoring-side-title {{
            font-size: .9rem !important;
            margin-bottom: 10px !important;
        }}
        body:has(.monitoring-page) .latest-violation-list,
        body:has(.monitoring-page) .camera-status-list {{
            max-height: calc(100dvh - 222px) !important;
            overflow-y: auto !important;
            padding-right: 4px !important;
        }}
        body:has(.monitoring-page) .latest-violation-item {{
            padding: .8rem !important;
            margin-bottom: .75rem !important;
            border-radius: 14px !important;
        }}
        body:has(.monitoring-page) .latest-violation-type {{
            font-size: .9rem !important;
            margin: .48rem 0 !important;
        }}
        body:has(.monitoring-page) .latest-violation-preview {{
            min-height: 86px !important;
        }}
        body:has(.monitoring-page) .camera-status-row {{
            padding: .75rem !important;
            border-radius: 12px !important;
            font-size: .84rem !important;
        }}
        @media (max-width: 1366px) {{
            body:has(.monitoring-page) .block-container {{
                --edu-header-h: 52px;
                --edu-gap: 9px;
                --edu-right: 292px;
                padding: 8px 10px !important;
            }}
            body:has(.monitoring-page) .monitoring-top-actions span:not(.monitoring-tab-active),
            body:has(.monitoring-page) .monitoring-user {{
                display: none !important;
            }}
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
                height: calc(100dvh - var(--edu-header-h) - 76px) !important;
            }}
            body:has(.monitoring-page) .latest-violation-preview {{
                min-height: 72px !important;
            }}
            body:has(.monitoring-page) .latest-violation-list,
            body:has(.monitoring-page) .camera-status-list {{
                max-height: calc(100dvh - 196px) !important;
            }}
        }}
        @media (max-width: 1024px) {{
            body:has(.monitoring-page) .block-container {{
                height: auto !important;
                min-height: 100dvh !important;
                overflow-y: auto !important;
                padding: 12px !important;
            }}
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
                grid-template-columns: 1fr !important;
                height: auto !important;
                overflow: visible !important;
            }}
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"],
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child > div,
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stVerticalBlock"] {{
                height: auto !important;
                display: block !important;
                overflow: visible !important;
            }}
            body:has(.monitoring-page) .camera-card {{
                height: clamp(220px, 36vw, 320px) !important;
                margin-bottom: 8px !important;
            }}
            body:has(.monitoring-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
                height: auto !important;
                margin-top: 12px !important;
            }}
        }}
        @media (max-width: 768px) {{
            body:has(.monitoring-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
                gap: 8px !important;
                margin-bottom: 12px !important;
            }}
            body:has(.monitoring-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
                min-width: 0 !important;
                padding: 0 !important;
            }}
            body:has(.monitoring-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] button {{
                min-height: 44px !important;
                border-radius: 14px !important;
                padding: 0 6px !important;
                font-size: .82rem !important;
                box-shadow: none !important;
            }}
            body:has(.monitoring-page) .monitoring-topbar {{
                height: auto !important;
                min-height: 44px !important;
                display: block !important;
            }}
            body:has(.monitoring-page) .monitoring-top-actions,
            body:has(.monitoring-page) .monitoring-user {{
                display: none !important;
            }}
            body:has(.monitoring-page) .monitoring-filter-row + div [data-testid="stHorizontalBlock"],
            body:has(.monitoring-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: 1fr !important;
                gap: 10px !important;
            }}
            body:has(.monitoring-page) .camera-card {{
                height: 260px !important;
            }}
            body:has(.monitoring-page) [data-testid="stElementContainer"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"],
            body:has(.monitoring-page) [data-testid="element-container"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] {{
                width: 100% !important;
                margin: 0 0 10px 0 !important;
            }}
            body:has(.monitoring-page) [data-testid="stElementContainer"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] button,
            body:has(.monitoring-page) [data-testid="element-container"]:has(.camera-card:not(.thumb)) + div[data-testid="stButton"] button {{
                width: 100% !important;
                min-height: 44px !important;
                height: 44px !important;
                background: #37BD74 !important;
                border-color: #37BD74 !important;
                color: #fff !important;
                box-shadow: 0 8px 18px rgba(55,189,116,.18) !important;
            }}
            body:has(.monitoring-page) .latest-violation-list,
            body:has(.monitoring-page) .camera-status-list {{
                max-height: none !important;
            }}
        }}

        /* Pixel-focused camera dashboard layer. Logic remains in Streamlit/Python, visuals are scoped here. */
        .monitor-topbar-marker,
        .monitor-search-marker,
        .monitor-mode-toggle,
        .monitor-select-row {{
            display: block;
            height: 0;
            overflow: hidden;
        }}
        body:has(.monitor-page) .stApp {{
            background: #f7fbf8 !important;
        }}
        body:has(.monitor-page) header[data-testid="stHeader"] {{
            display: none !important;
        }}
        body:has(.monitor-page) .block-container {{
            --monitor-gap: 42px;
            --monitor-right: 360px;
            --monitor-side-pad: 64px;
            height: 100vh !important;
            height: 100dvh !important;
            padding: 48px var(--monitor-side-pad) 42px !important;
            background: #f7fbf8 !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
        }}
        body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: minmax(420px, 600px) minmax(360px, 1fr) !important;
            align-items: center !important;
            gap: 24px !important;
            margin-bottom: 34px !important;
        }}
        body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width: 0 !important;
            padding: 0 !important;
        }}
        body:has(.monitor-page) .monitor-search-marker + div .stTextInput label,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-search-marker) + [data-testid="stElementContainer"] .stTextInput label,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-search-marker) + [data-testid="element-container"] .stTextInput label {{
            display: none !important;
        }}
        body:has(.monitor-page) .monitor-search-marker + div .stTextInput input,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-search-marker) + [data-testid="element-container"] .stTextInput input {{
            width: 100% !important;
            height: 52px !important;
            min-height: 52px !important;
            border-radius: 0 !important;
            border: 0 !important;
            background: #e6e8eb !important;
            color: #6b7280 !important;
            font-size: 20px !important;
            font-weight: 500 !important;
            padding: 0 24px !important;
            box-shadow: none !important;
        }}
        .monitor-tabs {{
            display: flex !important;
            justify-content: flex-end !important;
            align-items: center !important;
            gap: 42px !important;
            height: 52px !important;
            color: #9ca3af !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            white-space: nowrap !important;
        }}
        .monitor-tabs .monitoring-tab-active {{
            color: #3fa34d !important;
            border-bottom: 3px solid #5ac46f !important;
            padding-bottom: 12px !important;
        }}
        .monitor-nav-icon {{
            color: #6b7280 !important;
            font-size: 20px !important;
        }}
        body:has(.monitor-page) .monitoring-filter-card {{
            height: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.monitor-page) .monitor-mode-toggle + div [data-testid="stRadio"],
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] [data-testid="stRadio"],
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] [data-testid="stRadio"] {{
            width: 420px !important;
            margin: 0 0 24px 0 !important;
        }}
        body:has(.monitor-page) .monitor-mode-toggle + div .stRadio > div,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] .stRadio > div,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] .stRadio > div {{
            height: 44px !important;
            min-height: 44px !important;
            background: #f2f5f2 !important;
            border-radius: 999px !important;
            padding: 4px !important;
            gap: 4px !important;
            box-shadow: 0 12px 26px rgba(15,23,42,.04) !important;
        }}
        body:has(.monitor-page) .monitor-mode-toggle + div .stRadio label,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] .stRadio label,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] .stRadio label {{
            height: 36px !important;
            min-height: 36px !important;
            border-radius: 999px !important;
            padding: 0 34px !important;
            color: #5ac46f !important;
            font-size: 17px !important;
            font-weight: 900 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}
        body:has(.monitor-page) .monitor-mode-toggle + div .stRadio label[data-checked="true"],
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] .stRadio label[data-checked="true"],
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] .stRadio label[data-checked="true"] {{
            background: #5ac46f !important;
            color: #fff !important;
            box-shadow: 0 10px 22px rgba(90,196,111,.26) !important;
        }}
        body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"],
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: minmax(0, 2.1fr) minmax(260px, .9fr) !important;
            gap: 28px !important;
            margin: 0 0 28px 0 !important;
            align-items: end !important;
        }}
        body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width: 0 !important;
            padding: 0 !important;
        }}
        body:has(.monitor-page) .monitor-select-row + div .stSelectbox label,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] .stSelectbox label,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] .stSelectbox label {{
            color: #111827 !important;
            font-size: 15px !important;
            font-weight: 900 !important;
            margin-bottom: 10px !important;
        }}
        body:has(.monitor-page) .monitor-select-row + div .stSelectbox [data-baseweb="select"] > div,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] .stSelectbox [data-baseweb="select"] > div,
        body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] .stSelectbox [data-baseweb="select"] > div {{
            height: 52px !important;
            min-height: 52px !important;
            border-radius: 5px !important;
            border: 1.5px solid #bfc5c3 !important;
            background: #fff !important;
            box-shadow: none !important;
            font-size: 20px !important;
            color: #2d2f33 !important;
        }}
        body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
            grid-template-columns: minmax(0, 1fr) var(--monitor-right) !important;
            gap: var(--monitor-gap) !important;
            height: calc(100dvh - 218px) !important;
            min-height: 0 !important;
            align-items: stretch !important;
        }}
        body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child > div,
        body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stVerticalBlock"] {{
            grid-template-rows: repeat(2, minmax(0, 1fr)) !important;
            gap: 16px !important;
        }}
        body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] {{
            gap: 16px !important;
        }}
        body:has(.monitor-page) .camera-card {{
            border-radius: 26px !important;
            border: 4px solid transparent !important;
            box-shadow: 0 18px 35px rgba(15,23,42,.10) !important;
            background: #111 !important;
        }}
        body:has(.monitor-page) .camera-card.alert {{
            border-color: #d7193f !important;
            box-shadow: 0 0 0 7px rgba(215,25,63,.14), 0 18px 35px rgba(15,23,42,.12) !important;
        }}
        body:has(.monitor-page) .camera-name {{
            background: rgba(0,0,0,.72) !important;
            border-radius: 9px !important;
            padding: .58rem .82rem !important;
            color: #fff !important;
            font-size: .95rem !important;
            font-weight: 900 !important;
        }}
        body:has(.monitor-page) .camera-status-badge {{
            background: #5ac46f !important;
            border-radius: 10px !important;
            padding: .56rem .9rem !important;
            color: #fff !important;
            font-size: .95rem !important;
            font-weight: 900 !important;
        }}
        body:has(.monitor-page) .camera-status-badge.offline,
        body:has(.monitor-page) .camera-status-badge.error {{
            background: #a7a7a7 !important;
        }}
        body:has(.monitor-page) .camera-detection-box {{
            border: 4px solid #d7193f !important;
            background: rgba(200,16,46,.68) !important;
            color: #fff !important;
            font-size: 1rem !important;
            font-weight: 900 !important;
            align-items: flex-start !important;
            padding-top: 1rem !important;
        }}
        body:has(.monitor-page) .camera-meta {{
            color: #fff !important;
            font-size: .9rem !important;
            font-weight: 900 !important;
            text-shadow: 0 1px 4px rgba(0,0,0,.7) !important;
        }}
        body:has(.monitor-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #fff !important;
            border: 0 !important;
            border-radius: 0 !important;
            height: 100% !important;
            min-height: 0 !important;
            padding: 34px 28px !important;
            box-shadow: none !important;
            overflow: hidden !important;
        }}
        body:has(.monitor-page) .monitoring-side-title {{
            color: #111827 !important;
            font-size: 21px !important;
            font-weight: 900 !important;
            margin-bottom: 28px !important;
        }}
        body:has(.monitor-page) .monitoring-side-dot {{
            width: 10px !important;
            height: 10px !important;
            background: #c4001a !important;
        }}
        body:has(.monitor-page) .latest-violation-list {{
            max-height: calc(100dvh - 210px) !important;
            overflow-y: auto !important;
            padding: 0 8px 0 0 !important;
        }}
        body:has(.monitor-page) .latest-violation-item {{
            background: #f3f5f4 !important;
            border-radius: 21px !important;
            padding: 22px !important;
            margin-bottom: 28px !important;
            box-shadow: none !important;
        }}
        body:has(.monitor-page) .latest-violation-top {{
            color: #6b7280 !important;
            font-size: .98rem !important;
            font-weight: 700 !important;
            align-items: center !important;
        }}
        body:has(.monitor-page) .latest-violation-top .ew-status-warn {{
            background: #ff9800 !important;
            color: #fff !important;
            border-radius: 6px !important;
            padding: .22rem .7rem !important;
            font-size: .8rem !important;
            font-weight: 900 !important;
        }}
        body:has(.monitor-page) .latest-violation-type {{
            color: #c8102e !important;
            font-size: 1.18rem !important;
            font-weight: 900 !important;
            margin: 1.15rem 0 1.1rem !important;
        }}
        body:has(.monitor-page) .latest-violation-preview {{
            min-height: 170px !important;
            border: 3px solid #d7193f !important;
            border-radius: 18px !important;
            background: #111 !important;
            background-size: cover !important;
            background-position: center !important;
            box-shadow: none !important;
        }}
        body:has(.monitor-page) .latest-confidence {{
            left: 16px !important;
            bottom: 14px !important;
            background: #d7193f !important;
            color: #fff !important;
            border-radius: 999px !important;
            padding: .52rem .9rem !important;
            font-size: .82rem !important;
            font-weight: 900 !important;
        }}
        body:has(.monitor-page) .ew-btn-primary + div button,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.ew-btn-primary) + [data-testid="stElementContainer"] button,
        body:has(.monitor-page) .ew-btn-danger + div button,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.ew-btn-danger) + [data-testid="stElementContainer"] button {{
            height: 44px !important;
            min-height: 44px !important;
            border-radius: 12px !important;
            background: #5ac46f !important;
            border-color: #5ac46f !important;
            color: #fff !important;
            font-size: 1rem !important;
            font-weight: 900 !important;
            box-shadow: 0 7px 14px rgba(15,23,42,.18) !important;
        }}
        body:has(.monitor-page) .ew-btn-outline + div button,
        body:has(.monitor-page) [data-testid="stElementContainer"]:has(.ew-btn-outline) + [data-testid="stElementContainer"] button {{
            height: 44px !important;
            min-height: 44px !important;
            border-radius: 4px !important;
            background: #fff !important;
            border: 3px solid #5ac46f !important;
            color: #5ac46f !important;
            box-shadow: none !important;
            font-size: 1rem !important;
            font-weight: 900 !important;
        }}
        @media (max-width: 1366px) {{
            body:has(.monitor-page) .block-container {{
                --monitor-gap: 28px;
                --monitor-right: 320px;
                --monitor-side-pad: 44px;
                padding-top: 34px !important;
                padding-bottom: 30px !important;
            }}
            body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"] {{
                grid-template-columns: minmax(360px, 560px) minmax(320px, 1fr) !important;
                margin-bottom: 28px !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
                height: calc(100dvh - 194px) !important;
            }}
            body:has(.monitor-page) .latest-violation-preview {{
                min-height: 128px !important;
            }}
            body:has(.monitor-page) .latest-violation-item {{
                padding: 18px !important;
                margin-bottom: 22px !important;
            }}
        }}
        @media (max-width: 1024px) {{
            body:has(.monitor-page) .block-container {{
                height: auto !important;
                overflow-y: auto !important;
                padding: 22px !important;
            }}
            body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {{
                grid-template-columns: 1fr !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
                grid-template-columns: 1fr !important;
                height: auto !important;
                overflow: visible !important;
            }}
            body:has(.monitor-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"] {{
                height: auto !important;
                margin-top: 24px !important;
            }}
        }}
        @media (max-width: 768px) {{
            body:has(.monitor-page) .block-container {{
                padding: 16px !important;
            }}
            .monitor-tabs {{
                justify-content: flex-start !important;
                gap: 18px !important;
                font-size: 16px !important;
            }}
            body:has(.monitor-page) .monitor-mode-toggle + div [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] [data-testid="stRadio"] {{
                width: 100% !important;
            }}
            body:has(.monitor-page) .monitor-mode-toggle + div .stRadio label,
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] .stRadio label {{
                padding: 0 18px !important;
                font-size: 14px !important;
            }}
            body:has(.monitor-page) .camera-card {{
                height: 260px !important;
            }}
            body:has(.monitor-page) .latest-violation-preview {{
                min-height: 150px !important;
            }}
        }}

        /* Final dashboard override: match the supplied camera mockup while preserving existing data/action logic. */
        body:has(.monitor-page) {{
            --monitor-green: #5ac46f;
            --monitor-green-dark: #3fa34d;
            --monitor-red: #c8102e;
            --monitor-red-strong: #d7193f;
            --monitor-muted: #eef2f0;
            --monitor-text: #14191f;
        }}
        body:has(.monitor-page) .camera-img {{
            position: absolute !important;
            inset: 0 !important;
            width: 100% !important;
            height: 100% !important;
            object-fit: cover !important;
            display: block !important;
            z-index: 0 !important;
        }}
        body:has(.monitor-page) .camera-placeholder {{
            position: absolute !important;
            inset: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: #111 !important;
            color: rgba(255,255,255,.72) !important;
            font-weight: 900 !important;
            z-index: 0 !important;
        }}
        body:has(.monitor-page) .camera-header,
        body:has(.monitor-page) .camera-detection-box,
        body:has(.monitor-page) .camera-meta {{
            z-index: 2 !important;
        }}

        @media (min-width: 1025px) {{
            body:has(.monitor-page) section[data-testid="stSidebar"],
            body:has(.monitor-page) section[data-testid="stSidebar"] > div:first-child,
            body:has(.monitor-page) [data-testid="stSidebar"],
            body:has(.monitor-page) [data-testid="collapsedControl"] {{
                display: none !important;
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                flex: 0 0 0 !important;
                padding: 0 !important;
                margin: 0 !important;
                overflow: hidden !important;
                visibility: hidden !important;
            }}
            body:has(.monitor-page) .main,
            body:has(.monitor-page) [data-testid="stAppViewContainer"],
            body:has(.monitor-page) [data-testid="stMain"],
            body:has(.monitor-page) main {{
                margin-left: 0 !important;
                width: 100vw !important;
                max-width: 100vw !important;
            }}
            body:has(.monitor-page) .block-container {{
                --monitor-gap: clamp(24px, 2.8vw, 54px);
                --monitor-right: clamp(330px, 28vw, 430px);
                --monitor-x: clamp(42px, 4.7vw, 90px);
                padding: clamp(34px, 5vh, 62px) var(--monitor-x) 0 !important;
                height: 100vh !important;
                height: 100dvh !important;
                max-width: none !important;
                overflow: hidden !important;
                background: #f7fbf8 !important;
            }}
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-mobile-actions),
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-mobile-actions),
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-mobile-actions) + [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-mobile-actions) + [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] {{
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            }}
            body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-topbar-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-topbar-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: minmax(430px, 48vw) minmax(380px, 1fr) !important;
                align-items: center !important;
                gap: var(--monitor-gap) !important;
                margin: 0 0 clamp(30px, 3.7vh, 44px) 0 !important;
            }}
            body:has(.monitor-page) .monitor-search-marker + div .stTextInput input,
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-search-marker) + [data-testid="element-container"] .stTextInput input {{
                height: 64px !important;
                min-height: 64px !important;
                border-radius: 0 !important;
                border: 0 !important;
                background: #e6e8eb !important;
                font-size: 21px !important;
                padding: 0 28px !important;
                box-shadow: none !important;
            }}
            body:has(.monitor-page) .monitor-tabs {{
                justify-content: flex-end !important;
                gap: clamp(28px, 3.1vw, 54px) !important;
                height: 64px !important;
                font-size: 22px !important;
            }}
            body:has(.monitor-page) .monitor-mode-toggle + div [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] [data-testid="stRadio"] {{
                width: 430px !important;
                margin: 0 0 22px 0 !important;
            }}
            body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: minmax(0, 2.1fr) minmax(260px, .9fr) !important;
                gap: clamp(24px, 2.4vw, 42px) !important;
                margin: 0 0 clamp(24px, 2.6vh, 34px) 0 !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-main-grid) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-main-grid) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: minmax(0, 1fr) var(--monitor-right) !important;
                gap: var(--monitor-gap) !important;
                height: calc(100dvh - clamp(214px, 28vh, 264px)) !important;
                min-height: 0 !important;
                align-items: stretch !important;
                overflow: visible !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-main-grid) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-main-grid) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
                width: auto !important;
                min-width: 0 !important;
                height: 100% !important;
                min-height: 0 !important;
                padding: 0 !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stVerticalBlock"] {{
                display: grid !important;
                grid-template-rows: repeat(2, minmax(0, 1fr)) !important;
                gap: clamp(16px, 2vh, 24px) !important;
                height: 100% !important;
                min-height: 0 !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
                gap: clamp(16px, 1.8vw, 28px) !important;
                min-height: 0 !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
                height: 100% !important;
                min-height: 0 !important;
                padding: 0 !important;
            }}
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-focus-button),
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-focus-button),
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-focus-button) + div[data-testid="stButton"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-focus-button) + div[data-testid="stButton"] {{
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            }}
            body:has(.monitor-page) .camera-card {{
                position: relative !important;
                width: 100% !important;
                height: 100% !important;
                min-height: 0 !important;
                overflow: hidden !important;
                border-radius: 26px !important;
                background: #111 !important;
                border: 4px solid var(--monitor-red-strong) !important;
                box-shadow: 0 0 0 7px rgba(215,25,63,.12), 0 18px 34px rgba(15,23,42,.10) !important;
            }}
            body:has(.monitor-page) .camera-card:not(.alert) {{
                border-color: var(--monitor-red-strong) !important;
            }}
            body:has(.monitor-page) .camera-detection-box {{
                left: 50% !important;
                top: 32% !important;
                width: 30% !important;
                min-width: 150px !important;
                height: 34% !important;
                transform: translateX(-4%) !important;
                border: 4px solid var(--monitor-red-strong) !important;
                background: rgba(200,16,46,.68) !important;
                color: #fff !important;
                display: flex !important;
                align-items: flex-start !important;
                justify-content: center !important;
                text-align: center !important;
                padding-top: 1rem !important;
            }}
            body:has(.monitor-page) .monitoring-side-panel-target + div,
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-side-panel-target) + [data-testid="stElementContainer"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-side-panel-target) + [data-testid="element-container"] {{
                height: 100% !important;
                min-height: 0 !important;
            }}
            body:has(.monitor-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-side-panel-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-side-panel-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
                height: 100% !important;
                min-height: 0 !important;
                background: #fff !important;
                border: 0 !important;
                border-radius: 0 !important;
                padding: clamp(24px, 3vh, 42px) clamp(20px, 2vw, 32px) !important;
                box-shadow: none !important;
                overflow: hidden !important;
            }}
            body:has(.monitor-page) .latest-violation-list {{
                max-height: calc(100dvh - clamp(320px, 34vh, 380px)) !important;
                overflow-y: auto !important;
            }}
        }}

        @media (min-width: 1025px) and (max-width: 1366px) {{
            body:has(.monitor-page) .block-container {{
                --monitor-gap: 26px;
                --monitor-right: 330px;
                --monitor-x: 44px;
                padding-top: 34px !important;
            }}
            body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"] {{
                grid-template-columns: minmax(360px, 560px) minmax(310px, 1fr) !important;
                margin-bottom: 24px !important;
            }}
            body:has(.monitor-page) .monitor-search-marker + div .stTextInput input,
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-search-marker) + [data-testid="stElementContainer"] .stTextInput input {{
                height: 52px !important;
                min-height: 52px !important;
                font-size: 18px !important;
            }}
            body:has(.monitor-page) .monitor-tabs {{
                height: 52px !important;
                font-size: 18px !important;
                gap: 30px !important;
            }}
            body:has(.monitor-page) .monitor-mode-toggle + div [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] [data-testid="stRadio"] {{
                margin-bottom: 18px !important;
            }}
            body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {{
                margin-bottom: 22px !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-main-grid) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {{
                height: calc(100dvh - 198px) !important;
            }}
        }}

        @media (max-width: 1024px) {{
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-mobile-actions) + [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-mobile-actions) + [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) .monitoring-mobile-actions + div [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
                gap: 8px !important;
                margin-bottom: 14px !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: 1fr !important;
                height: auto !important;
                overflow: visible !important;
            }}
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stVerticalBlock"] {{
                display: block !important;
                height: auto !important;
            }}
            body:has(.monitor-page) .camera-card {{
                aspect-ratio: 16 / 10 !important;
                height: auto !important;
                min-height: 240px !important;
            }}
        }}

        @media (max-width: 768px) {{
            body:has(.monitor-page) .monitoring-main-grid + div [data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child [data-testid="stHorizontalBlock"] {{
                display: grid !important;
                grid-template-columns: 1fr !important;
            }}
        }}

        @media (min-width: 1025px) {{
            body:has(.monitor-page) .monitor-topbar-marker + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-topbar-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-topbar-marker) + [data-testid="element-container"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) .monitor-mode-toggle + div [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-mode-toggle) + [data-testid="stElementContainer"] [data-testid="stRadio"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-mode-toggle) + [data-testid="element-container"] [data-testid="stRadio"],
            body:has(.monitor-page) .monitor-select-row + div [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitor-select-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitor-select-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
                max-width: calc(100vw - var(--monitor-right) - var(--monitor-gap) - var(--monitor-x) - var(--monitor-x)) !important;
            }}
            body:has(.monitor-page) .monitoring-side-panel-target + div,
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-side-panel-target) + [data-testid="stElementContainer"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-side-panel-target) + [data-testid="element-container"] {{
                position: fixed !important;
                top: clamp(28px, 4.6vh, 62px) !important;
                right: var(--monitor-x) !important;
                bottom: 0 !important;
                width: var(--monitor-right) !important;
                height: auto !important;
                min-height: 0 !important;
                z-index: 20 !important;
            }}
            body:has(.monitor-page) .monitoring-side-panel-target + div [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.monitor-page) [data-testid="stElementContainer"]:has(.monitoring-side-panel-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.monitor-page) [data-testid="element-container"]:has(.monitoring-side-panel-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
                height: 100% !important;
                min-height: 0 !important;
                max-height: none !important;
            }}
        }}

        /* Danh sach toa nha: final, page-scoped layout matching the supplied desktop reference. */
        body:has(.locations-page) .stApp {{
            background: #f6faf7 !important;
        }}
        body:has(.locations-page) .block-container {{
            padding: 38px 38px 54px !important;
        }}
        body:has(.locations-page) .location-page-title {{
            color: #37BD74 !important;
            font-size: 38px !important;
            line-height: 1.08 !important;
            font-weight: 900 !important;
            letter-spacing: -0.025em !important;
            text-align: left !important;
            margin: 0 0 4px !important;
        }}
        body:has(.locations-page) .location-page-subtitle {{
            color: #6b7280 !important;
            font-size: 17px !important;
            line-height: 1.4 !important;
            font-weight: 500 !important;
            text-align: left !important;
            margin: 0 0 28px !important;
        }}
        body:has(.locations-page) .location-grid + div [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
            gap: 28px !important;
            align-items: stretch !important;
            width: 100% !important;
        }}
        body:has(.locations-page) .location-card-target + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-target) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-target) + [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {{
            height: auto !important;
            min-height: 620px !important;
            padding: 24px !important;
            background: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 20px !important;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06) !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) .location-card-header-row + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-card-header-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-card-header-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) 122px !important;
            gap: 14px !important;
            align-items: center !important;
            height: 50px !important;
            min-height: 50px !important;
            margin: 0 0 16px !important;
        }}
        body:has(.locations-page) .location-card-title {{
            color: #17201b !important;
            font-size: 18px !important;
            line-height: 1.2 !important;
            font-weight: 850 !important;
            text-align: left !important;
            margin: 0 !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-add-btn),
        body:has(.locations-page) .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            width: 122px !important;
            min-width: 122px !important;
            max-width: 122px !important;
        }}
        body:has(.locations-page) .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            height: 44px !important;
            min-height: 44px !important;
            padding: 0 14px !important;
            border: 0 !important;
            border-radius: 7px !important;
            background: #5cc779 !important;
            box-shadow: 0 4px 9px rgba(38, 123, 68, 0.23) !important;
            align-self: center !important;
        }}
        body:has(.locations-page) .location-add-btn + div button p,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button p,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button p {{
            color: #ffffff !important;
            font-size: 15px !important;
            line-height: 1 !important;
            font-weight: 800 !important;
            margin: 0 !important;
        }}
        body:has(.locations-page) .location-add-btn + div button:disabled,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button:disabled,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button:disabled {{
            background: #86d29b !important;
            color: #ffffff !important;
            opacity: 1 !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-list-content),
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] .location-list-content) {{
            gap: 10px !important;
            padding: 0 2px 0 0 !important;
            margin: 0 !important;
            align-items: stretch !important;
        }}
        body:has(.locations-page) .location-item-target + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            grid-template-columns: minmax(0, 1fr) 28px 28px 42px !important;
            column-gap: 9px !important;
            min-height: 76px !important;
            padding: 12px 14px !important;
            background: #f7f9fa !important;
            border: 1px solid transparent !important;
            border-radius: 14px !important;
            text-align: left !important;
        }}
        body:has(.locations-page) .location-item-target.active + div [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target.active) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target.active) + [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-item-target.active) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.locations-page) [data-testid="element-container"]:has(.location-item-target.active) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {{
            background: #edf8f0 !important;
            border-color: #d8eedf !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-item-content) {{
            align-items: flex-start !important;
            justify-content: center !important;
            text-align: left !important;
        }}
        body:has(.locations-page) .location-item-title,
        body:has(.locations-page) .location-item-name {{
            color: #17201b !important;
            font-size: 16px !important;
            line-height: 1.24 !important;
            font-weight: 800 !important;
            text-align: left !important;
        }}
        body:has(.locations-page) .location-item-status,
        body:has(.locations-page) .location-item-meta {{
            color: #788397 !important;
            font-size: 14px !important;
            line-height: 1.24 !important;
            font-weight: 500 !important;
            text-align: left !important;
        }}
        body:has(.locations-page) .empty-hint {{
            color: #687386 !important;
            font-size: 15px !important;
            line-height: 1.45 !important;
            text-align: left !important;
            padding: 2px 0 0 !important;
            margin: 0 !important;
        }}
        body:has(.locations-page) .icon-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn) + [data-testid="element-container"] button {{
            width: 28px !important;
            min-width: 28px !important;
            max-width: 28px !important;
            height: 28px !important;
            min-height: 28px !important;
            color: #59c77a !important;
            font-size: 19px !important;
        }}
        body:has(.locations-page) .icon-btn.delete + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.icon-btn.delete) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.icon-btn.delete) + [data-testid="element-container"] button {{
            width: 40px !important;
            min-width: 40px !important;
            max-width: 40px !important;
            height: 40px !important;
            min-height: 40px !important;
            background: #df2371 !important;
            border-radius: 50% !important;
            color: #ffffff !important;
        }}
        body:has(.locations-page) .location-item-text {{
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            justify-content: center !important;
            justify-self: start !important;
            align-self: center !important;
            width: 100% !important;
            min-width: 0 !important;
            gap: 4px !important;
            margin: 0 !important;
            padding: 0 !important;
            text-align: left !important;
            pointer-events: auto !important;
        }}
        body:has(.locations-page) .location-item-text .location-item-title,
        body:has(.locations-page) .location-item-text .location-item-name {{
            display: block !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            color: #111827 !important;
            font-weight: 800 !important;
            text-align: left !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }}
        body:has(.locations-page) .location-item-text .location-item-status,
        body:has(.locations-page) .location-item-text .location-item-meta {{
            display: block !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            color: #64748b !important;
            text-align: left !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-item-text) {{
            position: relative !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            justify-content: center !important;
            justify-self: start !important;
            width: 100% !important;
            min-width: 0 !important;
            text-align: left !important;
            overflow: hidden !important;
        }}
        /* Stable selectors: markers live inside the Streamlit wrapper they style. */
        body:has(.locations-page) [data-testid="stVerticalBlockBorderWrapper"]:has(.location-card-target) {{
            width: 100% !important;
            height: 100% !important;
            min-height: 620px !important;
            padding: 24px !important;
            background: #ffffff !important;
            border: 1px solid #e5e7eb !important;
            border-radius: 20px !important;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06) !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlockBorderWrapper"]:has(.location-card-target) > div {{
            width: 100% !important;
            height: auto !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-card-header-row):not(:has(.location-card-target)) {{
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) 118px !important;
            align-items: center !important;
            width: 100% !important;
            min-width: 0 !important;
            min-height: 46px !important;
            gap: 16px !important;
            margin: 0 0 18px !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-card-header-row):not(:has(.location-card-target)) > [data-testid="column"] {{
            width: auto !important;
            min-width: 0 !important;
            max-width: none !important;
            padding: 0 !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-card-header-row):not(:has(.location-card-target)) [data-testid="column"]:has(.location-add-btn) {{
            width: 118px !important;
            min-width: 118px !important;
            max-width: 118px !important;
            justify-self: end !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-card-header-row) .location-card-title {{
            display: block !important;
            font-size: 18px !important;
            line-height: 1.2 !important;
            font-weight: 900 !important;
            color: #111827 !important;
            text-align: left !important;
            white-space: nowrap !important;
            margin: 0 !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="column"]:has(.location-add-btn),
        body:has(.locations-page) .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            width: 118px !important;
            min-width: 118px !important;
            max-width: 118px !important;
        }}
        body:has(.locations-page) .location-add-btn + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-add-btn) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-add-btn) + [data-testid="element-container"] button {{
            position: static !important;
            height: 42px !important;
            min-height: 42px !important;
            padding: 0 14px !important;
            border: 0 !important;
            border-radius: 6px !important;
            background: #5dc878 !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            box-shadow: 0 8px 16px rgba(55, 189, 116, 0.25) !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) {{
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) 26px 26px 38px !important;
            align-items: center !important;
            width: 100% !important;
            min-width: 0 !important;
            min-height: 64px !important;
            column-gap: 10px !important;
            margin: 0 !important;
            padding: 11px 14px 11px 16px !important;
            background: #f8fafc !important;
            border: 1px solid transparent !important;
            border-radius: 13px !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target.active):not(:has(.location-card-target)) {{
            background: #effaf3 !important;
            border-color: #bdecc8 !important;
            box-shadow: none !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) > [data-testid="column"] {{
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: auto !important;
            min-width: 0 !important;
            max-width: none !important;
            padding: 0 !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) > [data-testid="column"]:first-child {{
            position: relative !important;
            align-self: stretch !important;
            align-items: flex-start !important;
            justify-content: center !important;
            width: 100% !important;
            min-width: 0 !important;
            text-align: left !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) .location-item-status,
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) .location-item-meta {{
            width: 100% !important;
            margin: 3px 0 0 !important;
            font-size: 13px !important;
            line-height: 1.15 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(.location-item-target):not(:has(.location-card-target)) [data-testid="column"]:last-child {{
            width: 38px !important;
            min-width: 38px !important;
            max-width: 38px !important;
            justify-content: center !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-list-content),
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] .location-list-content) {{
            display: flex !important;
            flex-direction: column !important;
            gap: 10px !important;
            width: 100% !important;
            min-width: 0 !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            padding: 0 2px 0 0 !important;
            box-sizing: border-box !important;
        }}
        body:has(.locations-page) .location-item-text .location-item-title,
        body:has(.locations-page) .location-item-text .location-item-name {{
            display: block !important;
            width: 100% !important;
            line-height: 1.18 !important;
            margin: 0 0 3px !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            overflow-wrap: normal !important;
        }}
        body:has(.locations-page) .location-item-text .location-item-status,
        body:has(.locations-page) .location-item-text .location-item-meta {{
            font-size: 13px !important;
            line-height: 1.15 !important;
            margin: 0 !important;
            white-space: nowrap !important;
        }}
        body:has(.locations-page) .location-action-button + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-action-button) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-action-button) + [data-testid="element-container"] button {{
            width: 26px !important;
            min-width: 26px !important;
            max-width: 26px !important;
            height: 26px !important;
            min-height: 26px !important;
        }}
        body:has(.locations-page) .location-delete-button + div button,
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-delete-button) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.location-delete-button) + [data-testid="element-container"] button {{
            width: 38px !important;
            min-width: 38px !important;
            max-width: 38px !important;
            height: 38px !important;
            min-height: 38px !important;
            border-radius: 999px !important;
            background: #df2371 !important;
            color: #ffffff !important;
            overflow: visible !important;
            box-shadow: 0 10px 20px rgba(223, 35, 113, 0.20) !important;
        }}
        body:has(.locations-page) .location-card-header {{
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            width: 100% !important;
            min-height: 44px !important;
            height: auto !important;
            gap: 16px !important;
            margin: 0 0 16px !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) .location-card-title {{
            display: block !important;
            color: #111827 !important;
            font-size: 21px !important;
            line-height: 1.2 !important;
            font-weight: 900 !important;
            text-align: left !important;
            white-space: nowrap !important;
            margin: 0 !important;
        }}
        body:has(.locations-page) .location-add-button {{
            position: static !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            flex: 0 0 118px !important;
            width: 118px !important;
            height: 42px !important;
            border-radius: 6px !important;
            background: #5dc878 !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            text-decoration: none !important;
            box-shadow: 0 8px 16px rgba(55, 189, 116, 0.25) !important;
        }}
        body:has(.locations-page) .location-add-button.disabled {{
            background: #86d29b !important;
            cursor: not-allowed !important;
        }}
        body:has(.locations-page) .location-list {{
            display: flex !important;
            flex-direction: column !important;
            width: 100% !important;
            min-width: 0 !important;
            gap: 10px !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            padding: 0 2px 0 0 !important;
            box-sizing: border-box !important;
        }}
        body:has(.locations-page) .location-item {{
            display: grid !important;
            grid-template-columns: minmax(0, 1fr) 120px !important;
            align-items: center !important;
            width: 100% !important;
            min-width: 0 !important;
            min-height: 64px !important;
            padding: 11px 14px 11px 0 !important;
            gap: 12px !important;
            background: #f8fafc !important;
            border: 1px solid transparent !important;
            border-radius: 13px !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) .location-item.active {{
            background: #effaf3 !important;
            border-color: #bdecc8 !important;
        }}
        body:has(.locations-page) a.location-item-main {{
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            justify-content: center !important;
            align-self: stretch !important;
            width: 100% !important;
            min-width: 0 !important;
            padding: 0 !important;
            color: inherit !important;
            text-align: left !important;
            text-decoration: none !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) a.location-item-main:hover .location-item-title {{
            color: #269a4b !important;
        }}
        body:has(.locations-page) .location-item-title {{
            display: block !important;
            width: 100% !important;
            color: #111827 !important;
            font-size: 16px !important;
            line-height: 1.18 !important;
            font-weight: 900 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            margin: 0 0 3px !important;
        }}
        body:has(.locations-page) .location-item-status {{
            display: block !important;
            width: 100% !important;
            color: #64748b !important;
            font-size: 13px !important;
            line-height: 1.15 !important;
            font-weight: 500 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            margin: 0 !important;
        }}
        body:has(.locations-page) .location-item-actions {{
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            flex: 0 0 120px !important;
            width: 120px !important;
            gap: 10px !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) .location-action,
        body:has(.locations-page) .location-delete {{
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            flex-shrink: 0 !important;
            text-decoration: none !important;
        }}
        body:has(.locations-page) .location-action {{
            width: 26px !important;
            height: 26px !important;
            color: #5bc572 !important;
            font-size: 20px !important;
        }}
        body:has(.locations-page) .location-delete {{
            width: 38px !important;
            height: 38px !important;
            border-radius: 999px !important;
            background: #df2371 !important;
            color: #ffffff !important;
            font-size: 17px !important;
            overflow: visible !important;
            box-shadow: 0 10px 20px rgba(223, 35, 113, 0.20) !important;
        }}
        .location-native-grid-marker,
        .location-native-card-marker,
        .location-native-header-marker,
        .location-native-add-marker,
        .location-native-list-marker,
        .location-native-item-marker,
        .location-native-select-marker,
        .location-native-action-marker {{
            display: block !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-header-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-header-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-add-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-add-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-list-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-list-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-item-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-item-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-select-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-select-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-action-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-action-marker) {{
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-grid-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-grid-marker),
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.location-native-card-marker),
        body:has(.locations-page) [data-testid="element-container"]:has(.location-native-card-marker) {{
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-native-card-marker) {{
            width: 100% !important;
            min-width: 0 !important;
            min-height: 560px !important;
            padding: 20px !important;
            background: #ffffff !important;
            border: 1px solid #dfe7e2 !important;
            border-radius: 20px !important;
            box-shadow: 0 16px 32px rgba(15, 23, 42, 0.07) !important;
            overflow: visible !important;
            box-sizing: border-box !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-header-marker) {{
            align-items: center !important;
            width: 100% !important;
            min-height: 44px !important;
            column-gap: 16px !important;
            margin: 0 0 18px !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-header-marker) > [data-testid="stColumn"] {{
            min-width: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-header-marker) > [data-testid="stColumn"]:first-child {{
            flex: 1 1 0 !important;
            width: auto !important;
            max-width: none !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-header-marker) > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{
            gap: 0 !important;
        }}
        body:has(.locations-page) .location-native-card-title {{
            color: #111827 !important;
            font-size: 20px !important;
            line-height: 1.25 !important;
            font-weight: 900 !important;
            text-align: left !important;
            white-space: nowrap !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) button {{
            position: static !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            flex: 0 0 112px !important;
            width: 112px !important;
            min-width: 112px !important;
            max-width: 112px !important;
            height: 44px !important;
            min-height: 44px !important;
            padding: 0 14px !important;
            white-space: nowrap !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
            writing-mode: horizontal-tb !important;
            line-height: 1 !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            transform: none !important;
            rotate: none !important;
            border: 0 !important;
            border-radius: 6px !important;
            background: #37BD74 !important;
            color: #ffffff !important;
            box-shadow: 0 8px 16px rgba(55, 189, 116, 0.25) !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) {{
            flex: 0 0 112px !important;
            width: 112px !important;
            min-width: 112px !important;
            max-width: 112px !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) button * {{
            white-space: nowrap !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
            writing-mode: horizontal-tb !important;
            transform: none !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) button:disabled {{
            background: #86d29b !important;
            color: #ffffff !important;
            opacity: 1 !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) button p {{
            color: #ffffff !important;
            margin: 0 !important;
            font-size: 15px !important;
            line-height: 1 !important;
            font-weight: 800 !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-add-marker) button:not(:disabled):hover {{
            background: #2e9f62 !important;
        }}
        body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-native-list-marker) {{
            display: flex !important;
            flex-direction: column !important;
            width: 100% !important;
            min-width: 0 !important;
            min-height: 40px !important;
            gap: 9px !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            box-sizing: border-box !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker) {{
            align-items: center !important;
            width: 100% !important;
            min-width: 0 !important;
            min-height: 68px !important;
            height: auto !important;
            column-gap: 8px !important;
            margin: 0 !important;
            padding: 10px 12px 10px 16px !important;
            background: #f8fafc !important;
            border: 1px solid transparent !important;
            border-radius: 13px !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker.active) {{
            background: #effaf3 !important;
            border-color: #bdecc8 !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker.active)
        [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button p strong {{
            color: #37a957 !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker) > [data-testid="stColumn"] {{
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-width: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker) > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{
            gap: 0 !important;
            justify-content: center !important;
        }}
        body:has(.locations-page) [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-item-marker) > [data-testid="stColumn"]:first-child {{
            flex: 1 1 0 !important;
            width: auto !important;
            max-width: none !important;
            align-items: stretch !important;
            justify-content: flex-start !important;
            overflow: hidden !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button {{
            position: static !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            width: 100% !important;
            height: auto !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            color: #64748b !important;
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            opacity: 1 !important;
            text-align: left !important;
            cursor: pointer !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) [data-testid="stButton"],
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button > div {{
            width: 100% !important;
            min-width: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button > div > span,
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button [data-testid="stMarkdownContainer"] {{
            width: 100% !important;
            min-width: 0 !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button p {{
            display: block !important;
            width: 100% !important;
            min-width: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            color: #64748b !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            line-height: 1.15 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button p strong {{
            display: block !important;
            width: 100% !important;
            min-width: 0 !important;
            margin: 0 0 2px !important;
            padding: 0 !important;
            color: #111827 !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            line-height: 1.18 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button p em {{
            display: block !important;
            width: 100% !important;
            min-width: 0 !important;
            margin: 2px 0 0 !important;
            padding: 0 !important;
            color: #94a3b8 !important;
            font-size: 11px !important;
            font-weight: 400 !important;
            font-style: normal !important;
            line-height: 1.12 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-select-marker) button p br {{
            display: none !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker) button {{
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 24px !important;
            min-width: 24px !important;
            max-width: 24px !important;
            height: 24px !important;
            min-height: 24px !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            color: #5bc572 !important;
            box-shadow: none !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker) button p {{
            color: inherit !important;
            margin: 0 !important;
            font-size: 17px !important;
            line-height: 1 !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker.edit),
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker.power) {{
            flex: 0 0 24px !important;
            width: 24px !important;
            min-width: 24px !important;
            max-width: 24px !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker.delete) button {{
            width: 36px !important;
            min-width: 36px !important;
            max-width: 36px !important;
            height: 36px !important;
            min-height: 36px !important;
            border-radius: 999px !important;
            background: #e8286b !important;
            color: #ffffff !important;
            box-shadow: 0 10px 20px rgba(223, 35, 113, 0.20) !important;
            overflow: visible !important;
        }}
        body:has(.locations-page) [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] .location-native-action-marker.delete) {{
            flex: 0 0 36px !important;
            width: 36px !important;
            min-width: 36px !important;
            max-width: 36px !important;
        }}
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.ew-btn-danger) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.ew-btn-danger) + [data-testid="element-container"] button {{
            background: #e8286b !important;
            border-color: #e8286b !important;
            color: #ffffff !important;
        }}
        body:has(.locations-page) [data-testid="stElementContainer"]:has(.ew-btn-outline) + [data-testid="stElementContainer"] button,
        body:has(.locations-page) [data-testid="element-container"]:has(.ew-btn-outline) + [data-testid="element-container"] button {{
            background: #ffffff !important;
            border-color: #37BD74 !important;
            color: #37BD74 !important;
        }}
        @media (max-width: 767px) {{
            body:has(.locations-page) .block-container {{
                padding: 16px !important;
            }}
            body:has(.locations-page) [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .location-native-card-marker) {{
                height: auto !important;
                min-height: 420px !important;
            }}
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    defaults = {
        "is_authenticated": False,
        "current_user": None,
        "role": None,
        "page": "signin",
        "password_reset_contact": "",
        "password_reset_otp": "",
        "reset_user_id": None,
        "reset_user_code": "",
        "reset_identifier": "",
        "reset_otp": "",
        "reset_otp_expire": None,
        "reset_verified": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def db_rows(query: str, params: tuple | list = ()) -> list[dict]:
    with db_connect() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def db_row(query: str, params: tuple | list = ()) -> dict | None:
    with db_connect() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def normalize_page(page: str | None) -> str:
    target = page or "signin"
    return PAGE_ALIASES.get(target, target)


def set_page(page: str) -> None:
    st.session_state.page = normalize_page(page)


def current_user() -> dict | None:
    return st.session_state.current_user


def normalize_role(user: dict | None) -> str:
    user = user or {}
    role_value = user.get("role")
    if role_value is None or str(role_value).strip() == "":
        role_value = user.get("role_name")
    raw_role = str(role_value if role_value is not None else "").strip().lower()
    username = str(
        user.get("username")
        or user.get("user_code")
        or user.get("ma_nguoi_dung")
        or ""
    ).strip().upper()

    if username.startswith("AD") or raw_role in {"admin", "administrator", "quản trị viên", "quan tri vien"}:
        return "admin"
    if username.startswith("BV") or raw_role in {"security", "guard", "bảo vệ", "bao ve", "bảo vệ/kỹ thuật", "bao ve/ky thuat"}:
        return "guard"
    if raw_role in {str(ROLE_ADMIN).lower(), str(int(ROLE_ADMIN)).lower()}:
        return "admin"
    if raw_role in {str(ROLE_GUARD).lower(), str(int(ROLE_GUARD)).lower()}:
        return "guard"
    return "teacher"


def normalized_role_value(user: dict | None) -> int:
    role = normalize_role(user)
    if role == "admin":
        return ROLE_ADMIN
    if role == "guard":
        return ROLE_GUARD
    return ROLE_TEACHER


def default_page_for_normalized_role(role: str) -> str:
    return {"admin": "reports", "guard": "security"}.get(role, "monitoring")


def login_user(user: dict) -> None:
    normalized = normalize_role(user)
    normalized_value = normalized_role_value(user)
    user = dict(user)
    user["role"] = normalized_value
    st.session_state.is_authenticated = True
    st.session_state.current_user = user
    st.session_state.role = normalized_value
    st.session_state.page = default_page_for_normalized_role(normalized)


def logout_user() -> None:
    st.session_state.is_authenticated = False
    st.session_state.current_user = None
    st.session_state.role = None
    st.session_state.page = "signin"
    st.rerun()


def require_auth(roles: list[int] | None = None) -> bool:
    if not st.session_state.is_authenticated or not current_user():
        set_page("signin")
        st.warning("Vui lòng đăng nhập để tiếp tục.")
        return False
    if roles is not None and int(st.session_state.role) not in roles:
        st.warning("Tài khoản không có quyền truy cập màn hình này.")
        set_page(default_page_for_role(int(st.session_state.role)))
        return False
    return True










def avatar_path(value: str | None) -> Path:
    if not value:
        return DEFAULT_AVATAR
    cleaned = value.replace("\\", "/")
    if cleaned.startswith("/data/"):
        path = BASE_DIR / cleaned.lstrip("/")
    elif cleaned.startswith("data/"):
        path = BASE_DIR / cleaned
    else:
        path = Path(cleaned)
    return path if path.exists() else DEFAULT_AVATAR


def login_cover_path() -> Path:
    for path in LOGIN_COVER_CANDIDATES:
        if path.exists():
            return path
    return DEFAULT_AVATAR


def recovery_cover_uri() -> str:
    return file_to_data_uri(login_cover_path())


RESET_STATE_KEYS = [
    "password_reset_contact",
    "password_reset_otp",
    "reset_user_id",
    "reset_user_code",
    "reset_identifier",
    "reset_otp",
    "reset_otp_expire",
    "reset_verified",
]


def find_password_reset_user(identifier: str) -> dict | None:
    value = identifier.strip()
    if not value:
        return None

    user = get_user_by_login(value)
    if user:
        return user

    phone_digits = re.sub(r"\D", "", value)
    if phone_digits and phone_digits != value:
        user = get_user_by_login(phone_digits)
        if user:
            return user

    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM Users
            WHERE status=1
              AND (
                    LOWER(ma_nguoi_dung)=?
                 OR LOWER(email)=?
                 OR so_dien_thoai=?
              )
            """,
            (value.lower(), value.lower(), phone_digits or value),
        ).fetchone()
        return dict(row) if row else None


def generate_reset_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_password_reset_otp(user: dict, identifier: str) -> str:
    otp = generate_reset_otp()
    st.session_state.reset_user_id = int(user["id"])
    st.session_state.reset_user_code = str(user.get("ma_nguoi_dung") or "")
    st.session_state.reset_identifier = identifier.strip()
    st.session_state.reset_otp = otp
    st.session_state.reset_otp_expire = datetime.now() + timedelta(minutes=5)
    st.session_state.reset_verified = False
    st.session_state.password_reset_contact = identifier.strip()
    st.session_state.password_reset_otp = otp
    return otp


def clear_password_reset_state() -> None:
    for key in RESET_STATE_KEYS:
        st.session_state.pop(key, None)


def reset_otp_is_expired() -> bool:
    expire_at = st.session_state.get("reset_otp_expire")
    if not isinstance(expire_at, datetime):
        return True
    return datetime.now() > expire_at


def current_reset_user() -> dict | None:
    user_id = st.session_state.get("reset_user_id")
    if not user_id:
        return None
    return get_user_by_id(int(user_id))


def status_badge(text: str, kind: str = "ok") -> str:
    css = {"ok": "ew-status-ok", "bad": "ew-status-bad", "warn": "ew-status-warn"}.get(kind, "ew-status-ok")
    return f'<span class="{css}">{text}</span>'


def render_title(title: str, subtitle: str = "") -> None:
    user = current_user()
    st.markdown('<div class="ew-page-header">', unsafe_allow_html=True)
    st.markdown(
        f'<div><div class="ew-title">{title}</div>{f"<div class=\"ew-subtitle\">{subtitle}</div>" if subtitle else ""}</div>',
        unsafe_allow_html=True,
    )
    if user:
        st.markdown(
            f'<div class="ew-user-chip"><strong>{user.get("ho_ten") or user.get("ma_nguoi_dung")}</strong><span>{role_name(int(user.get("role") or ROLE_TEACHER))} · {user.get("ma_nguoi_dung")}</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_metrics(items: list[tuple[str, str]]) -> None:
    cols = st.columns(min(len(items), 4))
    for col, (label, value) in zip(cols, items):
        col.markdown(
            f'<div class="ew-metric"><div class="ew-metric-label">{label}</div><div class="ew-metric-value">{value}</div></div>',
            unsafe_allow_html=True,
        )


def render_panel_start(title: str | None = None, subtitle: str | None = None) -> None:
    st.markdown('<div class="ew-card">', unsafe_allow_html=True)
    if title:
        st.markdown(f'<div style="font-size:1.2rem;font-weight:800;margin-bottom:.2rem;">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="ew-subtitle" style="margin-bottom:1rem;">{subtitle}</div>', unsafe_allow_html=True)


def render_panel_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def button_marker(style: str) -> None:
    st.markdown(f'<div class="ew-btn-{style}"></div>', unsafe_allow_html=True)




def render_card_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="ew-card-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="ew-card-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def evidence_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = (BASE_DIR / raw_path) if not Path(raw_path).is_absolute() else Path(raw_path)
    return path if path.exists() else None


def bytes_to_data_uri(data: bytes | None, mime_type: str = "image/jpeg") -> str:
    if not data:
        return ""
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def file_to_data_uri(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime_type = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
    return bytes_to_data_uri(path.read_bytes(), mime_type)


def image_to_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")




def save_avatar(uploaded_file, user_code: str) -> str:
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Ảnh đại diện chỉ hỗ trợ JPG, JPEG, PNG hoặc WEBP.")
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    safe_code = "".join(ch for ch in user_code if ch.isalnum() or ch in {"-", "_"}) or "user"
    file_name = f"avatar_{safe_code}_{uuid.uuid4().hex[:10]}{suffix}"
    path = AVATAR_DIR / file_name
    path.write_bytes(uploaded_file.getbuffer())
    return f"data/avatars/{file_name}"


def fetch_recent_violations(limit: int = 6, room_id: int | None = None, mode: int | None = None) -> list[dict]:
    clauses = []
    params: list[object] = []
    if room_id is not None:
        clauses.append("c.room_id=?")
        params.append(int(room_id))
    if mode is not None:
        clauses.append("v.mode=?")
        params.append(int(mode))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(int(limit))
    return db_rows(
        f"""
        SELECT v.*, c.vi_tri_goc, r.ten_phong, b.ten_toa
        FROM Violation_Logs v
        LEFT JOIN Cameras c ON c.id = v.camera_id
        LEFT JOIN Rooms r ON r.id = c.room_id
        LEFT JOIN Buildings b ON b.id = r.building_id
        {where}
        ORDER BY v.created_at DESC, v.id DESC
        LIMIT ?
        """,
        params,
    )


def violation_types() -> list[str]:
    rows = db_rows(
        """
        SELECT DISTINCT ten_vi_pham
        FROM Violation_Types
        WHERE COALESCE(is_active, 1)=1
        ORDER BY id
        """
    )
    return [row["ten_vi_pham"] for row in rows]


def daily_report_rows(report_date: str) -> list[dict]:
    return db_rows(
        """
        SELECT b.ten_toa, r.ten_phong,
               SUM(CASE WHEN v.mode=0 THEN 1 ELSE 0 END) AS normal_total,
               SUM(CASE WHEN v.mode=1 THEN 1 ELSE 0 END) AS exam_total
        FROM Rooms r
        LEFT JOIN Buildings b ON b.id = r.building_id
        LEFT JOIN Cameras c ON c.room_id = r.id AND COALESCE(c.is_deleted, 0)=0
        LEFT JOIN Violation_Logs v ON v.camera_id = c.id AND DATE(COALESCE(v.created_at, v.thoi_gian))=?
        WHERE COALESCE(r.is_deleted, 0)=0
        GROUP BY b.id, r.id
        ORDER BY b.ten_toa, r.ten_phong
        """,
        (report_date,),
    )




def report_rows_for_range(start_date: str, end_date: str) -> list[dict]:
    """Aggregate report totals once per room for an inclusive date range."""
    return db_rows(
        """
        SELECT b.ten_toa, r.ten_phong,
               SUM(CASE WHEN v.mode=0 THEN 1 ELSE 0 END) AS normal_total,
               SUM(CASE WHEN v.mode=1 THEN 1 ELSE 0 END) AS exam_total
        FROM Rooms r
        LEFT JOIN Buildings b ON b.id = r.building_id
        LEFT JOIN Cameras c ON c.room_id = r.id AND COALESCE(c.is_deleted, 0)=0
        LEFT JOIN Violation_Logs v ON v.camera_id = c.id
             AND DATE(COALESCE(v.created_at, v.thoi_gian)) BETWEEN ? AND ?
        WHERE COALESCE(r.is_deleted, 0)=0
        GROUP BY b.id, r.id
        ORDER BY b.ten_toa, r.ten_phong
        """,
        (start_date, end_date),
    )


def popular_violation_for_range(start_date: str, end_date: str, mode: int) -> str:
    """Return the most frequent violation for one room mode in a date range."""
    row = db_row(
        """
        SELECT v.loai_vi_pham, COUNT(*) AS total
        FROM Violation_Logs v
        WHERE v.mode=?
          AND DATE(COALESCE(v.created_at, v.thoi_gian)) BETWEEN ? AND ?
        GROUP BY v.loai_vi_pham
        ORDER BY total DESC, v.loai_vi_pham
        LIMIT 1
        """,
        (int(mode), start_date, end_date),
    )
    if not row:
        return "Chưa có dữ liệu"
    return f"{row['loai_vi_pham']} ({int(row['total'] or 0)})"


def latest_report_date_with_data() -> date | None:
    """Return the latest report date backed by a valid camera/room/building chain."""
    try:
        row = db_row(
            """
            SELECT MAX(DATE(COALESCE(v.created_at, v.thoi_gian))) AS latest_date
            FROM Violation_Logs v
            JOIN Cameras c ON c.id=v.camera_id AND COALESCE(c.is_deleted, 0)=0
            JOIN Rooms r ON r.id=c.room_id AND COALESCE(r.is_deleted, 0)=0
            JOIN Buildings b ON b.id=r.building_id
            WHERE COALESCE(v.created_at, v.thoi_gian) IS NOT NULL
            """
        )
        value = str((row or {}).get("latest_date") or "").strip()
        return date.fromisoformat(value) if value else None
    except Exception:
        LOGGER.exception("Unable to determine latest report date")
        return None




def make_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="EduWatch", index=False)
    return buffer.getvalue()


def make_pdf_bytes(title: str, subtitle: str, df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 8),
        Paragraph(subtitle, styles["BodyText"]),
        Spacer(1, 16),
    ]
    table_data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(PRIMARY)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d6e7dc")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f4fbf6")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def save_report_file(name: str, extension: str, content: bytes) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    file_path = REPORT_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
    file_path.write_bytes(content)
    return file_path




@st.cache_resource(show_spinner=False)
def get_detection_service_resource():
    from src.services.detection_service import detection_service

    return detection_service


def camera_snapshot(camera_id: int) -> bytes | None:
    try:
        camera = get_camera(int(camera_id)) or {}
        source = str(camera.get("video_source") or "").strip().lower()
        if source.startswith("rtsp://"):
            return None
        return get_detection_service_resource().snapshot_jpeg(int(camera_id))
    except Exception:
        return None


def _reset_monitoring_focus() -> None:
    st.session_state.monitoring_expanded_camera_id = None


def _focus_monitoring_camera(camera_id: int) -> None:
    st.session_state.monitoring_expanded_camera_id = int(camera_id)


def _exit_monitoring_camera_focus() -> None:
    _reset_monitoring_focus()


def _toggle_monitoring_camera_focus(camera_id: int) -> None:
    camera_id = int(camera_id)
    current_id = st.session_state.get("monitoring_expanded_camera_id")

    try:
        current_id = int(current_id) if current_id is not None else None
    except (TypeError, ValueError):
        current_id = None

    if current_id == camera_id:
        _exit_monitoring_camera_focus()
    else:
        _focus_monitoring_camera(camera_id)


def _apply_monitoring_mode(room_id: int, widget_key: str) -> None:
    label = str(st.session_state.get(widget_key) or "PHÒNG THƯỜNG")
    mode_value = 1 if label == "PHÒNG THI" else 0
    st.session_state.monitoring_mode = mode_value
    update_room_monitor_mode(int(room_id), mode_value)


def _render_monitoring_status_footer() -> None:
    now = datetime.now()
    st.markdown(
        '<div class="monitor-v3-status-footer">'
        '<span><b class="ok">●</b>&nbsp; Hệ thống hoạt động ổn định</span>'
        '<span>⟳&nbsp; Tự động làm mới mỗi 5 giây</span>'
        f'<span>◷&nbsp; Thời gian hệ thống: {now.strftime("%H:%M:%S")}&nbsp;&nbsp; {now.strftime("%d/%m/%Y")}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def password_checks(password: str) -> dict[str, bool]:
    return {
        "Ít nhất 8 ký tự": len(password) >= 8,
        "Có chữ hoa": bool(re.search(r"[A-Z]", password)),
        "Có chữ thường": bool(re.search(r"[a-z]", password)),
        "Có số": bool(re.search(r"\d", password)),
        "Có ký tự đặc biệt": bool(re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)),
    }






def render_monitoring_page(security_mode: bool = False) -> None:
    render_monitoring_rebuild(security_mode)


def inject_monitoring_rebuild_css() -> None:
    """Single, scoped stylesheet for the rebuilt monitoring screen."""
    st.markdown(
        """
<style>
body:has(.ewmon-page) .stApp { background:#f6f8f7; }
body:has(.ewmon-page) .block-container {
  max-width:none !important; height:auto !important; min-height:0 !important;
  padding:24px 28px 24px 24px !important; overflow-y:visible !important;
}
.ewmon-page { display:block; height:1px; overflow:visible; }
body:has(.ewmon-page) [data-testid="stVerticalBlock"] { gap:.75rem; }
body:has(.ewmon-page) .st-key-monitoring-layout > [data-testid="stHorizontalBlock"],
body:has(.ewmon-page) .st-key-monitoring-layout > div > [data-testid="stHorizontalBlock"] {
  display:grid !important;
  grid-template-columns:minmax(760px,1fr) minmax(360px,390px) !important;
  align-items:start !important; gap:28px !important; width:100% !important;
}
body:has(.ewmon-page) .st-key-monitoring-layout > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
body:has(.ewmon-page) .st-key-monitoring-layout > div > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  width:100% !important; min-width:0 !important; max-width:none !important; flex:none !important;
}
body:has(.ewmon-page) .st-key-monitoring-topbar > [data-testid="stHorizontalBlock"],
body:has(.ewmon-page) .st-key-monitoring-topbar > div > [data-testid="stHorizontalBlock"] {
  display:grid !important; grid-template-columns:minmax(360px,560px) minmax(300px,auto) !important;
  align-items:center !important; justify-content:space-between !important; gap:28px !important;
  width:100% !important; height:auto !important; min-height:52px !important; margin-bottom:18px !important; overflow:visible !important;
}
body:has(.ewmon-page) .st-key-monitoring-topbar > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
body:has(.ewmon-page) .st-key-monitoring-topbar > div > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  width:100% !important; min-width:0 !important; max-width:none !important; flex:none !important;
}
body:has(.monitoring-page) [class*="st-key-ewmon_search_"] [data-baseweb="input"] {
  height:52px !important; min-height:52px !important; box-sizing:border-box !important;
  border:1px solid #dce3df !important; border-radius:14px !important; background:#fff !important;
  box-shadow:0 2px 8px rgba(15,23,42,.025) !important;
}
body:has(.monitoring-page) [class*="st-key-ewmon_search_"] input { height:50px !important; min-height:50px !important; border:0 !important; background:transparent !important; box-shadow:none !important; font-size:15px !important; color:#263248 !important; }
body:has(.monitoring-page) [class*="st-key-ewmon_search_"] input::placeholder { color:#8a94a6 !important; opacity:1 !important; }
body:has(.monitoring-page) [class*="st-key-ewmon_search_"] [data-testid="stTextInputIcon"] { color:#8a94a6 !important; }
body:has(.monitoring-page) .ewmon-nav { display:flex; align-items:center; justify-content:flex-end; gap:0; min-height:52px; color:#8f98a8; }
body:has(.monitoring-page) .monitoring-tab { display:flex; align-items:center; justify-content:center; min-width:102px; height:52px; box-sizing:border-box; font-size:15px; white-space:nowrap; }
body:has(.monitoring-page) .monitoring-tab-active { color:#2d9d48; border-bottom:3px solid #3ca954; font-weight:800; }
body:has(.monitoring-page) .monitoring-tab-inactive { min-width:76px; margin-left:30px; color:#8f98a8; border-bottom:3px solid transparent; font-weight:700; }
body:has(.monitoring-page) .monitoring-system-dot { display:block; flex:0 0 16px; width:16px; height:16px; margin-left:30px; border-radius:50%; background:#43a84f; box-shadow:0 0 0 3px #edf7ef; }
body:has(.monitoring-page) .monitoring-settings { display:grid; place-items:center; flex:0 0 28px; width:28px; height:28px; margin-left:25px; color:#121a22; font-size:25px; line-height:1; }
body:has(.monitoring-page) .monitoring-settings svg { width:24px; height:24px; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
body:has(.monitoring-page) .st-key-monitoring-mode-section {
  position:relative !important; display:block !important; width:100% !important; min-width:0 !important; max-width:none !important;
  height:auto !important; min-height:0 !important;
  gap:0 !important; margin:0 !important; padding:0 !important;
  overflow:visible !important; visibility:visible !important; opacity:1 !important;
  transform:none !important; z-index:auto !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stVerticalBlock"],
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stMarkdownContainer"] {
  height:auto !important; min-height:0 !important; gap:0 !important; overflow:visible !important;
}
body:has(.monitoring-page) .monitoring-mode-label {
  position:relative !important; display:block !important;
  margin:0 0 7px !important; padding:0 !important;
  color:#1b241f !important; font-size:14px !important; font-weight:600 !important; line-height:20px !important;
  white-space:normal !important; overflow:visible !important;
  visibility:visible !important; opacity:1 !important;
  transform:none !important; z-index:2 !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] {
  display:block !important; width:100% !important; max-width:100% !important;
  height:auto !important; min-height:0 !important; margin:0 !important;
  overflow:visible !important; visibility:visible !important; opacity:1 !important; pointer-events:auto !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] {
  display:inline-flex !important; align-items:center !important;
  box-sizing:border-box !important; width:100% !important; max-width:none !important; height:44px !important; min-height:44px !important;
  gap:0 !important; padding:3px !important; border:1px solid #dce4df !important; border-radius:22px !important; background:#fff !important;
  box-shadow:none !important;
  overflow:visible !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label {
  display:inline-flex !important; flex:1 1 0 !important; align-items:center !important; justify-content:center !important;
  min-width:0 !important; height:36px !important; min-height:36px !important; max-height:36px !important;
  box-sizing:border-box !important; margin:0 !important; padding:0 14px !important; border:1px solid transparent !important; border-radius:18px !important;
  background:#fff !important; color:#29322d !important; box-shadow:none !important;
  font-size:13px !important; font-weight:650 !important; line-height:1 !important; text-align:center !important;
  white-space:nowrap !important; cursor:pointer !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label:hover:not(:has(input:checked)) {
  background:#eaf7ee !important; color:#249950 !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label p {
  margin:0 !important; color:inherit !important; font-size:inherit !important; font-weight:inherit !important; line-height:inherit !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"],
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked),
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] label:has([data-checked="true"]) {
  background:#48b75a !important; color:#fff !important; border-color:#48b75a !important; font-weight:800 !important; box-shadow:0 3px 9px rgba(55,169,78,.18) !important;
}
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] [role="radiogroup"] > label > div:first-child,
body:has(.monitoring-page) .st-key-monitoring-mode-section [data-testid="stRadio"] input {
  display:none !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar {
  position:relative !important; display:block !important; box-sizing:border-box !important;
  width:100% !important; height:auto !important; min-height:0 !important;
  gap:0 !important; margin:0 0 18px !important;
  padding:18px 20px 20px !important; overflow:visible !important;
  background:#fff !important; border:1px solid #dde4e0 !important; border-radius:15px !important;
  box-shadow:none !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stVerticalBlock"] {
  height:auto !important; min-height:0 !important; gap:0 !important; overflow:visible !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] {
  display:grid !important; grid-template-columns:280px minmax(0,1fr) 260px !important;
  align-items:end !important; width:100% !important; gap:32px !important; overflow:visible !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
  width:100% !important; min-width:0 !important; max-width:none !important; flex:none !important; overflow:visible !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar .stSelectbox label {
  margin-bottom:8px !important; color:#1b241f !important; font-size:14px !important; font-weight:600 !important; line-height:1.35 !important;
}
body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-baseweb="select"] > div {
  box-sizing:border-box !important; height:44px !important; min-height:44px !important; border-radius:11px !important; border-color:#dce4df !important;
  background:#fff !important; font-size:14px !important; padding-left:5px !important;
}
body:has(.ewmon-page) .ewmon-selects + div [data-testid="stHorizontalBlock"] { align-items:end; gap:22px; }
body:has(.ewmon-page) .ewmon-selects + div .stSelectbox label { color:#17211c; font-weight:700; }
body:has(.ewmon-page) .ewmon-selects + div [data-baseweb="select"] > div { height:46px; border-radius:10px; border-color:#d8dedb; }
.ewmon-card { position:relative; width:100%; aspect-ratio:16/10; min-height:280px; overflow:hidden; box-sizing:border-box; border:2px solid #5fc66f; border-radius:18px; background:#111; box-shadow:0 10px 24px rgba(15,23,42,.12); }
.ewmon-card.focus { height:auto; max-height:480px; aspect-ratio:16/9; }
.ewmon-card.thumb { height:auto; aspect-ratio:16/9; border-width:2px; border-radius:13px; }
.ewmon-card img,.ewmon-frame { display:block; width:100%; height:100%; object-fit:cover; object-position:center; }
.ewmon-placeholder { width:100%; height:100%; background:linear-gradient(rgba(20,31,26,.18),rgba(20,31,26,.18)),linear-gradient(135deg,#d8e6dc 0%,#eef5f0 100%); display:flex; align-items:center; justify-content:center; color:#314238; font-size:15px; font-weight:800; }
body:has(.monitoring-page) .ewmon-dblclick-frame { cursor:zoom-in; user-select:none; -webkit-user-drag:none; }
body:has(.monitoring-page) .ewmon-card.focus > .ewmon-dblclick-frame { cursor:zoom-out; }
.ewmon-name,.ewmon-status,.ewmon-meta { position:absolute; z-index:2; color:white; font-weight:800; }
.ewmon-name { top:14px; left:14px; max-width:68%; padding:10px 14px; border-radius:9px; background:rgba(0,0,0,.76); font-size:14px; line-height:1.2; font-weight:950; }
.ewmon-status { top:14px; right:14px; display:flex; align-items:center; justify-content:center; box-sizing:border-box; height:42px; min-width:96px; padding:0 12px; border-radius:10px; background:#5fc66f; font-size:14px; line-height:1; font-weight:950; }
.ewmon-status.offline { background:#b7bcc7; }
.ewmon-meta { right:12px; bottom:12px; padding:9px 10px; border-radius:8px; background:rgba(0,0,0,.76); text-align:right; font-size:12px; line-height:1.35; font-weight:900; }
.ewmon-detect { position:absolute; z-index:2; left:43%; top:32%; width:24%; height:35%; box-sizing:border-box; border:2px solid #ed2654; color:white; background:rgba(234,28,74,.05); font-size:13px; line-height:1.5; font-weight:800; }
.ewmon-detect > span { position:absolute; top:-2px; left:100%; min-width:82px; max-width:116px; padding:8px 9px; border-radius:0 7px 7px 0; background:#e82a56; color:#fff; box-sizing:border-box; line-height:1.45; }
.ewmon-detect-1 { left:29%; top:27%; width:16%; height:28%; }
.ewmon-detect-2 { left:48%; top:32%; width:24%; height:32%; }
.ewmon-detect-3 { left:20%; top:44%; width:27%; height:36%; }
.ewmon-detect-4 { left:45%; top:34%; width:24%; height:32%; }
body:has(.ewmon-page) [data-testid="stVerticalBlock"]:has(.ewmon-card) { position:relative; gap:0; }
body:has(.monitoring-page) [data-testid="stHorizontalBlock"]:has(.ewmon-card) { display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)) !important; gap:14px !important; width:100% !important; margin-bottom:14px !important; }
body:has(.monitoring-page) [data-testid="stHorizontalBlock"]:has(.ewmon-card) > [data-testid="stColumn"] { width:100% !important; min-width:0 !important; max-width:none !important; flex:none !important; }
.ewmon-panel-title { display:flex; align-items:center; justify-content:space-between; font-weight:950; font-size:17px; line-height:1.35; color:#111827; padding:3px 1px 10px; letter-spacing:.01em; white-space:normal; word-break:normal; overflow-wrap:normal; }
.ewmon-panel-title b { color:#dc294f; font-size:12px; }
.ewmon-summary { width:100%; box-sizing:border-box; margin:0 0 8px; padding:16px; border-radius:12px; color:#315da8; background:#eef4ff; font-size:15px; font-weight:700; white-space:normal; word-break:normal; overflow-wrap:normal; }
body:has(.ewmon-page) .st-key-monitoring-violation-scroll { height:min(680px,calc(100vh - 245px)) !important; overflow-y:auto !important; overflow-x:hidden !important; padding:1px 4px 1px 0 !important; scrollbar-width:thin; scrollbar-color:#b8b8b8 transparent; }
body:has(.ewmon-page) [class*="st-key-monitoring-log-card-"] { margin:0 0 10px !important; padding:12px !important; border:1px solid #e2e7e4 !important; border-radius:13px !important; background:#fff !important; box-shadow:0 2px 8px rgba(15,23,42,.025) !important; }
body:has(.ewmon-page) [class*="st-key-monitoring-log-card-"] > [data-testid="stVerticalBlock"] { gap:.75rem !important; }
.ewmon-vcard { display:grid; grid-template-columns:112px minmax(0,1fr); gap:14px; min-height:142px; padding:0; border:0; border-radius:0; background:transparent; box-shadow:none; }
.ewmon-vthumb { height:142px; border-radius:10px; background:#1b241f center/cover no-repeat; }
.ewmon-vbody { min-width:0; padding-top:2px; }
.ewmon-vcam { color:#1c2430; font-size:14px; font-weight:850; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ewmon-vtime { color:#8a94a3; font-size:12px; margin:8px 0; }
.ewmon-vtype { color:#d91b46; font-size:13px; font-weight:850; line-height:1.35; }
.ewmon-confidence { display:inline-block; margin-top:8px; padding:6px 9px; border-radius:999px; background:#ffedf1; color:#d91b46; font-size:12px; font-weight:850; }
body:has(.ewmon-page) [class*="st-key-monitoring-log-card-"] [data-testid="stHorizontalBlock"] { gap:10px; }
body:has(.ewmon-page) [class*="st-key-ewmon_confirm_"] button,
body:has(.ewmon-page) [class*="st-key-ewmon_false_"] button { height:40px; border:1px solid #3dad58; color:#31994c; font-size:13px; font-weight:850; border-radius:9px; }
body:has(.ewmon-page) [class*="st-key-ewmon_confirm_"] button { background:#4db661; color:#fff; border-color:#4db661; }
body:has(.ewmon-page) [class*="st-key-ewmon_false_"] button { background:#fff; color:#31994c; border-color:#4db661; }
body:has(.ewmon-page) [class*="st-key-ewmon_all_"] button { height:48px; background:#43aa55; color:white; border:1px solid #43aa55; border-radius:9px; font-size:15px; font-weight:850; }
body:has(.ewmon-page) .st-key-monitoring-violation-panel { width:100% !important; min-width:0 !important; min-height:calc(100vh - 34px) !important; padding:22px !important; overflow:hidden !important; border:1px solid #dfe7e2 !important; border-radius:16px !important; background:#fff !important; box-shadow:none !important; box-sizing:border-box !important; }
body:has(.ewmon-page) .st-key-monitoring-violation-panel > [data-testid="stVerticalBlock"] { gap:.65rem !important; }
body:has(.monitoring-page) .monitoring-tab { padding:0 !important; }
body:has(.ewmon-page) header[data-testid="stHeader"],
body:has(.ewmon-page) [data-testid="stToolbar"],
body:has(.ewmon-page) [data-testid="stDecoration"] { display:none !important; }
.ewmon-page {
  display:block; width:0; height:0; min-height:0; margin:0; padding:0; overflow:hidden;
}

/* Monitoring-only shell overrides: match the target card sidebar without leaking to other pages. */
/* Previous monitoring-only sidebar rewrite is intentionally disabled. */
@media(min-width:99999px){
  body:has(.authenticated-shell):has(.ewmon-page) section[data-testid="stSidebar"] {
    position:sticky !important; inset:10px auto auto 12px !important;
    flex:0 0 264px !important; width:264px !important; min-width:264px !important; max-width:264px !important;
    height:calc(100vh - 20px) !important; min-height:calc(100vh - 20px) !important;
    margin:0 4px 0 0 !important; overflow:hidden !important;
    background:#fbfcfb !important; border:1px solid #e6ebe8 !important; border-radius:17px !important;
    box-shadow:0 5px 18px rgba(31,50,39,.035) !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) section[data-testid="stSidebar"] > div:first-child {
    height:calc(100vh - 20px) !important; padding:72px 18px 22px !important;
    background:#fbfcfb !important; overflow-x:hidden !important; overflow-y:auto !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stMain"] {
    width:calc(100vw - 280px) !important;
  }
  body:has(.authenticated-shell):has(.monitoring-page):has(.ewmon-page) .block-container {
    padding:24px 28px 24px 36px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-brand-row { gap:13px !important; margin-bottom:8px !important; }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-brand-logo {
    flex-basis:52px !important; width:52px !important; height:52px !important;
    background:#fff !important; border-color:#e1e8e3 !important; border-radius:15px !important;
    box-shadow:0 3px 10px rgba(22,54,34,.035) !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-brand { color:#369c45 !important; font-size:25px !important; }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-role-label {
    margin:0 0 58px 65px !important; color:#8a90a3 !important; font-size:11px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-nav-marker + div[data-testid="stButton"],
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] {
    margin:0 0 11px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .stButton > button,
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-nav-marker + div[data-testid="stButton"] button,
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button {
    height:59px !important; min-height:59px !important; padding:0 17px !important;
    color:#232d3c !important; background:transparent !important; border:0 !important; border-radius:15px !important;
    box-shadow:none !important; font-size:15px !important; font-weight:700 !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .stButton > button [data-testid="stIconMaterial"] {
    font-size:23px !important; margin-right:5px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-nav-marker.active + div[data-testid="stButton"] button,
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button {
    color:#318e44 !important; background:#e8f4ea !important; border:0 !important; box-shadow:none !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-nav-marker.active + div[data-testid="stButton"] button p,
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button p {
    color:#318e44 !important; font-weight:800 !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-card {
    position:relative !important; min-height:90px !important; padding:14px 40px 14px 14px !important;
    background:#fff !important; border-color:#dce4df !important; border-radius:17px !important; box-shadow:none !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-avatar { width:49px !important; height:49px !important; flex-basis:49px !important; }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-code { color:#318e44 !important; font-size:14px !important; }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-name { color:#7f899d !important; font-size:12px !important; }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-chevron {
    position:absolute; top:50%; right:16px; transform:translateY(-55%); color:#172132; font-size:19px; font-weight:800;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-card-click + div[data-testid="stButton"],
  body:has(.authenticated-shell):has(.ewmon-page) div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] {
    height:90px !important; margin-top:-90px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) .sidebar-user-card-click + div[data-testid="stButton"] button,
  body:has(.authenticated-shell):has(.ewmon-page) div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button {
    height:90px !important; min-height:90px !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-logout-marker + div[data-testid="stButton"],
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] {
    margin:12px 0 0 !important; padding-top:0 !important; border-top:0 !important;
  }
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] .sidebar-logout-marker + div[data-testid="stButton"] button,
  body:has(.authenticated-shell):has(.ewmon-page) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] button {
    height:52px !important; min-height:52px !important; color:#273143 !important; font-size:14px !important; font-weight:850 !important;
  }
}
@media(max-width:1366px) and (min-width:1024px){
  body:has(.ewmon-page) .st-key-monitoring-layout > [data-testid="stHorizontalBlock"],
  body:has(.ewmon-page) .st-key-monitoring-layout > div > [data-testid="stHorizontalBlock"] { grid-template-columns:minmax(620px,1fr) minmax(320px,340px) !important; gap:18px !important; }
  body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] { grid-template-columns:230px minmax(0,1fr) 180px !important; gap:18px !important; }
  .ewmon-card { min-height:240px; }
}
@media(max-width:1023px){body:has(.ewmon-page) .st-key-monitoring-layout > [data-testid="stHorizontalBlock"],body:has(.ewmon-page) .st-key-monitoring-layout > div > [data-testid="stHorizontalBlock"]{grid-template-columns:minmax(0,1fr) !important}.ewmon-card{height:auto}}
@media(max-width:1450px){
  body:has(.monitoring-page) .monitoring-tab{min-width:96px;font-size:14px}
  body:has(.monitoring-page) .monitoring-tab-inactive{min-width:70px;margin-left:28px}
  body:has(.monitoring-page) .monitoring-system-dot{margin-left:24px}
  body:has(.monitoring-page) .monitoring-settings{margin-left:20px}
}
@media(max-width:767px){
  body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] {
    display:grid !important; grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important; gap:14px !important;
  }
  body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    grid-column:auto !important; width:100% !important; min-width:0 !important;
  }
  body:has(.ewmon-page) main .st-key-monitoring-filter-bar [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) {
    grid-column:1 / -1 !important;
  }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _ewmon_camera_html(
    camera: dict,
    index: int,
    pending: dict[int, dict],
    variant: str = "",
    *,
    enable_double_click: bool = False,
) -> str:
    camera_id = int(camera["id"])
    source = str(camera.get("video_source") or "").strip()
    online = bool(source) and int(camera.get("status") or 0) == 1
    frame = bytes_to_data_uri(camera_snapshot(camera_id)) if source else ""
    placeholder = (
        '<div class="ewmon-placeholder">'
        '<span>Đang kết nối luồng camera</span>'
        '</div>'
    )
    if enable_double_click and frame:
        preview = (
            f'<img class="ewmon-frame ewmon-dblclick-frame" data-ewmon-camera-id="{camera_id}" '
            f'src="{frame}" alt="Camera {camera_id}" draggable="false">'
        )
    elif enable_double_click:
        preview = (
            f'<div class="ewmon-placeholder ewmon-frame ewmon-dblclick-frame" '
            f'data-ewmon-camera-id="{camera_id}">'
            '<span>Đang kết nối luồng camera</span></div>'
        )
    else:
        preview = f'<img src="{frame}" alt="Camera {camera_id}">' if frame else placeholder
    alert = pending.get(camera_id)
    detection = ""
    if alert:
        detection = (
            f'<div class="ewmon-detect ewmon-detect-{index}">'
            f'<span>{escape(str(alert.get("loai_vi_pham") or "Vi phạm"))}<br>'
            f'{float(alert.get("confidence") or 0):.0%}</span></div>'
        )
    name = escape(str(camera.get("vi_tri_goc") or f"Camera #{camera_id}"))
    status = "TRỰC TIẾP" if online else "NGHỈ" if source else "KHÔNG TÍN HIỆU"
    return (f'<div class="ewmon-card {variant}">{preview}<div class="ewmon-name">Cam {index:02d} - {name}</div>'
            f'<div class="ewmon-status{"" if online else " offline"}">{status}</div>{detection}'
            '<div class="ewmon-meta">FPS: 30<br>Độ trễ: 12ms</div></div>')


def _render_ewmon_camera(
    camera: dict,
    index: int,
    pending: dict[int, dict],
    *,
    variant: str = "",
    enable_double_click: bool = False,
) -> None:
    camera_id = int(camera["id"])
    st.markdown(
        _ewmon_camera_html(
            camera,
            index,
            pending,
            variant,
            enable_double_click=enable_double_click,
        ),
        unsafe_allow_html=True,
    )
    if enable_double_click:
        camera_dblclick_bridge(
            camera_id,
            "focus" if st.session_state.get("monitoring_expanded_camera_id") is not None else "grid",
            key=f"ewmon_dblclick_{camera_id}",
            on_double_click=lambda camera_id=camera_id: _toggle_monitoring_camera_focus(camera_id),
        )


def _render_ewmon_violations(
    rows: list[dict],
    pending_count: int,
    *,
    security_mode: bool,
    building_name: str,
    room_name: str,
    mode_label: str,
    camera_index_by_id: dict[int, int],
) -> None:
    st.markdown('<div class="ewmon-panel-title"><span>NHẬT KÝ VI PHẠM MỚI NHẤT</span><b>●</b></div>', unsafe_allow_html=True)
    if not rows:
        st.info("Chưa có vi phạm mới.")
    else:
        if pending_count:
            st.markdown(f'<div class="ewmon-summary">Có {pending_count} vi phạm mới chưa xử lý.</div>', unsafe_allow_html=True)
        with st.container(height=680, border=False, key="monitoring-violation-scroll"):
            for row in rows:
                image = file_to_data_uri(evidence_path(row.get("image_path")))
                style = f' style="background-image:url({image})"' if image else ""
                vietnam_time = to_vietnam_time(row.get("thoi_gian") or row.get("created_at"))
                raw_time = vietnam_time.strftime("%d/%m/%Y %H:%M:%S") if vietnam_time else "Không rõ thời gian"
                camera_id = int(row.get("camera_id") or 0)
                camera_index = camera_index_by_id.get(camera_id, camera_id)
                with st.container(border=False, key=f"monitoring-log-card-{security_mode}-{row['id']}"):
                    st.markdown(
                        f'<div class="ewmon-vcard"><div class="ewmon-vthumb"{style}></div><div class="ewmon-vbody">'
                        f'<div class="ewmon-vcam">Cam {camera_index:02d} - {escape(str(row.get("vi_tri_goc") or "N/A"))}</div>'
                        f'<div class="ewmon-vtime">{escape(raw_time)}</div>'
                        f'<div class="ewmon-vtype">{escape(str(row.get("loai_vi_pham") or ""))}</div>'
                        f'<div class="ewmon-confidence">Độ tin cậy: {float(row.get("confidence") or 0):.1%}</div>'
                        '</div></div>', unsafe_allow_html=True,
                    )
                    if int(row.get("is_confirmed") or 0) == 0:
                        action_cols = st.columns(2, gap="small")
                        if action_cols[0].button("XÁC NHẬN", key=f"ewmon_confirm_{security_mode}_{row['id']}", width="stretch"):
                            confirm_violation(int(row["id"]), "")
                            st.rerun()
                        if action_cols[1].button("BÁO SAI", key=f"ewmon_false_{security_mode}_{row['id']}", width="stretch"):
                            mark_false_ai(int(row["id"]))
                            st.rerun()
    if st.button("XEM TẤT CẢ", key=f"ewmon_all_{security_mode}", width="stretch"):
        st.session_state.hz_v_prefill = {"building": building_name, "room": room_name, "mode": mode_label}
        st.session_state.hz_v_search_applied = True
        st.session_state.hz_v_page = 1
        set_page("violations")
        st.rerun()


def render_monitoring_rebuild(security_mode: bool = False) -> None:
    allowed = [ROLE_ADMIN, ROLE_TEACHER, ROLE_GUARD] if security_mode else [ROLE_ADMIN, ROLE_TEACHER]
    if not require_auth(allowed):
        return
    inject_monitoring_rebuild_css()
    st.markdown('<div class="ewmon-page monitoring-page"></div>', unsafe_allow_html=True)
    for key, default in (("monitoring_expanded_camera_id", None),
                         ("monitoring_selected_building_id", None), ("monitoring_selected_room_id", None)):
        st.session_state.setdefault(key, default)
    buildings = list_buildings()
    if not buildings:
        st.info("Chưa có tòa nhà nào trong hệ thống.")
        return
    building_options = {str(row["ten_toa"]): int(row["id"]) for row in buildings}
    building_names = list(building_options)
    building_key = f"ewmon_building_{security_mode}"
    if st.session_state.get(building_key) not in building_names:
        preferred_building = "Giảng đường Nguyễn Đăng"
        st.session_state[building_key] = preferred_building if preferred_building in building_options else building_names[0]
    building_name = str(st.session_state[building_key])
    building_id = building_options[building_name]
    rooms = list_rooms(building_id)
    if not rooms:
        st.warning("Tòa nhà này chưa có phòng hoạt động.")
        return
    room_options = {str(row["ten_phong"]): int(row["id"]) for row in rooms}
    room_key = f"ewmon_room_{security_mode}_{building_id}"
    if st.session_state.get(room_key) not in room_options:
        st.session_state[room_key] = next(iter(room_options))
    room_name = str(st.session_state[room_key])
    room_id = int(room_options[room_name])
    room = get_room(room_id) or {}
    st.session_state.setdefault("monitoring_mode", int(room.get("monitor_mode") or 0))
    if st.session_state.get("monitoring_selected_room_id") != room_id:
        st.session_state.monitoring_mode = int(room.get("monitor_mode") or 0)
        _reset_monitoring_focus()

    monitoring_layout = st.container(key="monitoring-layout")
    main_col, log_col = monitoring_layout.columns([2.45, 1.0], gap="large", vertical_alignment="top")
    with main_col:
        monitoring_topbar = st.container(key="monitoring-topbar")
        top = monitoring_topbar.columns([1.48, 1.0], gap="large", vertical_alignment="center")
        with top[0]:
            st.text_input(
                "Tìm kiếm camera",
                placeholder="Tòa nhà, phòng học...",
                key=f"ewmon_search_{security_mode}",
                label_visibility="collapsed",
                icon=":material/search:",
            )
        top[1].markdown(
            '<div class="ewmon-nav monitoring-tabs">'
            '<span class="monitoring-tab monitoring-tab-active">Tổng quan</span>'
            '<span class="monitoring-tab monitoring-tab-inactive">Phân tích</span>'
            '<span class="monitoring-system-dot" aria-label="Hệ thống trực tuyến"></span>'
            '<span class="monitoring-settings" aria-label="Cài đặt">'
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/>'
            '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.55V20.3h-3v-.09a1.7 1.7 0 0 0-1.04-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 15a1.7 1.7 0 0 0-1.55-1.04H5.3v-3h.15A1.7 1.7 0 0 0 7 9.92a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.7 4.7V4.6h3v.1a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.55 1.04h.15v3h-.15A1.7 1.7 0 0 0 19.4 15Z"/></svg>'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        can_change_mode = not security_mode and int(st.session_state.role) in (ROLE_ADMIN, ROLE_TEACHER)
        filter_bar = st.container(key="monitoring-filter-bar") if can_change_mode else nullcontext()
        with filter_bar:
            if can_change_mode:
                mode_key = f"ewmon_mode_{room_id}"
                options = ["PHÒNG THI", "PHÒNG THƯỜNG"]
                expected = options[0] if int(st.session_state.monitoring_mode or 0) == 1 else options[1]
                if st.session_state.get(mode_key) not in options:
                    st.session_state[mode_key] = expected
                filter_fields = st.columns([1.08, 1.0, 1.0], gap="large", vertical_alignment="bottom")
                with filter_fields[0]:
                    with st.container(key="monitoring-mode-section"):
                        st.markdown(
                            '<div class="monitoring-mode-label ewmon-mode-label">Chế độ giám sát</div>',
                            unsafe_allow_html=True,
                        )
                        st.radio(
                            "Chế độ",
                            options,
                            horizontal=True,
                            key=mode_key,
                            label_visibility="collapsed",
                            on_change=_apply_monitoring_mode,
                            args=(room_id, mode_key),
                        )
                selectors = filter_fields[1:]
            else:
                st.markdown('<div class="ewmon-selects"></div>', unsafe_allow_html=True)
                selectors = st.columns([1, .34], gap="large")
            building_name = selectors[0].selectbox("Tòa nhà", building_names, key=building_key, on_change=_reset_monitoring_focus)
            building_id = building_options[building_name]
            rooms = list_rooms(building_id)
            room_options = {str(row["ten_phong"]): int(row["id"]) for row in rooms}
            room_key = f"ewmon_room_{security_mode}_{building_id}"
            if st.session_state.get(room_key) not in room_options:
                st.session_state[room_key] = next(iter(room_options))
            room_name = selectors[1].selectbox("Phòng học", list(room_options), key=room_key, on_change=_reset_monitoring_focus)
            room_id = int(room_options[room_name])
            room = get_room(room_id) or {}
        st.session_state.monitoring_selected_building_id = int(building_id)
        st.session_state.monitoring_selected_room_id = room_id
        st.session_state.selected_building, st.session_state.selected_room = building_name, room_name
        current_mode = None if security_mode else int(st.session_state.get("monitoring_mode") or 0)
        cameras = list(list_cameras(room_id) or [])[:4]
        params: list[object] = [room_id]
        mode_sql = ""
        if current_mode is not None:
            mode_sql = "AND v.mode=?"
            params.append(current_mode)
        pending_rows = db_rows(f"""SELECT v.*,c.vi_tri_goc FROM Violation_Logs v LEFT JOIN Cameras c ON c.id=v.camera_id
            WHERE c.room_id=? AND COALESCE(v.is_confirmed,0)=0 {mode_sql} ORDER BY v.created_at DESC,v.id DESC LIMIT 25""", params)
        pending = {int(row["camera_id"]): row for row in pending_rows if row.get("camera_id")}
        camera_ids = {int(camera["id"]) for camera in cameras}
        focused_id = st.session_state.get("monitoring_expanded_camera_id")
        try:
            focused_id = int(focused_id) if focused_id is not None else None
        except (TypeError, ValueError):
            focused_id = None
        if focused_id is not None and focused_id not in camera_ids:
            _reset_monitoring_focus()
            focused_id = None
        elif focused_id is not None:
            st.session_state.monitoring_expanded_camera_id = focused_id
        if not cameras:
            st.info("Phòng học chưa được cấu hình camera.")
        elif focused_id is not None:
            focused = next(camera for camera in cameras if int(camera["id"]) == focused_id)
            _render_ewmon_camera(
                focused,
                cameras.index(focused) + 1,
                pending,
                variant="focus",
                enable_double_click=not security_mode,
            )
            thumbnails = [camera for camera in cameras if int(camera["id"]) != focused_id]
            if thumbnails:
                thumb_cols = st.columns(len(thumbnails), gap="small", vertical_alignment="top")
                for thumb_col, camera in zip(thumb_cols, thumbnails):
                    with thumb_col:
                        _render_ewmon_camera(
                            camera,
                            cameras.index(camera) + 1,
                            pending,
                            variant="thumb",
                            enable_double_click=not security_mode,
                        )
        else:
            for start in range(0, len(cameras), 2):
                cols = st.columns(2, gap="small")
                for col, camera in zip(cols, cameras[start:start + 2]):
                    with col:
                        _render_ewmon_camera(
                            camera,
                            cameras.index(camera) + 1,
                            pending,
                            enable_double_click=not security_mode,
                        )
    with log_col:
        recent = fetch_recent_violations(limit=8, room_id=room_id, mode=current_mode)
        count_row = db_row(f"""SELECT COUNT(*) total FROM Violation_Logs v INNER JOIN Cameras c ON c.id=v.camera_id
            WHERE c.room_id=? AND COALESCE(v.is_confirmed,0)=0 {mode_sql}""", params)
        mode_label = "Phòng thi" if int(room.get("monitor_mode") or 0) else "Phòng thường"
        with st.container(border=False, key="monitoring-violation-panel"):
            _render_ewmon_violations(
                recent,
                int((count_row or {}).get("total") or 0),
                security_mode=security_mode,
                building_name=building_name,
                room_name=room_name,
                mode_label=mode_label,
                camera_index_by_id={int(camera["id"]): index for index, camera in enumerate(cameras, 1)},
            )




def render_reports_page() -> None:
    if not require_auth([ROLE_ADMIN, ROLE_TEACHER]):
        return
    today = date.today()
    initializing_reports = "reports_selected_date" not in st.session_state
    default_report_date = (latest_report_date_with_data() or today) if initializing_reports else today
    defaults = {
        "reports_selected_date": default_report_date, "reports_range_mode": "custom",
        "reports_start_date": default_report_date, "reports_end_date": default_report_date,
        "reports_search_text": "", "reports_last_search_text": "",
        "reports_page_number": 1, "reports_rows": None,
        "reports_popular_normal": "Chưa có dữ liệu",
        "reports_popular_exam": "Chưa có dữ liệu", "reports_error": None,
        "reports_pdf_bytes": None, "reports_excel_bytes": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    def clear_report_exports() -> None:
        st.session_state.reports_pdf_bytes = None
        st.session_state.reports_excel_bytes = None

    def set_report_range(mode: str) -> None:
        end_value = st.session_state.get("reports_selected_date")
        if not isinstance(end_value, date):
            end_value = today
        if mode == "today":
            end_value = today
            st.session_state.reports_selected_date = today
        days = {"today": 1, "7days": 7, "30days": 30, "custom": 1}[mode]
        st.session_state.reports_range_mode = mode
        st.session_state.reports_end_date = end_value
        st.session_state.reports_start_date = end_value - timedelta(days=days - 1)
        st.session_state.reports_page_number = 1

    def select_report_preset(mode: str) -> None:
        set_report_range(mode)

    def select_custom_report_date() -> None:
        st.session_state.reports_range_mode = "custom"
        set_report_range("custom")
        clear_report_exports()

    def load_report_data() -> None:
        selected = st.session_state.get("reports_selected_date")
        if not isinstance(selected, date):
            selected = today
            st.session_state.reports_selected_date = selected
        mode = st.session_state.get("reports_range_mode", "custom")
        set_report_range(mode if mode in {"today", "7days", "30days", "custom"} else "custom")
        start_value = st.session_state.reports_start_date
        end_value = st.session_state.reports_end_date
        try:
            raw = report_rows_for_range(start_value.isoformat(), end_value.isoformat())
            st.session_state.reports_rows = [
                {
                    "TÒA NHÀ": str(row.get("ten_toa") or ""),
                    "PHÒNG HỌC": str(row.get("ten_phong") or ""),
                    "SỐ VI PHẠM PHÒNG THƯỜNG": int(row.get("normal_total") or 0),
                    "SỐ VI PHẠM PHÒNG THI": int(row.get("exam_total") or 0),
                }
                for row in raw
                if int(row.get("normal_total") or 0) or int(row.get("exam_total") or 0)
            ]
            st.session_state.reports_popular_normal = popular_violation_for_range(start_value.isoformat(), end_value.isoformat(), 0)
            st.session_state.reports_popular_exam = popular_violation_for_range(start_value.isoformat(), end_value.isoformat(), 1)
            st.session_state.reports_error = None
            st.session_state.reports_page_number = 1
            clear_report_exports()
        except Exception:
            LOGGER.exception("Unable to load reports data")
            st.session_state.reports_rows = []
            st.session_state.reports_error = "Không thể tải dữ liệu báo cáo. Vui lòng thử lại."

    def reset_reports_state() -> None:
        reset_date = latest_report_date_with_data() or today
        st.session_state.reports_selected_date = reset_date
        st.session_state.reports_range_mode = "custom"
        st.session_state.reports_start_date = reset_date
        st.session_state.reports_end_date = reset_date
        st.session_state.reports_search_text = ""
        st.session_state.reports_last_search_text = ""
        st.session_state.reports_page_number = 1
        st.session_state.reports_error = None
        load_report_data()

    if st.session_state.reports_rows is None:
        load_report_data()

    st.markdown('<div class="reports-page"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        .reports-page{display:block;width:0;height:0;overflow:hidden}
        .reports-page~* .reports-toolbar,.reports-page~* .reports-title-row-marker,.reports-page~* .reports-filter-marker,.reports-page~* .reports-table-marker,.reports-page~* .reports-row-marker,.reports-page~* .reports-pager-marker,.reports-page~* .reports-widget-marker{display:block;width:0;height:0;overflow:hidden}
        .reports-page~* .reports-top-nav{display:flex;align-items:center;justify-content:flex-end;gap:28px;min-height:46px;color:#64748b;font-size:14px;font-weight:750;white-space:nowrap}
        .reports-page~* .reports-tab-active{color:#159447;border-bottom:2px solid #159447;padding:13px 0}
        .reports-page~* .reports-system-badge{padding:11px 22px;color:#fff;background:#199b4c;border-radius:10px;font-weight:800}
        .reports-page~* .reports-online-dot{color:#24a65a;font-size:20px}.reports-page~* .reports-gear{font-size:20px;color:#43516a}
        .reports-page~* .reports-title{margin:20px 0 16px;color:#118a40;font-size:clamp(32px,2.5vw,38px);line-height:1.15;font-weight:800}
        .reports-page~* .reports-popular-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:2px 0 18px}
        .reports-page~* .reports-popular-card{display:flex;align-items:center;gap:20px;min-height:130px;padding:22px 26px;background:#fff;border:1px solid #e7ece9;border-radius:18px;box-shadow:0 8px 24px rgba(15,23,42,.06);box-sizing:border-box}
        .reports-page~* .reports-popular-icon{display:grid;place-items:center;flex:0 0 72px;width:72px;height:72px;border-radius:50%;background:#edf8f1;color:#1ca255;font-size:32px}
        .reports-page~* .reports-popular-label{color:#59657a;font-size:15px;font-weight:800}.reports-page~* .reports-popular-value{margin-top:10px;color:#159447;font-size:clamp(24px,2vw,28px);line-height:1.1;font-weight:800}
        .reports-page~* .reports-popular-date{margin-top:12px;color:#64748b;font-size:12px;font-weight:500}
        .reports-page~* .reports-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:18px}
        .reports-page~* .reports-kpi-card{display:flex;align-items:center;gap:16px;min-height:106px;padding:18px;background:#fff;border:1px solid #e7ece9;border-radius:15px;box-shadow:0 7px 20px rgba(15,23,42,.055);box-sizing:border-box}
        .reports-page~* .reports-kpi-icon{display:grid;place-items:center;flex:0 0 54px;width:54px;height:54px;border-radius:15px;font-size:27px}.reports-page~* .green{color:#20a95a;background:#edf9f1}.reports-page~* .blue{color:#2669dc;background:#eef3ff}.reports-page~* .orange{color:#ef7900;background:#fff6eb}.reports-page~* .purple{color:#7543df;background:#f5efff}
        .reports-page~* .reports-kpi-label{color:#64748b;font-size:12px;font-weight:650}.reports-page~* .reports-kpi-number{margin-top:5px;font-size:25px;line-height:1;font-weight:800}.reports-page~* .reports-kpi-unit{margin-top:7px;color:#64748b;font-size:12px}
        .reports-page~* .reports-table-header-cell{display:flex;align-items:center;min-height:48px;color:#fff;font-size:13px;font-weight:800;text-transform:uppercase}
        .reports-page~* .reports-table-cell{display:flex;align-items:center;min-height:48px;color:#152238;font-size:13px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.reports-page~* .reports-building{font-weight:800}
        .reports-page~* .reports-empty-state{display:flex;align-items:center;justify-content:center;min-height:120px;padding:24px;color:#64748b;font-size:14px;text-align:center}
        .reports-page~* .reports-range-label{color:#526078;font-size:12px;font-weight:650}
        body:has(.reports-page) .stApp{background:#f8faf9!important}body:has(.reports-page) .block-container{max-width:none!important;width:calc(100vw - var(--sidebar-width-desktop,280px))!important;padding:26px 34px 56px!important;margin:0!important;box-sizing:border-box!important;overflow-x:hidden!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-toolbar)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{align-items:center!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-widget)+[data-testid="stElementContainer"] input{height:46px!important;border-radius:10px!important;background:#f0f2f3!important;border:0!important;padding-left:16px!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-title-row-marker)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{align-items:center!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-export-marker)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{justify-content:flex-end!important;gap:12px!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-export-pdf)+[data-testid="stElementContainer"] button{height:44px!important;border-radius:8px!important;background:#159b4b!important;color:#fff!important;border-color:#159b4b!important;font-size:14px!important;font-weight:800!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-export-excel)+[data-testid="stElementContainer"] button{height:44px!important;border-radius:8px!important;background:#fff!important;color:#148e43!important;border:1px solid #1a9c4c!important;font-size:14px!important;font-weight:800!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-marker)+[data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"]{padding:16px 20px!important;background:#fff!important;border:1px solid #e6ebe8!important;border-radius:14px!important;box-shadow:0 7px 20px rgba(15,23,42,.055)!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-filter-row)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{align-items:end!important;gap:14px!important}
        body:has(.reports-page) .stDateInput label{color:#263247!important;font-size:13px!important;font-weight:750!important}body:has(.reports-page) .stDateInput [data-baseweb="input"]>div{min-height:40px!important;border-radius:7px!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-range-button)+[data-testid="stElementContainer"] button,body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-action)+[data-testid="stElementContainer"] button,body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-reset-action)+[data-testid="stElementContainer"] button{height:40px!important;border-radius:7px!important;font-size:13px!important;font-weight:700!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-range-button)+[data-testid="stElementContainer"] button{background:#fff!important;color:#263248!important;border:1px solid #d9e2dc!important;box-shadow:none!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-range-button)+[data-testid="stElementContainer"] button:hover{background:#f1fbf5!important;color:#249950!important;border-color:#9dddb5!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-range-active)+[data-testid="stElementContainer"] button{background:#37bd74!important;color:#fff!important;border-color:#37bd74!important;box-shadow:0 6px 14px rgba(55,189,116,.22)!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-range-active)+[data-testid="stElementContainer"] button:hover{background:#37bd74!important;color:#fff!important;border-color:#37bd74!important;box-shadow:0 6px 14px rgba(55,189,116,.22)!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-action)+[data-testid="stElementContainer"] button{background:#269e50!important;color:#fff!important;border-color:#269e50!important;box-shadow:0 6px 14px rgba(38,158,80,.2)!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-search-action)+[data-testid="stElementContainer"] button:hover{background:#208b46!important;border-color:#208b46!important;color:#fff!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-reset-action)+[data-testid="stElementContainer"] button{background:#fff!important;color:#249950!important;border:1px solid #37bd74!important;box-shadow:none!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-reset-action)+[data-testid="stElementContainer"] button:hover{background:#f1fbf5!important;color:#208b46!important;border-color:#249950!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-table-marker)+[data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"]{padding:0!important;margin-top:14px;overflow:hidden!important;background:#fff!important;border:1px solid #e5e9e7!important;border-radius:10px!important;box-shadow:0 7px 20px rgba(15,23,42,.055)!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-table-marker)+[data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"]>div{gap:0!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-table-head)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{min-width:900px;gap:0!important;padding:0 20px!important;background:#29a956!important}
        body:has(.reports-page) .reports-table-head+div [data-testid="stHorizontalBlock"],body:has(.reports-page) [data-testid="element-container"]:has(.reports-table-head)+[data-testid="element-container"] [data-testid="stHorizontalBlock"]{min-width:900px;gap:0!important;padding:0 20px!important;background:#29a956!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-row-marker)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{min-width:900px;gap:0!important;padding:0 20px!important;border-bottom:1px solid #edf0ee!important;background:#fff!important}body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-row-marker)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]:hover{background:#f1fbf5!important}
        body:has(.reports-page) .reports-row-marker+div [data-testid="stHorizontalBlock"],body:has(.reports-page) [data-testid="element-container"]:has(.reports-row-marker)+[data-testid="element-container"] [data-testid="stHorizontalBlock"]{min-width:900px;gap:0!important;padding:0 20px!important;border-bottom:1px solid #edf0ee!important;background:#fff!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-row-action)+[data-testid="stElementContainer"] button{height:34px!important;min-height:34px!important;padding:0!important;border:0!important;background:transparent!important;color:#30415b!important;box-shadow:none!important;font-size:22px!important}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-pager-marker)+[data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]{align-items:center!important;padding:10px 18px 13px!important;gap:7px!important}body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-page-button)+[data-testid="stElementContainer"] button{height:36px!important;min-height:36px!important;padding:0!important;border-radius:6px!important;font-size:13px!important}body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-page-active)+[data-testid="stElementContainer"] button{background:#24a653!important;color:#fff!important;border-color:#24a653!important}
        body:has(.reports-page) .reports-toolbar,body:has(.reports-page) .reports-title-row-marker,body:has(.reports-page) .reports-filter-marker,body:has(.reports-page) .reports-table-marker,body:has(.reports-page) .reports-row-marker,body:has(.reports-page) .reports-pager-marker,body:has(.reports-page) .reports-widget-marker{display:block;width:0;height:0;overflow:hidden}
        body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-toolbar),body:has(.reports-page) [data-testid="stElementContainer"]:has(.reports-title-row-marker){display:none!important}
        body:has(.reports-page) .reports-top-nav{display:flex;align-items:center;justify-content:flex-end;gap:28px;min-height:46px;color:#64748b;font-size:14px;font-weight:750;white-space:nowrap}
        body:has(.reports-page) .reports-tab-active{color:#159447;border-bottom:2px solid #159447;padding:13px 0}body:has(.reports-page) .reports-system-badge{padding:11px 22px;color:#fff;background:#199b4c;border-radius:10px;font-weight:800}body:has(.reports-page) .reports-online-dot{color:#24a65a;font-size:20px}body:has(.reports-page) .reports-gear{font-size:20px;color:#43516a}
        body:has(.reports-page) .reports-title{margin:24px 0 22px;padding:0!important;color:#118a40;font-size:clamp(32px,2.5vw,38px);line-height:1.15;font-weight:800}
        body:has(.reports-page) .reports-popular-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:2px 0 18px}body:has(.reports-page) .reports-popular-card{display:flex;align-items:center;gap:20px;min-height:130px;padding:22px 26px;background:#fff;border:1px solid #e7ece9;border-radius:18px;box-shadow:0 8px 24px rgba(15,23,42,.06);box-sizing:border-box}body:has(.reports-page) .reports-popular-icon{display:grid;place-items:center;flex:0 0 72px;width:72px;height:72px;border-radius:50%;background:#edf8f1;color:#1ca255;font-size:32px}body:has(.reports-page) .reports-popular-label{color:#59657a;font-size:15px;font-weight:800}body:has(.reports-page) .reports-popular-value{margin-top:10px;color:#159447;font-size:clamp(24px,2vw,28px);line-height:1.1;font-weight:800}body:has(.reports-page) .reports-popular-date{margin-top:12px;color:#64748b;font-size:12px;font-weight:500}
        body:has(.reports-page) .reports-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:18px}body:has(.reports-page) .reports-kpi-card{display:flex;align-items:center;gap:16px;min-height:106px;padding:18px;background:#fff;border:1px solid #e7ece9;border-radius:15px;box-shadow:0 7px 20px rgba(15,23,42,.055);box-sizing:border-box}body:has(.reports-page) .reports-kpi-icon{display:grid;place-items:center;flex:0 0 54px;width:54px;height:54px;border-radius:15px;font-size:27px}body:has(.reports-page) .green{color:#20a95a;background:#edf9f1}body:has(.reports-page) .blue{color:#2669dc;background:#eef3ff}body:has(.reports-page) .orange{color:#ef7900;background:#fff6eb}body:has(.reports-page) .purple{color:#7543df;background:#f5efff}body:has(.reports-page) .reports-kpi-label{color:#64748b;font-size:12px;font-weight:650}body:has(.reports-page) .reports-kpi-number{margin-top:5px;font-size:25px;line-height:1;font-weight:800}body:has(.reports-page) .reports-kpi-unit{margin-top:7px;color:#64748b;font-size:12px}
        body:has(.reports-page) .reports-table-header-cell{display:flex;align-items:center;min-height:48px;color:#fff;font-size:13px;font-weight:800;text-transform:uppercase}body:has(.reports-page) .reports-table-cell{display:flex;align-items:center;min-height:48px;color:#152238;font-size:13px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}body:has(.reports-page) .reports-building{font-weight:800}body:has(.reports-page) .reports-empty-state{display:flex;align-items:center;justify-content:center;min-height:120px;padding:24px;color:#64748b;font-size:14px;text-align:center}body:has(.reports-page) .reports-range-label{color:#526078;font-size:12px;font-weight:650}
        body:has(.reports-page) .reports-table-header{display:grid;grid-template-columns:1.25fr 1fr 1.25fr 1.25fr .18fr;min-width:900px;padding:0 20px;background:#29a956}
        @media(max-width:1200px){body:has(.reports-page) .reports-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}body:has(.reports-page) .block-container{width:calc(100vw - var(--sidebar-width-laptop,260px))!important;padding:24px 26px 48px!important}}
        @media(max-width:850px){body:has(.reports-page) .reports-popular-grid{grid-template-columns:1fr}body:has(.reports-page) .reports-top-nav{gap:12px;justify-content:flex-start;flex-wrap:wrap}body:has(.reports-page) .block-container{width:calc(100vw - var(--sidebar-width-tablet,82px))!important;padding:20px!important}}
        @media(max-width:620px){body:has(.reports-page) .reports-kpi-grid{grid-template-columns:1fr}body:has(.reports-page) .reports-popular-card{padding:18px}body:has(.reports-page) .reports-system-badge{padding:8px 12px}}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="reports-toolbar"></div>', unsafe_allow_html=True)
    toolbar = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with toolbar[0]:
        st.markdown('<div class="reports-widget-marker reports-search-widget"></div>', unsafe_allow_html=True)
        search_text = st.text_input("Tìm kiếm báo cáo", placeholder="⌕  Tìm kiếm tòa nhà, phòng học...", key="reports_search_text", label_visibility="collapsed")
    with toolbar[1]:
        st.markdown('<div class="reports-top-nav"><span>Tổng quan</span><span class="reports-tab-active">Phân tích</span><span class="reports-system-badge">System Online</span><span class="reports-online-dot">●</span><span class="reports-gear">⚙</span></div>', unsafe_allow_html=True)
    normalized_query = str(search_text or "").strip().casefold()
    if str(st.session_state.reports_last_search_text).strip().casefold() != normalized_query:
        st.session_state.reports_last_search_text = search_text
        st.session_state.reports_page_number = 1
        clear_report_exports()

    all_rows = list(st.session_state.reports_rows or [])
    filtered_rows = [row for row in all_rows if not normalized_query or normalized_query in str(row["TÒA NHÀ"]).casefold() or normalized_query in str(row["PHÒNG HỌC"]).casefold()]
    buildings_total = len({row["TÒA NHÀ"] for row in filtered_rows if row["TÒA NHÀ"]})
    rooms_total = len({(row["TÒA NHÀ"], row["PHÒNG HỌC"]) for row in filtered_rows if row["PHÒNG HỌC"]})
    normal_total = sum(int(row["SỐ VI PHẠM PHÒNG THƯỜNG"]) for row in filtered_rows)
    exam_total = sum(int(row["SỐ VI PHẠM PHÒNG THI"]) for row in filtered_rows)
    start_value, end_value = st.session_state.reports_start_date, st.session_state.reports_end_date
    range_text = start_value.strftime("%d/%m/%Y") if start_value == end_value else f"{start_value:%d/%m/%Y} – {end_value:%d/%m/%Y}"
    file_range = start_value.isoformat() if start_value == end_value else f"{start_value.isoformat()}_den_{end_value.isoformat()}"
    export_df = pd.DataFrame(filtered_rows, columns=["TÒA NHÀ", "PHÒNG HỌC", "SỐ VI PHẠM PHÒNG THƯỜNG", "SỐ VI PHẠM PHÒNG THI"])

    st.markdown('<div class="reports-title-row-marker"></div>', unsafe_allow_html=True)
    title_cols = st.columns([1, .48], gap="large", vertical_alignment="center")
    title_cols[0].markdown('<h1 class="reports-title">Thống kê báo cáo</h1>', unsafe_allow_html=True)
    with title_cols[1]:
        st.markdown('<div class="reports-widget-marker reports-export-marker"></div>', unsafe_allow_html=True)
        export_cols = st.columns(2, gap="small")
        with export_cols[0]:
            st.markdown('<div class="reports-widget-marker reports-export-pdf"></div>', unsafe_allow_html=True)
            if st.session_state.reports_pdf_bytes:
                st.download_button("▣  TẢI PDF", st.session_state.reports_pdf_bytes, file_name=f"bao_cao_vi_pham_{file_range}.pdf", mime="application/pdf", key="reports_download_pdf", width="stretch")
            elif st.button("▣  XUẤT PDF", key="reports_prepare_pdf", disabled=export_df.empty, width="stretch"):
                try:
                    subtitle = f"Phạm vi: {range_text}<br/>Xuất lúc: {datetime.now():%d/%m/%Y %H:%M}<br/>Phổ biến phòng thường: {escape(st.session_state.reports_popular_normal)}<br/>Phổ biến phòng thi: {escape(st.session_state.reports_popular_exam)}<br/>Tòa nhà: {buildings_total} | Phòng: {rooms_total} | Vi phạm phòng thường: {normal_total} | Vi phạm phòng thi: {exam_total}"
                    st.session_state.reports_pdf_bytes = make_pdf_bytes("Báo cáo thống kê EduWatch", subtitle, export_df)
                    st.rerun()
                except Exception:
                    LOGGER.exception("Unable to create reports PDF")
                    st.error("Không thể tạo file báo cáo. Vui lòng thử lại.")
        with export_cols[1]:
            st.markdown('<div class="reports-widget-marker reports-export-excel"></div>', unsafe_allow_html=True)
            if st.session_state.reports_excel_bytes:
                st.download_button("▦  TẢI EXCEL", st.session_state.reports_excel_bytes, file_name=f"bao_cao_vi_pham_{file_range}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="reports_download_excel", width="stretch")
            elif st.button("▦  EXCEL", key="reports_prepare_excel", disabled=export_df.empty, width="stretch"):
                try:
                    st.session_state.reports_excel_bytes = make_excel_bytes(export_df)
                    st.rerun()
                except Exception:
                    LOGGER.exception("Unable to create reports Excel")
                    st.error("Không thể tạo file báo cáo. Vui lòng thử lại.")

    st.markdown(f'<div class="reports-popular-grid"><div class="reports-popular-card"><div class="reports-popular-icon">▯</div><div><div class="reports-popular-label">VI PHẠM PHỔ BIẾN PHÒNG THƯỜNG</div><div class="reports-popular-value">{escape(st.session_state.reports_popular_normal)}</div><div class="reports-popular-date">Cập nhật: {range_text}</div></div></div><div class="reports-popular-card"><div class="reports-popular-icon">♧</div><div><div class="reports-popular-label">VI PHẠM PHỔ BIẾN PHÒNG THI</div><div class="reports-popular-value">{escape(st.session_state.reports_popular_exam)}</div><div class="reports-popular-date">Cập nhật: {range_text}</div></div></div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="reports-kpi-grid"><div class="reports-kpi-card"><div class="reports-kpi-icon green">▥</div><div><div class="reports-kpi-label">Tổng số tòa nhà</div><div class="reports-kpi-number" style="color:#20a95a">{buildings_total}</div><div class="reports-kpi-unit">tòa nhà</div></div></div><div class="reports-kpi-card"><div class="reports-kpi-icon blue">▯</div><div><div class="reports-kpi-label">Tổng số phòng học</div><div class="reports-kpi-number" style="color:#2669dc">{rooms_total}</div><div class="reports-kpi-unit">phòng</div></div></div><div class="reports-kpi-card"><div class="reports-kpi-icon orange">♢</div><div><div class="reports-kpi-label">Tổng vi phạm phòng thường</div><div class="reports-kpi-number" style="color:#ef7900">{normal_total}</div><div class="reports-kpi-unit">vi phạm</div></div></div><div class="reports-kpi-card"><div class="reports-kpi-icon purple">♙</div><div><div class="reports-kpi-label">Tổng vi phạm phòng thi</div><div class="reports-kpi-number" style="color:#7543df">{exam_total}</div><div class="reports-kpi-unit">vi phạm</div></div></div></div>', unsafe_allow_html=True)

    st.markdown('<div class="reports-filter-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="reports-widget-marker reports-filter-row"></div>', unsafe_allow_html=True)
        filters = st.columns([1.5, .55, .55, .62, 1.15, 1.05], gap="small", vertical_alignment="bottom")
        with filters[0]:
            selected_date = st.date_input("Ngày báo cáo", format="DD/MM/YYYY", key="reports_selected_date", on_change=select_custom_report_date)
        mode_buttons = [("today", "Hôm nay", "reports-range-today"), ("7days", "7 ngày", "reports-range-7days"), ("30days", "30 ngày", "reports-range-30days")]
        for col, (mode, label, marker_class) in zip(filters[1:4], mode_buttons):
            with col:
                active = st.session_state.reports_range_mode == mode
                st.markdown(f'<div class="reports-widget-marker reports-range-button {marker_class} {"reports-range-active" if active else ""}"></div>', unsafe_allow_html=True)
                st.button(label, key=f"reports_range_{mode}", width="stretch", on_click=select_report_preset, args=(mode,))
        with filters[4]:
            st.markdown('<div class="reports-widget-marker reports-search-action"></div>', unsafe_allow_html=True)
            if st.button("⌕  TÌM KIẾM", key="reports_submit", width="stretch"):
                with st.spinner("Đang tải dữ liệu báo cáo..."):
                    load_report_data()
                st.rerun()
        with filters[5]:
            st.markdown('<div class="reports-widget-marker reports-reset-action"></div>', unsafe_allow_html=True)
            st.button("⟳  ĐẶT LẠI", key="reports_reset", width="stretch", on_click=reset_reports_state)

    if st.session_state.reports_error:
        st.error(st.session_state.reports_error)

    page_size = 10
    total_rows = len(filtered_rows)
    total_pages = max(1, math.ceil(total_rows / page_size))
    page_number = min(max(int(st.session_state.reports_page_number or 1), 1), total_pages)
    st.session_state.reports_page_number = page_number
    page_rows = filtered_rows[(page_number - 1) * page_size:page_number * page_size]
    st.markdown('<div class="reports-table-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        ratios = [1.25, 1, 1.25, 1.25, .18]
        st.markdown('<div class="reports-table-header"><div class="reports-table-header-cell">TÒA NHÀ</div><div class="reports-table-header-cell">PHÒNG HỌC</div><div class="reports-table-header-cell">SỐ VI PHẠM PHÒNG THƯỜNG</div><div class="reports-table-header-cell">SỐ VI PHẠM PHÒNG THI</div><div></div></div>', unsafe_allow_html=True)
        if not page_rows:
            st.markdown('<div class="reports-empty-state">⌕ &nbsp; Không có dữ liệu báo cáo phù hợp với bộ lọc đã chọn.</div>', unsafe_allow_html=True)
        for index, row in enumerate(page_rows):
            st.markdown('<div class="reports-widget-marker reports-row-marker"></div>', unsafe_allow_html=True)
            cols = st.columns(ratios, gap=None)
            cols[0].markdown(f'<div class="reports-table-cell reports-building">{escape(row["TÒA NHÀ"])}</div>', unsafe_allow_html=True)
            cols[1].markdown(f'<div class="reports-table-cell">{escape(row["PHÒNG HỌC"])}</div>', unsafe_allow_html=True)
            cols[2].markdown(f'<div class="reports-table-cell">{row["SỐ VI PHẠM PHÒNG THƯỜNG"]}</div>', unsafe_allow_html=True)
            cols[3].markdown(f'<div class="reports-table-cell">{row["SỐ VI PHẠM PHÒNG THI"]}</div>', unsafe_allow_html=True)
            with cols[4]:
                st.markdown('<div class="reports-widget-marker reports-row-action"></div>', unsafe_allow_html=True)
                if st.button("›", key=f"reports_detail_{page_number}_{index}", help="Xem nhật ký của phòng"):
                    location = db_row("SELECT b.id AS building_id, r.id AS room_id FROM Rooms r LEFT JOIN Buildings b ON b.id=r.building_id WHERE b.ten_toa=? AND r.ten_phong=? AND COALESCE(r.is_deleted,0)=0 LIMIT 1", (row["TÒA NHÀ"], row["PHÒNG HỌC"])) or {}
                    st.session_state.violations_building = row["TÒA NHÀ"]
                    st.session_state.violations_room = row["PHÒNG HỌC"]
                    st.session_state.violations_start_date = start_value
                    st.session_state.violations_end_date = end_value
                    st.session_state.violations_mode = "Tất cả"
                    st.session_state.violations_has_searched = True
                    st.session_state.violations_page_number = 1
                    st.session_state.violations_applied_filters = {"query": "", "building_id": location.get("building_id"), "room_id": location.get("room_id"), "mode": "all", "status": "all", "violation_type": "all", "start_at": f"{start_value.isoformat()} 00:00:00", "end_at": f"{end_value.isoformat()} 23:59:59"}
                    set_page("violations")
                    st.rerun()
        st.markdown('<div class="reports-widget-marker reports-pager-marker"></div>', unsafe_allow_html=True)
        pager_items: list[int | str] = list(range(1, total_pages + 1)) if total_pages <= 7 else ([1, 2, 3, "…", total_pages] if page_number <= 3 else [1, "…", page_number - 1, page_number, page_number + 1, "…", total_pages] if page_number < total_pages - 2 else [1, "…", total_pages - 2, total_pages - 1, total_pages])
        pager = st.columns([4.2, .42] + [.42] * len(pager_items) + [.42], gap="small", vertical_alignment="center")
        start_index = (page_number - 1) * page_size + 1 if total_rows else 0
        end_index = min(page_number * page_size, total_rows)
        pager[0].markdown(f'<div class="reports-range-label">Hiển thị {start_index} - {end_index} trong tổng số {total_rows} kết quả</div>', unsafe_allow_html=True)
        with pager[1]:
            st.markdown('<div class="reports-widget-marker reports-page-button"></div>', unsafe_allow_html=True)
            if st.button("‹", key="reports_prev", disabled=page_number <= 1, width="stretch"):
                st.session_state.reports_page_number = page_number - 1; st.rerun()
        for col, item in zip(pager[2:-1], pager_items):
            with col:
                if item == "…":
                    st.markdown('<div class="reports-range-label" style="text-align:center">…</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="reports-widget-marker reports-page-button {"reports-page-active" if item == page_number else ""}"></div>', unsafe_allow_html=True)
                    if st.button(str(item), key=f"reports_page_{item}", width="stretch"):
                        st.session_state.reports_page_number = int(item); st.rerun()
        with pager[-1]:
            st.markdown('<div class="reports-widget-marker reports-page-button"></div>', unsafe_allow_html=True)
            if st.button("›", key="reports_next", disabled=page_number >= total_pages, width="stretch"):
                st.session_state.reports_page_number = page_number + 1; st.rerun()




def _status_label(value: object) -> str:
    status = int(value or 0)
    if status == 1:
        return "Đã xác nhận"
    if status == -1:
        return "Báo sai AI"
    return "Chờ xác nhận"




def _format_log_time(row: dict) -> str:
    raw = row.get("thoi_gian") or row.get("created_at") or ""
    text = str(raw)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], pattern).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    return text


def _confidence_text(row: dict) -> str:
    try:
        return f"{float(row.get('confidence') or 0):.0%}"
    except (TypeError, ValueError):
        return "0%"


def _preview_style(row: dict) -> str:
    image_file = evidence_path(row.get("image_path"))
    image_uri = file_to_data_uri(image_file) if image_file and image_file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ""
    return f' style="background-image:url({image_uri});"' if image_uri else ""


def violation_log_export_dataframe(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": row.get("id"),
                "Thời gian": _format_log_time(row),
                "Camera": row.get("vi_tri_goc") or "",
                "Phòng học": row.get("ten_phong") or "",
                "Tòa nhà": row.get("ten_toa") or "",
                "Loại vi phạm": row.get("loai_vi_pham") or "",
                "Độ tin cậy": _confidence_text(row),
                "Trạng thái": _status_label(row.get("is_confirmed")),
                "Chế độ": "Phòng thi" if int(row.get("mode") or 0) == 1 else "Phòng thường",
            }
            for row in rows
        ]
        or [
            {
                "ID": "",
                "Thời gian": "",
                "Camera": "",
                "Phòng học": "",
                "Tòa nhà": "",
                "Loại vi phạm": "",
                "Độ tin cậy": "",
                "Trạng thái": "",
                "Chế độ": "",
            }
        ]
    )




def _render_violation_journal() -> None:
    """Render the database-backed violation journal without touching shared sidebar UI."""
    pending_default_end = date.today()
    defaults = {
        "violations_search_submitted": False,
        "violations_applied_filters": None,
        "violations_page_number": 1,
        "violations_page_size": 10,
        "violations_selected_detail_id": None,
        "violations_detail_closed": False,
        "violations_selected_ids": set(),
        "violations_last_updated": None,
        "violations_range_mode": None,
        "violations_building": "Tất cả tòa nhà",
        "violations_room": "Tất cả phòng",
        "violations_type": "Tất cả vi phạm",
        "violations_status": "Chờ xác nhận",
        "violations_mode": "Tất cả",
        "violations_camera": "Tất cả camera",
        "violations_start_date": pending_default_end - timedelta(days=6),
        "violations_end_date": pending_default_end,
        "violations_min_confidence": 0,
        "violations_confirm_action": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.violations_range_mode not in {None, "today", "7days", "30days", "custom"}:
        st.session_state.violations_range_mode = None

    def reset_journal() -> None:
        for state_key, state_value in defaults.items():
            st.session_state[state_key] = state_value.copy() if isinstance(state_value, set) else state_value

    def set_journal_range(mode: str) -> None:
        if mode == "today":
            range_end = date.today()
            range_days = 1
        else:
            current_end = st.session_state.get("violations_end_date")
            range_end = current_end if isinstance(current_end, date) else date.today()
            range_days = 7 if mode == "7days" else 30
        st.session_state.violations_start_date = range_end - timedelta(days=range_days - 1)
        st.session_state.violations_end_date = range_end
        st.session_state.violations_range_mode = mode

    def mark_journal_range_custom() -> None:
        st.session_state.violations_range_mode = "custom"

    # Compatibility with links created by the Reports page.
    if st.session_state.pop("violations_has_searched", False) and st.session_state.get("violations_applied_filters"):
        st.session_state.violations_search_submitted = True

    st.markdown('<div class="violations-page"></div>', unsafe_allow_html=True)
    st.markdown("""
    <style>
    body:has(.violations-page) .violations-page{display:block;width:0;height:0;overflow:hidden}
    body:has(.violations-page) .block-container{padding-top:1.45rem!important;max-width:none!important}
    body:has(.violations-page) .v-title{margin:0;color:#0f172a;font-size:2.15rem;line-height:1.1;font-weight:850;letter-spacing:-.025em}
    body:has(.violations-page) .v-subtitle{margin:.55rem 0 1.35rem;color:#64748b;font-size:.86rem}
    body:has(.violations-page) .v-marker{display:block;width:0;height:0;overflow:hidden}
    body:has(.violations-page) [data-testid="stVerticalBlockBorderWrapper"]{border-color:#e3e9e5;border-radius:14px;box-shadow:0 4px 14px rgba(15,23,42,.045)}
    body:has(.violations-page) .stSelectbox label,body:has(.violations-page) .stDateInput label,body:has(.violations-page) .stNumberInput label{font-size:.76rem!important;font-weight:650!important;color:#334155!important}
    body:has(.violations-page) .stSelectbox [data-baseweb="select"]>div,body:has(.violations-page) .stDateInput [data-baseweb="input"]>div,body:has(.violations-page) .stNumberInput [data-baseweb="input"]>div{min-height:46px;border-color:#dce3df;border-radius:9px;background:#fff}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.v-action-primary)+[data-testid="stElementContainer"] button{color:#fff;background:#168c34;border-color:#168c34;font-weight:750}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.v-action-outline)+[data-testid="stElementContainer"] button{color:#168c34;background:#fff;border-color:#35a64d;font-weight:700}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.v-search)+[data-testid="stElementContainer"] button{min-height:46px;color:#fff;background:#168c34;border-color:#168c34;font-weight:750}
    body:has(.violations-page) .v-applied{display:flex;align-items:center;min-height:46px;color:#475569;font-size:.82rem}
    body:has(.violations-page) .v-summary{display:flex;align-items:center;gap:26px;min-height:68px;padding:0 18px;border:1px solid #e3e9e5;border-radius:13px;background:#fff;box-shadow:0 4px 14px rgba(15,23,42,.04);font-size:.8rem;color:#475569}
    body:has(.violations-page) .v-summary strong{font-size:1.03rem;color:#0f172a}body:has(.violations-page) .v-summary .n{display:inline-grid;place-items:center;width:38px;height:38px;margin-right:8px;border-radius:50%;font-size:1.1rem;font-weight:800}body:has(.violations-page) .v-summary .pending{color:#e99a08;background:#fff4d7}body:has(.violations-page) .v-summary .ok{color:#168c34;background:#eaf7ed}body:has(.violations-page) .v-summary .bad{color:#e33448;background:#fdebed}
    body:has(.violations-page) .v-empty{display:grid;place-items:center;min-height:205px;padding:24px;text-align:center;color:#64748b;border:1px solid #e3e9e5;border-radius:14px;background:#fff;box-shadow:0 4px 14px rgba(15,23,42,.04)}
    body:has(.violations-page) .v-empty-icon{display:grid;place-items:center;width:58px;height:58px;margin:0 auto 18px;border-radius:50%;color:#168c34;background:#edf8f0;font-size:1.7rem}
    body:has(.violations-page) .st-key-violations_detail_card [data-testid="stVerticalBlockBorderWrapper"]{min-width:0;max-height:790px;padding:16px!important;overflow-x:hidden;overflow-y:auto;border:1px solid #e1e8e3!important;border-radius:15px!important;background:#fff;box-shadow:0 4px 14px rgba(15,23,42,.04)}
    body:has(.violations-page) .st-key-violations_detail_card [data-testid="stVerticalBlock"]{gap:10px!important}
    body:has(.violations-page) .st-key-violations_detail_card img{width:100%!important;max-height:220px;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:#f1f5f3}
    body:has(.violations-page) .v-detail-title{margin:0;color:#0f172a;font-size:1rem;font-weight:800;white-space:nowrap}
    body:has(.violations-page) .v-detail-placeholder{display:grid;place-items:center;min-height:635px;padding:18px;text-align:center;color:#94a3b8}
    body:has(.violations-page) .v-detail-placeholder p{max-width:220px;margin:8px 0 0;font-size:.78rem;line-height:1.5}
    body:has(.violations-page) .v-detail-placeholder-icon{margin-bottom:12px;font-size:2rem}
    body:has(.violations-page) .v-detail-image-placeholder{display:grid;place-items:center;width:100%;min-height:150px;padding:16px;box-sizing:border-box;border-radius:10px;background:#f7faf8;color:#94a3b8;text-align:center;font-size:.8rem}
    body:has(.violations-page) .st-key-vj_close_x button{min-height:30px!important;padding:0!important;border:0!important;background:transparent!important;color:#334155!important;font-size:1.25rem!important;box-shadow:none!important}
    body:has(.violations-page) .v-meta{display:grid;grid-template-columns:92px minmax(0,1fr);gap:12px 8px;margin:8px 0;font-size:.78rem;align-items:start}
    body:has(.violations-page) .v-meta span{color:#64748b}body:has(.violations-page) .v-meta strong{min-width:0;color:#1e293b;font-weight:600;overflow-wrap:break-word}body:has(.violations-page) .v-progress{height:5px;margin-top:5px;border-radius:9px;background:#e5e7eb;overflow:hidden}body:has(.violations-page) .v-progress i{display:block;height:100%;background:#168c34}
    body:has(.violations-page) .v-badge{display:inline-flex;padding:5px 9px;border-radius:7px;font-size:.72rem;font-weight:700}body:has(.violations-page) .v-badge.pending{color:#d88900;background:#fff4d7;border:1px solid #ffe3a0}body:has(.violations-page) .v-badge.confirmed{color:#168c34;background:#e9f7ed}body:has(.violations-page) .v-badge.false-ai{color:#df2d3f;background:#fde9ec}
    body:has(.violations-page) .v-table{width:100%;min-width:0;overflow:hidden;border:1px solid #e3e9e5;border-radius:12px;background:#fff}body:has(.violations-page) .v-table-grid{display:grid;grid-template-columns:4% 13% 17% 9% 10% 16% 11% 13% 7%;width:100%;min-width:0;align-items:center}body:has(.violations-page) .v-th{display:flex;align-items:center;justify-content:center;min-width:0;min-height:44px;padding:8px 5px;box-sizing:border-box;color:#fff;background:#168c34;font-size:.7rem;font-weight:750;line-height:1.25;white-space:nowrap}body:has(.violations-page) .v-td{min-width:0;min-height:57px;padding:9px 5px;border-bottom:1px solid #edf1ee;color:#243047;font-size:.72rem;line-height:1.45;overflow-wrap:break-word}body:has(.violations-page) .v-row-selected .v-td{background:#f0f9f2}body:has(.violations-page) .v-confidence{display:flex;align-items:center;gap:7px}body:has(.violations-page) .v-confidence i{display:block;width:38px;height:4px;border-radius:5px;background:#168c34}
    body:has(.violations-page) .v-page-note{padding:11px 2px;color:#64748b;font-size:.76rem}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.v-eye)+[data-testid="stElementContainer"] button{min-height:32px;padding:0;color:#168c34;background:#fff;border-color:#dbe5df}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.v-danger)+[data-testid="stElementContainer"] button{color:#e33448;background:#fff;border-color:#ff6673}
    body:has(.violations-page) .violations-filter-label{height:18px;margin:0 0 7px;font-size:12px;line-height:18px;font-weight:600;color:#263248;white-space:nowrap;overflow:visible}
    body:has(.violations-page) .violations-filter-label-hidden{visibility:hidden}
    body:has(.violations-page) .stDateInput [data-baseweb="input"]>div{height:44px!important;min-height:44px!important;max-height:44px!important;box-sizing:border-box!important;border-radius:9px!important}
    body:has(.violations-page) .st-key-violations_preset_today button,body:has(.violations-page) .st-key-violations_preset_7days button,body:has(.violations-page) .st-key-violations_preset_30days button{width:100%!important;height:44px!important;min-width:76px!important;min-height:44px!important;max-height:44px!important;padding:0 10px!important;border-radius:9px!important;font-size:13px!important;line-height:1!important;white-space:nowrap!important;text-align:center!important}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.violations-preset-active)+[data-testid="stElementContainer"] button{color:#fff!important;background:#37bd74!important;border:1px solid #37bd74!important;font-weight:700!important;box-shadow:0 8px 20px rgba(55,189,116,.18)!important}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.violations-preset-inactive)+[data-testid="stElementContainer"] button{color:#263248!important;background:#fff!important;border:1px solid #d9e2dc!important;font-weight:600!important;box-shadow:none!important}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.violations-preset-inactive)+[data-testid="stElementContainer"] button:hover{color:#249950!important;background:#f1fbf5!important;border-color:#9dddb5!important}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.violations-advanced-control)+[data-testid="stElementContainer"] button,body:has(.violations-page) .st-key-vj_search button,body:has(.violations-page) .st-key-vj_reset button{width:100%!important;height:44px!important;min-height:44px!important;max-height:44px!important;padding:0 12px!important;box-sizing:border-box!important;border-radius:9px!important;font-size:13px!important;line-height:1!important;white-space:nowrap!important}
    body:has(.violations-page) [data-testid="stElementContainer"]:has(.violations-advanced-control)+[data-testid="stElementContainer"] button{min-width:150px!important;color:#263248!important;background:#fff!important;border-color:#d9e2dc!important}
    body:has(.violations-page) .st-key-vj_search button{color:#fff!important;background:#269e50!important;border-color:#269e50!important;font-weight:700!important}
    body:has(.violations-page) .st-key-vj_reset button{color:#249950!important;background:#fff!important;border-color:#37bd74!important;font-weight:700!important}
    body:has(.violations-page) .st-key-violations_filter_chips{display:flex!important;flex-wrap:wrap!important;align-items:center!important;gap:8px!important}
    body:has(.violations-page) .st-key-violations_filter_chips button{width:auto!important;min-height:34px!important;padding:7px 12px!important;white-space:nowrap!important;font-size:.75rem!important;color:#168c34!important;background:#eff9f2!important;border-color:#d8eddd!important;box-shadow:none!important}
    body:has(.violations-page) .st-key-vj_clear_chips button{color:#64748b!important;background:#fff!important;border-color:transparent!important}
    body:has(.violations-page) [data-testid="stHorizontalBlock"]:has(.v-summary){align-items:flex-start!important;gap:16px!important}
    body:has(.violations-page) [data-testid="stHorizontalBlock"]:has(.v-summary)>[data-testid="stColumn"]{min-width:0!important}
    @media(max-width:1100px){body:has(.violations-page) .v-detail{min-height:420px}body:has(.violations-page) .v-summary{gap:10px;flex-wrap:wrap;padding:12px}}
    </style>
    """, unsafe_allow_html=True)

    title_col, actions_col = st.columns([1.5, 1], gap="large")
    title_col.markdown('<h1 class="v-title">Nhật ký vi phạm</h1><div class="v-subtitle">Dữ liệu giám sát tự động từ hệ thống AI EduWatch. Vui lòng xác nhận các trường hợp vi phạm để cập nhật báo cáo đào tạo.</div>', unsafe_allow_html=True)
    with actions_col:
        ac = st.columns([.8, 1.25, .9, .12], gap="small")
        submitted = bool(st.session_state.violations_search_submitted)
        with ac[0]:
            st.markdown('<span class="v-marker v-action-outline"></span>', unsafe_allow_html=True)
            export_excel = st.button("▦  EXCEL", disabled=not submitted, width="stretch", key="vj_excel")
        with ac[1]:
            st.markdown('<span class="v-marker v-action-primary"></span>', unsafe_allow_html=True)
            export_pdf = st.button("▣  XUẤT BÁO CÁO PDF", disabled=not submitted, width="stretch", key="vj_pdf")
        with ac[2]:
            st.markdown('<span class="v-marker v-action-outline"></span>', unsafe_allow_html=True)
            refresh = st.button("⟳  LÀM MỚI", width="stretch", key="vj_refresh")
        ac[3].markdown('<div style="width:12px;height:12px;margin:13px auto;border-radius:50%;background:#1aaa3f"></div>', unsafe_allow_html=True)

    buildings = list_buildings()
    building_by_name = {str(x["ten_toa"]): int(x["id"]) for x in buildings}
    building_options = ["Tất cả tòa nhà", *building_by_name]
    if st.session_state.violations_building not in building_options:
        st.session_state.violations_building = "Tất cả tòa nhà"
    pending_building_id = building_by_name.get(st.session_state.violations_building)
    rooms = list_rooms(pending_building_id) if pending_building_id else list_rooms()
    room_by_name = {str(x["ten_phong"]): int(x["id"]) for x in rooms}
    room_options = ["Tất cả phòng", *room_by_name]
    if st.session_state.violations_room not in room_options:
        st.session_state.violations_room = "Tất cả phòng"
    cameras = list_cameras(room_by_name.get(st.session_state.violations_room)) if room_by_name.get(st.session_state.violations_room) else []
    camera_by_name = {str(x.get("vi_tri_goc") or f'CAM {x["id"]}'): int(x["id"]) for x in cameras}
    camera_options = ["Tất cả camera", *camera_by_name]
    if st.session_state.violations_camera not in camera_options:
        st.session_state.violations_camera = "Tất cả camera"

    left = st.container()
    search_clicked = False
    with left:
        with st.container(border=True):
            top = st.columns(4, gap="medium")
            top[0].selectbox("Tòa nhà", building_options, key="violations_building")
            top[1].selectbox("Phòng", room_options, key="violations_room")
            top[2].selectbox("Loại vi phạm", ["Tất cả vi phạm", *violation_types()], key="violations_type")
            top[3].selectbox("Trạng thái", ["Tất cả trạng thái", "Chờ xác nhận", "Đã xác nhận", "Báo sai AI"], key="violations_status")
            bottom = st.columns(
                [1.35, 1.35, .82, .74, .78, 1.55, 1.22, 1.22],
                gap="small",
                vertical_alignment="bottom",
            )
            bottom[0].markdown('<div class="violations-filter-label">Từ ngày</div>', unsafe_allow_html=True)
            bottom[0].date_input("Từ ngày", format="DD/MM/YYYY", key="violations_start_date", label_visibility="collapsed", on_change=mark_journal_range_custom)
            bottom[1].markdown('<div class="violations-filter-label">Đến ngày</div>', unsafe_allow_html=True)
            bottom[1].date_input("Đến ngày", format="DD/MM/YYYY", key="violations_end_date", label_visibility="collapsed", on_change=mark_journal_range_custom)
            bottom[2].markdown('<div class="violations-filter-label">Khoảng thời gian nhanh</div>', unsafe_allow_html=True)
            bottom[2].markdown(f'<span class="v-marker violations-preset-{"active" if st.session_state.violations_range_mode == "today" else "inactive"}"></span>', unsafe_allow_html=True)
            bottom[2].button("Hôm nay", width="stretch", key="violations_preset_today", on_click=set_journal_range, args=("today",))
            bottom[3].markdown('<div class="violations-filter-label violations-filter-label-hidden">Nhãn giữ chỗ</div>', unsafe_allow_html=True)
            bottom[3].markdown(f'<span class="v-marker violations-preset-{"active" if st.session_state.violations_range_mode == "7days" else "inactive"}"></span>', unsafe_allow_html=True)
            bottom[3].button("7 ngày", width="stretch", key="violations_preset_7days", on_click=set_journal_range, args=("7days",))
            bottom[4].markdown('<div class="violations-filter-label violations-filter-label-hidden">Nhãn giữ chỗ</div>', unsafe_allow_html=True)
            bottom[4].markdown(f'<span class="v-marker violations-preset-{"active" if st.session_state.violations_range_mode == "30days" else "inactive"}"></span>', unsafe_allow_html=True)
            bottom[4].button("30 ngày", width="stretch", key="violations_preset_30days", on_click=set_journal_range, args=("30days",))
            bottom[5].markdown('<div class="violations-filter-label violations-filter-label-hidden">Nhãn giữ chỗ</div>', unsafe_allow_html=True)
            bottom[5].markdown('<span class="v-marker violations-advanced-control"></span>', unsafe_allow_html=True)
            with bottom[5].popover("⚲  Bộ lọc nâng cao", use_container_width=True):
                st.selectbox("Chế độ", ["Tất cả", "Phòng thường", "Phòng thi"], key="violations_mode")
                st.selectbox("Camera", camera_options, key="violations_camera")
                st.number_input("Độ tin cậy tối thiểu (%)", 0, 100, key="violations_min_confidence")
            with bottom[6]:
                st.markdown('<div class="violations-filter-label violations-filter-label-hidden">Nhãn giữ chỗ</div>', unsafe_allow_html=True)
                st.markdown('<span class="v-marker v-search"></span>', unsafe_allow_html=True)
                search_clicked = st.button("⌕  TÌM KIẾM", width="stretch", key="vj_search")
            with bottom[7]:
                st.markdown('<div class="violations-filter-label violations-filter-label-hidden">Nhãn giữ chỗ</div>', unsafe_allow_html=True)
                st.markdown('<span class="v-marker violations-reset-control"></span>', unsafe_allow_html=True)
                st.button("⟳  ĐẶT LẠI", width="stretch", key="vj_reset", on_click=reset_journal)

        if search_clicked:
            if st.session_state.violations_start_date > st.session_state.violations_end_date:
                st.error("Từ ngày không được lớn hơn Đến ngày.")
            else:
                status_map = {"Tất cả trạng thái":"all", "Chờ xác nhận":0, "Đã xác nhận":1, "Báo sai AI":-1}
                mode_map = {"Tất cả":"all", "Phòng thường":0, "Phòng thi":1}
                st.session_state.violations_applied_filters = {
                    "query":"", "building_id":building_by_name.get(st.session_state.violations_building),
                    "room_id":room_by_name.get(st.session_state.violations_room), "camera_id":camera_by_name.get(st.session_state.violations_camera),
                    "mode":mode_map[st.session_state.violations_mode], "status":status_map[st.session_state.violations_status],
                    "violation_type":"all" if st.session_state.violations_type=="Tất cả vi phạm" else st.session_state.violations_type,
                    "start_at":f"{st.session_state.violations_start_date.isoformat()} 00:00:00",
                    "end_at":f"{st.session_state.violations_end_date.isoformat()} 23:59:59",
                    "min_confidence":float(st.session_state.violations_min_confidence)/100,
                }
                st.session_state.violations_search_submitted=True; st.session_state.violations_page_number=1
                st.session_state.violations_selected_detail_id=None; st.session_state.violations_detail_closed=False; st.session_state.violations_last_updated=datetime.now(); st.rerun()

        applied = st.session_state.violations_applied_filters or {}
        chip_entries=[]
        if submitted:
            if applied.get("building_id"): chip_entries.append((next((n for n,i in building_by_name.items() if i==applied["building_id"]), "Tòa nhà"), "building_id", None))
            if applied.get("room_id"): chip_entries.append((next((n for n,i in room_by_name.items() if i==applied["room_id"]), "Phòng"), "room_id", None))
            if applied.get("mode") != "all": chip_entries.append(("Phòng thi" if applied.get("mode")==1 else "Phòng thường", "mode", "all"))
            if applied.get("status") != "all": chip_entries.append((_status_label(int(applied["status"])), "status", "all"))
            if applied.get("violation_type") != "all": chip_entries.append((str(applied["violation_type"]), "violation_type", "all"))
            chip_entries.append((f'{str(applied.get("start_at",""))[:10]} – {str(applied.get("end_at",""))[:10]}', "date_range", None))
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center", gap="small", key="violations_filter_chips"):
                st.markdown('<div class="v-applied"><b>Bộ lọc đang áp dụng:</b></div>',unsafe_allow_html=True)
                if chip_entries:
                    for label,key,empty_value in chip_entries:
                        if st.button(f"{label}  ×",key=f"vj_chip_{key}",width="content"):
                            new_filters=dict(applied)
                            if key=="date_range": new_filters["start_at"]=None; new_filters["end_at"]=None
                            else: new_filters[key]=empty_value
                            if key=="building_id": new_filters["room_id"]=None; new_filters["camera_id"]=None
                            if key=="room_id": new_filters["camera_id"]=None
                            st.session_state.violations_applied_filters=new_filters
                            st.session_state.violations_page_number=1; st.session_state.violations_selected_detail_id=None; st.session_state.violations_last_updated=datetime.now(); st.rerun()
                st.button("♲  Xóa tất cả",disabled=not submitted,key="vj_clear_chips",on_click=reset_journal,width="content")

        result_col, detail_col = st.columns(
            [4.35, 1.35], gap="medium", vertical_alignment="top"
        )
        rows=[]; total=0; summary={"pending":0,"confirmed":0,"false_ai":0}
        if submitted:
            try:
                total=service_count_violation_logs(applied)
                page_size=int(st.session_state.violations_page_size); max_page=max(1,math.ceil(total/page_size))
                st.session_state.violations_page_number=min(max(1,int(st.session_state.violations_page_number)),max_page)
                offset=(st.session_state.violations_page_number-1)*page_size
                rows=service_list_violation_logs(applied,limit=page_size,offset=offset)
                summary=service_summarize_violation_logs({**applied,"status":"all"})
                if rows and st.session_state.violations_selected_detail_id is None and not st.session_state.violations_detail_closed:
                    st.session_state.violations_selected_detail_id=int(rows[0]["id"])
            except Exception:
                LOGGER.exception("Cannot load violation journal")
                st.error("Không thể tải nhật ký vi phạm. Vui lòng thử lại.")
        if submitted and total:
            updated=st.session_state.violations_last_updated or datetime.now()
            result_col.markdown(f'<div class="v-summary"><div><small>Kết quả tìm kiếm</small><br><strong>Tìm thấy {total} vi phạm</strong></div><div><span class="n pending">{summary["pending"]}</span>Chờ xác nhận</div><div><span class="n ok">{summary["confirmed"]}</span>Đã xác nhận</div><div><span class="n bad">{summary["false_ai"]}</span>Báo sai AI</div><div style="margin-left:auto">Cập nhật lúc: {updated:%d/%m/%Y %H:%M:%S}</div></div>',unsafe_allow_html=True)
            result_col.write("")
            result_col.markdown('<div class="v-table"><div class="v-table-grid">'+''.join(f'<div class="v-th">{x}</div>' for x in ["□","THỜI GIAN","PHÒNG / TÒA NHÀ","CAMERA","CHẾ ĐỘ","LOẠI VI PHẠM","ĐỘ TIN CẬY","TRẠNG THÁI","CHI TIẾT"])+"</div></div>",unsafe_allow_html=True)
            for row in rows:
                rid=int(row["id"]); status=int(row.get("is_confirmed") or 0); confidence=float(row.get("confidence") or 0); selected=rid==st.session_state.violations_selected_detail_id
                cls,label=("confirmed","Đã xác nhận") if status==1 else (("false-ai","Báo sai AI") if status==-1 else ("pending","Chờ xác nhận"))
                cols=result_col.columns([.28,1,1.22,.62,.78,1.05,.82,1,.52],gap="small")
                cols[0].checkbox("Chọn",key=f"vj_sel_{rid}",label_visibility="collapsed",disabled=status!=0)
                cols[1].markdown(f'<div class="v-td">{escape(_format_log_time(row))}</div>',unsafe_allow_html=True)
                cols[2].markdown(f'<div class="v-td">{escape(str(row.get("ten_phong") or "—"))}<br>{escape(str(row.get("ten_toa") or "—"))}</div>',unsafe_allow_html=True)
                cols[3].markdown(f'<div class="v-td">{escape(str(row.get("vi_tri_goc") or "—"))}</div>',unsafe_allow_html=True)
                cols[4].markdown(f'<div class="v-td">{"Phòng thi" if int(row.get("mode") or 0)==1 else "Phòng thường"}</div>',unsafe_allow_html=True)
                cols[5].markdown(f'<div class="v-td">{escape(str(row.get("loai_vi_pham") or "—"))}</div>',unsafe_allow_html=True)
                cols[6].markdown(f'<div class="v-td v-confidence">{confidence:.0%}<i style="width:{max(4,confidence*40):.0f}px"></i></div>',unsafe_allow_html=True)
                cols[7].markdown(f'<div class="v-td"><span class="v-badge {cls}">{label}</span></div>',unsafe_allow_html=True)
                with cols[8]:
                    st.markdown('<span class="v-marker v-eye"></span>',unsafe_allow_html=True)
                    if st.button("◉",key=f"vj_view_{rid}"):
                        st.session_state.violations_selected_detail_id=rid; st.session_state.violations_detail_closed=False; st.rerun()
            page=int(st.session_state.violations_page_number); max_page=max(1,math.ceil(total/int(st.session_state.violations_page_size)))
            pg=result_col.columns([2.4,.75,.35,.35,.35],gap="small")
            pg[0].markdown(f'<div class="v-page-note">Hiển thị {(page-1)*int(st.session_state.violations_page_size)+1} – {min(page*int(st.session_state.violations_page_size),total)} trong tổng số {total} kết quả</div>',unsafe_allow_html=True)
            size=pg[1].selectbox("Số dòng",[10,20,50],key="violations_page_size",label_visibility="collapsed")
            if pg[2].button("‹",disabled=page<=1,key="vj_prev"): st.session_state.violations_page_number=page-1; st.session_state.violations_selected_detail_id=None; st.session_state.violations_detail_closed=False; st.rerun()
            pg[3].markdown(f'<div class="v-page-note" style="text-align:center"><b>{page}</b> / {max_page}</div>',unsafe_allow_html=True)
            if pg[4].button("›",disabled=page>=max_page,key="vj_next"): st.session_state.violations_page_number=page+1; st.session_state.violations_selected_detail_id=None; st.session_state.violations_detail_closed=False; st.rerun()
        elif submitted:
            result_col.markdown('<div class="v-empty"><div><div class="v-empty-icon">⌕</div>Không có vi phạm phù hợp với bộ lọc đã chọn.</div></div>',unsafe_allow_html=True)
            st.session_state.violations_selected_detail_id=None
        else:
            result_col.markdown('<div class="v-empty"><div><div class="v-empty-icon">▣</div>Chọn bộ lọc và bấm Tìm kiếm để xem nhật ký vi phạm.</div></div>',unsafe_allow_html=True)

    selected_id=st.session_state.violations_selected_detail_id if submitted else None
    detail=None
    if selected_id:
        try: detail=service_get_violation_detail(selected_id)
        except Exception: LOGGER.exception("Cannot load violation detail %s",selected_id)
    def render_violation_detail_panel(detail_row: dict | None, *, selected_id: int | None) -> None:
        with st.container(border=True, key="violations_detail_card"):
            if detail_row is None:
                st.markdown(
                    '<div class="v-detail-placeholder"><div class="v-detail-placeholder-icon">▤</div>'
                    '<b>Chi tiết vi phạm sẽ hiển thị tại đây</b>'
                    '<p>Vui lòng chọn một vi phạm để xem chi tiết.</p></div>',
                    unsafe_allow_html=True,
                )
                return

            status = int(detail_row.get("is_confirmed") or 0)
            confidence = float(detail_row.get("confidence") or 0)
            cls, label = (
                ("confirmed", "Đã xác nhận") if status == 1
                else (("false-ai", "Báo sai AI") if status == -1 else ("pending", "Chờ xác nhận"))
            )
            header = st.columns([1, .16], gap="small", vertical_alignment="center")
            header[0].markdown('<h3 class="v-detail-title">Chi tiết vi phạm</h3>', unsafe_allow_html=True)
            if header[1].button("×", key="vj_close_x", help="Đóng chi tiết"):
                st.session_state.violations_selected_detail_id = None
                st.session_state.violations_detail_closed = True
                st.session_state.violations_confirm_action = None
                st.rerun()

            image_file = evidence_path(detail_row.get("image_path"))
            if image_file and image_file.exists():
                st.image(str(image_file), width="stretch")
            else:
                st.markdown(
                    '<div class="v-detail-image-placeholder">Không có ảnh bằng chứng</div>',
                    unsafe_allow_html=True,
                )

            meta = [
                ("Thời gian", _format_log_time(detail_row)),
                ("Tòa nhà", str(detail_row.get("ten_toa") or "—")),
                ("Phòng", str(detail_row.get("ten_phong") or "—")),
                ("Camera", str(detail_row.get("vi_tri_goc") or "—")),
                ("Chế độ", "Phòng thi" if int(detail_row.get("mode") or 0) == 1 else "Phòng thường"),
                ("Loại vi phạm", str(detail_row.get("loai_vi_pham") or "—")),
            ]
            st.markdown(
                '<div class="v-meta">'
                + ''.join(f'<span>{escape(key)}</span><strong>{escape(value)}</strong>' for key, value in meta)
                + f'<span>Độ tin cậy AI</span><strong>{confidence:.0%}'
                  f'<div class="v-progress"><i style="width:{confidence * 100:.0f}%"></i></div></strong>'
                  f'<span>Trạng thái</span><strong><span class="v-badge {cls}">{label}</span></strong></div>',
                unsafe_allow_html=True,
            )

            if st.session_state.violations_confirm_action:
                action = st.session_state.violations_confirm_action
                st.warning("Xác nhận trường hợp này là vi phạm?" if action == "confirm" else "Đánh dấu trường hợp này là AI nhận diện sai?")
                confirm_cols = st.columns(2, gap="small")
                if confirm_cols[0].button("ĐỒNG Ý", width="stretch", key="vj_action_yes"):
                    try:
                        user_id = str((current_user() or {}).get("ma_nguoi_dung") or "")
                        (service_confirm_violation if action == "confirm" else service_mark_false_alarm)(selected_id, user_id)
                        st.session_state.violations_confirm_action = None
                        st.session_state.violations_last_updated = datetime.now()
                        st.success("Đã cập nhật trạng thái vi phạm.")
                        st.rerun()
                    except Exception:
                        LOGGER.exception("Cannot update violation %s", selected_id)
                        st.error("Không thể cập nhật trạng thái vi phạm. Vui lòng thử lại.")
                if confirm_cols[1].button("HỦY", width="stretch", key="vj_action_no"):
                    st.session_state.violations_confirm_action = None
                    st.rerun()

            st.markdown('<span class="v-marker v-action-primary"></span>', unsafe_allow_html=True)
            if st.button("⚒  XÁC NHẬN", disabled=status != 0, width="stretch", key="vj_confirm"):
                st.session_state.violations_confirm_action = "confirm"
                st.rerun()
            st.markdown('<span class="v-marker v-danger"></span>', unsafe_allow_html=True)
            if st.button("⌁  BÁO SAI AI", disabled=status != 0, width="stretch", key="vj_false"):
                st.session_state.violations_confirm_action = "false"
                st.rerun()
            if st.button("ĐÓNG", width="stretch", key="vj_close"):
                st.session_state.violations_selected_detail_id = None
                st.session_state.violations_detail_closed = True
                st.session_state.violations_confirm_action = None
                st.rerun()

    with detail_col:
        render_violation_detail_panel(detail, selected_id=selected_id)

    if refresh and submitted:
        st.session_state.violations_last_updated=datetime.now(); st.rerun()
    if export_excel or export_pdf:
        try:
            export_rows=service_list_violation_logs(st.session_state.violations_applied_filters,limit=max(1,service_count_violation_logs(st.session_state.violations_applied_filters)),offset=0)
            if not export_rows: st.warning("Không có dữ liệu để xuất.")
            else:
                df=violation_log_export_dataframe(export_rows)
                if export_excel: st.download_button("TẢI FILE EXCEL",make_excel_bytes(df),f"nhat_ky_vi_pham_{datetime.now():%Y%m%d_%H%M%S}.xlsx",width="stretch")
                else: st.download_button("TẢI FILE PDF",make_pdf_bytes("Nhật ký vi phạm EduWatch","Dữ liệu xuất theo bộ lọc đã áp dụng.",df),f"nhat_ky_vi_pham_{datetime.now():%Y%m%d_%H%M%S}.pdf",width="stretch")
        except Exception: LOGGER.exception("Cannot export violations"); st.error("Không thể tạo file báo cáo. Vui lòng thử lại.")


def render_violations_page() -> None:
    if not require_auth([ROLE_ADMIN, ROLE_TEACHER]):
        return
    _render_violation_journal()
def render_buildings_page() -> None:
    if not require_auth([ROLE_ADMIN]):
        return

    if "selected_building_id" not in st.session_state:
        st.session_state.selected_building_id = None
    if "selected_room_id" not in st.session_state:
        st.session_state.selected_room_id = None
    if "location_delete_type" not in st.session_state:
        st.session_state.location_delete_type = None
    if "location_delete_id" not in st.session_state:
        st.session_state.location_delete_id = None
    if "location_delete_name" not in st.session_state:
        st.session_state.location_delete_name = None

    if st.session_state.location_delete_type not in {"building", "room", "camera", None}:
        st.session_state.location_delete_type = None
        st.session_state.location_delete_id = None
        st.session_state.location_delete_name = None

    def select_building(building_id: int) -> None:
        st.session_state.selected_building_id = int(building_id)
        st.session_state.selected_room_id = None

    def select_room(room_id: int) -> None:
        st.session_state.selected_room_id = int(room_id)

    buildings_all = list_buildings(include_deleted=True)
    buildings = [row for row in buildings_all if int(row.get("is_deleted") or 0) == 0]

    st.markdown('<div class="locations-page"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div>
            <h1 class="locations-title location-page-title">Danh sách tòa nhà</h1>
            <div class="locations-subtitle location-page-subtitle">Quản lý tòa nhà, phòng và góc camera theo cấu trúc dữ liệu hiện có.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_building_id = st.session_state.selected_building_id
    if selected_building_id is not None and all(int(row["id"]) != int(selected_building_id) for row in buildings):
        selected_building_id = None
        st.session_state.selected_building_id = None
        st.session_state.selected_room_id = None
    if selected_building_id is not None:
        selected_building_id = int(selected_building_id)
        st.session_state.selected_building_id = selected_building_id
    rooms_all = list_rooms(int(selected_building_id), include_deleted=True) if selected_building_id is not None else []
    rooms = [row for row in rooms_all if int(row.get("is_deleted") or 0) == 0]
    selected_room_id = st.session_state.selected_room_id
    if selected_room_id is not None and all(int(row["id"]) != int(selected_room_id) for row in rooms):
        selected_room_id = None
        st.session_state.selected_room_id = None
    if selected_room_id is not None:
        selected_room_id = int(selected_room_id)
        st.session_state.selected_room_id = selected_room_id
    cameras = list_cameras(int(selected_room_id)) if selected_room_id is not None else []

    def row_status(row: dict) -> str:
        if int(row.get("is_deleted") or 0) == 1:
            return "Đã xóa mềm"
        return "Hoạt động" if int(row.get("status") or 0) == 1 else "Ngừng hoạt động"

    def keep_buildings_page() -> None:
        st.session_state.page = "buildings"

    def clear_location_delete() -> None:
        st.session_state.location_delete_type = None
        st.session_state.location_delete_id = None
        st.session_state.location_delete_name = None

    def button_item_label(title: str, status: str, source: str | None = None) -> str:
        def escape_markdown(value: str) -> str:
            return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", value)

        label = f"**{escape_markdown(title)}**  \n{escape_markdown(status)}"
        if source is not None:
            label += f"  \n*{escape_markdown(source)}*"
        return label

    def render_card_header(title: str, form_state_key: str, *, disabled: bool = False) -> None:
        title_col, add_col = st.columns([1, 0.42], gap="small", vertical_alignment="center")
        with title_col:
            st.markdown('<div class="location-native-header-marker"></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="location-native-card-title">{escape(title)}</div>', unsafe_allow_html=True)
        with add_col:
            st.markdown('<div class="location-native-add-marker"></div>', unsafe_allow_html=True)
            if st.button("+ THÊM", key=f"loc_native_add_{form_state_key}", width="stretch", disabled=disabled):
                keep_buildings_page()
                st.session_state[form_state_key] = "add"
                st.rerun()

    def render_native_item(
        kind: str,
        row: dict,
        title: str,
        status: str,
        *,
        active: bool = False,
        source: str | None = None,
    ) -> None:
        row_id = int(row["id"])
        text_col, edit_col, power_col, delete_col = st.columns(
            [7, 0.8, 0.8, 1.25], gap="small", vertical_alignment="center"
        )
        with text_col:
            active_class = " active" if active else ""
            st.markdown(f'<div class="location-native-item-marker{active_class}"></div>', unsafe_allow_html=True)
            st.markdown('<div class="location-native-select-marker"></div>', unsafe_allow_html=True)
            label = button_item_label(title, status, source)
            tooltip = source or title
            if kind == "building":
                st.button(
                    label,
                    key=f"select_building_{row_id}",
                    width="stretch",
                    help=tooltip,
                    on_click=select_building,
                    args=(row_id,),
                )
            elif kind == "room":
                st.button(
                    label,
                    key=f"select_room_{row_id}",
                    width="stretch",
                    help=tooltip,
                    on_click=select_room,
                    args=(row_id,),
                )
            else:
                st.button(label, key=f"loc_native_select_camera_{row_id}", width="stretch", help=tooltip)

        with edit_col:
            st.markdown('<div class="location-native-action-marker edit"></div>', unsafe_allow_html=True)
            if st.button("✎", key=f"loc_native_edit_{kind}_{row_id}", width="stretch"):
                keep_buildings_page()
                st.session_state[f"loc_{kind}_form"] = f"edit:{row_id}"
                st.rerun()

        with power_col:
            st.markdown('<div class="location-native-action-marker power"></div>', unsafe_allow_html=True)
            if st.button("⏻", key=f"loc_native_toggle_{kind}_{row_id}", width="stretch"):
                keep_buildings_page()
                new_status = 0 if int(row.get("status") or 0) == 1 else 1
                if kind == "building":
                    set_building_status(row_id, new_status)
                elif kind == "room":
                    set_room_status(row_id, new_status)
                else:
                    update_camera_status(row_id, new_status)
                st.rerun()

        with delete_col:
            st.markdown('<div class="location-native-action-marker delete"></div>', unsafe_allow_html=True)
            if st.button("🗑", key=f"request_delete_{kind}_{row_id}", width="stretch"):
                st.session_state.location_delete_type = kind
                st.session_state.location_delete_id = row_id
                st.session_state.location_delete_name = str(title)

    def render_delete_confirmation() -> None:
        delete_type = st.session_state.location_delete_type
        delete_id = st.session_state.location_delete_id
        delete_name = str(st.session_state.location_delete_name or "").strip()
        if delete_type not in {"building", "room", "camera"} or delete_id is None:
            return

        type_label = {
            "building": "tòa nhà",
            "room": "phòng",
            "camera": "góc camera",
        }[delete_type]
        with st.container(border=True):
            st.warning(f'Bạn có chắc chắn muốn xóa {type_label} “{delete_name}” không?')
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                button_marker("danger")
                if st.button("XÁC NHẬN XÓA", key="confirm_location_delete", width="stretch"):
                    target_type = st.session_state.location_delete_type
                    target_id = int(st.session_state.location_delete_id)
                    if target_type == "building":
                        soft_delete_building(target_id)
                        if st.session_state.selected_building_id == target_id:
                            st.session_state.selected_building_id = None
                            st.session_state.selected_room_id = None
                        message = "Đã xóa tòa nhà."
                    elif target_type == "room":
                        soft_delete_room(target_id)
                        if st.session_state.selected_room_id == target_id:
                            st.session_state.selected_room_id = None
                        message = "Đã xóa phòng."
                    elif target_type == "camera":
                        if camera_is_used(target_id):
                            update_camera_status(target_id, 0)
                            message = "Camera đã có nhật ký nên được chuyển sang ngừng hoạt động."
                        else:
                            delete_camera(target_id)
                            message = "Đã xóa camera."
                    else:
                        clear_location_delete()
                        st.warning("Yêu cầu xóa không hợp lệ.")
                        st.rerun()
                    clear_location_delete()
                    st.success(message)
                    st.rerun()
            with cancel_col:
                button_marker("outline")
                if st.button("QUAY LẠI", key="cancel_location_delete", width="stretch"):
                    clear_location_delete()
                    st.rerun()

    def render_building_form() -> None:
        form_mode = st.session_state.get("loc_building_form")
        if not form_mode:
            return
        editing = None
        if str(form_mode).startswith("edit:"):
            target_id = int(str(form_mode).split(":", 1)[1])
            editing = next((row for row in buildings if int(row["id"]) == target_id), None)
            if not editing:
                st.session_state.loc_building_form = None
                return
        with st.form(f"loc_building_form_{form_mode}"):
            st.markdown("**Thêm tòa nhà**" if form_mode == "add" else "**Sửa tòa nhà**")
            name = st.text_input("Tên tòa nhà", value=str((editing or {}).get("ten_toa") or ""))
            status = st.selectbox(
                "Trạng thái",
                ["Hoạt động", "Ngừng hoạt động"],
                index=0 if int((editing or {}).get("status", 1)) == 1 else 1,
            )
            save_col, cancel_col = st.columns(2)
            submitted = save_col.form_submit_button("Lưu", width="stretch")
            cancelled = cancel_col.form_submit_button("Hủy", width="stretch")
            if cancelled:
                st.session_state.loc_building_form = None
                st.rerun()
            if submitted:
                status_value = 1 if status == "Hoạt động" else 0
                if not name.strip():
                    st.error("Tên tòa nhà không được để trống.")
                elif form_mode == "add":
                    add_building(name.strip())
                    st.session_state.loc_building_form = None
                    st.success("Đã thêm tòa nhà.")
                    st.rerun()
                else:
                    update_building(int(editing["id"]), name.strip(), status_value)
                    st.session_state.loc_building_form = None
                    st.success("Đã cập nhật tòa nhà.")
                    st.rerun()

    def render_room_form() -> None:
        form_mode = st.session_state.get("loc_room_form")
        if not form_mode or not selected_building_id:
            return
        editing = None
        if str(form_mode).startswith("edit:"):
            target_id = int(str(form_mode).split(":", 1)[1])
            editing = next((row for row in rooms if int(row["id"]) == target_id), None)
            if not editing:
                st.session_state.loc_room_form = None
                return
        with st.form(f"loc_room_form_{form_mode}_{selected_building_id}"):
            st.markdown("**Thêm phòng**" if form_mode == "add" else "**Sửa phòng**")
            name = st.text_input("Tên phòng", value=str((editing or {}).get("ten_phong") or ""))
            status = st.selectbox(
                "Trạng thái phòng",
                ["Hoạt động", "Ngừng hoạt động"],
                index=0 if int((editing or {}).get("status", 1)) == 1 else 1,
            )
            monitor_mode = st.selectbox(
                "Chế độ mặc định",
                ["Phòng thường", "Phòng thi"],
                index=1 if int((editing or {}).get("monitor_mode") or 0) == 1 else 0,
            )
            save_col, cancel_col = st.columns(2)
            submitted = save_col.form_submit_button("Lưu", width="stretch")
            cancelled = cancel_col.form_submit_button("Hủy", width="stretch")
            if cancelled:
                st.session_state.loc_room_form = None
                st.rerun()
            if submitted:
                status_value = 1 if status == "Hoạt động" else 0
                mode_value = 1 if monitor_mode == "Phòng thi" else 0
                if not name.strip():
                    st.error("Tên phòng không được để trống.")
                elif form_mode == "add":
                    new_room_id = add_room(int(selected_building_id), name.strip())
                    update_room_monitor_mode(new_room_id, mode_value)
                    st.session_state.loc_room_form = None
                    st.success("Đã thêm phòng.")
                    st.rerun()
                else:
                    update_room(int(editing["id"]), int(selected_building_id), name.strip(), status_value)
                    update_room_monitor_mode(int(editing["id"]), mode_value)
                    st.session_state.loc_room_form = None
                    st.success("Đã cập nhật phòng.")
                    st.rerun()

    def render_camera_form() -> None:
        form_mode = st.session_state.get("loc_camera_form")
        if not form_mode or not selected_room_id:
            return
        editing = None
        if str(form_mode).startswith("edit:"):
            target_id = int(str(form_mode).split(":", 1)[1])
            editing = next((row for row in cameras if int(row["id"]) == target_id), None)
            if not editing:
                st.session_state.loc_camera_form = None
                return
        with st.form(f"loc_camera_form_{form_mode}_{selected_room_id}"):
            st.markdown("**Thêm góc camera**" if form_mode == "add" else "**Sửa góc camera**")
            position = st.text_input("Vị trí góc camera", value=str((editing or {}).get("vi_tri_goc") or ""))
            video_source = st.text_input("Nguồn video", value=str((editing or {}).get("video_source") or ""), placeholder="rtsp://... hoặc data/video/...")
            status = st.selectbox(
                "Trạng thái camera",
                ["Hoạt động", "Ngừng hoạt động"],
                index=0 if int((editing or {}).get("status", 1)) == 1 else 1,
            )
            save_col, cancel_col = st.columns(2)
            submitted = save_col.form_submit_button("Lưu", width="stretch")
            cancelled = cancel_col.form_submit_button("Hủy", width="stretch")
            if cancelled:
                st.session_state.loc_camera_form = None
                st.rerun()
            if submitted:
                status_value = 1 if status == "Hoạt động" else 0
                if not position.strip():
                    st.error("Vị trí camera không được để trống.")
                elif form_mode == "add":
                    add_camera(int(selected_room_id), position.strip(), video_source.strip(), status_value)
                    st.session_state.loc_camera_form = None
                    st.success("Đã thêm camera.")
                    st.rerun()
                else:
                    update_camera(int(editing["id"]), int(selected_room_id), position.strip(), video_source.strip(), status_value)
                    st.session_state.loc_camera_form = None
                    st.success("Đã cập nhật camera.")
                    st.rerun()

    st.markdown('<div class="location-native-grid-marker"></div>', unsafe_allow_html=True)
    building_col, room_col, camera_col = st.columns([1, 1, 1], gap="large")

    with building_col:
        with st.container(border=True):
            st.markdown('<div class="location-native-card-marker"></div>', unsafe_allow_html=True)
            render_card_header("Tòa nhà", "loc_building_form")
            render_building_form()
            with st.container(border=False):
                st.markdown('<div class="location-native-list-marker"></div>', unsafe_allow_html=True)
                if not buildings:
                    st.markdown('<div class="empty-hint">Chưa có tòa nhà nào.</div>', unsafe_allow_html=True)
                for row in buildings:
                    row_id = int(row["id"])
                    render_native_item(
                        "building",
                        row,
                        str(row.get("ten_toa") or f"Tòa nhà #{row_id}"),
                        row_status(row),
                        active=row_id == selected_building_id,
                    )

    with room_col:
        with st.container(border=True):
            st.markdown('<div class="location-native-card-marker"></div>', unsafe_allow_html=True)
            render_card_header("Phòng", "loc_room_form", disabled=selected_building_id is None)
            render_room_form()
            with st.container(border=False):
                st.markdown('<div class="location-native-list-marker"></div>', unsafe_allow_html=True)
                if selected_building_id is None:
                    st.markdown('<div class="empty-hint">Vui lòng chọn một tòa nhà để xem danh sách phòng.</div>', unsafe_allow_html=True)
                elif not rooms:
                    st.markdown('<div class="empty-hint">Tòa nhà này chưa có phòng học.</div>', unsafe_allow_html=True)
                else:
                    for row in rooms:
                        row_id = int(row["id"])
                        render_native_item(
                            "room",
                            row,
                            str(row.get("ten_phong") or f"Phòng #{row_id}"),
                            row_status(row),
                            active=row_id == selected_room_id,
                        )

    with camera_col:
        with st.container(border=True):
            st.markdown('<div class="location-native-card-marker"></div>', unsafe_allow_html=True)
            render_card_header("Góc camera", "loc_camera_form", disabled=selected_room_id is None)
            render_camera_form()
            with st.container(border=False):
                st.markdown('<div class="location-native-list-marker"></div>', unsafe_allow_html=True)
                if selected_room_id is None:
                    st.markdown('<div class="empty-hint">Vui lòng chọn một phòng học để xem danh sách góc camera.</div>', unsafe_allow_html=True)
                elif not cameras:
                    st.markdown('<div class="empty-hint">Phòng học này chưa có góc camera.</div>', unsafe_allow_html=True)
                else:
                    for row in cameras:
                        row_id = int(row["id"])
                        video_source = str(row.get("video_source") or "").strip() or "Chưa cấu hình nguồn camera"
                        render_native_item(
                            "camera",
                            row,
                            str(row.get("vi_tri_goc") or f"Camera #{row_id}"),
                            "Hoạt động" if int(row.get("status") or 0) == 1 else "Ngừng hoạt động",
                            source=video_source,
                        )

    render_delete_confirmation()


def render_users_page() -> None:
    if not require_auth([ROLE_ADMIN]):
        return
    st.markdown('<div class="users-page"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        body:has(.users-page) .users-page { display:block; width:0; height:0; overflow:hidden; }
        body:has(.users-page) .users-page-title {
            margin:0; color:#111827; font-size:clamp(2.35rem,3.2vw,3rem); line-height:1.08;
            font-weight:900; letter-spacing:-.035em;
        }
        body:has(.users-page) .users-page-subtitle {
            margin:14px 0 30px; color:#64748b; font-size:1.04rem; line-height:1.55; font-weight:500;
        }
        body:has(.users-page) .users-table-card-marker,
        body:has(.users-page) .users-toolbar-marker,
        body:has(.users-page) .users-table-header-marker,
        body:has(.users-page) .users-table-row-marker,
        body:has(.users-page) .users-search-marker,
        body:has(.users-page) .users-detail-link,
        body:has(.users-page) .users-role-select,
        body:has(.users-page) .users-delete-btn,
        body:has(.users-page) .users-actions-cell,
        body:has(.users-page) .users-pager-marker,
        body:has(.users-page) .users-confirm-marker { display:block; width:0; height:0; overflow:hidden; }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] {
            width:100%; padding:0 !important; overflow-x:auto; overflow-y:hidden; box-sizing:border-box;
            background:#fff; border:1px solid #dfe7e2 !important; border-radius:18px;
            box-shadow:0 14px 38px rgba(15,23,42,.06);
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] > div {
            gap:0 !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-toolbar-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
            align-items:center !important; gap:16px !important; padding:22px 24px !important;
        }
        body:has(.users-page) .users-toolbar-title {
            display:flex; align-items:center; gap:11px; color:#28a957; font-size:1rem; font-weight:850;
        }
        body:has(.users-page) .users-toolbar-title span { font-size:1.35rem; line-height:1; }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-search-marker) + [data-testid="stElementContainer"] input {
            height:46px !important; min-height:46px !important; padding:0 16px !important;
            color:#334155 !important; background:#fff !important; border:1px solid #d6dee6 !important;
            border-radius:11px !important; box-shadow:none !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-search-marker) + [data-testid="stElementContainer"] input:focus {
            border-color:#37bd74 !important; box-shadow:0 0 0 3px rgba(55,189,116,.12) !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
            min-width:1080px; min-height:62px; align-items:stretch !important; gap:0 !important;
            padding:0 !important; color:#fff; background:linear-gradient(90deg,#20ad58,#1da956) !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
            min-width:1080px; min-height:108px; align-items:stretch !important; gap:0 !important;
            padding:0 !important; background:#fff !important; border-bottom:1px solid #edf1ee !important;
            transition:background .16s ease;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"]:hover {
            background:#fbfefc !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"],
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-row-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            display:flex !important; align-items:center !important; min-width:0 !important;
            padding:16px 13px !important; overflow:hidden !important; border:0 !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] p,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-table-header-marker) + [data-testid="stElementContainer"] strong {
            margin:0 !important; color:#fff !important; font-size:.88rem !important; font-weight:850 !important;
            white-space:nowrap !important;
        }
        body:has(.users-page) .users-index { color:#0f172a; font-size:.92rem; font-weight:700; }
        body:has(.users-page) .users-person { display:flex; align-items:center; gap:13px; min-width:0; width:100%; }
        body:has(.users-page) .users-avatar {
            display:grid; place-items:center; flex:0 0 44px; width:44px; height:44px; border-radius:50%;
            color:#249953; background:#e3f5e9; font-size:.84rem; font-weight:900;
        }
        body:has(.users-page) .users-avatar.teacher { color:#2877b8; background:#e9f2fc; }
        body:has(.users-page) .users-avatar.admin { color:#7651c6; background:#f0eafe; }
        body:has(.users-page) .users-full-name {
            min-width:0; overflow:hidden; color:#111827; font-size:.93rem; line-height:1.3; font-weight:850;
            white-space:nowrap; text-overflow:ellipsis;
        }
        body:has(.users-page) .users-cell-text { color:#17233b; font-size:.9rem; font-weight:520; white-space:nowrap; }
        body:has(.users-page) .users-detail-link + div button,
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-detail-link) + [data-testid="stElementContainer"] button {
            min-height:34px !important; padding:0 !important; justify-content:flex-start !important;
            color:#25a957 !important; background:transparent !important; border:0 !important;
            box-shadow:none !important; font-size:.9rem !important; font-weight:750 !important;
        }
        body:has(.users-page) .role-badge {
            display:inline-flex; align-items:center; justify-content:center; gap:7px; width:fit-content;
            max-width:100%; min-height:35px; padding:0 12px; border-radius:10px;
            font-size:.82rem; font-weight:800; white-space:nowrap;
        }
        body:has(.users-page) .role-badge.guard { color:#249953; background:#e6f5ea; }
        body:has(.users-page) .role-badge.teacher { color:#2877b8; background:#e9f2fc; }
        body:has(.users-page) .role-badge.admin { color:#7651c6; background:#f0eafe; }
        body:has(.users-page) [data-testid="column"]:has(.users-actions-cell) [data-testid="stHorizontalBlock"] {
            width:100% !important; align-items:center !important; gap:10px !important;
        }
        body:has(.users-page) [data-testid="column"]:has(.users-actions-cell) [data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width:0 !important; padding:0 !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-role-select) + [data-testid="stElementContainer"] [data-baseweb="select"] > div {
            min-height:44px !important; height:44px !important; color:#17233b !important; background:#fff !important;
            border:1px solid #d6dee6 !important; border-radius:10px !important; box-shadow:none !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-delete-btn) + [data-testid="stElementContainer"] button {
            width:42px !important; min-width:42px !important; height:42px !important; min-height:42px !important;
            padding:0 !important; border-radius:50% !important; color:#fff !important;
            background:#e8286b !important; border:1px solid #e8286b !important;
            box-shadow:0 9px 20px rgba(232,40,107,.22) !important; font-size:1rem !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-delete-btn) + [data-testid="stElementContainer"] button:disabled {
            opacity:.32 !important;
        }
        body:has(.users-page) .users-empty {
            min-width:1080px; padding:44px 24px; color:#64748b; text-align:center; font-size:.95rem;
        }
        body:has(.users-page) .users-table-scroll { width:100%; overflow-x:auto; }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-pager-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
            min-height:72px !important; align-items:center !important; gap:9px !important;
            padding:14px 18px !important; box-sizing:border-box !important;
            background:#fff !important; border-top:1px solid #e7ece9 !important;
        }
        body:has(.users-page) .users-footer-summary {
            display:flex; align-items:center; min-height:44px; color:#53627a;
            font-size:13px; line-height:1; font-weight:550; white-space:nowrap;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-page-size-control) + [data-testid="stElementContainer"] [data-baseweb="select"] > div {
            width:100% !important; height:44px !important; min-height:44px !important; max-height:44px !important;
            box-sizing:border-box !important; color:#334155 !important; background:#fff !important;
            border:1px solid #d6dee6 !important; border-radius:10px !important;
            font-size:13px !important; line-height:1 !important; white-space:nowrap !important; box-shadow:none !important;
        }
        body:has(.users-page) .users-page-indicator {
            display:flex; align-items:center; justify-content:center; width:100%; height:44px;
            box-sizing:border-box; color:#53627a; background:#fff; border:1px solid #e1e7e3;
            border-radius:10px; font-size:13px; line-height:1; font-weight:600; white-space:nowrap;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-page-button) + [data-testid="stElementContainer"] button {
            width:100% !important; height:44px !important; min-height:44px !important; max-height:44px !important;
            padding:0 !important; box-sizing:border-box !important; border-radius:10px !important;
            color:#fff !important; background:#37bd74 !important; border:1px solid #37bd74 !important;
            font-size:18px !important; line-height:1 !important; box-shadow:none !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-page-button) + [data-testid="stElementContainer"] button:hover:not(:disabled) {
            background:#2e9f62 !important; border-color:#2e9f62 !important;
        }
        body:has(.users-page) [data-testid="stElementContainer"]:has(.users-page-button) + [data-testid="stElementContainer"] button:disabled {
            color:#a9b4ad !important; background:#f4f7f5 !important; border-color:#e3e9e5 !important;
            opacity:1 !important; box-shadow:none !important;
        }
        @media (max-width:980px) {
            body:has(.users-page) [data-testid="stElementContainer"]:has(.users-pager-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
                flex-wrap:wrap !important;
            }
        }
        body:has(.users-page) .users-stats-grid {
            display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px; margin-top:22px;
        }
        body:has(.users-page) .users-stat-card {
            display:flex; align-items:center; gap:17px; min-height:132px; padding:22px 24px;
            background:#fff; border:1px solid #e2e9e4; border-radius:16px;
            box-shadow:0 12px 30px rgba(15,23,42,.055); box-sizing:border-box;
        }
        body:has(.users-page) .users-stat-icon {
            display:grid; place-items:center; flex:0 0 54px; width:54px; height:54px; border-radius:13px;
            color:#24a657; background:#e3f5e9; font-size:1.5rem;
        }
        body:has(.users-page) .users-stat-card.teacher .users-stat-icon { color:#2877b8; background:#e9f2fc; }
        body:has(.users-page) .users-stat-card.guard .users-stat-icon { color:#e3a000; background:#fff3cf; }
        body:has(.users-page) .users-stat-value { color:#111827; font-size:1.75rem; line-height:1; font-weight:900; }
        body:has(.users-page) .users-stat-label { margin-top:9px; color:#17233b; font-size:.93rem; font-weight:750; }
        body:has(.users-page) .users-stat-desc { margin-top:5px; color:#94a3b8; font-size:.78rem; }
        body:has(.users-page) .users-detail-card,
        body:has(.users-page) .users-confirm-card {
            margin-top:18px; padding:20px 22px; background:#fff; border:1px solid #e2e9e4;
            border-radius:16px; box-shadow:0 12px 28px rgba(15,23,42,.05);
        }
        @media (max-width:1100px) {
            body:has(.users-page) .users-stats-grid { grid-template-columns:1fr; }
        }
        @media (max-width:760px) {
            body:has(.users-page) .users-page-title { font-size:2.1rem; }
            body:has(.users-page) .users-page-subtitle { margin-bottom:22px; }
            body:has(.users-page) [data-testid="stElementContainer"]:has(.users-toolbar-marker) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"] {
                flex-direction:column !important; align-items:stretch !important; padding:18px !important;
            }
            body:has(.users-page) .users-stat-card { min-height:112px; }
        }
        </style>
        <h1 class="users-page-title">Quản lý người dùng</h1>
        <div class="users-page-subtitle">Theo dõi tài khoản EduWatch VNUA. Admin có thể đổi vai trò hoặc khóa tài khoản khi cần.</div>
        """,
        unsafe_allow_html=True,
    )
    users = list_users()
    if not users:
        st.info("Chưa có người dùng.")
        return

    def user_initials(full_name: str) -> str:
        parts = [part for part in str(full_name).strip().split() if part]
        if not parts:
            return "US"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return f"{parts[0][0]}{parts[-1][0]}".upper()

    role_options = ["Admin", "Giảng viên", "Bảo vệ"]
    role_to_value = {"Admin": ROLE_ADMIN, "Giảng viên": ROLE_TEACHER, "Bảo vệ": ROLE_GUARD}
    value_to_role = {ROLE_ADMIN: "Admin", ROLE_TEACHER: "Giảng viên", ROLE_GUARD: "Bảo vệ"}
    role_meta = {
        ROLE_ADMIN: ("admin", "♛", "Admin"),
        ROLE_TEACHER: ("teacher", "◆", "Giảng viên"),
        ROLE_GUARD: ("guard", "◈", "Bảo vệ"),
    }
    current_user_id = int(current_user()["id"])
    st.session_state.setdefault("users_search_query", "")
    st.session_state.setdefault("users_page_number", 1)
    st.session_state.setdefault("users_page_size", 10)
    st.session_state.setdefault("users_detail_id", None)
    st.session_state.setdefault("delete_user_id", None)
    st.session_state.setdefault("delete_user_name", None)

    query = str(st.session_state.get("users_search_query") or "").strip().casefold()
    filtered_users = [
        user for user in users
        if not query or query in " ".join(
            str(user.get(field) or "") for field in ("ho_ten", "ma_nguoi_dung", "so_dien_thoai")
        ).casefold()
    ]
    page_size = int(st.session_state.get("users_page_size") or 10)
    if page_size not in {10, 20, 50}:
        page_size = 10
        st.session_state.users_page_size = page_size
    max_page = max((len(filtered_users) - 1) // page_size + 1, 1)
    page_number = min(max(int(st.session_state.get("users_page_number") or 1), 1), max_page)
    st.session_state.users_page_number = page_number
    page_start = (page_number - 1) * page_size
    page_users = filtered_users[page_start : page_start + page_size]

    st.markdown('<div class="users-table-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="users-toolbar-marker"></div>', unsafe_allow_html=True)
        toolbar_cols = st.columns([1, 0.42], gap="large", vertical_alignment="center")
        toolbar_cols[0].markdown('<div class="users-toolbar-title"><span>♧</span>Danh sách người dùng</div>', unsafe_allow_html=True)
        with toolbar_cols[1]:
            st.markdown('<div class="users-search-marker"></div>', unsafe_allow_html=True)
            st.text_input(
                "Tìm kiếm người dùng",
                key="users_search_query",
                placeholder="Tìm kiếm theo họ tên, tài khoản...",
                label_visibility="collapsed",
                on_change=lambda: st.session_state.update(users_page_number=1, users_detail_id=None),
            )

        st.markdown('<div class="users-table-header-marker"></div>', unsafe_allow_html=True)
        header_cols = st.columns([0.48, 1.68, 1.08, 1.02, 0.92, 1.02, 1.72], gap=None, vertical_alignment="center")
        for col, label in zip(header_cols, ["STT", "Họ và tên", "Số điện thoại", "Tên tài khoản", "Thông tin", "Vai trò", "Tùy chọn"]):
            col.markdown(f"**{label}**")

        if not page_users:
            st.markdown('<div class="users-empty">Không tìm thấy người dùng phù hợp.</div>', unsafe_allow_html=True)

        for index, user in enumerate(page_users, start=page_start + 1):
            user_id = int(user["id"])
            current_role_value = int(user.get("role") if user.get("role") is not None else ROLE_TEACHER)
            current_role_label = value_to_role.get(current_role_value, "Giảng viên")
            role_class, role_icon, role_label = role_meta.get(current_role_value, role_meta[ROLE_TEACHER])
            active = int(user.get("status") or 0) == 1
            st.markdown('<div class="users-table-row-marker"></div>', unsafe_allow_html=True)
            row_cols = st.columns([0.48, 1.68, 1.08, 1.02, 0.92, 1.02, 1.72], gap=None, vertical_alignment="center")
            row_cols[0].markdown(f'<div class="users-index">{index}</div>', unsafe_allow_html=True)
            full_name = str(user.get("ho_ten") or "")
            row_cols[1].markdown(
                f'<div class="users-person"><span class="users-avatar {role_class}">{escape(user_initials(full_name))}</span>'
                f'<span class="users-full-name" title="{escape(full_name)}">{escape(full_name)}</span></div>',
                unsafe_allow_html=True,
            )
            row_cols[2].markdown(f'<div class="users-cell-text">{escape(str(user.get("so_dien_thoai") or "Chưa có"))}</div>', unsafe_allow_html=True)
            row_cols[3].markdown(f'<div class="users-cell-text">{escape(str(user.get("ma_nguoi_dung") or ""))}</div>', unsafe_allow_html=True)
            with row_cols[4]:
                st.markdown('<div class="users-detail-link"></div>', unsafe_allow_html=True)
                if st.button("◉  Chi tiết", key=f"users_detail_{user_id}"):
                    st.session_state.users_detail_id = None if st.session_state.get("users_detail_id") == user_id else user_id
                    st.rerun()
            row_cols[5].markdown(
                f'<span class="role-badge {role_class}"><span>{role_icon}</span>{escape(role_label)}</span>',
                unsafe_allow_html=True,
            )
            with row_cols[6]:
                st.markdown('<div class="users-actions-cell"></div>', unsafe_allow_html=True)
                action_cols = st.columns([1, 0.24], gap="small", vertical_alignment="center")
                with action_cols[0]:
                    st.markdown('<div class="users-role-select"></div>', unsafe_allow_html=True)
                    selected_role = st.selectbox(
                        "Vai trò",
                        role_options,
                        index=role_options.index(current_role_label),
                        key=f"users_role_{user_id}",
                        label_visibility="collapsed",
                        disabled=not active,
                    )
                    if active and role_to_value[selected_role] != current_role_value:
                        update_user_role(user_id, role_to_value[selected_role])
                        st.success("Đã cập nhật vai trò.")
                        st.rerun()
                with action_cols[1]:
                    st.markdown('<div class="users-delete-btn"></div>', unsafe_allow_html=True)
                    if st.button("🗑", key=f"users_delete_{user_id}", disabled=(user_id == current_user_id or not active)):
                        st.session_state.delete_user_id = user_id
                        st.session_state.delete_user_name = full_name
                        st.rerun()

        shown_from = (page_number - 1) * page_size + 1 if page_users else 0
        shown_to = min(page_number * page_size, len(filtered_users)) if page_users else 0
        st.markdown('<div class="users-pager-marker"></div>', unsafe_allow_html=True)
        pager = st.columns(
            [4.4, 2.3, 1.25, .58, .82, .58],
            gap="small",
            vertical_alignment="center",
        )
        pager[0].markdown(
            f'<div class="users-footer-summary">Hiển thị {shown_from}–{shown_to} trong tổng số {len(filtered_users)} người dùng</div>',
            unsafe_allow_html=True,
        )
        with pager[2]:
            st.markdown('<div class="users-page-size-control"></div>', unsafe_allow_html=True)
            st.selectbox(
                "Số dòng mỗi trang",
                [10, 20, 50],
                key="users_page_size",
                format_func=lambda value: f"{value} / trang",
                label_visibility="collapsed",
                on_change=lambda: st.session_state.update(users_page_number=1),
            )
        with pager[3]:
            st.markdown('<div class="users-page-button users-page-prev"></div>', unsafe_allow_html=True)
            if st.button("‹", key="users_prev_page", disabled=page_number <= 1, width="stretch"):
                st.session_state.users_page_number = page_number - 1
                st.session_state.users_detail_id = None
                st.rerun()
        pager[4].markdown(
            f'<div class="users-page-indicator">{page_number} / {max_page}</div>',
            unsafe_allow_html=True,
        )
        with pager[5]:
            st.markdown('<div class="users-page-button users-page-next"></div>', unsafe_allow_html=True)
            if st.button("›", key="users_next_page", disabled=page_number >= max_page, width="stretch"):
                st.session_state.users_page_number = page_number + 1
                st.session_state.users_detail_id = None
                st.rerun()

    delete_user_id = st.session_state.get("delete_user_id")
    delete_user = next((row for row in users if int(row["id"]) == int(delete_user_id)), None) if delete_user_id else None
    if delete_user and int(delete_user["id"]) != current_user_id and int(delete_user.get("status") or 0) == 1:
        delete_name = str(st.session_state.get("delete_user_name") or delete_user.get("ho_ten") or "tài khoản")
        st.markdown('<div class="users-confirm-card">', unsafe_allow_html=True)
        st.warning(f'Bạn có chắc chắn muốn khóa tài khoản “{delete_name}” không?')
        confirm_cols = st.columns([0.22, 0.22, 0.56], gap="small")
        with confirm_cols[0]:
            st.markdown('<div class="users-confirm-marker"></div>', unsafe_allow_html=True)
            if st.button("XÁC NHẬN", key="users_confirm_delete", width="stretch"):
                soft_delete_user(int(delete_user["id"]))
                st.session_state.delete_user_id = None
                st.session_state.delete_user_name = None
                st.session_state.users_detail_id = None
                st.warning("Đã khóa tài khoản người dùng.")
                st.rerun()
        with confirm_cols[1]:
            if st.button("QUAY LẠI", key="users_cancel_delete", width="stretch"):
                st.session_state.delete_user_id = None
                st.session_state.delete_user_name = None
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    elif delete_user_id:
        st.session_state.delete_user_id = None
        st.session_state.delete_user_name = None

    detail_id = st.session_state.get("users_detail_id")
    detail_user = next((row for row in users if int(row["id"]) == int(detail_id)), None) if detail_id else None
    if detail_user:
        st.markdown('<div class="users-detail-card">', unsafe_allow_html=True)
        st.markdown(f"**Chi tiết:** {escape(str(detail_user.get('ho_ten') or ''))}")
        detail_cols = st.columns(3, gap="medium")
        detail_cols[0].markdown(f"**Tên tài khoản**  \n{escape(str(detail_user.get('ma_nguoi_dung') or ''))}")
        detail_cols[1].markdown(f"**Email**  \n{escape(str(detail_user.get('email') or 'Chưa có'))}")
        detail_cols[2].markdown(f"**Số điện thoại**  \n{escape(str(detail_user.get('so_dien_thoai') or 'Chưa có'))}")
        detail_cols_2 = st.columns(3, gap="medium")
        detail_role_value = int(detail_user.get("role") if detail_user.get("role") is not None else ROLE_TEACHER)
        detail_cols_2[0].markdown(f"**Vai trò**  \n{value_to_role.get(detail_role_value, 'Giảng viên')}")
        detail_cols_2[1].markdown(f"**Ngày sinh**  \n{escape(str(detail_user.get('ngay_sinh') or 'Chưa có'))}")
        detail_cols_2[2].markdown(f"**Giới tính**  \n{escape(str(detail_user.get('gioi_tinh') or 'Chưa có'))}")
        st.markdown("</div>", unsafe_allow_html=True)

    active_users = [user for user in users if int(user.get("status") or 0) == 1]
    teacher_count = sum(
        1 for user in active_users
        if int(user.get("role") if user.get("role") is not None else ROLE_TEACHER) == ROLE_TEACHER
    )
    guard_count = sum(
        1 for user in active_users
        if int(user.get("role") if user.get("role") is not None else ROLE_TEACHER) == ROLE_GUARD
    )
    st.markdown(
        f"""
        <div class="users-stats-grid">
          <div class="users-stat-card">
            <div class="users-stat-icon">♣</div>
            <div><div class="users-stat-value">{len(active_users)}</div><div class="users-stat-label">Tổng người dùng</div><div class="users-stat-desc">Tất cả tài khoản đang hoạt động</div></div>
          </div>
          <div class="users-stat-card teacher">
            <div class="users-stat-icon">◆</div>
            <div><div class="users-stat-value">{teacher_count}</div><div class="users-stat-label">Giảng viên</div><div class="users-stat-desc">Tài khoản giảng viên</div></div>
          </div>
          <div class="users-stat-card guard">
            <div class="users-stat-icon">◈</div>
            <div><div class="users-stat-value">{guard_count}</div><div class="users-stat-label">Bảo vệ</div><div class="users-stat-desc">Tài khoản bảo vệ</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_profile_page() -> None:
    if not require_auth([ROLE_ADMIN, ROLE_TEACHER, ROLE_GUARD]):
        return
    user = get_user_by_id(int(current_user()["id"])) or current_user()
    user_code = str(user.get("ma_nguoi_dung") or "")
    user_name = str(user.get("ho_ten") or "")
    user_email = str(user.get("email") or "")
    user_role = role_name(int(user.get("role") or ROLE_TEACHER))
    user_status = "Hoạt động" if int(user.get("status") or 0) == 1 else "Đã khóa"
    avatar_uri = file_to_data_uri(avatar_path(user.get("anh_dai_dien")))

    def profile_field(label: str, value: str) -> None:
        st.markdown(
            f"""
            <div class="profile-field">
              <div class="profile-field-label">{escape(label)}</div>
              <div class="profile-field-value">{escape(value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="profile-page"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="profile-title">Hồ sơ cá nhân</div>
        <div class="profile-subtitle">Quản lý ảnh đại diện, số điện thoại và mật khẩu đăng nhập. Các thông tin định danh chỉ được xem.</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="profile-main-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        left, right = st.columns([0.42, 0.58], gap="large", vertical_alignment="top")
        with left:
            st.markdown(
                f"""
                <div class="profile-left">
                  <img class="profile-avatar" src="{avatar_uri}" alt="">
                  <div class="profile-name">{escape(user_name)}</div>
                  <div class="profile-code">{escape(user_code)}</div>
                  <span class="profile-role-badge">{escape(user_role)}</span>
                </div>
                <div class="profile-upload-box">
                  <div class="profile-upload-head">
                    <div>
                      <div>Đổi ảnh đại diện</div>
                      <div class="profile-upload-progress">0.0B / 0.00%</div>
                    </div>
                    <div class="profile-upload-plus">+</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="profile-upload-widget"></div>', unsafe_allow_html=True)
            uploaded = st.file_uploader(
                "Đổi ảnh đại diện",
                type=["jpg", "jpeg", "png", "webp"],
                key="hz_profile_avatar",
                label_visibility="collapsed",
            )
        with right:
            profile_field("Mã người dùng", user_code)
            profile_field("Họ tên", user_name)
            profile_field("Email VNUA", user_email)
            profile_field("Vai trò", user_role)
            profile_field("Trạng thái tài khoản", user_status)
            st.markdown('<div class="profile-phone-label">Số điện thoại</div>', unsafe_allow_html=True)
            st.markdown('<div class="profile-phone-field"></div>', unsafe_allow_html=True)
            phone = st.text_input(
                "Số điện thoại",
                value=user.get("so_dien_thoai") or "",
                key="hz_profile_phone",
                label_visibility="collapsed",
            )
            st.markdown('<div class="profile-save-button-marker"></div>', unsafe_allow_html=True)
            if st.button("LƯU THAY ĐỔI", key="hz_profile_save"):
                avatar_value = user.get("anh_dai_dien")
                if uploaded is not None:
                    avatar_value = save_avatar(uploaded, user.get("ma_nguoi_dung") or str(user["id"]))
                if phone.strip() and phone_exists(phone.strip(), int(user["id"])):
                    st.error("Số điện thoại này đã được tài khoản khác sử dụng.")
                else:
                    updated = update_profile_contact(int(user["id"]), phone.strip(), avatar_value)
                    if updated:
                        st.session_state.current_user = updated
                    st.success("Đã cập nhật hồ sơ.")
                    st.rerun()

    st.markdown('<div class="profile-password-card-marker"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="profile-section-title">Đổi mật khẩu</div>', unsafe_allow_html=True)
        with st.form("hz_password_form"):
            old_password = st.text_input("Mật khẩu hiện tại", type="password")
            new_password = st.text_input("Mật khẩu mới", type="password")
            confirm_password = st.text_input("Nhập lại mật khẩu mới", type="password")
            st.markdown('<div class="profile-password-button-marker"></div>', unsafe_allow_html=True)
            submitted = st.form_submit_button("CẬP NHẬT MẬT KHẨU")
            if submitted:
                if verify_login(user.get("ma_nguoi_dung") or "", old_password) is None:
                    st.error("Mật khẩu hiện tại không đúng.")
                elif len(new_password) < 6:
                    st.error("Mật khẩu mới cần tối thiểu 6 ký tự.")
                elif new_password != confirm_password:
                    st.error("Mật khẩu nhập lại không khớp.")
                else:
                    update_password(int(user["id"]), new_password)
                    st.success("Đã đổi mật khẩu.")


def render_device_status_page() -> None:
    if not require_auth([ROLE_GUARD]):
        return
    render_title("Trạng thái thiết bị", "Tổng quan trạng thái dùng grid card, danh sách chính nằm dưới.")
    buildings = list_buildings()
    if not buildings:
        st.info("Chưa có dữ liệu thiết bị.")
        return
    c1, c2 = st.columns(2, gap="large")
    building_name = c1.selectbox("Tòa nhà", [row["ten_toa"] for row in buildings], key="hz_device_building")
    building_id = next(int(row["id"]) for row in buildings if row["ten_toa"] == building_name)
    rooms = list_rooms(building_id)
    room_name = c2.selectbox("Phòng", [row["ten_phong"] for row in rooms], key="hz_device_room") if rooms else None
    room_id = next((int(row["id"]) for row in rooms if row["ten_phong"] == room_name), None) if room_name else None
    cameras = list_cameras(room_id) if room_id else []
    render_metrics(
        [
            ("Tòa nhà", building_name),
            ("Phòng", room_name or "-"),
            ("Tổng camera", str(len(cameras))),
            ("Hoạt động", str(sum(1 for c in cameras if int(c.get("status") or 0) == 1))),
        ]
    )
    render_panel_start("Danh sách thiết bị")
    device_df = pd.DataFrame(
        [
            {
                "Camera": camera.get("vi_tri_goc") or f"Camera #{camera.get('id')}",
                "Nguồn video": camera.get("video_source") or "",
                "Trạng thái": "Không có tín hiệu" if not str(camera.get("video_source") or "").strip() else "Hoạt động" if int(camera.get("status") or 0) == 1 else "Mất kết nối",
            }
            for camera in cameras
        ]
    )
    st.dataframe(device_df, width="stretch", hide_index=True)
    render_panel_end()


def render_incidents_page() -> None:
    if not require_auth([ROLE_GUARD]):
        return
    render_title("Báo cáo sự cố", "Dùng 2 cột: trái là form chính, phải là panel tóm tắt/lịch sử gần nhất.")
    buildings = list_buildings()
    if not buildings:
        st.info("Chưa có dữ liệu tòa nhà.")
        return
    left, right = st.columns([7, 3], gap="large")
    with left:
        render_panel_start("Tạo báo cáo sự cố")
        with st.form("hz_incident_form"):
            building_name = st.selectbox("Tòa nhà", [row["ten_toa"] for row in buildings])
            building_id = next(int(row["id"]) for row in buildings if row["ten_toa"] == building_name)
            rooms = list_rooms(building_id)
            room_name = st.selectbox("Phòng", [row["ten_phong"] for row in rooms]) if rooms else ""
            issue_type = st.text_input("Loại sự cố", placeholder="Mất tín hiệu, hỏng camera, mất điện...")
            description = st.text_area("Mô tả sự cố")
            submitted = st.form_submit_button("Gửi báo cáo", width="stretch")
            if submitted:
                if not issue_type.strip():
                    st.error("Vui lòng nhập loại sự cố.")
                else:
                    with db_connect() as conn:
                        conn.execute(
                            """
                            INSERT INTO System_Requests (user_id, loai_yeu_cau, noi_dung, trang_thai)
                            VALUES (?, ?, ?, 0)
                            """,
                            (int(current_user()["id"]), "Báo cáo sự cố", f"{building_name} - {room_name} - {issue_type.strip()}: {description.strip()}"),
                        )
                        conn.commit()
                    st.success("Đã gửi báo cáo sự cố cho Admin.")
                    st.rerun()
        render_panel_end()
    with right:
        requests = db_rows(
            """
            SELECT *
            FROM System_Requests
            WHERE user_id=? AND loai_yeu_cau='Báo cáo sự cố'
            ORDER BY created_at DESC, id DESC
            LIMIT 30
            """,
            (int(current_user()["id"]),),
        )
        st.markdown('<div class="side-panel">', unsafe_allow_html=True)
        render_card_header("Lịch sử gần nhất")
        if not requests:
            st.info("Chưa có báo cáo sự cố.")
        else:
            for row in requests:
                status_value = int(row.get("trang_thai") or 0)
                status_text = {0: "Chờ xử lý", 1: "Đã xử lý", 2: "Từ chối", 3: "Đang xử lý"}.get(status_value, "Chờ xử lý")
                status_kind = "ok" if status_value == 1 else "bad" if status_value == 2 else "warn"
                st.markdown(
                    f'<div class="ew-list-item" style="display:block;"><div style="display:flex;justify-content:space-between;gap:.5rem;"><div style="font-weight:800;">#{row.get("id")}</div>{status_badge(status_text, status_kind)}</div><div class="ew-note" style="margin-top:.45rem;">{row.get("noi_dung")}</div></div>',
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)


def render_exam_report_page() -> None:
    if not require_auth([ROLE_TEACHER]):
        return
    render_title("Báo cáo phòng thi", "Giữ tương đương NiceGUI cũ: thông tin ca thi dùng dữ liệu mẫu, file xuất lấy từ log vi phạm gần nhất.")
    subject = st.text_input("Môn thi", value="Tin học đại cương", key="hz_exam_subject")
    exam_room = st.text_input("Phòng thi", value="Giảng đường Nguyễn Đăng - ND.202", key="hz_exam_room_text")
    rows = db_rows(
        """
        SELECT v.id, v.loai_vi_pham, v.thoi_gian, v.created_at, v.confidence, v.is_confirmed,
               c.vi_tri_goc, r.ten_phong, b.ten_toa
        FROM Violation_Logs v
        LEFT JOIN Cameras c ON c.id = v.camera_id
        LEFT JOIN Rooms r ON r.id = c.room_id
        LEFT JOIN Buildings b ON b.id = r.building_id
        WHERE v.is_confirmed != -1
        ORDER BY v.id DESC
        LIMIT 50
        """
    )
    render_metrics(
        [
            ("Môn thi", subject),
            ("Phòng thi", exam_room),
            ("Số log", str(len(rows))),
            ("Nguồn dữ liệu", "Mẫu + 50 log gần nhất"),
        ]
    )
    df = pd.DataFrame(
        [
            {
                "Tòa nhà": row.get("ten_toa") or "",
                "Phòng học": row.get("ten_phong") or "",
                "Loại vi phạm": row.get("loai_vi_pham"),
                "Thời gian": row.get("thoi_gian") or row.get("created_at"),
                "Camera": row.get("vi_tri_goc"),
                "Trạng thái": "Đã duyệt" if int(row.get("is_confirmed") or 0) == 1 else "Chờ xác nhận" if int(row.get("is_confirmed") or 0) == 0 else "AI báo sai",
            }
            for row in rows
        ]
    )
    if df.empty:
        df = pd.DataFrame([{"Tòa nhà": "", "Phòng học": "", "Loại vi phạm": "Không có", "Thời gian": date.today().isoformat(), "Camera": "", "Trạng thái": ""}])
    left, right = st.columns([7, 3], gap="large")
    with left:
        render_panel_start("Danh sách vi phạm ca thi")
        st.text_area("Ghi chú giáo viên", value="Danh sách vi phạm do giáo viên ghi nhận và xác nhận trong ca thi.", key="hz_exam_notes")
        st.dataframe(df, width="stretch", hide_index=True)
        render_panel_end()
    with right:
        pdf_bytes = make_pdf_bytes(
            "Biên bản ca thi EduWatch",
            f"Môn thi: {subject} | Phòng thi: {exam_room} | Ghi chú: {st.session_state.get('hz_exam_notes', '')} | Nguồn dữ liệu: 50 log gần nhất, loại bỏ AI báo sai",
            df,
        )
        excel_bytes = make_excel_bytes(df)
        pdf_path = save_report_file("bien_ban_ca_thi", "pdf", pdf_bytes)
        excel_path = save_report_file("bien_ban_ca_thi", "xlsx", excel_bytes)
        st.markdown('<div class="side-panel">', unsafe_allow_html=True)
        render_card_header("Xuất báo cáo", "Giữ tương đương NiceGUI cũ, không thêm workflow mới ngoài phần export.")
        st.download_button("Xuất biên bản PDF", pdf_bytes, file_name=pdf_path.name, mime="application/pdf", width="stretch")
        button_marker("outline")
        st.download_button("Xuất Excel", excel_bytes, file_name=excel_path.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)


def render_login_page() -> None:
    st.markdown('<div class="auth-page auth-login-page auth-signin"></div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([1.08, 0.92], gap="large")
    with left_col:
        st.markdown(
            f"""
            <div class="auth-login-left">
            <div class="auth-login-brand">
                <div class="auth-logo-row">
                    <div class="auth-logo-icon">{AUTH_LOGO_SVG}</div>
                    <div class="auth-brand">EduWatch VNUA</div>
                </div>
                <h1 class="auth-hero-heading">
                    Kiến tạo tương lai
                    <span class="auth-hero-green">số hóa giáo dục</span>
                </h1>
                <div class="auth-hero-desc">
                    Hệ thống giám sát và quản lý đào tạo hiện đại dành cho giảng viên Học viện Nông nghiệp Việt Nam
                </div>
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="auth-campus-card auth-image-target"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.image(str(login_cover_path()), width="stretch")
    with right_col:
        st.markdown('<div class="auth-login-card-target"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="auth-login-card"></div>', unsafe_allow_html=True)
            st.markdown('<h2 class="auth-title">ĐĂNG NHẬP HỆ THỐNG</h2>', unsafe_allow_html=True)
            st.markdown('<div class="auth-subtitle">Cổng thông tin Giám sát Đào tạo</div>', unsafe_allow_html=True)
            signin_success = st.session_state.pop("signin_success_message", "")
            if signin_success:
                st.success(signin_success)
            with st.form("signin_form", clear_on_submit=False):
                username = st.text_input("Tên đăng nhập", placeholder="AD001")
                password = st.text_input("Mật khẩu", type="password", placeholder="Nhập mật khẩu")
                st.markdown('<div class="auth-forgot-link-trigger"></div>', unsafe_allow_html=True)
                forgot_clicked = st.form_submit_button("Quên mật khẩu?")
                submitted = st.form_submit_button("ĐĂNG NHẬP", width="stretch")
                if forgot_clicked:
                    clear_password_reset_state()
                    set_page("forgot_password")
                    st.rerun()
                elif submitted:
                    if not username.strip() or not password:
                        st.error("Vui lòng nhập mã người dùng và mật khẩu.")
                    else:
                        user = verify_login(username.strip(), password)
                        if not user:
                            st.error("Mã người dùng hoặc mật khẩu không đúng.")
                        else:
                            login_user(user)
                            st.success(f"Đăng nhập thành công: {user['ho_ten']}")
                            st.rerun()
            st.markdown('<div class="auth-divider">HOẶC</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-outline-trigger"></div>', unsafe_allow_html=True)
            if st.button("TẠO TÀI KHOẢN MỚI", key="goto_signup", width="stretch"):
                set_page("signup")
                st.rerun()


def render_recovery_left(kind: str) -> None:
    cover_uri = recovery_cover_uri()
    if kind == "otp":
        title = 'Xác minh danh tính<span>bảo mật tài khoản</span>'
        copy = "Vui lòng nhập mã xác minh để hoàn tất quá trình truy cập hệ thống giám sát. Hệ thống giúp bảo vệ thông tin học thuật của bạn an toàn tuyệt đối."
        caption = '<div class="recovery-image-caption">Cổng thông tin<br>Học viện Nông nghiệp Việt Nam</div>'
    else:
        title = 'Khôi phục quyền truy<span>cập tài khoản của bạn</span>'
        copy = "Nhập email hoặc số điện thoại đã đăng ký để nhận mã xác minh đặt lại mật khẩu."
        caption = ""
    st.markdown(
        f"""
        <div class="recovery-left">
            <div class="recovery-logo">
                <div class="auth-logo-icon">{AUTH_LOGO_SVG}</div>
                <div>EduWatch VNUA</div>
            </div>
            <h1 class="recovery-title">{title}</h1>
            <div class="recovery-copy">{copy}</div>
            <div class="recovery-image">
                <img src="{cover_uri}" alt="">
                {caption}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_forgot_password_page() -> None:
    st.markdown('<div class="auth-page auth-recovery auth-forgot"></div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([0.52, 0.48], gap="large")
    with left_col:
        render_recovery_left("forgot")
    with right_col:
        st.markdown('<div class="recovery-card-anchor"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<h2 class="recovery-card-title">QUÊN MẬT KHẨU</h2>', unsafe_allow_html=True)
            st.markdown(
                '<div class="recovery-card-desc">Nhập Email VNUA hoặc số điện thoại để nhận mã xác minh.</div>',
                unsafe_allow_html=True,
            )
            with st.form("forgot_password_form", clear_on_submit=False):
                contact = st.text_input("Email hoặc số điện thoại", placeholder="example@vnua.edu.vn hoặc 0987xxxxxx")
                submitted = st.form_submit_button("GỬI MÃ XÁC MINH  →", width="stretch")
                if submitted:
                    user = find_password_reset_user(contact)
                    if not user:
                        st.error("Không tìm thấy tài khoản phù hợp.")
                    else:
                        issue_password_reset_otp(user, contact)
                        set_page("verify_otp")
                        st.rerun()
            link_text, link_btn = st.columns([0.58, 0.42], gap="small", vertical_alignment="center")
            with link_text:
                st.markdown('<div class="recovery-small-link-row">Đã nhớ mật khẩu?</div>', unsafe_allow_html=True)
            with link_btn:
                st.markdown('<div class="recovery-inline-link"></div>', unsafe_allow_html=True)
                if st.button("Quay lại Đăng nhập", key="forgot_back_signin"):
                    set_page("signin")
                    st.rerun()
            st.markdown('<div class="recovery-secure-line">EDUWATCH VNUA SECURE PORTAL</div>', unsafe_allow_html=True)
    st.markdown('<div class="recovery-footer">© 2024 EduWatch VNUA. All rights reserved.</div>', unsafe_allow_html=True)


def render_verify_otp_page() -> None:
    if not st.session_state.get("reset_user_id") or not st.session_state.get("reset_otp"):
        set_page("forgot_password")
        st.rerun()
    st.markdown('<div class="auth-page auth-recovery auth-otp"></div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([0.52, 0.48], gap="large")
    with left_col:
        render_recovery_left("otp")
    with right_col:
        st.markdown('<div class="recovery-card-anchor"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<h2 class="recovery-card-title">XÁC MINH TÀI KHOẢN</h2>', unsafe_allow_html=True)
            st.markdown(
                '<div class="recovery-card-desc">Nhập mã xác minh 6 số đã được gửi tới Email hoặc số điện thoại của bạn.</div>',
                unsafe_allow_html=True,
            )
            st.info(f"TODO: Kết nối SMTP/SMS sau. OTP demo: {st.session_state.get('reset_otp', '')}")
            with st.form("verify_otp_form", clear_on_submit=False):
                st.markdown('<div style="color:#394155;font-size:13px;font-weight:900;margin-bottom:9px;">Mã xác minh</div>', unsafe_allow_html=True)
                otp_cols = st.columns(6, gap="small")
                otp_digits: list[str] = []
                for index, col in enumerate(otp_cols):
                    with col:
                        if index == 0:
                            st.markdown('<div class="otp-input-row"></div>', unsafe_allow_html=True)
                        otp_digits.append(
                            st.text_input(
                                f"OTP {index + 1}",
                                max_chars=1,
                                label_visibility="collapsed",
                                key=f"reset_otp_{index}",
                            )
                        )
                submitted = st.form_submit_button("XÁC MINH  🛡", width="stretch")
                if submitted:
                    entered_otp = "".join(otp_digits).strip()
                    if reset_otp_is_expired():
                        st.error("Mã xác minh đã hết hạn. Vui lòng gửi lại mã.")
                    elif entered_otp != st.session_state.get("reset_otp"):
                        st.error("Mã xác minh không đúng.")
                    else:
                        st.session_state.reset_verified = True
                        st.session_state.password_reset_otp = entered_otp
                        set_page("reset_password")
                        st.rerun()
            resend_text, resend_btn = st.columns([0.64, 0.36], gap="small", vertical_alignment="center")
            with resend_text:
                st.markdown('<div class="otp-resend">Không nhận được mã?</div>', unsafe_allow_html=True)
            with resend_btn:
                st.markdown('<div class="recovery-inline-link"></div>', unsafe_allow_html=True)
                if st.button("Gửi lại mã", key="otp_resend"):
                    user = current_reset_user()
                    if not user:
                        set_page("forgot_password")
                        st.rerun()
                    issue_password_reset_otp(user, st.session_state.get("reset_identifier") or user.get("ma_nguoi_dung") or "")
                    st.rerun()
            st.markdown('<div class="recovery-inline-link"></div>', unsafe_allow_html=True)
            if st.button("←  Quay lại Đăng nhập", key="otp_back_signin"):
                set_page("signin")
                st.rerun()


def render_reset_password_page() -> None:
    if not st.session_state.get("reset_verified") or not current_reset_user():
        set_page("forgot_password")
        st.rerun()
    cover_uri = recovery_cover_uri()
    st.markdown('<div class="auth-page auth-recovery auth-reset"></div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([0.5, 0.5], gap="small")
    with left_col:
        st.markdown(
            f"""
            <div class="reset-left-panel" style="background-image:url('{cover_uri}')">
                <div class="reset-left-content">
                    <div class="reset-brand">
                        <div class="auth-logo-icon">{AUTH_LOGO_SVG}</div>
                        <div>EduWatch VNUA</div>
                    </div>
                    <h1 class="reset-title">Khôi phục quyền truy cập tài<br>khoản của bạn</h1>
                    <div class="reset-copy">Nhập email hoặc số điện thoại đã đăng ký để nhận mã xác minh đặt lại mật khẩu</div>
                    <div class="reset-divider"></div>
                    <div class="reset-join">
                        <div class="reset-bubbles"><span></span><span></span><span></span></div>
                        <div>Tham gia cùng +10,000 sinh viên & giảng viên</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right_col:
        st.markdown('<div class="reset-card-anchor"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<h2 class="recovery-card-title">ĐẶT LẠI MẬT KHẨU</h2>', unsafe_allow_html=True)
            st.markdown(
                '<div class="recovery-card-desc">Tạo mật khẩu mới để tiếp tục sử dụng hệ thống.</div>',
                unsafe_allow_html=True,
            )
            with st.form("reset_password_form", clear_on_submit=False):
                new_password = st.text_input("Mật khẩu mới", type="password", placeholder="Nhập mật khẩu mới")
                confirm_password = st.text_input("Nhập lại mật khẩu mới", type="password", placeholder="Nhập lại mật khẩu mới")
                submitted = st.form_submit_button("CẬP NHẬT MẬT KHẨU  ⊙", width="stretch")
                if submitted:
                    user = current_reset_user()
                    checks = password_checks(new_password)
                    if not new_password or not confirm_password:
                        st.error("Vui lòng nhập đầy đủ mật khẩu mới.")
                    elif not user:
                        st.error("Không tìm thấy tài khoản phù hợp.")
                        set_page("forgot_password")
                        st.rerun()
                    elif not all(checks.values()):
                        missing = ", ".join(label for label, ok in checks.items() if not ok)
                        st.error(f"Mật khẩu mới chưa đáp ứng yêu cầu bảo mật: {missing}.")
                    elif new_password != confirm_password:
                        st.error("Mật khẩu xác nhận không khớp.")
                    else:
                        update_password(int(user["id"]), new_password)
                        clear_password_reset_state()
                        st.session_state.signin_success_message = "Đổi mật khẩu thành công. Vui lòng đăng nhập lại."
                        set_page("signin")
                        st.rerun()
            st.markdown('<div class="recovery-inline-link"></div>', unsafe_allow_html=True)
            if st.button("←  Quay lại Đăng nhập", key="reset_back_signin"):
                set_page("signin")
                st.rerun()


def render_signup_page() -> None:
    st.markdown('<div class="auth-page auth-register-page auth-signup"></div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([0.35, 0.65], gap="large")
    with left_col:
        st.markdown(
            f"""
            <div class="auth-register-left">
                <div class="auth-logo-row">
                    <div class="auth-logo-icon">{AUTH_LOGO_SVG}</div>
                    <div class="auth-brand">EduWatch VNUA</div>
                </div>
                <div class="auth-register-heading">
                    Chào mừng đến<br>
                    với hệ thống<br>
                    AI quản trị học<br>
                    tập và thi cử
                </div>
                <div class="auth-register-copy">
                    Tham gia cộng đồng giảng viên tại Học viện Nông nghiệp Việt Nam để quản lý và theo dõi tiến độ đào tạo hiệu quả hơn
                </div>
                <div class="auth-decor-circle one"></div>
                <div class="auth-decor-circle two"></div>
                <div class="auth-decor-circle three"></div>
                <div class="auth-decor-circle four"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right_col:
        st.markdown('<div class="auth-register-right"></div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-signup-card-target"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<h2 class="auth-title">ĐĂNG KÝ TÀI KHOẢN</h2>', unsafe_allow_html=True)
            with st.form("signup_form", clear_on_submit=False):
                row1_col1, row1_col2 = st.columns(2, gap="large")
                with row1_col1:
                    teacher_id = st.text_input("Mã giảng viên", placeholder="VD: GV12345")
                with row1_col2:
                    full_name = st.text_input("Họ và tên", placeholder="Nguyễn Văn A")

                row2_col1, row2_col2 = st.columns(2, gap="large")
                with row2_col1:
                    dob = st.date_input("Ngày sinh", value=None, format="DD/MM/YYYY")
                with row2_col2:
                    gender = st.selectbox("Giới tính", ["Nam", "Nữ", "Khác"])

                row3_col1, row3_col2 = st.columns(2, gap="large")
                with row3_col1:
                    email = st.text_input("Email", placeholder="example@vnua.edu.vn")
                with row3_col2:
                    phone = st.text_input("Số điện thoại", placeholder="0987xxxxxx", max_chars=10)

                row4_col1, row4_col2 = st.columns(2, gap="large")
                with row4_col1:
                    password = st.text_input("Mật khẩu", type="password")
                with row4_col2:
                    confirm_password = st.text_input("Nhập lại mật khẩu", type="password")

                submitted = st.form_submit_button("ĐĂNG KÝ", width="stretch")
                if submitted:
                    email_value = email.strip().lower()
                    phone_value = re.sub(r"\D", "", phone.strip())
                    if not all([teacher_id.strip(), full_name.strip(), email_value, phone_value, password, confirm_password]):
                        st.error("Vui lòng nhập đầy đủ thông tin.")
                    elif not email_value.endswith("@vnua.edu.vn"):
                        st.error("Email phải kết thúc bằng @vnua.edu.vn.")
                    elif not re.fullmatch(r"0\d{9}", phone_value):
                        st.error("Số điện thoại phải gồm 10 chữ số và bắt đầu bằng 0.")
                    elif not all(password_checks(password).values()):
                        st.error("Mật khẩu chưa đủ mạnh.")
                    elif password != confirm_password:
                        st.error("Mật khẩu xác nhận không khớp.")
                    elif get_user_by_code(teacher_id.strip()):
                        st.error("Mã người dùng đã tồn tại.")
                    elif email_exists(email_value):
                        st.error("Email đã tồn tại.")
                    elif phone_exists(phone_value):
                        st.error("Số điện thoại đã tồn tại.")
                    else:
                        create_user(
                            {
                                "ma_nguoi_dung": teacher_id.strip(),
                                "password": password,
                                "role": ROLE_TEACHER,
                                "ho_ten": full_name.strip(),
                                "ngay_sinh": dob.isoformat() if isinstance(dob, date) else "",
                                "gioi_tinh": gender,
                                "email": email_value,
                                "so_dien_thoai": phone_value,
                            }
                        )
                        st.success("Đăng ký thành công. Vui lòng đăng nhập bằng tài khoản vừa tạo.")
                        set_page("signin")
                        st.rerun()
            footer_text, footer_link = st.columns([0.96, 1.04], gap="small", vertical_alignment="center")
            with footer_text:
                st.markdown('<div class="signup-login-text">Đã có tài khoản?</div>', unsafe_allow_html=True)
            with footer_link:
                st.markdown('<div class="signup-login-link"></div>', unsafe_allow_html=True)
                if st.button("Quay lại Đăng nhập", key="back_signin"):
                    set_page("signin")
                    st.rerun()


def sidebar_items_for_role(role: int) -> list[tuple[str, str, list[int]]]:
    menu = [
        ("reports", "Thống kê báo cáo", [ROLE_ADMIN]),
        ("monitoring", "Giám sát trực tiếp", [ROLE_ADMIN, ROLE_TEACHER]),
        ("violations", "Nhật ký vi phạm", [ROLE_ADMIN, ROLE_TEACHER]),
        ("buildings", "Danh sách tòa nhà", [ROLE_ADMIN]),
        ("users", "Quản lý người dùng", [ROLE_ADMIN]),
        ("security", "Giám sát an ninh", [ROLE_GUARD]),
        ("device-status", "Trạng thái thiết bị", [ROLE_GUARD]),
        ("incidents", "Báo cáo sự cố", [ROLE_GUARD]),
        ("exam-report", "Báo cáo phòng thi", [ROLE_TEACHER]),
    ]
    return [(key, label, roles) for key, label, roles in menu if role in roles]


def sidebar_menu() -> None:
    user = current_user()
    if not user:
        return

    role_key = normalize_role(user)
    role = normalized_role_value(user)
    if st.session_state.role != role:
        st.session_state.role = role
    if user.get("role") != role:
        user = dict(user)
        user["role"] = role
        st.session_state.current_user = user
    role_labels = {
        ROLE_ADMIN: "ADMIN",
        ROLE_TEACHER: "GIẢNG VIÊN",
        ROLE_GUARD: "BẢO VỆ",
    }
    allowed_items = [(key, label) for key, label, _ in sidebar_items_for_role(role)]
    item_icons = {
        "reports": ":material/bar_chart:",
        "monitoring": ":material/play_circle:",
        "violations": ":material/assignment:",
        "buildings": ":material/apartment:",
        "users": ":material/person_outline:",
        "security": ":material/shield:",
        "device-status": ":material/devices:",
        "incidents": ":material/warning:",
        "exam-report": ":material/description:",
    }
    current = normalize_page(st.session_state.page)
    user_code = str(user.get("ma_nguoi_dung") or "AD001")
    user_name = "Admin VNUA" if user_code.upper() == "AD001" else str(user.get("ho_ten") or role_name(role))
    logo_b64 = image_to_base64(DEFAULT_AVATAR)

    with st.sidebar:
        st.markdown(
            f"""
            <div class="sidebar-brand-row">
              <div class="sidebar-brand-logo">{AUTH_LOGO_SVG}</div>
              <div class="sidebar-brand"><span class="sidebar-brand-full">EduWatch<br>VNUA</span><span class="sidebar-brand-short">EW</span></div>
            </div>
            <div class="sidebar-role-label">{escape(role_labels.get(role, role_name(role)))}</div>
            <div class="sidebar-menu-spacer"></div>
            """,
            unsafe_allow_html=True,
        )
        for item_key, item_label in allowed_items:
            active_class = " active" if item_key == current else ""
            st.markdown(f'<div class="sidebar-nav-marker{active_class}"></div>', unsafe_allow_html=True)
            if st.button(
                item_label,
                key=f"sidebar_nav_{item_key}",
                icon=item_icons.get(item_key),
                width="stretch",
            ):
                if item_key != current:
                    set_page(item_key)
                    st.rerun()

        st.markdown('<div class="sidebar-footer-spacer"></div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="sidebar-user-card">
              <img class="sidebar-user-avatar" src="data:image/jpeg;base64,{logo_b64}" alt="">
              <div class="sidebar-user-meta">
                <div class="sidebar-user-code">{escape(user_code)}</div>
                <div class="sidebar-user-name">{escape(user_name)}</div>
              </div>
              <span class="sidebar-user-chevron" aria-hidden="true">⌄</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sidebar-user-card-click"></div>', unsafe_allow_html=True)
        if st.button(" ", key="sidebar_user_card", width="stretch"):
            st.session_state["page"] = "profile"
            st.rerun()

        st.markdown('<div class="sidebar-logout-marker"></div>', unsafe_allow_html=True)
        if st.button("ĐĂNG XUẤT", key="sidebar_logout", icon=":material/logout:", width="stretch"):
            logout_user()


def inject_authenticated_shell_css() -> None:
    """Apply one authoritative app shell after page-specific styles are rendered."""
    st.markdown('<div class="authenticated-shell"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        :root {
            --sidebar-width-desktop: 280px;
            --sidebar-width-laptop: 260px;
            --sidebar-width-tablet: 82px;
            --sidebar-width-mobile: 72px;
            --main-padding-desktop-y: 32px;
            --main-padding-desktop-x: 36px;
            --authenticated-content-top: 20px;
            --main-padding-laptop: 28px;
            --main-padding-tablet: 22px;
            --main-padding-mobile: 16px;
            --sidebar-bg: #eefaf2;
            --sidebar-primary: #37bd74;
            --sidebar-primary-soft: #5cc672;
            --sidebar-text: #26324a;
            --sidebar-muted: #8a96aa;
            --page-bg: #f6faf7;
        }
        .authenticated-shell {
            display: block;
            width: 0;
            height: 0;
            overflow: hidden;
        }
        html,
        body,
        body:has(.authenticated-shell) .stApp,
        body:has(.authenticated-shell) [data-testid="stAppViewContainer"] {
            width: 100%;
            max-width: 100vw;
            min-height: 100%;
            overflow-x: hidden !important;
            box-sizing: border-box;
        }
        body:has(.authenticated-shell),
        body:has(.authenticated-shell) .stApp {
            background: var(--page-bg) !important;
        }
        body:has(.authenticated-shell) [data-testid="stAppViewContainer"] {
            display: flex !important;
            align-items: stretch !important;
        }
        body:has(.authenticated-shell) section[data-testid="stSidebar"] {
            position: sticky !important;
            inset: 0 auto auto 0 !important;
            z-index: 100 !important;
            flex: 0 0 var(--sidebar-width-desktop) !important;
            width: var(--sidebar-width-desktop) !important;
            min-width: var(--sidebar-width-desktop) !important;
            max-width: var(--sidebar-width-desktop) !important;
            height: 100vh !important;
            min-height: 100vh !important;
            transform: none !important;
            visibility: visible !important;
            background: var(--sidebar-bg) !important;
            border-right: 1px solid rgba(55, 189, 116, 0.16) !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        body:has(.authenticated-shell) section[data-testid="stSidebar"] > div:first-child {
            width: 100% !important;
            min-width: 0 !important;
            max-width: none !important;
            height: 100vh !important;
            padding: 32px 22px 22px !important;
            background: var(--sidebar-bg) !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            scrollbar-width: thin;
        }
        body:has(.authenticated-shell) section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            min-height: 100% !important;
            gap: 0 !important;
        }
        body:has(.authenticated-shell) [data-testid="stMain"] {
            flex: 1 1 auto !important;
            width: calc(100vw - var(--sidebar-width-desktop)) !important;
            min-width: 0 !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow-x: hidden !important;
            box-sizing: border-box !important;
        }
        body:has(.authenticated-shell) [data-testid="stMainBlockContainer"] {
            width: 100% !important;
            min-width: 0 !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
            justify-content: flex-start !important;
            align-items: stretch !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
        }
        body:has(.authenticated-shell) .block-container,
        body:has(.authenticated-shell):has(.reports-page) .block-container,
        body:has(.authenticated-shell):has(.report-page) .block-container,
        body:has(.authenticated-shell):has(.monitoring-page) .block-container,
        body:has(.authenticated-shell):has(.monitor-page) .block-container,
        body:has(.authenticated-shell):has(.violations-page) .block-container,
        body:has(.authenticated-shell):has(.violations-v2-page) .block-container,
        body:has(.authenticated-shell):has(.violations-v3-page) .block-container,
        body:has(.authenticated-shell):has(.locations-page) .block-container,
        body:has(.authenticated-shell):has(.users-page) .block-container,
        body:has(.authenticated-shell):has(.profile-page) .block-container {
            width: 100% !important;
            min-width: 0 !important;
            max-width: none !important;
            margin: 0 !important;
            padding: var(--authenticated-content-top) var(--main-padding-desktop-x) 48px !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
        }
        body:has(.authenticated-shell):has(.ewmon-page) .block-container {
            padding-top: var(--authenticated-content-top) !important;
        }
        body:has(.authenticated-shell) .sidebar-brand-row {
            display: flex !important;
            align-items: center !important;
            gap: 13px !important;
            width: 100% !important;
            margin: 0 0 8px !important;
        }
        body:has(.authenticated-shell) .sidebar-brand-logo {
            display: grid !important;
            place-items: center !important;
            flex: 0 0 52px !important;
            width: 52px !important;
            height: 52px !important;
            color: #35a853 !important;
            background: rgba(255, 255, 255, 0.72) !important;
            border: 1px solid rgba(55, 189, 116, 0.22) !important;
            border-radius: 16px !important;
        }
        body:has(.authenticated-shell) .sidebar-brand-logo svg {
            width: 34px !important;
            height: 34px !important;
        }
        body:has(.authenticated-shell) .sidebar-brand {
            color: #2fa34b !important;
            font-size: 27px !important;
            line-height: 1.02 !important;
            font-weight: 900 !important;
            letter-spacing: -0.02em !important;
            margin: 0 !important;
        }
        body:has(.authenticated-shell) .sidebar-role-label {
            color: var(--sidebar-muted) !important;
            font-size: 12px !important;
            line-height: 1 !important;
            font-weight: 900 !important;
            letter-spacing: 0.13em !important;
            margin: 0 0 34px 65px !important;
        }
        body:has(.authenticated-shell) .sidebar-menu-spacer {
            display: none !important;
            height: 0 !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-nav-marker + div[data-testid="stButton"],
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"],
        body:has(.authenticated-shell) [data-testid="stSidebar"] div:has(.sidebar-nav-marker) + div[data-testid="stButton"] {
            width: 100% !important;
            margin: 0 0 10px !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-nav-marker + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker) + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div:has(.sidebar-nav-marker) + div[data-testid="stButton"] button {
            width: 100% !important;
            height: 52px !important;
            min-height: 52px !important;
            padding: 0 15px !important;
            justify-content: flex-start !important;
            color: var(--sidebar-text) !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 16px !important;
            box-shadow: none !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            line-height: 1.15 !important;
            text-align: left !important;
            white-space: nowrap !important;
            overflow: hidden !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button p {
            color: inherit !important;
            font-size: 15px !important;
            font-weight: 800 !important;
            line-height: 1.15 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button:hover {
            color: var(--sidebar-text) !important;
            background: #e4f6ea !important;
            border-color: #d4eedc !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-nav-marker.active + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button {
            color: #ffffff !important;
            background: var(--sidebar-primary-soft) !important;
            border-color: var(--sidebar-primary-soft) !important;
            box-shadow: 0 12px 25px rgba(55, 189, 116, 0.23) !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-nav-marker.active + div[data-testid="stButton"] button p,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button p,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div:has(.sidebar-nav-marker.active) + div[data-testid="stButton"] button p {
            color: #ffffff !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.sidebar-footer-spacer),
        body:has(.authenticated-shell) [data-testid="stSidebar"] [data-testid="element-container"]:has(.sidebar-footer-spacer) {
            flex: 1 1 auto !important;
            min-height: 24px !important;
        }
        body:has(.authenticated-shell) .sidebar-footer-spacer {
            height: 100% !important;
            min-height: 24px !important;
        }
        body:has(.authenticated-shell) .sidebar-user-card {
            width: 100% !important;
            min-height: 76px !important;
            margin: 0 !important;
            padding: 12px 13px !important;
            gap: 11px !important;
            background: rgba(255, 255, 255, 0.86) !important;
            border: 1px solid rgba(55, 189, 116, 0.18) !important;
            border-radius: 20px !important;
            box-shadow: 0 10px 24px rgba(42, 91, 58, 0.05) !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        body:has(.authenticated-shell) .sidebar-user-avatar {
            flex: 0 0 46px !important;
            width: 46px !important;
            height: 46px !important;
        }
        body:has(.authenticated-shell) .sidebar-user-code {
            color: #32a34f !important;
            font-size: 16px !important;
            font-weight: 900 !important;
        }
        body:has(.authenticated-shell) .sidebar-user-name {
            max-width: 150px !important;
            color: #718096 !important;
            font-size: 13px !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }
        body:has(.authenticated-shell) .sidebar-user-card-click + div[data-testid="stButton"],
        body:has(.authenticated-shell) div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] {
            height: 76px !important;
            margin-top: -76px !important;
        }
        body:has(.authenticated-shell) .sidebar-user-card-click + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) div[data-testid="stMarkdownContainer"]:has(.sidebar-user-card-click) + div[data-testid="stButton"] button {
            height: 76px !important;
            min-height: 76px !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-logout-marker + div[data-testid="stButton"],
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] {
            margin: 18px 0 0 !important;
            padding-top: 12px !important;
            border-top: 1px solid rgba(55, 189, 116, 0.14) !important;
        }
        body:has(.authenticated-shell) [data-testid="stSidebar"] .sidebar-logout-marker + div[data-testid="stButton"] button,
        body:has(.authenticated-shell) [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]:has(.sidebar-logout-marker) + div[data-testid="stButton"] button {
            height: 48px !important;
            min-height: 48px !important;
            color: #39aa57 !important;
            padding: 0 12px !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            font-size: 15px !important;
            font-weight: 900 !important;
        }

        /* Report page must consume the full main column instead of a centered fixed canvas. */
        body:has(.authenticated-shell) .report-shell,
        body:has(.authenticated-shell) .report-stat-grid,
        body:has(.authenticated-shell) .report-filter-card,
        body:has(.authenticated-shell) .report-table-card,
        body:has(.authenticated-shell) .report-table-scroll {
            width: 100% !important;
            max-width: none !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            box-sizing: border-box !important;
        }
        body:has(.authenticated-shell) .report-topbar-marker + div [data-testid="stHorizontalBlock"] {
            grid-template-columns: minmax(280px, 1.08fr) minmax(360px, 0.92fr) !important;
            gap: 24px !important;
            margin-bottom: 26px !important;
        }
        body:has(.authenticated-shell) .report-top-nav {
            gap: 18px !important;
            font-size: 16px !important;
        }
        body:has(.authenticated-shell) .report-tab-active {
            padding-bottom: 10px !important;
        }
        body:has(.authenticated-shell) .report-system-badge {
            padding: 9px 13px !important;
            font-size: 15px !important;
        }
        body:has(.authenticated-shell) .report-nav-icon {
            font-size: 17px !important;
        }
        body:has(.authenticated-shell) .report-search-marker + div .stTextInput input,
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-search-marker) + [data-testid="stElementContainer"] .stTextInput input,
        body:has(.authenticated-shell) [data-testid="element-container"]:has(.report-search-marker) + [data-testid="element-container"] .stTextInput input {
            height: 50px !important;
            min-height: 50px !important;
            padding-left: 58px !important;
            font-size: 15px !important;
        }
        body:has(.authenticated-shell) .report-title {
            font-size: clamp(34px, 3.2vw, 46px) !important;
        }
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-export-row) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.authenticated-shell) [data-testid="element-container"]:has(.report-export-row) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 12px !important;
            width: 100% !important;
            max-width: 340px !important;
            margin-left: auto !important;
        }
        body:has(.authenticated-shell) .report-pdf-marker + div .stDownloadButton > button,
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-pdf-marker) + [data-testid="stElementContainer"] .stDownloadButton > button,
        body:has(.authenticated-shell) .report-excel-marker + div .stDownloadButton > button,
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-excel-marker) + [data-testid="stElementContainer"] .stDownloadButton > button {
            width: 100% !important;
            height: 48px !important;
            min-height: 48px !important;
            padding: 0 12px !important;
            font-size: 14px !important;
        }
        body:has(.authenticated-shell) .report-stat-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 24px !important;
            margin-bottom: 28px !important;
        }
        body:has(.authenticated-shell) .report-stat-card {
            min-width: 0 !important;
            min-height: 154px !important;
            padding: 30px 32px !important;
            border-radius: 24px !important;
        }
        body:has(.authenticated-shell) .report-stat-label {
            margin-bottom: 18px !important;
            font-size: clamp(16px, 1.5vw, 21px) !important;
        }
        body:has(.authenticated-shell) .report-stat-value {
            font-size: clamp(27px, 2.5vw, 38px) !important;
            overflow-wrap: anywhere !important;
        }
        body:has(.authenticated-shell) .report-filter-card-marker + div [data-testid="stVerticalBlockBorderWrapper"],
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-filter-card-marker) + [data-testid="stElementContainer"] [data-testid="stVerticalBlockBorderWrapper"] {
            width: 100% !important;
            min-height: 112px !important;
            padding: 24px 26px !important;
            margin-bottom: 28px !important;
            border-radius: 22px !important;
            box-sizing: border-box !important;
        }
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-filter-controls) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
        body:has(.authenticated-shell) [data-testid="element-container"]:has(.report-filter-controls) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {
            grid-template-columns: minmax(190px, 260px) minmax(160px, 220px) minmax(0, 1fr) !important;
            gap: 18px !important;
            width: 100% !important;
        }
        body:has(.authenticated-shell) .report-search-button-marker + div button,
        body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-search-button-marker) + [data-testid="stElementContainer"] button {
            width: 100% !important;
            max-width: 220px !important;
            height: 56px !important;
            min-height: 56px !important;
            font-size: 15px !important;
        }
        body:has(.authenticated-shell) .report-table-card {
            border-radius: 22px !important;
        }
        body:has(.authenticated-shell) .report-table {
            width: 100% !important;
            min-width: 760px !important;
            table-layout: auto !important;
            font-size: 16px !important;
        }
        body:has(.authenticated-shell) .report-table th,
        body:has(.authenticated-shell) .report-table td {
            padding: 17px 24px !important;
        }
        body:has(.authenticated-shell) .report-table th {
            font-size: 15px !important;
        }
        body:has(.authenticated-shell) .report-table-scroll {
            overflow-x: auto !important;
        }
        body:has(.authenticated-shell) .report-table-card,
        body:has(.authenticated-shell) [data-testid="stDataFrame"],
        body:has(.authenticated-shell) [data-testid="stTable"],
        body:has(.authenticated-shell) .users-table-card,
        body:has(.authenticated-shell) .camera-grid,
        body:has(.authenticated-shell) .location-grid,
        body:has(.authenticated-shell) .monitoring-grid,
        body:has(.authenticated-shell) .profile-grid {
            min-width: 0 !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }

        @media (min-width: 1024px) and (max-width: 1279px) {
            body:has(.authenticated-shell) section[data-testid="stSidebar"] {
                flex-basis: var(--sidebar-width-laptop) !important;
                width: var(--sidebar-width-laptop) !important;
                min-width: var(--sidebar-width-laptop) !important;
                max-width: var(--sidebar-width-laptop) !important;
            }
            body:has(.authenticated-shell) section[data-testid="stSidebar"] > div:first-child {
                padding: 28px 18px 20px !important;
            }
            body:has(.authenticated-shell) [data-testid="stMain"] {
                width: calc(100vw - var(--sidebar-width-laptop)) !important;
            }
            body:has(.authenticated-shell) .block-container,
            body:has(.authenticated-shell):has(.reports-page) .block-container,
            body:has(.authenticated-shell):has(.monitoring-page) .block-container,
            body:has(.authenticated-shell):has(.violations-page) .block-container,
            body:has(.authenticated-shell):has(.violations-v3-page) .block-container,
            body:has(.authenticated-shell):has(.locations-page) .block-container,
            body:has(.authenticated-shell):has(.users-page) .block-container,
            body:has(.authenticated-shell):has(.profile-page) .block-container {
                padding: var(--authenticated-content-top) var(--main-padding-laptop) var(--main-padding-laptop) !important;
            }
            body:has(.authenticated-shell) .sidebar-brand {
                font-size: 24px !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-logo {
                flex-basis: 46px !important;
                width: 46px !important;
                height: 46px !important;
            }
            body:has(.authenticated-shell) .sidebar-role-label {
                margin-left: 59px !important;
            }
        }
        @media (min-width: 768px) and (max-width: 1023px) {
            body:has(.authenticated-shell) section[data-testid="stSidebar"] {
                flex-basis: var(--sidebar-width-tablet) !important;
                width: var(--sidebar-width-tablet) !important;
                min-width: var(--sidebar-width-tablet) !important;
                max-width: var(--sidebar-width-tablet) !important;
            }
            body:has(.authenticated-shell) section[data-testid="stSidebar"] > div:first-child {
                padding: 22px 10px 18px !important;
            }
            body:has(.authenticated-shell) [data-testid="stMain"] {
                width: calc(100vw - var(--sidebar-width-tablet)) !important;
            }
            body:has(.authenticated-shell) .block-container,
            body:has(.authenticated-shell):has(.reports-page) .block-container,
            body:has(.authenticated-shell):has(.monitoring-page) .block-container,
            body:has(.authenticated-shell):has(.violations-page) .block-container,
            body:has(.authenticated-shell):has(.violations-v3-page) .block-container,
            body:has(.authenticated-shell):has(.locations-page) .block-container,
            body:has(.authenticated-shell):has(.users-page) .block-container,
            body:has(.authenticated-shell):has(.profile-page) .block-container {
                padding: var(--authenticated-content-top) var(--main-padding-tablet) var(--main-padding-tablet) !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-row {
                justify-content: center !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-logo,
            body:has(.authenticated-shell) .sidebar-brand-full,
            body:has(.authenticated-shell) .sidebar-role-label,
            body:has(.authenticated-shell) .sidebar-user-meta {
                display: none !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-short {
                display: block !important;
                font-size: 19px !important;
                text-align: center !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button {
                width: 60px !important;
                padding: 0 !important;
                justify-content: center !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button p {
                width: 24px !important;
                max-width: 24px !important;
                height: 24px !important;
                font-size: 0 !important;
                line-height: 1 !important;
                text-overflow: clip !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button p::first-letter {
                font-size: 20px !important;
            }
            body:has(.authenticated-shell) .sidebar-user-card {
                min-height: 58px !important;
                padding: 6px !important;
                justify-content: center !important;
            }
            body:has(.authenticated-shell) .sidebar-user-avatar {
                width: 40px !important;
                height: 40px !important;
                flex-basis: 40px !important;
            }
            body:has(.authenticated-shell) .report-topbar-marker + div [data-testid="stHorizontalBlock"] {
                grid-template-columns: 1fr !important;
            }
            body:has(.authenticated-shell) .report-top-nav {
                justify-content: flex-start !important;
                flex-wrap: wrap !important;
            }
        }
        @media (max-width: 767px) {
            body:has(.authenticated-shell) section[data-testid="stSidebar"] {
                flex-basis: var(--sidebar-width-mobile) !important;
                width: var(--sidebar-width-mobile) !important;
                min-width: var(--sidebar-width-mobile) !important;
                max-width: var(--sidebar-width-mobile) !important;
            }
            body:has(.authenticated-shell) section[data-testid="stSidebar"] > div:first-child {
                padding: 16px 6px !important;
            }
            body:has(.authenticated-shell) [data-testid="stMain"] {
                width: calc(100vw - var(--sidebar-width-mobile)) !important;
            }
            body:has(.authenticated-shell) .block-container,
            body:has(.authenticated-shell):has(.reports-page) .block-container,
            body:has(.authenticated-shell):has(.monitoring-page) .block-container,
            body:has(.authenticated-shell):has(.violations-page) .block-container,
            body:has(.authenticated-shell):has(.violations-v3-page) .block-container,
            body:has(.authenticated-shell):has(.locations-page) .block-container,
            body:has(.authenticated-shell):has(.users-page) .block-container,
            body:has(.authenticated-shell):has(.profile-page) .block-container {
                padding: var(--main-padding-mobile) !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-row {
                justify-content: center !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-logo,
            body:has(.authenticated-shell) .sidebar-brand-full,
            body:has(.authenticated-shell) .sidebar-role-label,
            body:has(.authenticated-shell) .sidebar-user-meta {
                display: none !important;
            }
            body:has(.authenticated-shell) .sidebar-brand-short {
                display: block !important;
                font-size: 17px !important;
                text-align: center !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button {
                width: 60px !important;
                padding: 0 !important;
                justify-content: center !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button p {
                width: 22px !important;
                max-width: 22px !important;
                height: 22px !important;
                font-size: 0 !important;
                line-height: 1 !important;
            }
            body:has(.authenticated-shell) [data-testid="stSidebar"] .stButton > button p::first-letter {
                font-size: 18px !important;
            }
            body:has(.authenticated-shell) .sidebar-user-card {
                min-height: 52px !important;
                padding: 5px !important;
                justify-content: center !important;
            }
            body:has(.authenticated-shell) .sidebar-user-avatar {
                width: 36px !important;
                height: 36px !important;
                flex-basis: 36px !important;
            }
            body:has(.authenticated-shell) .report-topbar-marker + div [data-testid="stHorizontalBlock"],
            body:has(.authenticated-shell) .report-stat-grid {
                grid-template-columns: 1fr !important;
            }
            body:has(.authenticated-shell) .report-top-nav {
                justify-content: flex-start !important;
                flex-wrap: wrap !important;
            }
            body:has(.authenticated-shell) [data-testid="stElementContainer"]:has(.report-filter-controls) + [data-testid="stElementContainer"] [data-testid="stHorizontalBlock"],
            body:has(.authenticated-shell) [data-testid="element-container"]:has(.report-filter-controls) + [data-testid="element-container"] [data-testid="stHorizontalBlock"] {
                grid-template-columns: 1fr !important;
            }
            body:has(.authenticated-shell) .report-table {
                min-width: 680px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_router() -> None:
    page = normalize_page(st.session_state.page)
    if not st.session_state.is_authenticated:
        if page not in {"signin", "signup", "forgot_password", "verify_otp", "reset_password"}:
            set_page("signin")
            page = "signin"
        if page == "signup":
            render_signup_page()
        elif page == "forgot_password":
            render_forgot_password_page()
        elif page == "verify_otp":
            render_verify_otp_page()
        elif page == "reset_password":
            render_reset_password_page()
        else:
            render_login_page()
        return

    sidebar_menu()
    page = normalize_page(st.session_state.page)
    if page == "monitoring":
        render_monitoring_page(False)
    elif page == "violations":
        render_violations_page()
    elif page == "reports":
        render_reports_page()
    elif page == "buildings":
        render_buildings_page()
    elif page == "users":
        render_users_page()
    elif page in {"profile", "settings"}:
        render_profile_page()
    elif page == "security":
        render_monitoring_page(True)
    elif page == "device-status":
        render_device_status_page()
    elif page == "incidents":
        render_incidents_page()
    elif page == "exam-report":
        render_exam_report_page()
    else:
        set_page(default_page_for_role(int(st.session_state.role or ROLE_TEACHER)))
        st.rerun()


def main() -> None:
    ensure_schema()
    inject_global_css()
    init_session_state()
    render_router()
    if st.session_state.get("is_authenticated"):
        inject_authenticated_shell_css()


if __name__ == "__main__":
    main()
