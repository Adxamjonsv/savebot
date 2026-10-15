# Savebot

Telegram media downloader for Instagram and TikTok using aiogram 3, yt-dlp, and SQLite.

## Project Structure

```
savebot/
├── main.py           # Bot handlers, admin panel, FastAPI web server
├── config.py         # Environment variables and validation
├── i18n.py           # Uzbek / Russian localization strings
├── database.py       # aiosqlite persistence (users, downloads, media)
├── downloader.py     # yt-dlp media downloading with retry
├── middleware.py     # Anti-spam, rate-limit, user-status middleware
├── start.py          # Interactive launcher (installs deps, asks for config)
├── webapp/
│   └── index.html    # Telegram Mini App admin dashboard
├── requirements.txt
├── .env.example
├── .gitignore
└── railway.toml
```

## Setup (Windows PowerShell)

1. Install Python 3.10+ and FFmpeg. Add FFmpeg to `PATH` so yt-dlp can merge the best video and audio streams.
2. Open PowerShell in this folder and install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Create the Telegram bot with [@BotFather](https://t.me/BotFather). Copy `.env.example` to `.env` and fill in your values:

   ```powershell
   copy .env.example .env
   # Edit .env with your values:
   # BOT_TOKEN=your_bot_token_here
   # ADMIN_IDS=123456789,987654321
   ```

   Or set environment variables directly:

   ```powershell
   $env:BOT_TOKEN = "YOUR_NEW_TELEGRAM_BOT_TOKEN"
   $env:ADMIN_IDS = "123456789,987654321"
   ```

   Get your numeric ID from a trusted Telegram ID lookup bot. Keep the token private. If it has ever been exposed, revoke it through BotFather and use a newly generated token.

4. Optional: provide a yt-dlp Netscape-format cookies file for content that requires a logged-in session:

   ```powershell
   $env:YTDLP_COOKIES_FILE = "C:\path\to\cookies.txt"
   ```

5. Start the bot:

   ```powershell
   python start.py
   ```

   Or run directly if environment variables are already set:

   ```powershell
   python main.py
   ```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | BotFather bot token |
| `ADMIN_IDS` | Recommended | — | Comma-separated admin Telegram IDs |
| `WEBAPP_URL` | Optional | — | Public HTTPS URL for Mini App |
| `DATA_DIR` | Optional | Project dir | Directory for database and media |
| `MAX_UPLOAD_MB` | Optional | `49` | Max file size for Telegram upload |
| `MAX_MEDIA_ITEMS` | Optional | `10` | Max items per carousel/slideshow |
| `YTDLP_COOKIES_FILE` | Optional | — | Path to Netscape cookies file |
| `RATE_LIMIT_DOWNLOADS` | Optional | `5` | Max downloads per user per window |
| `RATE_LIMIT_WINDOW` | Optional | `60` | Rate limit window in seconds |
| `MEDIA_RETENTION_DAYS` | Optional | `7` | Days to keep archived media |
| `LOG_RETENTION_DAYS` | Optional | `90` | Days to keep download log records |

## Features

### User Interface
- Bilingual interface: Uzbek 🇺🇿 and Russian 🇷🇺 with language selection on `/start`
- Language preference saved per user
- Localized error messages and help text

### Media Downloads
- Instagram: posts, Reels, stories (with direct link), carousels
- TikTok: videos, slideshows
- Best available quality via yt-dlp, no re-encoding when possible
- Photos sent as photos, videos as videos
- Automatic retry with exponential backoff
- File size and resolution metadata tracked

### Admin Panel
- `/admin` command with inline keyboard dashboard
- Statistics: total users, downloads, today's active users
- Latest 20 download records with user and platform info
- Search user by Telegram ID
- Broadcast text, photos, or videos to all active users
- Telegram Mini App dashboard (when WEBAPP_URL is configured)
- All admin actions restricted to ADMIN_IDS

### Security
- Anti-spam middleware (5 messages per 10 seconds)
- Per-user download rate limiting (configurable)
- User blocking capability
- Telegram Mini App initData validation (HMAC-SHA256)
- No secrets in source code or logs
- Parameterized SQL queries throughout

### Database
- SQLite with aiosqlite (async)
- Automatic schema migration for upgrades
- Download history with metadata (file size, resolution, media type)
- Configurable log and media retention
- Activity logging disclosed to users

## Admin Mini App

The bot also starts a small web server on port `8000`. Telegram Mini Apps require a public HTTPS address, so localhost alone will not open inside Telegram. Publish or securely tunnel port 8000, then set `WEBAPP_URL` to the resulting public `https://...` address. `/admin` will show an **Admin Mini App** button. The dashboard validates Telegram's signed launch data and checks `ADMIN_IDS`; it lists every registered user by name, and selecting a user shows their downloaded videos/photos inline plus the source link they submitted. These details are available only to authorized admins; the app does not expose a public media URL.

Each supported link is recorded as soon as downloading starts; the dashboard shows status (downloading, completed, or failed). New media is kept in `media_archive` for the configured retention period (default 7 days) so it can be previewed in the Mini App, then the files are deleted automatically while history records remain. Existing SQLite databases are migrated automatically.

## Railway Deployment

This repository includes `railway.toml`: Railway builds from `requirements.txt`, starts with `python main.py`, and checks `/health`. Do not use `python start.py` as the Railway start command because it waits for interactive input.

1. Push this project to a GitHub repository and connect that repository to a Railway service.
2. In the Railway service's **Variables**, add `BOT_TOKEN` (a fresh BotFather token) and `ADMIN_IDS` (your numeric Telegram user ID). Do not create variables whose names are token or ID numbers. This bot does not require `TELEGRAM_API_ID` or `TELEGRAM_API_HASH`.
3. Add a Railway Volume mounted at `/data`, then set `DATA_DIR=/data` so the SQLite user/download history and media archive survive redeployments.
4. In **Settings → Networking**, create a public domain. Set `WEBAPP_URL` to that `https://` domain so `/admin` includes the Mini App button.
5. Redeploy. Railway supplies `PORT`; the app reads it automatically. Official guidance: [Railway start command](https://docs.railway.com/deployments/start-command), [Railway configuration](https://docs.railway.com/config-as-code).

If the build still reports `secret <number> not found`, inspect the service's Variables and build configuration for a secret reference using that number as its name. Correct or remove that reference; do not use the numeric Telegram ID as a secret name. Keep each Telegram bot on its own Railway service with its own bot token.

## Known Limitations

- **Telegram file size limit**: Files over 49 MB cannot be sent via the Bot API (50 MB hard limit minus safety margin).
- **Private content**: Private accounts, expired stories, and login-gated content require a valid cookies file. The bot does not bypass access controls.
- **Stories by username**: Stories cannot be downloaded by username alone. Only direct story links work when accessible.
- **Platform changes**: Instagram and TikTok may change their APIs or add protections at any time, which can break yt-dlp extraction temporarily until yt-dlp releases an update.
- **Rate limits**: Both platforms enforce rate limits. The bot uses sensible delays but heavy usage from a single IP may trigger blocks.
- **FFmpeg**: Without FFmpeg, the bot falls back to single-file formats which may have lower quality.
