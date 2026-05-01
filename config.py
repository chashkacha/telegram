import os

API_ID          = int(os.environ["API_ID"])
API_HASH        = os.environ["API_HASH"]
BOT_TOKEN       = os.environ["BOT_TOKEN"]
SESSION_STRING  = os.environ["SESSION_STRING"]
ALLOWED_USERS   = [int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()]

DOWNLOAD_DIR          = "downloads"
MAX_BOT_SIZE_MB       = 50
PROGRESS_UPDATE_EVERY = 3   # soniya

# Audio optimizer (ffmpeg bo'lsa ishlaydi)
AUDIO_OUTPUT_FORMAT  = "mp3"
AUDIO_TARGET_BITRATE = "128k"
AUDIO_TARGET_CODEC   = "libmp3lame"

MEDIA_LABELS = {
    "video"      : "🎬 Video",
    "photo"      : "🖼 Rasm",
    "document"   : "📄 Fayl",
    "audio"      : "🎵 Audio",
    "voice"      : "🎤 Ovozli xabar",
    "video_note" : "⭕ Video-xabar",
    "sticker"    : "😊 Stiker",
    "animation"  : "🎞 GIF",
    "story"      : "📖 Istoriya",
}
