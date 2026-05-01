import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

from config import ALLOWED_USERS, MEDIA_LABELS
from utils.downloader import download_message, download_story, send_media
from utils.parser import ParsedLink, extract_links, parse_link
from utils.queue_manager import download_queue
from utils.ytdlp_downloader import detect_platform, download_external, is_external_link

logger = logging.getLogger(__name__)

BUTTON_TEXTS = {"📖 Yordam", "📊 Statistika", "🧹 Navbatni tozala", "🛑 Toxtat"}
BOT_COMMANDS = ["start", "help", "stats", "stop"]


# ── Filtr ──────────────────────────────────────────────────────────────────────

def allowed():
    """ALLOWED_USERS bo'sh bo'lsa — barcha private chat."""
    if ALLOWED_USERS:
        return filters.user(ALLOWED_USERS) & filters.private
    return filters.private


def cb_filter():
    """Callback query filtri."""
    if ALLOWED_USERS:
        return filters.user(ALLOWED_USERS)
    return filters.all


# ── Klaviaturalar ──────────────────────────────────────────────────────────────

def _home_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("📖 Yordam"),          KeyboardButton("📊 Statistika")],
        [KeyboardButton("🧹 Navbatni tozala"), KeyboardButton("🛑 Toxtat")],
    ], resize_keyboard=True)


def _ext_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Eng yaxshi sifat",  callback_data=f"eq|best|{url}")],
        [
            InlineKeyboardButton("🖥 1080p", callback_data=f"eq|1080|{url}"),
            InlineKeyboardButton("📺 720p",  callback_data=f"eq|720|{url}"),
            InlineKeyboardButton("📱 480p",  callback_data=f"eq|480|{url}"),
        ],
        [InlineKeyboardButton("🎵 Faqat audio (MP3)", callback_data=f"eq|audio|{url}")],
        [InlineKeyboardButton("❌ Bekor",              callback_data="cancel")],
    ])


def _tg_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video",              callback_data=f"tq|video|{url}")],
        [InlineKeyboardButton("🎵 Faqat audio (MP3)", callback_data=f"tq|audio|{url}")],
        [InlineKeyboardButton("❌ Bekor",              callback_data="cancel")],
    ])


# ── Buyruqlar ──────────────────────────────────────────────────────────────────

def register_start(bot: Client):
    @bot.on_message(allowed() & filters.command("start"))
    async def _(__, msg: Message):
        await msg.reply(
            "<b>🤖 Universal Media Yuklovchi</b>\n\n"
            "📌 Telegram kanal / guruh / istoriya\n"
            "▶️ YouTube — 1080p / 720p / 480p / Audio\n"
            "🎵 TikTok · Twitter/X · VK · Vimeo ...\n"
            "📸 Instagram (cookie kerak)\n\n"
            "Havola yuboring → sifat tanlang!\n\n"
            "/help  /stats  /stop",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_help(bot: Client):
    @bot.on_message(allowed() & filters.command("help"))
    async def _(__, msg: Message):
        await msg.reply(
            "<b>📖 Foydalanish</b>\n\n"
            "<b>Tashqi platformalar:</b>\n"
            "Havola yuboring → ⚡ Best / 1080p / 720p / 480p / 🎵 Audio\n\n"
            "<b>Telegram havolalari:</b>\n"
            "<code>https://t.me/kanal/100</code> — public\n"
            "<code>https://t.me/c/1234567/293</code> — private\n"
            "<code>https://t.me/c/123/456/789</code> — thread xabar\n"
            "<code>https://t.me/user/s/5</code> — istoriya\n\n"
            "<b>Katta fayllar (50MB+):</b> user sessiya orqali 2GB gacha ✅\n\n"
            "<b>Instagram:</b> Railway → <code>INSTAGRAM_COOKIES</code>\n"
            "<b>YouTube:</b> Railway → <code>YOUTUBE_COOKIES</code> (ixtiyoriy)\n\n"
            "<b>To'xtatish:</b> /stop yoki 🛑 Toxtat tugmasi",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_stats(bot: Client):
    @bot.on_message(allowed() & filters.command("stats"))
    async def _(__, msg: Message):
        uid = msg.from_user.id
        s   = download_queue.stats.get(uid, {"done": 0, "failed": 0})
        q   = download_queue.queue_size(uid)
        await msg.reply(
            f"<b>📊 Statistika</b>\n\n"
            f"✅ Muvaffaqiyatli: <b>{s.get('done', 0)}</b>\n"
            f"❌ Xatolik:        <b>{s.get('failed', 0)}</b>\n"
            f"⏳ Navbatda:       <b>{q}</b>",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_stop(bot: Client):
    @bot.on_message(allowed() & filters.command("stop"))
    async def _(__, msg: Message):
        await _do_stop(msg)

    @bot.on_message(allowed() & filters.text & filters.regex(r"^🛑 Toxtat$"))
    async def __(__, msg: Message):
        await _do_stop(msg)


async def _do_stop(msg: Message):
    r     = await download_queue.stop_all(msg.from_user.id)
    parts = []
    if r["cancelled"]:
        parts.append("🛑 Joriy yuklanish to'xtatildi")
    if r["removed"]:
        parts.append(f"🧹 Navbatdan {r['removed']} ta vazifa o'chirildi")
    if not parts:
        parts.append("ℹ️ Hozir hech narsa yuklanmayapti")
    await msg.reply("\n".join(parts), reply_markup=_home_kb())


def register_quick_actions(bot: Client):
    @bot.on_message(allowed() & filters.text & filters.regex(r"^📖 Yordam$"))
    async def _(__, msg: Message):
        await msg.reply(
            "Havola yuboring → sifat tanlang → yuklab beraman!\n\n"
            "▶️ YouTube · 🎵 TikTok · 🐦 Twitter · 📸 Instagram · 📌 Telegram",
            reply_markup=_home_kb(),
        )

    @bot.on_message(allowed() & filters.text & filters.regex(r"^📊 Statistika$"))
    async def __(__, msg: Message):
        uid = msg.from_user.id
        s   = download_queue.stats.get(uid, {"done": 0, "failed": 0})
        q   = download_queue.queue_size(uid)
        await msg.reply(
            f"<b>📊 Statistika</b>\n\n"
            f"✅ Muvaffaqiyatli: <b>{s.get('done', 0)}</b>\n"
            f"❌ Xatolik:        <b>{s.get('failed', 0)}</b>\n"
            f"⏳ Navbatda:       <b>{q}</b>",
            parse_mode="html",
            reply_markup=_home_kb(),
        )

    @bot.on_message(allowed() & filters.text & filters.regex(r"^🧹 Navbatni tozala$"))
    async def ___(__, msg: Message):
        removed = await download_queue.clear_user_queue(msg.from_user.id)
        await msg.reply(
            f"🧹 Navbat tozalandi: <b>{removed}</b> ta o'chirildi",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


# ── Asosiy link handler ────────────────────────────────────────────────────────

def register_link_handler(bot: Client, user: Client):

    @bot.on_message(allowed() & filters.text & ~filters.command(BOT_COMMANDS))
    async def handle_text(__, msg: Message):
        text = msg.text.strip()

        # Tugma textlari — e'tibor bermaslik
        if text in BUTTON_TEXTS:
            return

        # Tashqi platforma (YouTube, TikTok, ...)
        if is_external_link(text):
            platform = detect_platform(text)
            await msg.reply(
                f"{platform}\n<b>Sifat tanlang:</b>",
                parse_mode="html",
                reply_markup=_ext_keyboard(text),
            )
            return

        # Telegram havolalari
        links = extract_links(text)
        if links:
            for link in links:
                parsed = parse_link(link)
                if not parsed:
                    await msg.reply(
                        f"❌ Noto'g'ri havola:\n<code>{link}</code>",
                        parse_mode="html",
                    )
                    continue
                await msg.reply(
                    "📥 Telegram havolasi\n<b>Qanday yuklab olmoqchisiz?</b>",
                    parse_mode="html",
                    reply_markup=_tg_keyboard(link),
                )
            return

        # Havola topilmadi
        await msg.reply(
            "❓ Havola topilmadi.\n\n"
            "<b>Misol:</b>\n"
            "<code>https://youtube.com/watch?v=...</code>\n"
            "<code>https://t.me/kanal/100</code>",
            parse_mode="html",
        )

    @bot.on_callback_query(cb_filter())
    async def handle_callback(__, cb: CallbackQuery):
        data = cb.data or ""

        if data == "cancel":
            await cb.message.edit_text("❌ Bekor qilindi.")
            await cb.answer("Bekor qilindi")
            return

        if data.startswith("eq|"):
            _, quality, url = data.split("|", 2)
            labels   = {"best": "⚡ Best", "1080": "1080p", "720": "720p",
                        "480": "480p", "audio": "🎵 Audio"}
            platform = detect_platform(url)
            await cb.message.edit_text(
                f"{platform} — <b>{labels.get(quality, quality)}</b> navbatga qo'shildi ⏳",
                parse_mode="html",
            )
            await cb.answer()
            await _enqueue_ext(user, cb.message, url, quality)
            return

        if data.startswith("tq|"):
            _, mode, url = data.split("|", 2)
            label = "🎬 Video" if mode == "video" else "🎵 Audio"
            await cb.message.edit_text(
                f"📥 Telegram — <b>{label}</b> navbatga qo'shildi ⏳",
                parse_mode="html",
            )
            await cb.answer()
            parsed = parse_link(url)
            if not parsed:
                await cb.message.edit_text("❌ Noto'g'ri havola.")
                return
            await _enqueue_tg(user, cb.message, parsed, url, audio_only=(mode == "audio"))
            return

        await cb.answer()


# ── Navbat yordamchilari ───────────────────────────────────────────────────────

async def _enqueue_tg(user, msg, parsed, link, audio_only=False):
    q = download_queue.queue_size(msg.from_user.id)
    if q > 0:
        await msg.reply(f"⏳ Navbatda <b>{q + 1}</b>-o'rinda", parse_mode="html")

    async def task():
        await _process_tg(user, msg, parsed, link, audio_only)

    await download_queue.add(msg.from_user.id, task)


async def _enqueue_ext(user, msg, url, quality):
    q = download_queue.queue_size(msg.from_user.id)
    if q > 0:
        await msg.reply(f"⏳ Navbatda <b>{q + 1}</b>-o'rinda", parse_mode="html")

    async def task():
        await _process_ext(user, msg, url, quality)

    await download_queue.add(msg.from_user.id, task)


# ── Yuklovchilar ───────────────────────────────────────────────────────────────

async def _process_tg(user, bot_msg, parsed, link, audio_only=False):
    status    = await bot_msg.reply("⏳ Tekshirilmoqda...")
    file_path = None
    try:
        if parsed.kind == "story":
            file_path, mtype = await download_story(
                user, str(parsed.peer), parsed.story_id, status
            )
        else:
            file_path, mtype = await download_message(
                user, parsed.peer, parsed.msg_id, status
            )

        if file_path is None:
            await status.edit("❌ Media topilmadi.")
            return
        if mtype == "text":
            await status.edit(f"📝 <b>Xabar:</b>\n\n{file_path}", parse_mode="html")
            return
        if mtype == "empty":
            await status.edit("❌ Xabar bo'sh.")
            return

        if audio_only and mtype == "video":
            mtype = "audio"

        await status.edit("📤 Yuborilmoqda...")
        await send_media(bot_msg, user, file_path, mtype,
                         caption=f"{MEDIA_LABELS.get(mtype, '📁')} | {link}")
        file_path = None
        await status.delete()

    except Exception as e:
        await _show_error(status, str(e))
    finally:
        _safe_rm(file_path)


async def _process_ext(user, bot_msg, url, quality):
    labels   = {"best": "⚡ Best", "1080": "1080p", "720": "720p",
                "480": "480p", "audio": "🎵 Audio"}
    platform = detect_platform(url)
    status   = await bot_msg.reply(
        f"⏳ {platform} ({labels.get(quality, quality)}) yuklanmoqda..."
    )
    file_path = None
    try:
        file_path, mtype = await download_external(url, status, quality)
        if not file_path:
            await status.edit("❌ Video topilmadi.")
            return
        await status.edit("📤 Yuborilmoqda...")
        await send_media(bot_msg, user, file_path, mtype,
                         caption=f"{platform} | {labels.get(quality, quality)} | {url[:60]}")
        file_path = None
        await status.delete()
    except Exception as e:
        await _show_error(status, str(e))
    finally:
        _safe_rm(file_path)


async def _show_error(status_msg: Message, err: str):
    HINTS = {
        "PEER_ID_INVALID":    "Kanal topilmadi. User sessiya kanalga a'zo bo'lishi kerak.",
        "CHAT_RESTRICTED":    "Bu kanaldan yuklab olish taqiqlangan.",
        "MESSAGE_ID_INVALID": "Xabar topilmadi yoki o'chirilgan.",
        "FLOOD_WAIT":         "Telegram cheklovi. Biroz kuting va qayta urinib ko'ring.",
        "STORY_ID_INVALID":   "Istoriya topilmadi yoki muddati o'tgan.",
        "Private video":      "Bu video yopiq (private).",
        "Sign in to confirm": "YouTube: YOUTUBE_COOKIES muhit o'zgaruvchisini sozlang.",
        "cookie":             err,
        "Instagram":          err,
        "HTTP Error 429":     "Juda ko'p so'rov. Biroz kuting.",
        "HTTP Error 403":     "Kirish taqiqlangan (403).",
    }
    err_lower = err.lower()
    hint = next(
        (v for k, v in HINTS.items() if k.lower() in err_lower),
        err[:300]
    )
    try:
        await status_msg.edit(
            f"❌ <b>Xatolik:</b>\n<code>{hint}</code>",
            parse_mode="html",
        )
    except Exception:
        pass


def _safe_rm(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ── Ro'yxatga olish ────────────────────────────────────────────────────────────

def register_all(bot: Client, user: Client):
    register_start(bot)
    register_help(bot)
    register_stats(bot)
    register_stop(bot)
    register_quick_actions(bot)
    register_link_handler(bot, user)
