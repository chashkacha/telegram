import asyncio
import logging
import os
import shutil
import time
from functools import partial
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import (
    ChannelInvalid, ChannelPrivate, ChatRestricted,
    FloodWait, MessageIdInvalid, PeerIdInvalid,
    UserNotParticipant,
)
from pyrogram.types import Message as PyroMsg

from config import AUDIO_OUTPUT_FORMAT, AUDIO_TARGET_BITRATE, AUDIO_TARGET_CODEC, DOWNLOAD_DIR, MAX_BOT_SIZE_MB, MEDIA_LABELS
from utils.progress import fmt_size, progress_callback

logger = logging.getLogger(__name__)


def get_media_and_type(msg) -> tuple:
    for attr in ("video", "photo", "document", "audio",
                 "voice", "video_note", "sticker", "animation"):
        media = getattr(msg, attr, None)
        if media:
            return media, attr
    return None, None


# ── Telegram yuklovchi ────────────────────────────────────────────────────────

async def download_message(user: Client, peer, msg_id: int, status_msg) -> tuple:
    try:
        msg = await user.get_messages(peer, msg_id)
    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        raise Exception(f"PEER_ID_INVALID: {e}")
    except MessageIdInvalid:
        raise Exception("MESSAGE_ID_INVALID")
    except FloodWait as e:
        raise Exception(f"FLOOD_WAIT:{e.value}")

    if not msg or msg.empty:
        return None, "empty"

    media, mtype = get_media_and_type(msg)
    if not media:
        return msg.text or msg.caption or "", "text"

    file_size  = getattr(media, "file_size", 0) or 0
    nice_label = MEDIA_LABELS.get(mtype, "📁 Fayl")
    await status_msg.edit(f"{nice_label} topildi\n📦 {fmt_size(file_size)}\n⬇️ Yuklanmoqda...")

    start_time = time.time()
    cb = partial(progress_callback, status_msg=status_msg,
                 label=f"{nice_label} yuklanmoqda...", start_time=start_time)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = await user.download_media(msg, file_name=f"{DOWNLOAD_DIR}/", progress=cb)
    return file_path, mtype


async def download_story(user: Client, username: str, story_id: int, status_msg) -> tuple:
    await status_msg.edit("📖 Istoriya qidirilmoqda...")
    try:
        story = await user.get_stories(username, story_id)
    except Exception as e:
        raise Exception(f"STORY_ID_INVALID: {e}")

    if not story:
        return None, "empty"

    media, mtype = get_media_and_type(story)
    if not media:
        return None, "empty"

    nice_label = MEDIA_LABELS.get(mtype, "📁 Fayl")
    await status_msg.edit(f"{nice_label} (istoriya)\n⬇️ Yuklanmoqda...")

    start_time = time.time()
    cb = partial(progress_callback, status_msg=status_msg,
                 label="📖 Istoriya yuklanmoqda...", start_time=start_time)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = await user.download_media(story, file_name=f"{DOWNLOAD_DIR}/", progress=cb)
    return file_path, mtype


# ── Audio optimizer (ffmpeg mavjud bo'lsa) ───────────────────────────────────

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def compress_audio(source_path: str) -> tuple[str, bool]:
    """(path, o'zgardimi) qaytaradi. ffmpeg yo'q bo'lsa original qaytadi."""
    if not source_path or not os.path.exists(source_path):
        return source_path, False
    if not _ffmpeg_available():
        return source_path, False

    p = Path(source_path)
    out_path = str(p.with_name(f"{p.stem}.opt.{AUDIO_OUTPUT_FORMAT}"))
    cmd = [
        "ffmpeg", "-y", "-i", source_path,
        "-vn", "-c:a", AUDIO_TARGET_CODEC, "-b:a", AUDIO_TARGET_BITRATE,
        "-movflags", "+faststart", out_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.communicate()

    if proc.returncode != 0 or not os.path.exists(out_path):
        if os.path.exists(out_path):
            os.remove(out_path)
        return source_path, False

    src_size = os.path.getsize(source_path)
    out_size = os.path.getsize(out_path)
    if out_size >= src_size:
        os.remove(out_path)
        return source_path, False

    return out_path, True


# ── Yuborish ──────────────────────────────────────────────────────────────────

async def send_media(bot_msg, user: Client, file_path: str, mtype: str, caption: str = ""):
    try:
        # Audio bo'lsa siqishga urinish
        actual_path = file_path
        if mtype == "audio" and _ffmpeg_available():
            compressed, changed = await compress_audio(file_path)
            if changed:
                actual_path = compressed

        size_mb = os.path.getsize(actual_path) / (1024 * 1024)
        user_id = bot_msg.from_user.id

        if size_mb > MAX_BOT_SIZE_MB:
            await _send_large(user, user_id, actual_path, mtype, caption, size_mb)
        else:
            await _send_via_bot(bot_msg, actual_path, mtype, caption)
    finally:
        _cleanup(file_path)
        if "actual_path" in dir() and actual_path != file_path:
            _cleanup(actual_path)


async def _send_via_bot(bot_msg, file_path: str, mtype: str, caption: str):
    kw = {"quote": True}
    if mtype not in ("sticker", "video_note"):
        kw["caption"] = caption

    dispatch = {
        "video":      lambda: bot_msg.reply_video(video=file_path, **kw),
        "photo":      lambda: bot_msg.reply_photo(photo=file_path, **kw),
        "audio":      lambda: bot_msg.reply_audio(audio=file_path, **kw),
        "voice":      lambda: bot_msg.reply_voice(voice=file_path, **kw),
        "video_note": lambda: bot_msg.reply_video_note(video_note=file_path, quote=True),
        "sticker":    lambda: bot_msg.reply_sticker(sticker=file_path, quote=True),
        "animation":  lambda: bot_msg.reply_animation(animation=file_path, **kw),
    }
    fn = dispatch.get(mtype, lambda: bot_msg.reply_document(document=file_path, **kw))
    await fn()


async def _send_large(user: Client, user_id: int, file_path: str,
                      mtype: str, caption: str, size_mb: float):
    cap = f"{caption}\n📦 {size_mb:.1f} MB"
    if mtype in ("video", "animation"):
        await user.send_video(user_id, file_path, caption=cap)
    elif mtype == "audio":
        await user.send_audio(user_id, file_path, caption=cap)
    elif mtype == "photo":
        await user.send_photo(user_id, file_path, caption=cap)
    else:
        await user.send_document(user_id, file_path, caption=cap)


def _cleanup(path: str):
    try:
        if path and isinstance(path, str) and os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.debug(f"Cleanup error: {e}")
