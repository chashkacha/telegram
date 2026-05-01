import os

API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
BOT_TOKEN      = os.environ["BOT_TOKEN"]
SESSION_STRING = os.environ["SESSION_STRING"]

# Bo'sh bo'lsa — hamma private foydalanuvchiga ruxsat
_raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
ALLOWED_USERS = [int(x) for x in _raw.split(",") if x.strip().isdigit()]

DOWNLOAD_DIR    = "downloads"
MAX_BOT_SIZE_MB = 50

AUDIO_OUTPUT_FORMAT  = "mp3"
AUDIO_TARGET_BITRATE = "128k"
AUDIO_TARGET_CODEC   = "libmp3lame"

MEDIA_LABELS = {
    "video"     : "🎬 Video",
    "photo"     : "🖼 Rasm",
    "document"  : "📄 Fayl",
    "audio"     : "🎵 Audio",
    "voice"     : "🎤 Ovozli xabar",
    "video_note": "⭕ Video-xabar",
    "sticker"   : "😊 Stiker",
    "animation" : "🎞 GIF",
    "story"     : "📖 Istoriya",
}
