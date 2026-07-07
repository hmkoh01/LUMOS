import threading
import time
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from src.context.sync import sync_enabled_connectors
from src.delivery.briefing_service import BriefingService
from src.delivery.desktop_notification import notify_signals_ready
from src.storage.sqlite_store import SQLiteStore


class DailyBriefingScheduler:
    def __init__(
        self,
        store: SQLiteStore,
        interval_seconds: int = 60,
        mode: str = "mock",
        notifier: Optional[Callable[[int], None]] = None,
        on_ready: Optional[Callable[[dict], None]] = None,
    ):
        self.store = store
        self.interval_seconds = interval_seconds
        self.mode = mode
        self.notifier = notifier or notify_signals_ready
        self.on_ready = on_ready
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_context_sync_at: Optional[datetime] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-briefing-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self, force: bool = False, show_notification: bool = False):
        return self.check_and_run_once(force=force, show_notification=show_notification)

    def sync_once(self, force: bool = False):
        settings = self.store.get_sync_settings()
        if not force and self._last_context_sync_at:
            interval = timedelta(minutes=settings["context_sync_interval_minutes"])
            if datetime.utcnow() - self._last_context_sync_at < interval:
                return {"ran": False, "reason": "before_sync_interval"}
        result = sync_enabled_connectors(self.store, limit=100)
        self._last_context_sync_at = datetime.utcnow()
        self.store.prune_interests(settings["max_interest_keywords"])
        return {"ran": True, "reason": "synced", "result": result}

    def tick(self, force: bool = False, show_notification: bool = False):
        sync_result = self.sync_once(force=force)
        briefing_result = self.check_and_run_once(force=force, show_notification=show_notification)
        return {"sync": sync_result, "briefing": briefing_result}

    def check_and_run_once(self, force: bool = False, show_notification: bool = False):
        today = date.today().isoformat()
        if self.store.has_completed_scheduled_briefing(today):
            return {"ran": False, "reason": "already_completed", "signals": self.store.get_today_active_signals()}

        settings = self.store.get_settings()
        if not force and not self._briefing_time_reached(settings.get("briefing_time", "08:00")):
            return {"ran": False, "reason": "before_briefing_time", "signals": self.store.get_today_active_signals()}

        selected_mode = settings.get("generate_mode") or self.mode
        sync_result = None
        if settings.get("sync_before_briefing"):
            sync_result = self.sync_once(force=True)
        result = BriefingService(self.store).ensure_today_signals(
            mode=selected_mode,
            replace_today=True,
            triggered_by="scheduler",
            run_type="scheduled_daily_briefing",
        )
        signals = result.get("signals", [])
        if show_notification and settings.get("desktop_push_enabled"):
            self.notifier(len(signals))
        if self.on_ready:
            self.on_ready({"signals": signals, **result})
        return {"ran": True, "reason": "generated", "context_sync": sync_result, **result}

    def _loop(self):
        while not self._stop_event.is_set():
            self.tick(show_notification=True)
            self._stop_event.wait(self.interval_seconds)

    def _briefing_time_reached(self, briefing_time: str) -> bool:
        try:
            hour, minute = [int(part) for part in briefing_time.split(":", 1)]
        except Exception:
            hour, minute = 8, 0
        now = datetime.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return now >= scheduled


Scheduler = DailyBriefingScheduler
