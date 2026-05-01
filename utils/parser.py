import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedLink:
    kind: str           # "message" | "story" | "unknown"
    peer: str | int     # username yoki channel_id (int)
    msg_id: int
    story_id: Optional[int] = None
    thread_id: Optional[int] = None  # forum/thread xabarlar uchun


def parse_link(link: str) -> Optional["ParsedLink"]:
    link = link.strip().split("?")[0]  # query parametrlarni olib tashlash

    # --- Istoriya: t.me/username/s/N ---
    m = re.match(r"https?://t\.me/([A-Za-z0-9_]+)/s/(\d+)", link)
    if m:
        return ParsedLink(kind="story", peer=m.group(1), msg_id=0, story_id=int(m.group(2)))

    # --- Private kanal thread: t.me/c/CHANNEL_ID/THREAD_ID/MSG_ID ---
    m = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if m:
        peer = int("-100" + m.group(1))
        return ParsedLink(kind="message", peer=peer,
                          msg_id=int(m.group(3)),
                          thread_id=int(m.group(2)))

    # --- Private kanal: t.me/c/CHANNEL_ID/MSG_ID ---
    m = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m:
        peer = int("-100" + m.group(1))
        return ParsedLink(kind="message", peer=peer, msg_id=int(m.group(2)))

    # --- Public thread: t.me/username/THREAD_ID/MSG_ID ---
    m = re.match(r"https?://t\.me/([A-Za-z0-9_]+)/(\d+)/(\d+)", link)
    if m:
        username = m.group(1)
        if username.lower() in ("joinchat", "addstickers", "share"):
            return None
        return ParsedLink(kind="message", peer=username,
                          msg_id=int(m.group(3)),
                          thread_id=int(m.group(2)))

    # --- Public kanal/guruh: t.me/USERNAME/MSG_ID ---
    m = re.match(r"https?://t\.me/([A-Za-z0-9_]+)/(\d+)", link)
    if m:
        username = m.group(1)
        if username.lower() in ("joinchat", "addstickers", "share"):
            return None
        return ParsedLink(kind="message", peer=username, msg_id=int(m.group(2)))

    return None


def extract_links(text: str) -> list[str]:
    """Bir xabardagi barcha t.me havolalarni ajratib oladi."""
    pattern = r"https?://t\.me/[^\s]+"
    return re.findall(pattern, text)
