"""Media downloading with yt-dlp: URL validation, download, retry, and file info."""
import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from config import COOKIES_FILE, MAX_BYTES, MAX_MEDIA_ITEMS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-type constants
# ---------------------------------------------------------------------------
PHOTO_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS: set[str] = {".mp4", ".mkv", ".webm", ".mov"}
ALL_MEDIA_EXTENSIONS: set[str] = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def is_supported_url(url: str) -> bool:
    """Return *True* if *url* is a valid Instagram or TikTok link."""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().removeprefix("www.")
        return parsed.scheme in {"http", "https"} and (
            host == "instagram.com"
            or host.endswith(".instagram.com")
            or host == "tiktok.com"
            or host.endswith(".tiktok.com")
        )
    except ValueError:
        return False


def platform_for(url: str) -> str:
    """Return ``'Instagram'`` or ``'TikTok'`` based on the URL hostname."""
    host = (urlparse(url).hostname or "").lower()
    return "Instagram" if "instagram.com" in host else "TikTok"


# ---------------------------------------------------------------------------
# Core download
# ---------------------------------------------------------------------------
def download_media(url: str, folder: str) -> list[Path]:
    """Download media from *url* into *folder* using yt-dlp.

    Returns a list of downloaded file paths sorted by modification time.
    """
    ffmpeg_available = shutil.which("ffmpeg") is not None
    options: dict = {
        "outtmpl": str(Path(folder) / "%(title).80s-%(id)s.%(ext)s"),
        "format": (
            "bestvideo*+bestaudio/best"
            if ffmpeg_available
            else "best[ext=mp4]/best"
        ),
        "noplaylist": False,
        "max_downloads": MAX_MEDIA_ITEMS,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": MAX_BYTES,
        "socket_timeout": 30,
        "retries": 3,
    }
    if ffmpeg_available:
        options["merge_output_format"] = "mp4"
    else:
        logger.warning(
            "FFmpeg not found; yt-dlp will use the best single-file format."
        )
    if COOKIES_FILE:
        if not Path(COOKIES_FILE).is_file():
            raise FileNotFoundError(
                "YTDLP_COOKIES_FILE does not point to a file"
            )
        options["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    return sorted(
        (
            p
            for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in ALL_MEDIA_EXTENSIONS
        ),
        key=lambda p: p.stat().st_mtime,
    )


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------
async def download_with_retry(
    url: str, folder: str, max_retries: int = 2
) -> list[Path]:
    """Download media with exponential-backoff retries.

    On each ``yt_dlp.utils.DownloadError`` the function waits
    ``2 ** attempt`` seconds before retrying, up to *max_retries* times.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(download_media, url, folder)
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            if attempt < max_retries:
                delay = 2**attempt
                logger.info(
                    "yt-dlp attempt %d/%d failed, retrying in %ds: %s",
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
            else:
                logger.info("yt-dlp download failed after %d attempts.", max_retries + 1)
    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# File info extraction
# ---------------------------------------------------------------------------
def get_file_info(file_path: Path) -> dict:
    """Return metadata about a downloaded media file.

    Keys: ``size`` (int, bytes), ``resolution`` (str or None, e.g.
    ``'1080x1920'``), ``is_photo`` (bool), ``media_type`` (``'photo'``
    or ``'video'``).
    """
    size = file_path.stat().st_size
    suffix = file_path.suffix.lower()
    is_photo = suffix in PHOTO_EXTENSIONS
    media_type = "photo" if is_photo else "video"
    resolution: str | None = None

    if not is_photo and shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-select_streams", "v:0",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                if streams:
                    w = streams[0].get("width")
                    h = streams[0].get("height")
                    if w and h:
                        resolution = f"{w}x{h}"
        except Exception:
            logger.debug("ffprobe resolution extraction failed", exc_info=True)

    return {
        "size": size,
        "resolution": resolution,
        "is_photo": is_photo,
        "media_type": media_type,
    }
