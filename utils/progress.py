import time
from pyrogram.types import Message

_last_edit: dict[int, float] = {}


def make_progress_bar(current: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = int(width * current / total)
    return "█" * filled + "░" * (width - filled)


def fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


def fmt_speed(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 ** 2:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / 1024 ** 2:.1f} MB/s"


async def progress_callback(current: int, total: int,
                             status_msg: Message, label: str,
                             start_time: float, update_interval: float = 3.0):
    now = time.time()
    key = status_msg.id
    if now - _last_edit.get(key, 0) < update_interval:
        return
    _last_edit[key] = now

    elapsed = max(now - start_time, 0.1)
    speed = current / elapsed
    remaining = int((total - current) / speed) if speed > 0 and total > current else 0

    bar = make_progress_bar(current, total)
    pct = (current / total * 100) if total else 0
    text = (
        f"{label}\n\n"
        f"{bar} {pct:.1f}%\n"
        f"📦 {fmt_size(current)} / {fmt_size(total)}\n"
        f"⚡ {fmt_speed(speed)}\n"
        f"⏱ {remaining}s qoldi"
    )
    try:
        await status_msg.edit(text)
    except Exception:
        pass
