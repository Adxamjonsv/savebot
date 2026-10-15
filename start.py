"""Install dependencies, ask for configuration when missing, and start the bot."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
REQUIREMENTS = PROJECT_DIR / "requirements.txt"


def main() -> None:
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"requirements.txt not found: {REQUIREMENTS}")
    print("Kerakli kutubxonalar tekshirilmoqda...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(REQUIREMENTS)],
        cwd=PROJECT_DIR,
        check=True,
    )

    # Load .env file if python-dotenv is available and .env exists.
    env_file = PROJECT_DIR / ".env"
    if env_file.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
            print(f".env fayldan sozlamalar yuklandi.")
        except ImportError:
            pass

    # These values apply only to this run. To save them permanently, configure
    # environment variables in the IDE instead of putting secrets in source code.
    if not os.getenv("BOT_TOKEN", "").strip():
        token = input("BotFather bergan yangi bot tokenini kiriting: ").strip()
        if not token:
            raise RuntimeError("Bot tokeni kiritilmadi.")
        os.environ["BOT_TOKEN"] = token
    if not os.getenv("ADMIN_IDS", "").strip():
        admin_ids = input("Admin Telegram raqamli IDsi (ixtiyoriy): ").strip()
        if admin_ids:
            os.environ["ADMIN_IDS"] = admin_ids
    if not os.getenv("WEBAPP_URL", "").strip():
        web_url = input("Mini App tugmasi uchun HTTPS manzil (Mini App ishlashi uchun kerak): ").strip()
        if web_url:
            os.environ["WEBAPP_URL"] = web_url

    sys.path.insert(0, str(PROJECT_DIR))
    from main import main as run_bot
    asyncio.run(run_bot())


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"Kutubxonalarni o'rnatishda xato (kod {error.returncode}).")
        raise SystemExit(error.returncode)
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")
