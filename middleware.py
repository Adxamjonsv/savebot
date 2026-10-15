"""Aiogram 3.x middleware: anti-spam, download rate-limiting, user blocking."""
import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import ADMIN_IDS, RATE_LIMIT_DOWNLOADS, RATE_LIMIT_WINDOW
from i18n import t

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. General anti-spam (in-memory, per-user message rate)
# ---------------------------------------------------------------------------
_SPAM_MAX_MESSAGES = 5
_SPAM_WINDOW_SECONDS = 10
_CLEANUP_INTERVAL = 100  # run cleanup every N calls


class AntiSpamMiddleware(BaseMiddleware):
    """Drop messages when a user exceeds the general message rate limit.

    Limit: *_SPAM_MAX_MESSAGES* messages per *_SPAM_WINDOW_SECONDS*.
    Admin users are exempt.
    """

    def __init__(self) -> None:
        self._timestamps: dict[int, list[float]] = defaultdict(list)
        self._call_count: int = 0

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        now = time.monotonic()
        self._call_count += 1
        if self._call_count % _CLEANUP_INTERVAL == 0:
            self._cleanup(now)

        timestamps = self._timestamps[user_id]
        # Remove timestamps outside the window.
        cutoff = now - _SPAM_WINDOW_SECONDS
        self._timestamps[user_id] = [ts for ts in timestamps if ts > cutoff]
        timestamps = self._timestamps[user_id]

        if len(timestamps) >= _SPAM_MAX_MESSAGES:
            try:
                from database import get_language

                lang = await get_language(user_id)
                await event.answer(t(lang, "rate_limited"))
            except Exception:
                logger.debug("Could not send rate-limit reply", exc_info=True)
            return None

        timestamps.append(now)
        return await handler(event, data)

    def _cleanup(self, now: float) -> None:
        """Remove entries older than 60 seconds to prevent memory growth."""
        cutoff = now - 60
        stale = [uid for uid, ts in self._timestamps.items() if not ts or ts[-1] < cutoff]
        for uid in stale:
            del self._timestamps[uid]


# ---------------------------------------------------------------------------
# 2. Download rate-limit (database-backed)
# ---------------------------------------------------------------------------
class DownloadRateLimitMiddleware(BaseMiddleware):
    """Reject download requests when user exceeds the per-user download limit.

    Only activates for messages that look like URLs.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        text = (event.text or "").strip()
        if not (text.startswith("http://") or text.startswith("https://")):
            return await handler(event, data)

        try:
            from database import get_language, user_download_count_since

            count = await user_download_count_since(user_id, RATE_LIMIT_WINDOW)
            if count >= RATE_LIMIT_DOWNLOADS:
                lang = await get_language(user_id)
                await event.answer(t(lang, "rate_limited"))
                return None
        except Exception:
            # If the DB check fails, let the request through.
            logger.debug("Download rate-limit check failed", exc_info=True)

        return await handler(event, data)


# ---------------------------------------------------------------------------
# 3. User status check (blocked users)
# ---------------------------------------------------------------------------
_BLOCK_CACHE_TTL = 300  # 5 minutes


class UserStatusMiddleware(BaseMiddleware):
    """Block interactions from users whose status is ``'blocked'``.

    Blocked status is cached for *_BLOCK_CACHE_TTL* seconds to reduce
    database queries.
    """

    def __init__(self) -> None:
        self._cache: dict[int, tuple[bool, float]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        now = time.monotonic()
        cached = self._cache.get(user_id)
        if cached and (now - cached[1]) < _BLOCK_CACHE_TTL:
            is_blocked = cached[0]
        else:
            is_blocked = False
            try:
                from database import get_user_status

                status = await get_user_status(user_id)
                is_blocked = status == "blocked"
                self._cache[user_id] = (is_blocked, now)
            except Exception:
                logger.debug("User status check failed", exc_info=True)

        if is_blocked:
            try:
                from database import get_language

                lang = await get_language(user_id)
                await event.answer(t(lang, "user_blocked"))
            except Exception:
                pass
            return None

        return await handler(event, data)
