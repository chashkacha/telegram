import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    task_fn: Callable[[], Coroutine]
    user_id: int
    description: str = ""
    task_ref: Optional[asyncio.Task] = field(default=None, repr=False)


class DownloadQueue:
    """
    Har bir foydalanuvchi uchun alohida navbat.
    Cancel qilish, statistika va navbat tozalash imkoniyati bor.
    """

    def __init__(self):
        self._queues:  dict[int, asyncio.Queue] = {}
        self._workers: dict[int, asyncio.Task]  = {}
        self._current: dict[int, Optional[asyncio.Task]] = {}  # joriy task
        self.stats:    dict[int, dict]          = {}

    # ── Worker ────────────────────────────────────────────────────────────────

    def _ensure_worker(self, user_id: int):
        if user_id not in self._workers or self._workers[user_id].done():
            self._workers[user_id] = asyncio.create_task(
                self._worker(user_id), name=f"worker-{user_id}"
            )

    async def _worker(self, user_id: int):
        q = self._queues[user_id]
        while True:
            item: QueueItem = await q.get()
            try:
                task = asyncio.create_task(item.task_fn(), name=f"dl-{user_id}")
                self._current[user_id] = task
                await task
                self.stats.setdefault(user_id, {"done": 0, "failed": 0})
                self.stats[user_id]["done"] += 1
            except asyncio.CancelledError:
                logger.info(f"Task cancelled for user {user_id}")
                self.stats.setdefault(user_id, {"done": 0, "failed": 0})
            except Exception as e:
                logger.error(f"Queue error user={user_id}: {e}")
                self.stats.setdefault(user_id, {"done": 0, "failed": 0})
                self.stats[user_id]["failed"] += 1
            finally:
                self._current[user_id] = None
                q.task_done()

    # ── Public API ────────────────────────────────────────────────────────────

    async def add(self, user_id: int, task_fn: Callable, description: str = "") -> int:
        if user_id not in self._queues:
            self._queues[user_id] = asyncio.Queue()
        self._ensure_worker(user_id)
        item = QueueItem(task_fn=task_fn, user_id=user_id, description=description)
        await self._queues[user_id].put(item)
        return self._queues[user_id].qsize()

    def queue_size(self, user_id: int) -> int:
        q = self._queues.get(user_id)
        return q.qsize() if q else 0

    def cancel_current(self, user_id: int) -> bool:
        """Joriy yuklanayotgan taskni bekor qiladi."""
        task = self._current.get(user_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def clear_user_queue(self, user_id: int) -> int:
        """Navbatdagi (hali boshlanmagan) itemlarni tozalaydi."""
        q = self._queues.get(user_id)
        if not q:
            return 0
        removed = 0
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
                removed += 1
            except asyncio.QueueEmpty:
                break
        return removed

    async def stop_all(self, user_id: int) -> dict:
        """Joriy taskni to'xtatadi va navbatni tozalaydi."""
        cancelled = self.cancel_current(user_id)
        removed   = await self.clear_user_queue(user_id)
        return {"cancelled": cancelled, "removed": removed}


download_queue = DownloadQueue()
