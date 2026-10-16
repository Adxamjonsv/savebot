
async def admin_media_gallery(platform: str | None = None) -> list[dict]:
    """Return archived media for the admin gallery, optionally filtered by platform."""
    async with aiosqlite.connect(DB_PATH) as conn:
        query = """
            SELECT
                ma.id,
                ma.download_id,
                ma.file_name,
                ma.media_type,
                ma.original_name,
                d.user_id,
                d.username,
                d.platform,
                d.link,
                d.downloaded_at,
                u.full_name
            FROM media_assets AS ma
            JOIN downloads AS d ON d.id = ma.download_id
            LEFT JOIN users AS u ON u.user_id = d.user_id
        """
        params: tuple = ()

        if platform:
            normalized = platform.strip().lower()
            aliases = {
                "instagram": ["instagram"],
                "youtube": ["youtube", "youtu.be"],
                "tiktok": ["tiktok"],
                "other": ["other", "boshqa"],
            }
            values = aliases.get(normalized, [normalized])
            placeholders = ", ".join("LOWER(d.platform) = ?" for _ in values)
            query += f" WHERE ({placeholders})"
            params = tuple(values)

        query += " ORDER BY d.id DESC, ma.id DESC"

        cursor = await conn.execute(query, params)
        rows = await cursor.fetchall()

    return [
        {
            "asset_id": row[0],
            "download_id": row[1],
            "available": row[2] is not None,
            "media_type": row[3],
            "file_name": row[4],
            "user_id": row[5],
            "username": row[6],
            "platform": row[7],
            "source_url": row[8],
            "timestamp": row[9],
            "full_name": row[10],
        }
        for row in rows
    ]
