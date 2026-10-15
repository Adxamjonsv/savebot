"""SQLite persistence for registered users, download history, and media assets."""
import aiosqlite

from config import DB_PATH, LOG_RETENTION_DAYS, MEDIA_RETENTION_DAYS


async def _column_names(db: aiosqlite.Connection, table: str) -> set[str]:
    """Return the set of column names for *table*."""
    rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


async def initialize_database() -> None:
    """Create tables, indexes, and migrate older schemas."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                full_name  TEXT    NOT NULL,
                language   TEXT    NOT NULL DEFAULT 'uz',
                status     TEXT    NOT NULL DEFAULT 'active',
                joined_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            CREATE TABLE IF NOT EXISTS downloads (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                username      TEXT,
                link          TEXT    NOT NULL,
                platform      TEXT    NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'downloading',
                file_size     INTEGER,
                resolution    TEXT,
                media_type    TEXT,
                downloaded_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS media_assets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                download_id   INTEGER NOT NULL,
                file_name     TEXT,
                media_type    TEXT    NOT NULL,
                original_name TEXT    NOT NULL,
                stored_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY(download_id) REFERENCES downloads(id)
            );

            CREATE INDEX IF NOT EXISTS idx_downloads_user  ON downloads(user_id);
            CREATE INDEX IF NOT EXISTS idx_downloads_date  ON downloads(downloaded_at DESC);
            CREATE INDEX IF NOT EXISTS idx_media_download  ON media_assets(download_id);
            CREATE INDEX IF NOT EXISTS idx_users_status     ON users(status);
        """)

        # ── Migrations for databases created by earlier versions ──────────
        user_cols = await _column_names(db, "users")
        if "status" not in user_cols:
            await db.execute(
                "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )

        dl_cols = await _column_names(db, "downloads")
        if "status" not in dl_cols:
            await db.execute(
                "ALTER TABLE downloads ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'"
            )
        if "file_size" not in dl_cols:
            await db.execute("ALTER TABLE downloads ADD COLUMN file_size INTEGER")
        if "resolution" not in dl_cols:
            await db.execute("ALTER TABLE downloads ADD COLUMN resolution TEXT")
        if "media_type" not in dl_cols:
            await db.execute("ALTER TABLE downloads ADD COLUMN media_type TEXT")

        await db.commit()


# ── Users ─────────────────────────────────────────────────────────────────


async def register_user(
    user_id: int, username: str | None, full_name: str
) -> str:
    """Register or update a user and return their language preference."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT language FROM users WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        language = row[0] if row else "uz"
        await db.execute(
            """INSERT INTO users(user_id, username, full_name, language)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   username=excluded.username, full_name=excluded.full_name""",
            (user_id, username, full_name, language),
        )
        await db.commit()
        return language


async def get_language(user_id: int) -> str:
    """Return the user's preferred language, defaulting to ``'uz'``."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT language FROM users WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else "uz"


async def set_language(user_id: int, language: str) -> None:
    """Persist *language* for the given user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET language=? WHERE user_id=?", (language, user_id)
        )
        await db.commit()


async def get_user_status(user_id: int) -> str | None:
    """Return ``'active'``, ``'blocked'``, or *None* if user not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT status FROM users WHERE user_id=?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_user_status(user_id: int, status: str) -> None:
    """Set user status to ``'active'`` or ``'blocked'``."""
    if status not in {"active", "blocked"}:
        raise ValueError("status must be 'active' or 'blocked'")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET status=? WHERE user_id=?", (status, user_id)
        )
        await db.commit()


async def search_user(user_id: int) -> dict | None:
    """Look up a user by Telegram ID; return info dict or *None*."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (
            await db.execute(
                """SELECT u.user_id, u.username, u.full_name, u.language,
                          u.status, u.joined_at, COUNT(d.id)
                   FROM users u
                   LEFT JOIN downloads d ON d.user_id = u.user_id
                   WHERE u.user_id=?
                   GROUP BY u.user_id""",
                (user_id,),
            )
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "full_name": row[2],
            "language": row[3],
            "status": row[4],
            "joined_at": row[5],
            "download_count": row[6],
        }


async def all_user_ids() -> list[int]:
    """Return IDs of all **active** users."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM users WHERE status='active'"
        )
        return [int(row[0]) for row in await cursor.fetchall()]


# ── Downloads ─────────────────────────────────────────────────────────────


async def log_download(
    user_id: int, username: str | None, link: str, platform: str
) -> int:
    """Insert a new download record and return its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO downloads(user_id, username, link, platform, status)
               VALUES(?, ?, ?, ?, 'downloading')""",
            (user_id, username, link, platform),
        )
        await db.commit()
        return int(cursor.lastrowid)  # type: ignore[arg-type]


async def update_download_status(download_id: int, status: str) -> None:
    """Set the download record's status to ``'completed'`` or ``'failed'``."""
    if status not in {"completed", "failed"}:
        raise ValueError("Invalid download status")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE downloads SET status=? WHERE id=?", (status, download_id)
        )
        await db.commit()


async def update_download_meta(
    download_id: int,
    *,
    file_size: int | None = None,
    resolution: str | None = None,
    media_type: str | None = None,
) -> None:
    """Attach file-size, resolution, and/or media-type to a download record."""
    parts: list[str] = []
    params: list[object] = []
    if file_size is not None:
        parts.append("file_size=?")
        params.append(file_size)
    if resolution is not None:
        parts.append("resolution=?")
        params.append(resolution)
    if media_type is not None:
        parts.append("media_type=?")
        params.append(media_type)
    if not parts:
        return
    params.append(download_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE downloads SET {', '.join(parts)} WHERE id=?", params
        )
        await db.commit()


async def user_download_count_since(user_id: int, since_seconds: int) -> int:
    """Count downloads by *user_id* within the last *since_seconds*."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) FROM downloads
               WHERE user_id=?
                 AND datetime(downloaded_at) >= datetime('now', ?)""",
            (user_id, f"-{since_seconds} seconds"),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


# ── Statistics and admin ──────────────────────────────────────────────────


async def statistics() -> tuple[int, int]:
    """Return ``(total_users, total_downloads)``."""
    async with aiosqlite.connect(DB_PATH) as db:
        users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        downloads = await (
            await db.execute("SELECT COUNT(*) FROM downloads")
        ).fetchone()
        return int(users[0]), int(downloads[0])  # type: ignore[index]


async def today_active_users() -> int:
    """Count distinct users who downloaded something today (UTC)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(DISTINCT user_id) FROM downloads
               WHERE date(downloaded_at) = date('now')"""
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def recent_downloads(limit: int = 20) -> list[tuple]:
    """Return the latest *limit* download records (joined with users)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT d.user_id, d.username, u.full_name, d.link,
                      d.platform, d.status, d.downloaded_at
               FROM downloads d
               LEFT JOIN users u ON u.user_id = d.user_id
               ORDER BY d.id DESC LIMIT ?""",
            (limit,),
        )
        return await cursor.fetchall()


async def admin_user_list() -> list[dict]:
    """Return every user with their download count for the Mini App."""
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (
            await conn.execute(
                """SELECT u.user_id, u.username, u.full_name, u.joined_at,
                          COUNT(d.id), MAX(d.downloaded_at)
                   FROM users u
                   LEFT JOIN downloads d ON d.user_id = u.user_id
                   GROUP BY u.user_id
                   ORDER BY COALESCE(MAX(d.downloaded_at), u.joined_at) DESC"""
            )
        ).fetchall()
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "full_name": row[2],
            "joined_at": row[3],
            "download_count": row[4],
            "last_download": row[5],
        }
        for row in rows
    ]


async def user_download_history(user_id: int) -> list[dict]:
    """Return full download history for *user_id*, including media assets."""
    async with aiosqlite.connect(DB_PATH) as conn:
        downloads = await (
            await conn.execute(
                """SELECT id, platform, status, downloaded_at, link
                   FROM downloads WHERE user_id=? ORDER BY id DESC""",
                (user_id,),
            )
        ).fetchall()
        result: list[dict] = []
        for download_id, platform, status, downloaded_at, link in downloads:
            assets = await (
                await conn.execute(
                    """SELECT id, file_name, media_type, original_name
                       FROM media_assets WHERE download_id=? ORDER BY id""",
                    (download_id,),
                )
            ).fetchall()
            result.append(
                {
                    "id": download_id,
                    "platform": platform,
                    "status": status,
                    "timestamp": downloaded_at,
                    "source_url": link,
                    "media": [
                        {
                            "id": item[0],
                            "available": item[1] is not None,
                            "type": item[2],
                            "name": item[3],
                        }
                        for item in assets
                    ],
                }
            )
    return result


# ── Media assets ──────────────────────────────────────────────────────────


async def save_media_asset(
    download_id: int, file_name: str, media_type: str, original_name: str
) -> int:
    """Store a media-asset reference and return its ID."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO media_assets(download_id, file_name, media_type, original_name)
               VALUES(?, ?, ?, ?)""",
            (download_id, file_name, media_type, original_name),
        )
        await conn.commit()
        return int(cursor.lastrowid)  # type: ignore[arg-type]


async def media_asset(asset_id: int) -> tuple | None:
    """Return ``(file_name, media_type, original_name)`` or *None*."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT file_name, media_type, original_name FROM media_assets WHERE id=?",
            (asset_id,),
        )
        return await cursor.fetchone()


async def expire_media_assets(days: int | None = None) -> list[str]:
    """Null out ``file_name`` for assets older than *days* and return the old names."""
    if days is None:
        days = MEDIA_RETENTION_DAYS
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT file_name FROM media_assets
               WHERE file_name IS NOT NULL
                 AND datetime(stored_at) < datetime('now', ?)""",
            (f"-{days} days",),
        )
        file_names = [row[0] for row in await cursor.fetchall()]
        await conn.execute(
            """UPDATE media_assets SET file_name=NULL
               WHERE file_name IS NOT NULL
                 AND datetime(stored_at) < datetime('now', ?)""",
            (f"-{days} days",),
        )
        await conn.commit()
        return file_names


# ── Maintenance ───────────────────────────────────────────────────────────


async def cleanup_old_logs(days: int | None = None) -> int:
    """Delete download records older than *days*.  Returns the count deleted."""
    if days is None:
        days = LOG_RETENTION_DAYS
    async with aiosqlite.connect(DB_PATH) as db:
        # Delete orphaned media_assets first.
        await db.execute(
            """DELETE FROM media_assets WHERE download_id IN (
                   SELECT id FROM downloads
                   WHERE datetime(downloaded_at) < datetime('now', ?)
               )""",
            (f"-{days} days",),
        )
        cursor = await db.execute(
            "DELETE FROM downloads WHERE datetime(downloaded_at) < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
        return cursor.rowcount
