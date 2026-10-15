"""Quick smoke-test for all modules (no bot token needed)."""
import asyncio
import sys

def run_tests() -> None:
    # ── i18n ──────────────────────────────────────────────────────────
    from i18n import t, TEXT
    assert t("uz", "welcome") != "welcome", "uz welcome missing"
    assert t("ru", "welcome") != "welcome", "ru welcome missing"
    assert "so'rov" in t("uz", "rate_limited"), "rate_limited wrong"
    result = t("ru", "search_result", full_name="Test", user_id=123,
               username="tst", download_count=5, joined_at="2025-01-01",
               status="active")
    assert "Test" in result and "123" in result
    assert t("xx", "welcome") == t("uz", "welcome"), "fallback broken"
    assert len(TEXT["uz"]) == len(TEXT["ru"]), "key count mismatch"
    print(f"i18n: {len(TEXT['uz'])} keys per language, all checks passed")

    # ── downloader ────────────────────────────────────────────────────
    from downloader import is_supported_url, platform_for
    assert is_supported_url("https://www.instagram.com/p/ABC123/")
    assert is_supported_url("https://www.tiktok.com/@user/video/123")
    assert is_supported_url("https://vm.tiktok.com/ZMxxxxxx/")
    assert not is_supported_url("https://youtube.com/watch?v=abc")
    assert not is_supported_url("not a url")
    assert platform_for("https://instagram.com/p/x") == "Instagram"
    assert platform_for("https://tiktok.com/@x/video/1") == "TikTok"
    print("downloader: URL validation checks passed")

    # ── middleware ─────────────────────────────────────────────────────
    from middleware import AntiSpamMiddleware, DownloadRateLimitMiddleware, UserStatusMiddleware
    a = AntiSpamMiddleware()
    b = DownloadRateLimitMiddleware()
    c = UserStatusMiddleware()
    print("middleware: all 3 classes instantiate OK")

    # ── database ──────────────────────────────────────────────────────
    from database import (initialize_database, register_user, get_language,
                          search_user, log_download, update_download_status,
                          statistics, today_active_users, user_download_count_since)
    asyncio.run(initialize_database())
    lang = asyncio.run(register_user(999999, "testbot", "Test User"))
    assert lang == "uz"
    assert asyncio.run(get_language(999999)) == "uz"
    info = asyncio.run(search_user(999999))
    assert info is not None
    assert info["full_name"] == "Test User"
    dl_id = asyncio.run(log_download(999999, "testbot", "https://instagram.com/p/test", "Instagram"))
    asyncio.run(update_download_status(dl_id, "completed"))
    users, downloads = asyncio.run(statistics())
    assert users >= 1 and downloads >= 1
    today = asyncio.run(today_active_users())
    assert today >= 1
    count = asyncio.run(user_download_count_since(999999, 60))
    assert count >= 1
    print(f"database: all checks passed (users={users}, downloads={downloads}, today={today})")

    # ── config ────────────────────────────────────────────────────────
    from config import MAX_BYTES, MAX_UPLOAD_MB, RATE_LIMIT_DOWNLOADS
    assert MAX_BYTES == MAX_UPLOAD_MB * 1024 * 1024
    assert RATE_LIMIT_DOWNLOADS == 5
    print("config: validation checks passed")

    # ── main imports ──────────────────────────────────────────────────
    from main import router, web_app, AdminFlow
    print(f"main: imports OK, states: {[s.state for s in AdminFlow.__all_states__]}")

    print("\n=== ALL CHECKS PASSED ===")

if __name__ == "__main__":
    run_tests()
