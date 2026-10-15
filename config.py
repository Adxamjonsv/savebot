"""Centralized configuration loaded from environment variables."""
import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_DIR)))
DB_PATH = DATA_DIR / "savebot.sqlite3"
MEDIA_ARCHIVE = DATA_DIR / "media_archive"
MINI_APP_HTML = _PROJECT_DIR / "webapp" / "index.html"

# ---------------------------------------------------------------------------
# Bot core
# ---------------------------------------------------------------------------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: set[int] = {
    int(v) for v in os.getenv("ADMIN_IDS", "").split(",") if v.strip().isdigit()
}
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "").strip().rstrip("/")

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))

# ---------------------------------------------------------------------------
# Download limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "49"))
MAX_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024
MAX_MEDIA_ITEMS: int = int(os.getenv("MAX_MEDIA_ITEMS", "10"))
COOKIES_FILE: str = os.getenv("YTDLP_COOKIES_FILE", "").strip()

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
RATE_LIMIT_DOWNLOADS: int = int(os.getenv("RATE_LIMIT_DOWNLOADS", "5"))
RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
MEDIA_RETENTION_DAYS: int = int(os.getenv("MEDIA_RETENTION_DAYS", "7"))
LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "90"))


def validate() -> None:
    """Validate critical configuration; raise RuntimeError on fatal issues."""
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is required. "
            "Get one from @BotFather on Telegram."
        )
    if not ADMIN_IDS:
        logging.warning("ADMIN_IDS is empty; /admin will be unavailable.")
    if COOKIES_FILE and not Path(COOKIES_FILE).is_file():
        raise RuntimeError(
            f"YTDLP_COOKIES_FILE is set but the file does not exist: "
            f"{COOKIES_FILE!r}"
        )
    if WEBAPP_URL and not WEBAPP_URL.startswith("https://"):
        logging.warning(
            "WEBAPP_URL must be a public HTTPS URL for Telegram Mini Apps."
        )
