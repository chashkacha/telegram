import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import ALLOWED_USERS, MEDIA_LABELS
from utils.downloader import download_message, download_story, send_media
from utils.parser import ParsedLink, extract_links, parse_link
from utils.queue_manager import download_queue
from utils.ytdlp_downloader import detect_platform, download_external, is_external_link

logger = logging.getLogger(__name__)
BOT_COMMANDS = ["start", "help", "stats", "stop"]


# ── Filtr ──────────────────────────────────────────────────────────────────────

def allowed():
    return filters.user(ALLOWED_USERS) & filters.private


# ── Klaviaturalar ──────────────────────────────────────────────────────────────

def _home_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📖 Yordam"), KeyboardButton("📊 Statistika")],
            [KeyboardButton("🧹 Navbatni tozala"), KeyboardButton("🛑 To'xtat")],
        ],
        resize_keyboard=True,
    )


def _ext_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 HD (eng yuqori)", callback_data=f"eq|best|{url}")],
        [
            InlineKeyboardButton("📺 720p", callback_data=f"eq|720|{url}"),
            InlineKeyboardButton("📱 480p", callback_data=f"eq|480|{url}"),
        ],
        [InlineKeyboardButton("🎵 Faqat audio (MP3)", callback_data=f"eq|audio|{url}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
    ])


def _tg_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video", callback_data=f"tq|video|{url}")],
        [InlineKeyboardButton("🎵 Faqat audio (MP3)", callback_data=f"tq|audio|{url}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
    ])


# ── Buyruqlar ──────────────────────────────────────────────────────────────────

def register_start(bot: Client):
    @bot.on_message(allowed() & filters.command("start"))
    async def cmd_start(_, msg: Message):
        await msg.reply(
            "<b>🤖 Universal Media Yuklovchi</b>\n\n"
            "📌 <b>Telegram:</b> private/public kanal, istoriya\n"
            "▶️ <b>YouTube:</b> HD, 720p, 480p yoki audio\n"
            "📸 <b>Instagram:</b> (cookie talab qilinadi)\n"
            "🎵 <b>TikTok, Twitter, VK va boshqalar</b>\n\n"
            "Havola yuboring — sifat tanlang, yuklab beraman!\n\n"
            "📖 /help | 📊 /stats | 🛑 /stop",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_help(bot: Client):
    @bot.on_message(allowed() & filters.command("help"))
    async def cmd_help(_, msg: Message):
        await msg.reply(
            "<b>📖 Foydalanish yo'riqnomasi</b>\n\n"
            "<b>Tashqi platformalar (YouTube, TikTok...):</b>\n"
            "Havola → HD / 720p / 480p / Audio\n\n"
            "<b>Telegram havolalari:</b>\n"
            "Havola → Video yoki Audio\n"
            "<code>https://t.me/c/1234567890/293</code> — private\n"
            "<code>https://t.me/kanal/100</code> — public\n"
            "<code>https://t.me/user/s/5</code> — istoriya\n"
            "<code>https://t.me/c/123/456/789</code> — thread xabar\n\n"
            "<b>Katta fayllar:</b> 50MB+ user-account orqali ✅ (2GB gacha)\n\n"
            "<b>Instagram:</b> <code>INSTAGRAM_COOKIES</code> kerak\n"
            "<b>YouTube cookie:</b> <code>YOUTUBE_COOKIES</code> (ixtiyoriy)\n\n"
            "<b>To'xtatish:</b> /stop yoki 🛑 To'xtat tugmasi",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_stats(bot: Client):
    @bot.on_message(allowed() & filters.command("stats"))
    async def cmd_stats(_, msg: Message):
        user_id = msg.from_user.id
        s = download_queue.stats.get(user_id, {"done": 0, "failed": 0})
        q = download_queue.queue_size(user_id)
        await msg.reply(
            f"<b>📊 Statistika</b>\n\n"
            f"✅ Muvaffaqiyatli: <b>{s.get('done', 0)}</b>\n"
            f"❌ Xatolik: <b>{s.get('failed', 0)}</b>\n"
            f"⏳ Navbatda: <b>{q}</b>",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


def register_stop(bot: Client):
    @bot.on_message(allowed() & (filters.command("stop") | filters.regex(r"^🛑 To'xtat$")))
    async def cmd_stop(_, msg: Message):
        user_id = msg.from_user.id
        result  = await download_queue.stop_all(user_id)
        parts   = []
        if result["cancelled"]:
            parts.append("🛑 Joriy yuklanish to'xtatildi")
        if result["removed"]:
            parts.append(f"🧹 Navbatdan {result['removed']} ta vazifa o'chirildi")
        if not parts:
            parts.append("ℹ️ Hozir hech narsa yuklanmayapti")
        await msg.reply("\n".join(parts), reply_markup=_home_kb())


def register_quick_actions(bot: Client):
    @bot.on_message(allowed() & filters.regex(r"^📖 Yordam$"))
    async def help_btn(_, msg: Message):
        await msg.reply(
            "<b>📖 Foydalanish yo'riqnomasi</b>\n\n"
            "Havola yuboring → sifat tanlang → yuklab beraman!\n\n"
            "🔗 Qo'llab-quvvatlanadigan: YouTube, TikTok, Twitter, "
            "Instagram (cookie kerak), Telegram.",
            parse_mode="html",
            reply_markup=_home_kb(),
        )

    @bot.on_message(allowed() & filters.regex(r"^📊 Statistika$"))
    async def stats_btn(_, msg: Message):
        user_id = msg.from_user.id
        s = download_queue.stats.get(user_id, {"done": 0, "failed": 0})
        q = download_queue.queue_size(user_id)
        await msg.reply(
            f"<b>📊 Statistika</b>\n\n"
            f"✅ Muvaffaqiyatli: <b>{s.get('done', 0)}</b>\n"
            f"❌ Xatolik: <b>{s.get('failed', 0)}</b>\n"
            f"⏳ Navbatda: <b>{q}</b>",
            parse_mode="html",
            reply_markup=_home_kb(),
        )

    @bot.on_message(allowed() & filters.regex(r"^🧹 Navbatni tozala$"))
    async def clear_btn(_, msg: Message):
        removed = await download_queue.clear_user_queue(msg.from_user.id)
        await msg.reply(
            f"🧹 Navbat tozalandi: <b>{removed}</b> ta vazifa o'chirildi",
            parse_mode="html",
            reply_markup=_home_kb(),
        )


# ── Asosiy handler ─────────────────────────────────────────────────────────────

def register_link_handler(bot: Client, user: Client):

    @bot.on_message(allowed() & filters.text & ~filters.command(BOT_COMMANDS)
                    & ~filters.regex(r"^(📖 Yordam|📊 Statistika|🧹 Navbatni tozala|🛑 To'xtat)$"))
    async def handle_text(_, msg: Message):
        text = msg.text.strip()

        # Tashqi platforma (YouTube, TikTok, ...)
        if is_external_link(text):
            platform = detect_platform(text)
            await msg.reply(
                f"{platform} havolasi qabul qilindi.\n<b>Qanday yuklab olmoqchisiz?</b>",
                parse_mode="html",
                reply_markup=_ext_keyboard(text),
            )
            return

        # Telegram havolasi
        links = extract_links(text)
        if not links:
            await msg.reply(
                "❓ Havola topilmadi.\n\n"
                "<b>Misol:</b>\n"
                "<code>https://t.me/c/1234567890/293</code>\n"
                "<code>https://youtube.com/watch?v=...</code>",
                parse_mode="html",
            )
            return

        for link in links:
            parsed = parse_link(link)
            if not parsed:
                await msg.reply(f"❌ Noto'g'ri havola:\n<code>{link}</code>", parse_mode="html")
                continue
            await msg.reply(
                "📥 Telegram havolasi qabul qilindi.\n<b>Qanday yuklab olmoqchisiz?</b>",
                parse_mode="html",
                reply_markup=_tg_keyboard(link),
            )

    @bot.on_callback_query(filters.user(ALLOWED_USERS))
    async def handle_callback(_, cb: CallbackQuery):
        data = cb.data or ""

        # Bekor qilish
        if data == "cancel":
            await cb.message.edit_text("❌ Bekor qilindi.")
            await cb.answer("Bekor qilindi")
            return

        # Tashqi (YouTube, Instagram, ...)
        if data.startswith("eq|"):
            _, quality, url = data.split("|", 2)
            label    = {"best": "HD", "720": "720p", "480": "480p", "audio": "🎵 Audio"}.get(quality, quality)
            platform = detect_platform(url)
            await cb.message.edit_text(
                f"{platform} — <b>{label}</b> navbatga qo'shildi ⏳",
                parse_mode="html",
            )
            await cb.answer()
            await _enqueue_external(user, cb.message, url, quality)
            return

        # Telegram
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

async def _enqueue_tg(user: Client, msg: Message, parsed: ParsedLink,
                      link: str, audio_only: bool = False):
    q = download_queue.queue_size(msg.from_user.id)
    if q > 0:
        await msg.reply(f"⏳ Navbatda <b>{q + 1}</b>-o'rinda", parse_mode="html")

    async def task():
        await _process_tg(user, msg, parsed, link, audio_only)

    await download_queue.add(msg.from_user.id, task)


async def _enqueue_external(user: Client, msg: Message, url: str, quality: str):
    q = download_queue.queue_size(msg.from_user.id)
    if q > 0:
        await msg.reply(f"⏳ Navbatda <b>{q + 1}</b>-o'rinda", parse_mode="html")

    async def task():
        await _process_external(user, msg, url, quality)

    await download_queue.add(msg.from_user.id, task)


# ── Yuklovchilar ───────────────────────────────────────────────────────────────

async def _process_tg(user: Client, bot_msg: Message, parsed: ParsedLink,
                      link: str, audio_only: bool = False):
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
            await status.edit(f"📝 <b>Xabar matni:</b>\n\n{file_path}", parse_mode="html")
            return
        if mtype == "empty":
            await status.edit("❌ Xabar bo'sh.")
            return

        if audio_only and mtype == "video":
            mtype = "audio"

        await status.edit("📤 Yuborilmoqda...")
        await send_media(
            bot_msg, user, file_path, mtype,
            caption=f"{MEDIA_LABELS.get(mtype, '📁')} | {link}"
        )
        file_path = None
        await status.delete()

    except Exception as e:
        await _handle_error(status, str(e))
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except Exception:
                pass


async def _process_external(user: Client, bot_msg: Message, url: str, quality: str):
    platform  = detect_platform(url)
    label     = {"best": "HD", "720": "720p", "480": "480p", "audio": "Audio"}.get(quality, quality)
    status    = await bot_msg.reply(f"⏳ {platform} ({label}) yuklanmoqda...")
    file_path = None
    try:
        file_path, mtype = await download_external(url, status, quality)
        if not file_path:
            await status.edit("❌ Video topilmadi.")
            return

        await status.edit("📤 Yuborilmoqda...")
        await send_media(
            bot_msg, user, file_path, mtype,
            caption=f"{platform} | {label} | {url[:60]}"
        )
        file_path = None
        await status.delete()

    except Exception as e:
        await _handle_error(status, str(e))
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except Exception:
                pass


async def _handle_error(status_msg: Message, err: str):
    hints = {
        "PEER_ID_INVALID":    "Kanal topilmadi. User sessiya kanalga a'zo emasmi?",
        "CHAT_RESTRICTED":    "Bu kanaldan yuklab olish taqiqlangan.",
        "MESSAGE_ID_INVALID": "Xabar topilmadi yoki o'chirilgan.",
        "FLOOD_WAIT":         "Telegram cheklovi — biroz kuting va qayta urinib ko'ring.",
        "STORY_ID_INVALID":   "Istoriya topilmadi yoki muddati o'tgan.",
        "Private video":      "Bu video yopiq (private).",
        "Instagram yuklab":   err,   # to'liq xabar
        "YouTube bot-detection": err,
        "cookie":             err,
    }
    hint = next((v for k, v in hints.items() if k in err), err[:300])
    try:
        await status_msg.edit(
            f"❌ <b>Xatolik:</b>\n<code>{hint}</code>",
            parse_mode="html",
        )
    except Exception:
        pass


# ── Registratsiya ──────────────────────────────────────────────────────────────

def register_all(bot: Client, user: Client):
    register_start(bot)
    register_help(bot)
    register_stats(bot)
    register_stop(bot)
    register_quick_actions(bot)
    register_link_handler(bot, user)
