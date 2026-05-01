import asyncio
import logging
import os
import tempfile
import time

import yt_dlp

from config import DOWNLOAD_DIR
from utils.progress import fmt_size, fmt_speed

logger = logging.getLogger(__name__)

PLATFORM_NAMES = {
    "youtube.com":     "▶️ YouTube",
    "youtu.be":        "▶️ YouTube",
    "instagram.com":   "📸 Instagram",
    "tiktok.com":      "🎵 TikTok",
    "twitter.com":     "🐦 Twitter/X",
    "x.com":           "🐦 Twitter/X",
    "facebook.com":    "👤 Facebook",
    "vimeo.com":       "🎬 Vimeo",
    "reddit.com":      "👾 Reddit",
    "twitch.tv":       "🎮 Twitch",
    "ok.ru":           "🌐 OK.ru",
    "vk.com":          "🌐 VK",
    "dailymotion.com": "🎬 Dailymotion",
    "rumble.com":      "📹 Rumble",
    "bilibili.com":    "📺 Bilibili",
}


def detect_platform(url: str) -> str:
    for domain, name in PLATFORM_NAMES.items():
        if domain in url:
            return name
    return "🌐 Video"


def is_external_link(url: str) -> bool:
    return any(d in url for d in PLATFORM_NAMES)


def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_instagram(url: str) -> bool:
    return "instagram.com" in url


def _make_cookie_file(env_key: str, prefix: str) -> str | None:
    content = os.environ.get(env_key, "").strip()
    if not content:
        return None
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix=prefix)
    if not content.startswith("# Netscape"):
        tmp.write("# Netscape HTTP Cookie File\n")
    tmp.write(content)
    tmp.close()
    return tmp.name


def _cleanup(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def _make_progress_hook(status_msg, loop, label: str):
    last_update = [0.0]

    def hook(d):
        now = time.time()
        if now - last_update[0] < 3:
            return
        last_update[0] = now
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total      = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed      = d.get("speed", 0) or 0
            eta        = d.get("eta", 0) or 0
            if total:
                pct  = downloaded / total * 100
                bar  = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                text = (
                    f"{label}\n\n"
                    f"{bar} {pct:.1f}%\n"
                    f"📦 {fmt_size(downloaded)} / {fmt_size(total)}\n"
                    f"⚡ {fmt_speed(speed)}\n"
                    f"⏱ {int(eta)}s qoldi"
                )
            else:
                text = f"{label}\n📦 {fmt_size(downloaded)} yuklanmoqda..."
            asyncio.run_coroutine_threadsafe(_safe_edit(status_msg, text), loop)

    return hook


async def _safe_edit(msg, text: str):
    try:
        await msg.edit(text)
    except Exception:
        pass


def _base_opts(output_tmpl: str, hook) -> dict:
    """Barcha platformalar uchun asosiy yt-dlp sozlamalari."""
    return {
        "outtmpl":         output_tmpl,
        "progress_hooks":  [hook],
        "quiet":           True,
        "no_warnings":     True,
        "noplaylist":      True,
        "socket_timeout":  30,
        "retries":         5,
        "fragment_retries": 5,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }


def _run_download(opts: dict, url: str) -> str:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Actual fayl yo'lini olish
        if "requested_downloads" in info and info["requested_downloads"]:
            path = info["requested_downloads"][0].get("filepath") or ydl.prepare_filename(info)
        else:
            path = ydl.prepare_filename(info)
        # Extension normalizatsiya
        for bad_ext in (".webm", ".mkv"):
            if path.endswith(bad_ext):
                mp4_path = path[:-len(bad_ext)] + ".mp4"
                if os.path.exists(mp4_path):
                    path = mp4_path
                break
        return path


async def download_external(url: str, status_msg, quality: str = "best") -> tuple[str, str]:
    platform = detect_platform(url)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    output_tmpl = os.path.join(DOWNLOAD_DIR, "%(title).60s.%(ext)s")
    loop        = asyncio.get_event_loop()
    hook        = _make_progress_hook(status_msg, loop, f"{platform} yuklanmoqda...")

    yt_cookie = _make_cookie_file("YOUTUBE_COOKIES", "yt_")
    ig_cookie = _make_cookie_file("INSTAGRAM_COOKIES", "ig_")

    try:
        # ── YouTube ────────────────────────────────────────────────────────
        if is_youtube(url):
            file_path = await _download_youtube(url, quality, output_tmpl, hook, yt_cookie)
            mtype = "audio" if quality == "audio" else "video"
            return file_path, mtype

        # ── Instagram ──────────────────────────────────────────────────────
        if is_instagram(url):
            file_path = await _download_instagram(url, quality, output_tmpl, hook, ig_cookie)
            mtype = "audio" if quality == "audio" else "video"
            return file_path, mtype

        # ── Boshqa platformalar (TikTok, Twitter, ...) ─────────────────────
        file_path = await _download_generic(url, quality, output_tmpl, hook)
        mtype = "audio" if quality == "audio" else "video"
        return file_path, mtype

    except yt_dlp.utils.DownloadError as e:
        raise _friendly_error(str(e), url)
    finally:
        _cleanup(yt_cookie, ig_cookie)


# ── Platform-specific yuklovchilar ────────────────────────────────────────────

async def _download_youtube(url: str, quality: str, output_tmpl: str, hook, cookie_file: str | None) -> str:
    """
    YouTube uchun maxsus: bot-detection ni chetlab o'tish uchun
    avval ios player bilan urinish, keyin cookies bilan fallback.
    """
    loop = asyncio.get_event_loop()

    def _fmt(quality: str) -> str:
        if quality == "audio":
            return "bestaudio[ext=m4a]/bestaudio/best"
        elif quality == "720":
            return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best"
        elif quality == "480":
            return "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best"
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    # 1-urinish: iOS player client (cookies siz ham ishlaydi)
    opts = {
        "outtmpl":        output_tmpl,
        "progress_hooks": [hook],
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "socket_timeout": 30,
        "retries":        5,
        "format":         _fmt(quality),
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "web"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "com.google.ios.youtube/19.09.3 (iPhone16,2; U; CPU iPhone OS 17_4 like Mac OS X)"
            ),
        },
    }

    if quality == "audio":
        opts["postprocessors"] = [{
            "key":           "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        opts["merge_output_format"] = "mp4"

    if cookie_file:
        opts["cookiefile"] = cookie_file

    try:
        return await loop.run_in_executor(None, lambda: _run_download(opts, url))
    except yt_dlp.utils.DownloadError as e:
        err_str = str(e)
        # Bot detection xatosi bo'lsa web_creator bilan urinib ko'ramiz
        if "Sign in" in err_str or "bot" in err_str.lower() or "confirm" in err_str.lower():
            logger.warning("YouTube: iOS player failed, trying web_creator...")
            opts2 = dict(opts)
            opts2["extractor_args"] = {
                "youtube": {"player_client": ["web_creator", "web"]}
            }
            opts2.pop("http_headers", None)
            return await loop.run_in_executor(None, lambda: _run_download(opts2, url))
        raise


async def _download_instagram(url: str, quality: str, output_tmpl: str, hook, cookie_file: str | None) -> str:
    loop = asyncio.get_event_loop()
    if not cookie_file:
        raise Exception(
            "Instagram yuklab olish uchun cookie kerak.\n\n"
            "📋 <b>Sozlash:</b>\n"
            "1. Brauzerga EditThisCookie kengaytmasi o'rnating\n"
            "2. instagram.com ga kiring\n"
            "3. Cookie larni Netscape formatida eksport qiling\n"
            "4. Railway → Environment → <code>INSTAGRAM_COOKIES</code> ga qo'ying"
        )
    opts = {
        "outtmpl":        output_tmpl,
        "progress_hooks": [hook],
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "socket_timeout": 30,
        "retries":        5,
        "cookiefile":     cookie_file,
        "format":         "best[ext=mp4]/best" if quality != "audio" else "bestaudio",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            ),
        },
    }
    return await loop.run_in_executor(None, lambda: _run_download(opts, url))


async def _download_generic(url: str, quality: str, output_tmpl: str, hook) -> str:
    loop = asyncio.get_event_loop()

    if quality == "audio":
        fmt = "bestaudio[ext=m4a]/bestaudio/best"
    elif quality == "720":
        fmt = "best[height<=720][ext=mp4]/best[height<=720]/best"
    elif quality == "480":
        fmt = "best[height<=480][ext=mp4]/best[height<=480]/best"
    else:
        fmt = "best[ext=mp4]/best"

    opts = {
        "outtmpl":        output_tmpl,
        "progress_hooks": [hook],
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "socket_timeout": 30,
        "retries":        5,
        "format":         fmt,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }
    return await loop.run_in_executor(None, lambda: _run_download(opts, url))


def _friendly_error(err: str, url: str = "") -> Exception:
    """yt-dlp xato xabarlarini foydalanuvchiga qulay qilish."""
    known = {
        "Sign in to confirm": (
            "YouTube bot-detection xatosi.\n\n"
            "Yechim: <code>YOUTUBE_COOKIES</code> muhit o'zgaruvchisini sozlang."
        ),
        "Private video":      "Bu video yopiq (private).",
        "This video is unavailable": "Video mavjud emas yoki o'chirilgan.",
        "Video unavailable":  "Video mavjud emas.",
        "This content isn't available": "Kontent mavjud emas.",
        "Unable to extract":  "Video ma'lumotlarini olishda xato.",
        "is not a valid URL": "Noto'g'ri havola formati.",
        "HTTP Error 429":     "Juda ko'p so'rov. Biroz kuting.",
        "HTTP Error 403":     "Kirish taqiqlangan (403).",
        "HTTP Error 404":     "Media topilmadi (404).",
    }
    for key, msg in known.items():
        if key in err:
            return Exception(msg)
    return Exception(err[:300])
