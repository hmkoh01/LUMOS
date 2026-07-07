from typing import Any, Dict, List, Optional

from src.signals.pipeline import SignalPipeline
from src.signals.feedback import FeedbackService
from src.context.sync import sync_enabled_connectors
from src.storage.sqlite_store import SQLiteStore


class BriefingService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def get_today_signals(self, active_only: bool = True) -> List[Dict[str, Any]]:
        if active_only:
            return self.store.get_today_active_signals()
        return self.store.get_today_signals()

    def ensure_today_signals(
        self,
        mode: str = "mock",
        replace_today: bool = False,
        triggered_by: str = "manual",
        run_type: str = "signal_generation",
    ) -> Dict[str, Any]:
        existing = self.get_today_signals(active_only=True)
        if existing and not replace_today:
            return {
                "generated": False,
                "signals": existing,
                "pipeline_run_id": None,
                "reason": "existing_active_signals",
            }
        result = SignalPipeline(self.store).generate_daily_signals(
            replace_today=True,
            triggered_by=triggered_by,
            mode=mode,
            run_type=run_type,
        )
        self.record_lifecycle_event(
            "briefing_ready",
            {
                "pipeline_run_id": result.get("pipeline_run_id"),
                "signal_count": len(result.get("signals", [])),
                "source": triggered_by,
                "mode": mode,
            },
        )
        return {"generated": True, **result}

    def generate_now(self, mode: Optional[str] = None) -> Dict[str, Any]:
        selected_mode = mode or self.get_settings().get("generate_mode", "mock")
        self.record_lifecycle_event("briefing_generate_clicked", {"mode": selected_mode, "source": "desktop"})
        return self.ensure_today_signals(mode=selected_mode, replace_today=True, triggered_by="manual")

    def record_feedback(self, signal_id: int, event_type: str, payload: Optional[Dict[str, Any]] = None):
        return FeedbackService(self.store).record(signal_id, event_type, payload or {})

    def record_lifecycle_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None):
        event_id = self.store.record_feedback(0, event_type, payload or {})
        return {"event_id": event_id}

    def get_latest_briefing_context(self) -> Dict[str, Any]:
        signals = self.get_today_signals(active_only=True)
        pipeline_run_id = signals[0].get("pipeline_run_id") if signals else None
        run = self.store.get_pipeline_run(pipeline_run_id) if pipeline_run_id else None
        settings = self.get_settings()
        summary = run.get("summary_json", {}) if run else {}
        return {
            "signals": signals,
            "signal_count": len(signals),
            "last_generated_at": run.get("completed_at") if run else None,
            "pipeline_run_id": pipeline_run_id,
            "generate_mode": summary.get("mode") or settings.get("generate_mode", "mock"),
            "summary": summary,
            "warnings": summary.get("errors_by_source", {}),
        }

    def is_first_run(self) -> bool:
        settings = self.get_settings()
        return not settings.get("onboarding_completed") or not self.store.get_profile()

    def get_settings(self) -> Dict[str, Any]:
        return self.store.get_settings()

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self.store.update_settings(updates)

    def list_source_configs(self) -> List[Dict[str, Any]]:
        return self.store.get_source_configs()

    def update_source_config(self, source_id: str, **updates) -> Dict[str, Any]:
        return self.store.upsert_source_config(
            source_id,
            enabled=updates.get("enabled"),
            priority=updates.get("priority"),
            config=updates.get("config_json"),
        )

    def get_connectors(self) -> List[Dict[str, Any]]:
        return self.store.get_connectors()

    def update_connector(self, connector_type: str, enabled: bool, config: Optional[Dict[str, Any]] = None):
        return self.store.update_connector(connector_type, enabled, config)

    def sync_context(self, connector_types: Optional[List[str]] = None, limit: int = 100):
        return sync_enabled_connectors(self.store, connector_types=connector_types, limit=limit)

    def get_interests(self, limit: int = 20, include_muted: bool = False):
        return self.store.get_interests(limit=limit, include_muted=include_muted)

    def mute_interest(self, keyword: str):
        return self.store.mute_interest(keyword)

    def unmute_interest(self, keyword: str):
        return self.store.unmute_interest(keyword)

    def delete_interest(self, keyword: str):
        return self.store.delete_interest(keyword)

    def update_interest(self, keyword: str, **updates):
        return self.store.update_interest(keyword, updates)

    def get_interest_evidence(self, keyword: str):
        return self.store.get_interest_evidence(keyword)
