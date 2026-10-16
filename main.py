"""Production-oriented Instagram/TikTok downloader bot (aiogram 3).

Modular architecture:
    config.py      – environment variables and validation
    i18n.py        – Uzbek / Russian localization
    database.py    – aiosqlite persistence
    downloader.py  – yt-dlp media downloading
    middleware.py  – anti-spam, rate-limit, user-status middleware
    main.py        – bot handlers, admin panel, FastAPI web server
"""

import asyncio
import hashlib
import hmac
import json
import logging
import mimetypes
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl

import uvicorn
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

import database as db
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    MAX_BYTES,
    MEDIA_ARCHIVE,
    MINI_APP_HTML,
    WEBAPP_URL,
    WEB_HOST,
    WEB_PORT,
    validate,
)
from downloader import (
    download_with_retry,
    get_file_info,
    is_supported_url,
    platform_for,
)
from i18n import TEXT, t
from middleware import (
    AntiSpamMiddleware,
    DownloadRateLimitMiddleware,
    UserStatusMiddleware,
)

logger = logging.getLogger(__name__)

# ── Aiogram router & FastAPI app ──────────────────────────────────────────

router = Router()

web_app = FastAPI(
    title="Savebot Admin Mini App",
    docs_url=None,
    redoc_url=None,
)

# Railway / Uvicorn ASGI compatibility.
# Both "uvicorn main:app" and the internal web server can use this app.
app = web_app

DATA_DIR = MEDIA_ARCHIVE.parent


# ── FSM states ────────────────────────────────────────────────────────────

class AdminFlow(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_search = State()


# ── Helpers ───────────────────────────────────────────────────────────────

async def get_lang(user_id: int) -> str:
    """Return the user's saved language; fall back to Uzbek."""
    value = await db.get_language(user_id)
    return value if value in TEXT else "uz"


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="O'zbekcha 🇺🇿",
                    callback_data="lang:uz",
                ),
                InlineKeyboardButton(
                    text="Русский 🇷🇺",
                    callback_data="lang:ru",
                ),
            ]
        ]
    )


def admin_keyboard(language: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if WEBAPP_URL.startswith("https://"):
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Admin Mini App",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=t(language, "stats"),
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "recent"),
                    callback_data="admin:recent",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "search"),
                    callback_data="admin:search",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "broadcast"),
                    callback_data="admin:broadcast",
                )
            ],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Telegram Mini App initData validation ─────────────────────────────────

def verify_webapp_init_data(init_data: str) -> dict:
    """Validate Telegram Mini App initData and return the signed user."""
    if not BOT_TOKEN or not init_data:
        raise HTTPException(
            status_code=401,
            detail="Telegram session is missing",
        )

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")

    if not received_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram session",
        )

    check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )

    # Correct Telegram Web App HMAC validation:
    # secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    expected_hash = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(
            status_code=401,
            detail="Telegram session verification failed",
        )

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram session data",
        )

    now = time.time()

    if auth_date > now + 60 or now - auth_date > 24 * 60 * 60:
        raise HTTPException(
            status_code=401,
            detail="Telegram session expired; reopen the Mini App",
        )

    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram user",
        )

    if user["id"] not in ADMIN_IDS:
        raise HTTPException(
            status_code=403,
            detail="Admin access only",
        )

    return user


# ── FastAPI endpoints ─────────────────────────────────────────────────────

@web_app.get("/", response_class=HTMLResponse)
async def mini_app_home() -> HTMLResponse:
    """Serve the Admin Mini App HTML."""
    if not MINI_APP_HTML.is_file():
        raise HTTPException(
            status_code=404,
            detail="Admin Mini App files are missing",
        )

    return HTMLResponse(
        MINI_APP_HTML.read_text(encoding="utf-8")
    )


@web_app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@web_app.get("/api/dashboard")
async def mini_app_dashboard(
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    verify_webapp_init_data(x_telegram_init_data)

    users = await db.admin_user_list()
    total_users, total_downloads = await db.statistics()
    today_active = await db.today_active_users()

    return {
        "total_users": total_users,
        "total_downloads": total_downloads,
        "today_active": today_active,
        "users": users,
    }


@web_app.get("/api/users/{user_id}/downloads")
async def mini_app_user_downloads(
    user_id: int,
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    verify_webapp_init_data(x_telegram_init_data)

    return {
        "downloads": await db.user_download_history(user_id)
    }


@web_app.get("/api/gallery")
async def mini_app_gallery(
    platform: str = "all",
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    """Return archived media filtered by platform for the admin gallery."""
    verify_webapp_init_data(x_telegram_init_data)

    allowed_platforms = {"all", "instagram", "youtube", "tiktok", "other"}
    selected = platform.strip().lower()
    if selected not in allowed_platforms:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    items = await db.admin_media_gallery(
        None if selected == "all" else selected
    )

    media = [
        {
            "asset_id": item["asset_id"],
            "download_id": item["download_id"],
            "available": item["available"],
            "media_type": item["media_type"],
            "original_name": item["file_name"],
            "user_id": item["user_id"],
            "username": item["username"],
            "platform": item["platform"],
            "source_url": item["source_url"],
            "timestamp": item["timestamp"],
            "full_name": item["full_name"],
        }
        for item in items
    ]
    return {"platform": selected, "count": len(media), "media": media}


@web_app.get("/api/media/{asset_id}")
async def mini_app_media(
    asset_id: int,
    x_telegram_init_data: str = Header(default=""),
) -> FileResponse:
    verify_webapp_init_data(x_telegram_init_data)

    asset = await db.media_asset(asset_id)

    if not asset or not asset[0]:
        raise HTTPException(
            status_code=404,
            detail="Video is no longer available",
        )

    file_name, media_type, original_name = asset

    # Prevent path traversal.
    if Path(file_name).name != file_name:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    path = MEDIA_ARCHIVE / file_name

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Video is no longer available",
        )

    mime_type = (
        mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )

    return FileResponse(
        path,
        media_type=mime_type,
        headers={"Content-Disposition": "inline"},
    )


# ── Background maintenance workers ───────────────────────────────────────

async def cleanup_expired_media() -> None:
    """Remove archived files whose retention period has expired."""
    for name in await db.expire_media_assets():
        if Path(name).name == name:
            (MEDIA_ARCHIVE / name).unlink(missing_ok=True)


async def maintenance_worker() -> None:
    """Periodically clean expired media and old download logs."""
    while True:
        await asyncio.sleep(6 * 60 * 60)

        try:
            await cleanup_expired_media()

            deleted = await db.cleanup_old_logs()

            if deleted:
                logger.info(
                    "Cleaned up %d old download log records.",
                    deleted,
                )

        except Exception:
            logger.exception("Maintenance worker failed")


# ── Bot handlers: /start, /language, /help ────────────────────────────────

@router.message(CommandStart())
async def start(message: Message) -> None:
    user = message.from_user

    if not user:
        return

    language = await db.register_user(
        user.id,
        user.username,
        user.full_name,
    )

    await message.answer(
        t(language, "welcome"),
        reply_markup=language_keyboard(),
    )


@router.message(Command("language", "lang"))
async def select_language(message: Message) -> None:
    if not message.from_user:
        return

    language = await get_lang(message.from_user.id)

    await message.answer(
        t(language, "choose"),
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def set_language(query: CallbackQuery) -> None:
    chosen = query.data.split(":", 1)[1]

    if chosen in TEXT:
        user = query.from_user

        await db.register_user(
            user.id,
            user.username,
            user.full_name,
        )

        await db.set_language(user.id, chosen)

        if query.message:
            await query.message.edit_text(
                t(chosen, "selected")
                + "\n"
                + t(chosen, "welcome")
            )

    await query.answer()


@router.message(Command("help"))
async def help_message(message: Message) -> None:
    if not message.from_user:
        return

    await message.answer(
        t(await get_lang(message.from_user.id), "help")
    )


# ── Bot handlers: /admin ──────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_dashboard(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.from_user:
        return

    await state.clear()

    if message.from_user.id not in ADMIN_IDS:
        await message.answer(
            t(
                await get_lang(message.from_user.id),
                "not_admin",
            )
        )
        return

    language = await get_lang(message.from_user.id)

    await message.answer(
        t(language, "admin"),
        reply_markup=admin_keyboard(language),
    )


@router.callback_query(F.data.startswith("admin:"))
async def admin_actions(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.from_user.id not in ADMIN_IDS:
        await query.answer(
            "Admins only",
            show_alert=True,
        )
        return

    language = await get_lang(query.from_user.id)
    action = query.data.split(":", 1)[1]

    if action == "stats":
        users, downloads = await db.statistics()
        today = await db.today_active_users()

        text = (
            f"{t(language, 'users')}: {users}\n"
            f"{t(language, 'downloads')}: {downloads}\n"
            f"{t(language, 'today_active')}: {today}"
        )

        await query.message.answer(text)

    elif action == "recent":
        rows = await db.recent_downloads(20)

        if not rows:
            await query.message.answer(t(language, "empty"))
        else:
            lines: list[str] = []

            for (
                user_id,
                username,
                full_name,
                link,
                platform,
                status,
                timestamp,
            ) in rows:
                who = (
                    f"@{username}"
                    if username
                    else (full_name or str(user_id))
                )

                lines.append(
                    f"{platform} | {who} | {status} | {timestamp}\n"
                    f"{link[:300]}"
                )

            await query.message.answer(
                "\n\n".join(lines)[:4000]
            )

    elif action == "search":
        await state.set_state(AdminFlow.waiting_for_search)
        await query.message.answer(
            t(language, "search_prompt")
        )

    elif action == "broadcast":
        await state.set_state(AdminFlow.waiting_for_broadcast)
        await query.message.answer(
            t(language, "broadcast_prompt")
        )

    await query.answer()


# ── Admin: search by user ID ──────────────────────────────────────────────

@router.message(AdminFlow.waiting_for_search)
async def admin_search_user(
    message: Message,
    state: FSMContext,
) -> None:
    if (
        not message.from_user
        or message.from_user.id not in ADMIN_IDS
    ):
        await state.clear()
        return

    language = await get_lang(message.from_user.id)
    text = (message.text or "").strip()

    if text.lower() == "/cancel":
        await state.clear()
        await message.answer(
            t(language, "cancelled")
        )
        return

    if not text.isdigit():
        await message.answer(
            t(language, "search_prompt")
        )
        return

    user_info = await db.search_user(int(text))
    await state.clear()

    if user_info:
        await message.answer(
            t(
                language,
                "search_result",
                full_name=user_info["full_name"] or "—",
                user_id=user_info["user_id"],
                username=user_info["username"] or "—",
                download_count=user_info["download_count"],
                joined_at=user_info["joined_at"],
                status=user_info["status"],
            )
        )
    else:
        await message.answer(
            t(language, "search_not_found")
        )


# ── Admin: cancel / broadcast ─────────────────────────────────────────────

@router.message(
    Command("cancel"),
    AdminFlow.waiting_for_broadcast,
)
async def cancel_broadcast(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()

    if message.from_user:
        await message.answer(
            t(
                await get_lang(message.from_user.id),
                "cancelled",
            )
        )


@router.message(AdminFlow.waiting_for_broadcast)
async def broadcast_message(
    message: Message,
    bot: Bot,
    state: FSMContext,
) -> None:
    if (
        not message.from_user
        or message.from_user.id not in ADMIN_IDS
    ):
        await state.clear()
        return

    recipients = await db.all_user_ids()
    sent = 0
    failed = 0

    for user_id in recipients:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1

        except Exception as error:
            failed += 1
            logger.info(
                "Broadcast delivery failed for user %s: %s",
                user_id,
                error,
            )

        await asyncio.sleep(0.04)

    await state.clear()

    language = await get_lang(message.from_user.id)

    await message.answer(
        t(
            language,
            "broadcast_done",
            sent=sent,
            failed=failed,
        )
    )


# ── Bot handler: media download ───────────────────────────────────────────

@router.message(F.text)
async def process_link(message: Message) -> None:
    if not message.from_user:
        return

    language = await get_lang(message.from_user.id)
    url = message.text.strip()

    if not is_supported_url(url):
        await message.answer(t(language, "bad"))
        return

    user = message.from_user

    download_id = await db.log_download(
        user.id,
        user.username,
        url,
        platform_for(url),
    )

    status_msg = await message.answer(
        t(language, "working")
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix="savebot-"
        ) as directory:
            files = await download_with_retry(
                url,
                directory,
            )

            if not files:
                await db.update_download_status(
                    download_id,
                    "failed",
                )
                await status_msg.edit_text(
                    t(language, "fail")
                )
                return

            total_size = 0
            first_media_type: str | None = None

            for file in files:
                info = get_file_info(file)

                if info["size"] > MAX_BYTES:
                    await message.answer(
                        t(language, "large")
                    )
                    continue

                suffix = file.suffix.lower()
                archived_name = f"{uuid.uuid4().hex}{suffix}"
                archived_path = MEDIA_ARCHIVE / archived_name

                await asyncio.to_thread(
                    shutil.copy2,
                    file,
                    archived_path,
                )

                await db.save_media_asset(
                    download_id,
                    archived_name,
                    info["media_type"],
                    file.name,
                )

                total_size += info["size"]

                if first_media_type is None:
                    first_media_type = info["media_type"]

                if info["is_photo"]:
                    await message.answer_photo(
                        FSInputFile(file)
                    )
                else:
                    await message.answer_video(
                        FSInputFile(file),
                        supports_streaming=True,
                    )

            await db.update_download_meta(
                download_id,
                file_size=total_size if total_size else None,
                media_type=(
                    "carousel"
                    if len(files) > 1
                    else (first_media_type or "video")
                ),
            )

        await db.update_download_status(
            download_id,
            "completed",
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as exc:
        if "DownloadError" in type(exc).__name__:
            logger.info(
                "yt-dlp download failed: %s",
                exc,
            )
        else:
            logger.exception(
                "Media download or delivery failed"
            )

        await db.update_download_status(
            download_id,
            "failed",
        )

        try:
            await status_msg.edit_text(
                t(language, "fail")
            )
        except Exception:
            pass


# ── Application entry point ───────────────────────────────────────────────

async def main() -> None:
    """Start the bot, web server, and maintenance worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    validate()

    await db.initialize_database()

    MEDIA_ARCHIVE.mkdir(
        parents=True,
        exist_ok=True,
    )

    await cleanup_expired_media()

    bot = Bot(BOT_TOKEN)
    dispatcher = Dispatcher(
        storage=MemoryStorage()
    )

    router.message.middleware(
        UserStatusMiddleware()
    )
    router.message.middleware(
        AntiSpamMiddleware()
    )
    router.message.middleware(
        DownloadRateLimitMiddleware()
    )

    dispatcher.include_router(router)

    web_config = uvicorn.Config(
        web_app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="warning",
    )

    web_server = uvicorn.Server(web_config)

    await asyncio.gather(
        dispatcher.start_polling(bot),
        web_server.serve(),
        maintenance_worker(),
    )


if __name__ == "__main__":
    asyncio.run(main())
