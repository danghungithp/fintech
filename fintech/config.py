"""Application configuration and constants."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Vercel (serverless) detection — kept for diagnostics and /api/health reporting.
ON_VERCEL = bool(os.environ.get("VERCEL"))


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency). Existing env vars win."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------- InfluxDB 3 (database)
# All application data is stored in InfluxDB Cloud Serverless. Configure via
# environment variables or a local .env file (see .env.example). On Vercel,
# add INFLUXDB_TOKEN (and optionally HOST/ORG/BUCKET) under
# Project → Settings → Environment Variables.
INFLUX_HOST = os.environ.get("INFLUXDB_HOST", "https://us-east-1-1.aws.cloud2.influxdata.com")
INFLUX_ORG = os.environ.get("INFLUXDB_ORG", "mcpsoftware")
INFLUX_TOKEN = os.environ.get("INFLUXDB_TOKEN", "")
INFLUX_BUCKET = os.environ.get("INFLUXDB_BUCKET", "fintech")

HOST = os.environ.get("FINTECH_HOST", "127.0.0.1")
PORT = int(os.environ.get("FINTECH_PORT", "5000"))
DEBUG = os.environ.get("FINTECH_DEBUG", "0") == "1"

# Public site URL used for SEO (canonical link, Open Graph, sitemap.xml).
# Override with the SITE_URL env var when a custom domain is attached.
SITE_URL = os.environ.get("SITE_URL", "https://fintech-52jk.vercel.app").rstrip("/")

# ------------------------------------------------- accounts & admin access
# Signs the login session cookie. MUST be a stable random value on Vercel
# (SECRET_KEY env var), otherwise sessions are dropped between invocations.
# Locally a per-process random key is used when unset (dev convenience).
SECRET_KEY = os.environ.get("SECRET_KEY", "")

# Password for the /quan-tri admin page (creates users, reviews requests).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# Registration-request notifications: SMTP (Gmail app password) when
# SMTP_USER/SMTP_PASS are set, otherwise the FormSubmit relay is used.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "mcpsoftware@gmail.com")

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

# Default user settings stored in InfluxDB (measurement settings, key/value)
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
