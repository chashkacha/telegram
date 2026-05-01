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

QUALITY_FORMATS = {
    "best":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080":  "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
    "720":   "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
    "480":   "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best",
    "audio": "bestaudio[ext=m4a]/bestaudio/best",
}


def detect_platform(url: str) -> str:
    for domain, name in PLATFORM_NAMES.items():
        if domain in url:
            return name
    return "🌐 Video"


def is_external_link(url: str) -> bool:
    url = url.lower()
    return any(d in url for d in PLATFORM_NAMES)


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


def _progress_hook(status_msg, loop, label: str):
    last_update = [0.0]

    def hook(d):
        now = time.time()
        if now - last_update[0] < 2.5:   # 2.5s — tezroq yangilanish
            return
        last_update[0] = now
        if d["status"] == "downloading":
            dl    = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed = d.get("speed", 0) or 0
            eta   = d.get("eta", 0) or 0
            if total:
                pct  = dl / total * 100
                bar  = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                text = (
                    f"{label}\n\n"
                    f"{bar} {pct:.1f}%\n"
                    f"📦 {fmt_size(dl)} / {fmt_size(total)}\n"
                    f"⚡ {fmt_speed(speed)} | ⏱ {int(eta)}s"
                )
            else:
                text = f"{label}\n📦 {fmt_size(dl)} yuklanmoqda..."
            asyncio.run_coroutine_threadsafe(_safe_edit(status_msg, text), loop)

    return hook


async def _safe_edit(msg, text: str):
    try:
        await msg.edit(text)
    except Exception:
        pass


def _run_ydl(opts: dict, url: str) -> str:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Haqiqiy fayl yo'lini aniqlash
        if info.get("requested_downloads"):
            path = info["requested_downloads"][0].get("filepath", "")
        else:
            path = ydl.prepare_filename(info)
        # .webm / .mkv → .mp4 tekshiruvi
        for bad in (".webm", ".mkv"):
            if path.endswith(bad):
                mp4 = path[: -len(bad)] + ".mp4"
                if os.path.exists(mp4):
                    return mp4
        return path


# ── Asosiy yuklovchi ──────────────────────────────────────────────────────────

async def download_external(url: str, status_msg, quality: str = "best") -> tuple[str, str]:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    output_tmpl = os.path.join(DOWNLOAD_DIR, "%(title).70s.%(ext)s")
    loop        = asyncio.get_event_loop()
    hook        = _progress_hook(status_msg, loop, f"{detect_platform(url)} yuklanmoqda...")

    yt_cookie = _make_cookie_file("YOUTUBE_COOKIES",   "yt_")
    ig_cookie = _make_cookie_file("INSTAGRAM_COOKIES", "ig_")

    try:
        url_lower = url.lower()

        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            path = await _yt_download(url, quality, output_tmpl, hook, yt_cookie, loop)

        elif "instagram.com" in url_lower:
            path = await _ig_download(url, quality, output_tmpl, hook, ig_cookie, loop)

        else:
            path = await _generic_download(url, quality, output_tmpl, hook, loop)

        mtype = "audio" if quality == "audio" else "video"
        return path, mtype

    except yt_dlp.utils.DownloadError as e:
        raise _nice_error(str(e))
    finally:
        _cleanup(yt_cookie, ig_cookie)


# ── YouTube ────────────────────────────────────────────────────────────────────

async def _yt_download(url, quality, tmpl, hook, cookie_file, loop) -> str:
    """
    1-urinish: iOS player (cookie siz ham ishlaydi, bot-detection yo'q).
    2-urinish: web_creator player.
    3-urinish: cookies bilan web player.
    """
    base_opts = {
        "outtmpl":           tmpl,
        "progress_hooks":    [hook],
        "quiet":             True,
        "no_warnings":       True,
        "noplaylist":        True,
        "format":            QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "merge_output_format": "mp4",
    }
    if quality == "audio":
        base_opts["postprocessors"] = [{
            "key":            "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        base_opts.pop("merge_output_format", None)

    # iOS player — bot-detection ni chetlab o'tadi
    opts1 = {**base_opts,
        "extractor_args": {"youtube": {"player_client": ["ios"]}},
        "http_headers": {
            "User-Agent": (
                "com.google.ios.youtube/19.29.1 "
                "(iPhone16,2; U; CPU iPhone OS 17_5 like Mac OS X)"
            ),
        },
    }
    if cookie_file:
        opts1["cookiefile"] = cookie_file

    try:
        return await loop.run_in_executor(None, lambda: _run_ydl(opts1, url))
    except yt_dlp.utils.DownloadError as e1:
        err = str(e1)
        logger.warning(f"YouTube iOS player failed: {err[:120]}")

        # 2-urinish: web_creator
        opts2 = {**base_opts,
            "extractor_args": {"youtube": {"player_client": ["web_creator", "web"]}},
        }
        if cookie_file:
            opts2["cookiefile"] = cookie_file
        try:
            return await loop.run_in_executor(None, lambda: _run_ydl(opts2, url))
        except yt_dlp.utils.DownloadError as e2:
            logger.warning(f"YouTube web_creator failed: {str(e2)[:120]}")
            raise e2


# ── Instagram ──────────────────────────────────────────────────────────────────

async def _ig_download(url, quality, tmpl, hook, cookie_file, loop) -> str:
    if not cookie_file:
        raise Exception(
            "Instagram yuklab olish uchun cookie kerak.\n\n"
            "📋 <b>Sozlash:</b>\n"
            "1. Chrome → cookies.txt kengaytmasi o'rnating\n"
            "2. instagram.com ga kiring\n"
            "3. Cookie ni Netscape formatida eksport qiling\n"
            "4. Railway → Variables → <code>INSTAGRAM_COOKIES</code> ga joylashtiring"
        )
    opts = {
        "outtmpl":        tmpl,
        "progress_hooks": [hook],
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "cookiefile":     cookie_file,
        "format":         "best[ext=mp4]/best" if quality != "audio" else "bestaudio",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.5 Mobile/15E148 Safari/604.1"
            ),
        },
    }
    return await loop.run_in_executor(None, lambda: _run_ydl(opts, url))


# ── Boshqa platformalar ────────────────────────────────────────────────────────

async def _generic_download(url, quality, tmpl, hook, loop) -> str:
    opts = {
        "outtmpl":        tmpl,
        "progress_hooks": [hook],
        "quiet":          True,
        "no_warnings":    True,
        "noplaylist":     True,
        "format":         QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
    }
    if quality == "audio":
        opts.pop("merge_output_format", None)
    return await loop.run_in_executor(None, lambda: _run_ydl(opts, url))


# ── Xato xabarlari ─────────────────────────────────────────────────────────────

def _nice_error(err: str) -> Exception:
    TABLE = [
        ("Sign in to confirm",           "YouTube bot-detection. YOUTUBE_COOKIES ni sozlang."),
        ("bot",                           "YouTube bot-detection. Cookies kerak yoki keyinroq urinib ko'ring."),
        ("Private video",                 "Bu video yopiq (private)."),
        ("Video unavailable",             "Video mavjud emas yoki o'chirilgan."),
        ("This video is unavailable",     "Video mavjud emas."),
        ("content isn't available",       "Kontent mavjud emas."),
        ("Unable to extract",             "Video ma'lumotlarini olishda xato."),
        ("is not a valid URL",            "Noto'g'ri havola formati."),
        ("HTTP Error 429",                "Juda ko'p so'rov. Biroz kuting."),
        ("HTTP Error 403",                "Kirish taqiqlangan (403)."),
        ("HTTP Error 404",                "Media topilmadi (404)."),
    ]
    el = err.lower()
    for key, msg in TABLE:
        if key.lower() in el:
            return Exception(msg)
    return Exception(err[:300])
