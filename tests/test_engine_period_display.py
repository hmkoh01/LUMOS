"""Regression coverage for Engine v2 period routing and display limits."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.api.signals import router as signals_router
from src.storage.sqlite_store import SQLiteStore


class EnginePeriodDisplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteStore(Path(self.temp.name) / "periods.db")
        self.user_id = self.store.get_or_create_user_by_external_id("period-test")
        self.store.update_settings({"signal_count": 5}, user_id=self.user_id)
        self.app = FastAPI()
        self.app.include_router(signals_router, prefix="/api/v1")
        self.app.dependency_overrides[get_store] = lambda: self.store
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=self.user_id)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def _signal(self, title, period=None):
        metadata = {}
        if period:
            metadata = {"briefing_provider": "engine-v2-structured", "engine_period": period}
        return self.store.create_signal({
            "dedupe_key": f"{period or 'legacy'}:{title}", "title": title,
            "summary": title, "why_it_matters": title, "recommended_action": "read",
            "source_name": "test", "source_url": f"https://example.test/{title}",
            "source_items_json": [{"published_at": "2026-11-08T02:00:00Z"}],
            "metadata_json": metadata, "rank": int(title.rsplit("-", 1)[-1]) if "-" in title else 1,
            "status": "active",
        }, user_id=self.user_id)

    def test_engine_tabs_are_independent_and_never_include_legacy_cards(self):
        for index in range(7):
            self._signal(f"daily-{index}", "daily")
        for index in range(2):
            self._signal(f"weekly-{index}", "weekly")
        for index in range(3):
            self._signal(f"monthly-{index}", "monthly")
        for index in range(5):
            self._signal(f"legacy-{index}")

        with patch.dict(os.environ, {"LUMOS_ENGINE_V2": "true"}, clear=False):
            today = self.client.get("/api/v1/signals?period=today").json()
            week = self.client.get("/api/v1/signals?period=week").json()
            month = self.client.get("/api/v1/signals?period=month").json()

        self.assertEqual(len(today["signals"]), 5)
        self.assertEqual(len(week["signals"]), 2)
        self.assertEqual(len(month["signals"]), 3)
        self.assertTrue(all(item["metadata_json"]["engine_period"] == "daily" for item in today["signals"]))
        self.assertTrue(all(item["metadata_json"]["engine_period"] == "weekly" for item in week["signals"]))
        self.assertTrue(all(item["metadata_json"]["engine_period"] == "monthly" for item in month["signals"]))

    def test_setting_reductions_apply_at_the_api_boundary(self):
        for index in range(5):
            self._signal(f"daily-{index}", "daily")
        self.store.update_settings({"signal_count": 3}, user_id=self.user_id)
        with patch.dict(os.environ, {"LUMOS_ENGINE_V2": "true"}, clear=False):
            response = self.client.get("/api/v1/signals?period=today").json()
        self.assertEqual(response["display_limit"], 3)
        self.assertEqual(len(response["signals"]), 3)
