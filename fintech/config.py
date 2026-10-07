"""Application configuration and constants."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Vercel (serverless) detection: the filesystem is read-only except /tmp,
# which is ephemeral per instance. Override with FINTECH_DATA_DIR when a
# persistent volume is available (VPS, Render, Railway...).
ON_VERCEL = bool(os.environ.get("VERCEL"))
_data_override = os.environ.get("FINTECH_DATA_DIR")
if _data_override:
    DATA_DIR = Path(_data_override)
elif ON_VERCEL:
    DATA_DIR = Path("/tmp/finviet-pro")
else:
    DATA_DIR = BASE_DIR / "data"

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only filesystem (misconfigured serverless) — DB path may still be writable
    pass

DB_PATH = str(DATA_DIR / "fintech.db")

HOST = os.environ.get("FINTECH_HOST", "127.0.0.1")
PORT = int(os.environ.get("FINTECH_PORT", "5000"))
DEBUG = os.environ.get("FINTECH_DEBUG", "0") == "1"

# Data cache
DEFAULT_HISTORY_DAYS = 400
CACHE_HOURS = 6
SYMBOLS_REFRESH_HOURS = 72
FUNDAMENTALS_REFRESH_HOURS = 24

# Signal score thresholds (-100..100)
SIGNAL_STRONG_BUY = 62
SIGNAL_BUY = 30
SIGNAL_SELL = -30
SIGNAL_STRONG_SELL = -62

# Default user settings stored in SQLite (key/value)
DEFAULT_SETTINGS = {
    "equity": 500000000.0,          # VND, tong von dau tu
    "risk_pct": 2.0,                # % von cho moi lenh (risk-based sizing)
    "max_position_pct": 20.0,       # % von toi da cho 1 ma
    "kelly_mode": "half",           # "half" = 1/2 Kelly (Edward Thorp)
    "history_days": DEFAULT_HISTORY_DAYS,
    "cache_hours": CACHE_HOURS,
    "scan_minutes": 30,             # tan suat quet canh bao danh muc
    "min_avg_volume": 100000.0,     # thanh khoan toi thieu (CP/phien)
    "lot": 100,                     # buoc mua toi thieu
    "screener_max_symbols": 250,
}

# Universe groups supported by Vietcap getByGroup endpoint (verified live)
UNIVERSE_GROUPS = [
    {"code": "VN30", "name": "VN30 (30 mã)"},
    {"code": "VN100", "name": "VN100 (100 mã)"},
    {"code": "HNX30", "name": "HNX30 (30 mã)"},
    {"code": "HOSE", "name": "HOSE (HSX)"},
    {"code": "HNX", "name": "HNX"},
    {"code": "UPCOM", "name": "UPCOM"},
    {"code": "ETF", "name": "ETF"},
]

EXCHANGES = ["HOSE", "HNX", "UPCOM"]

INDEX_SYMBOLS = ["VNINDEX", "VN30"]

# Signal presentation (labels are Vietnamese for the UI)
SIGNAL_META = {
    "STRONG_BUY": {"label": "MUA MẠNH", "short": "MM", "tone": "up"},
    "BUY": {"label": "MUA", "short": "M", "tone": "up"},
    "HOLD": {"label": "NẮM GIỮ", "short": "—", "tone": "neutral"},
    "SELL": {"label": "BÁN", "short": "B", "tone": "down"},
    "STRONG_SELL": {"label": "BÁN MẠNH", "short": "BM", "tone": "down"},
}
