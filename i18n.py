"""Uzbek / Russian localization strings."""
from config import MAX_UPLOAD_MB

TEXT: dict[str, dict[str, str]] = {
    "uz": {
        "welcome": (
            "Instagram yoki TikTok havolasini yuboring. "
            "Eng yaxshi mavjud sifatda yuklab beraman.\n\n"
            "ℹ️ Yuklash faoliyati admin paneli uchun saqlanadi."
        ),
        "choose": "Tilni tanlang / Выберите язык:",
        "selected": "Til tanlandi: O'zbekcha 🇺🇿",
        "working": "⏳ Media yuklanmoqda, kuting…",
        "bad": (
            "Havola noto'g'ri yoki Instagram/TikTok havolasi emas. "
            "To'liq URL yuboring."
        ),
        "fail": (
            "Media olinmadi. Havola ochiq va ishlashini tekshiring; "
            "story/yopiq post uchun cookies kerak bo'lishi mumkin."
        ),
        "large": f"Fayl Telegram uchun juda katta (limit: {MAX_UPLOAD_MB} MB).",
        "error": "Yuborishda xatolik yuz berdi. Boshqa havolani sinab ko'ring.",
        "help": (
            "Instagram (Reels, post, story) yoki TikTok (video, slideshow) "
            "URL manzilini yuboring.\n\n"
            "ℹ️ Yuklash tarixi admin panelda ko'rinadi."
        ),
        "admin": "Admin panel",
        "stats": "📊 Statistika",
        "recent": "📥 So'nggi yuklashlar",
        "broadcast": "📢 Xabar yuborish",
        "search": "🔍 Qidirish",
        "users": "Foydalanuvchilar",
        "downloads": "Yuklashlar",
        "today_active": "Bugungi faollar",
        "empty": "Hozircha yuklashlar yo'q.",
        "broadcast_prompt": (
            "Barcha foydalanuvchilarga yuboriladigan matn, rasm yoki "
            "videoni yuboring. Bekor qilish: /cancel"
        ),
        "cancelled": "Bekor qilindi.",
        "broadcast_done": "Xabar yuborildi: {sent}; xato: {failed}.",
        "not_admin": "Bu buyruq faqat adminlar uchun.",
        "rate_limited": "Juda ko'p so'rov. Biroz kuting.",
        "search_prompt": "Foydalanuvchi Telegram IDsini yuboring:",
        "search_result": (
            "👤 {full_name}\n"
            "🆔 {user_id}\n"
            "📛 @{username}\n"
            "📥 Yuklashlar: {download_count}\n"
            "📅 Qo'shilgan: {joined_at}\n"
            "📊 Holat: {status}"
        ),
        "search_not_found": "Foydalanuvchi topilmadi.",
        "story_note": (
            "⚠️ Storylarni faqat username orqali yuklab bo'lmaydi. "
            "Faqat to'g'ridan-to'g'ri story havolasi ishlaydi."
        ),
        "downloading": "Yuklanmoqda",
        "user_blocked": "Siz bloklangansiz. Botdan foydalana olmaysiz.",
    },
    "ru": {
        "welcome": (
            "Отправьте ссылку Instagram или TikTok. "
            "Скачаю в наилучшем доступном качестве.\n\n"
            "ℹ️ История загрузок сохраняется для панели администратора."
        ),
        "choose": "Tilni tanlang / Выберите язык:",
        "selected": "Выбран язык: Русский 🇷🇺",
        "working": "⏳ Загружаю медиа, подождите…",
        "bad": (
            "Неверная ссылка или это не Instagram/TikTok. "
            "Отправьте полный URL."
        ),
        "fail": (
            "Не удалось получить медиа. Проверьте ссылку; "
            "для stories/закрытого поста могут понадобиться cookies."
        ),
        "large": f"Файл слишком большой для Telegram (лимит: {MAX_UPLOAD_MB} МБ).",
        "error": "Ошибка отправки. Попробуйте другую ссылку.",
        "help": (
            "Отправьте URL Instagram (Reels, пост, story) или "
            "TikTok (видео, слайд-шоу).\n\n"
            "ℹ️ Активность загрузок видна в панели администратора."
        ),
        "admin": "Панель администратора",
        "stats": "📊 Статистика",
        "recent": "📥 Последние загрузки",
        "broadcast": "📢 Рассылка",
        "search": "🔍 Поиск",
        "users": "Пользователи",
        "downloads": "Загрузки",
        "today_active": "Активные сегодня",
        "empty": "Загрузок пока нет.",
        "broadcast_prompt": (
            "Отправьте текст, фото или видео для рассылки всем "
            "пользователям. Отмена: /cancel"
        ),
        "cancelled": "Отменено.",
        "broadcast_done": "Отправлено: {sent}; ошибок: {failed}.",
        "not_admin": "Команда доступна только администраторам.",
        "rate_limited": "Слишком много запросов. Подождите немного.",
        "search_prompt": "Отправьте Telegram ID пользователя:",
        "search_result": (
            "👤 {full_name}\n"
            "🆔 {user_id}\n"
            "📛 @{username}\n"
            "📥 Загрузки: {download_count}\n"
            "📅 Присоединился: {joined_at}\n"
            "📊 Статус: {status}"
        ),
        "search_not_found": "Пользователь не найден.",
        "story_note": (
            "⚠️ Stories нельзя скачать только по имени пользователя. "
            "Работает только прямая ссылка на story."
        ),
        "downloading": "Загрузка",
        "user_blocked": "Вы заблокированы. Использование бота невозможно.",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Return a localized string, formatted with *kwargs* if provided.

    Falls back to Uzbek when *lang* is unknown, and to the raw key name
    when the key itself is missing from the dictionary.
    """
    strings = TEXT.get(lang, TEXT["uz"])
    template = strings.get(key, TEXT["uz"].get(key, key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
