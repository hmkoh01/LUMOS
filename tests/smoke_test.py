from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.dependencies import get_store
from src.app.scheduler import DailyBriefingScheduler
from src.app.portable_entry import main as portable_main
from src.app.resource_paths import data_dir, web_landing_dir, web_static_dir
from src.app.version import APP_NAME, APP_VERSION, BUILD_STAGE
from src.app.main import app
from run import run_cloud, run_companion, run_demo_companion, run_demo_reset, run_demo_seed, run_demo_web_app, run_web_app
from src.cloud.app import app as cloud_app
from src.cloud.config import CLOUD_DB_PATH
from src.cloud.database import initialize_cloud_db
from src.app.demo_seed import demo_db_path
from src.app.server_control import is_server_running
from src.delivery.briefing_service import BriefingService
from src.desktop.app import main as desktop_main
from src.desktop.briefing_window import BriefingWindow
from src.desktop.companion_window import CompanionWindow, web_tab_url
from src.desktop.settings_window import SettingsWindow
from src.context.keyword_extraction import extract_keywords
from src.context.connectors.browser import BrowserHistoryConnector
from src.context.connectors.local_files import LocalFilesConnector
from src.sources.collector_registry import COLLECTOR_OVERRIDES, CollectorRegistry
from src.sources.collectors.base import BaseCollector, CollectedItem, CollectorResult, SourceQuery
from src.sources.collectors.github import GitHubCollector
from src.sources.collectors.hackernews import HackerNewsCollector
from src.sources.collectors.mock import MockCollector
from src.sources.collectors.rss import RSSCollector
from src.storage.sqlite_store import SQLiteStore
from src.product.account import UserAccount
from src.product.auth_service import MockAuthService
from src.product.cloud_client import MockCloudClient
from src.product.device import RegisteredDevice
from src.product.entitlement_cache import EntitlementSnapshot, InMemoryEntitlementCache, OfflineGraceDecision
from src.product.entitlements import MockEntitlementService, PlanEntitlement, StaticEntitlementService
from src.product.feature_gates import FeatureGateContext, FeatureKey, GateSeverity, StaticFeatureGateService
from src.product.token_store import InMemoryTokenStore, KeyringTokenStore, TokenBundle, TokenStoreUnavailable


def build_client():
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "lumos.db"
    store = SQLiteStore(db_path)
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), tmpdir, store


def main():
    client, tmpdir, store = build_client()
    try:
        assert isinstance(CollectorRegistry().get("mock", mode="mock"), MockCollector)
        assert isinstance(CollectorRegistry().get("rss", mode="live"), RSSCollector)
        assert isinstance(CollectorRegistry().get("hackernews", mode="live"), HackerNewsCollector)
        assert isinstance(CollectorRegistry().get("github", mode="live"), GitHubCollector)
        assert_collector_contracts()
        keyword_result = extract_keywords("AI agent workflow automation AI agent productivity", max_keywords=5)
        assert keyword_result and keyword_result[0]["keyword"] in {"ai", "agent"}

        response = client.get("/health")
        assert response.status_code == 200, response.text

        assert run_web_app
        assert run_cloud
        assert run_companion
        assert run_demo_reset
        assert run_demo_seed
        assert run_demo_web_app
        assert run_demo_companion
        assert portable_main
        assert APP_NAME == "LUMOS"
        assert APP_VERSION == "0.1.0-alpha"
        assert BUILD_STAGE == "closed_beta_prototype"
        assert web_static_dir().name == "static"
        assert web_landing_dir().name == "landing"
        assert data_dir().name == "data"
        assert demo_db_path().name == "demo_lumos.db"
        assert demo_db_path().name != "lumos.db"
        assert CLOUD_DB_PATH.name == "cloud_lumos.db"
        assert CLOUD_DB_PATH.name != "lumos.db"
        assert CLOUD_DB_PATH.name != demo_db_path().name
        account = UserAccount(id="user_1", email="user@example.com")
        device = RegisteredDevice(
            id="device_1",
            user_id=account.id,
            device_name="Demo PC",
            os="Windows",
            app_version="0.1.0",
            device_fingerprint_hash="hash",
        )
        entitlement = PlanEntitlement(key="daily_signals", value="3", description="Daily signal limit")
        entitlement_service = StaticEntitlementService({"daily_signals": entitlement})
        assert device.user_id == account.id
        assert entitlement_service.is_allowed(account.id, device.id, "daily_signals", quantity=3)
        assert not entitlement_service.is_allowed(account.id, device.id, "daily_signals", quantity=4)
        mock_auth = MockAuthService(plan="pro", session_minutes=1)
        signed_in = mock_auth.login(email="demo@lumos.local", device_name="Demo PC")
        assert signed_in.is_signed_in
        assert signed_in.session.is_mock
        assert signed_in.session.access_token.startswith("mock_access_")
        assert signed_in.session.device_id.startswith("mock_device_")
        refreshed = mock_auth.refresh()
        assert refreshed.is_signed_in
        mock_auth.record_usage("signal_generated", quantity=1, metadata={"surface": "smoke"})
        assert mock_auth.usage_events and mock_auth.usage_events[0]["mock"] is True
        assert mock_auth.logout().status.value == "anonymous"
        mock_device = mock_auth.register_device("mock_user_demo", device_name="Demo PC")
        assert mock_device.id.startswith("mock_device_")
        free_entitlements = MockEntitlementService("free").get_entitlements("u", "d")
        pro_entitlements = MockEntitlementService("pro").get_entitlements("u", "d")
        unknown_entitlements = MockEntitlementService("unknown").get_entitlements("u", "d")
        assert int(free_entitlements["max_signals_per_day"].value) == 3
        assert int(pro_entitlements["max_signals_per_day"].value) > 3
        assert unknown_entitlements["max_signals_per_day"].value == free_entitlements["max_signals_per_day"].value
        gate_service = StaticFeatureGateService()
        free_gate = gate_service.evaluate(FeatureGateContext(plan="free"), FeatureKey.TODAY_SIGNAL_COUNT.value, current_value=5)
        assert free_gate.allowed is True
        assert free_gate.is_enforced is False
        assert free_gate.severity == GateSeverity.UPGRADE_RECOMMENDED.value
        pro_gate = gate_service.evaluate(
            FeatureGateContext(plan="pro", entitlements={"max_signals_per_day": 10}),
            FeatureKey.TODAY_SIGNAL_COUNT.value,
            current_value=5,
        )
        assert pro_gate.allowed is True
        assert pro_gate.severity == GateSeverity.ALLOWED.value
        unknown_gate = gate_service.evaluate(FeatureGateContext(plan="unknown"), FeatureKey.SOURCE_COUNT.value, current_value=4)
        assert unknown_gate.allowed is True
        assert unknown_gate.is_enforced is False
        grace_gate = gate_service.evaluate(
            FeatureGateContext(plan="pro", cache_status="grace", entitlements={"max_signals_per_day": 10}),
            FeatureKey.AUTO_BRIEFING.value,
        )
        assert "grace" in grace_gate.message_ko
        expired_gate = gate_service.evaluate(
            FeatureGateContext(plan="local_mvp", cache_status="expired"),
            FeatureKey.TODAY_SIGNAL_COUNT.value,
            current_value=5,
        )
        assert expired_gate.allowed is True
        assert expired_gate.is_enforced is False
        mock_cloud = MockCloudClient(plan="pro")
        token_body = mock_cloud.dev_login(email="demo@lumos.local", name="Demo User", plan="pro")
        assert token_body["access_token"].startswith("mock_access_")
        assert mock_cloud.get_me()["user"]["plan"] == "pro"
        assert mock_cloud.register_device(device_name="Demo PC").id.startswith("mock_device_")
        cloud_user = mock_cloud.current_user()
        cloud_device = mock_cloud.register_device("Demo PC", "Windows", "0.1.0")
        assert cloud_user.id.startswith("mock_user_")
        assert cloud_device.user_id == cloud_user.id
        assert mock_cloud.record_usage_event(event_type="signal_generated", quantity=1)["success"] is True
        token_bundle = TokenBundle(
            access_token="dev_access_secret_for_test",
            refresh_token="dev_refresh_secret_for_test",
            expires_at="2026-07-05T00:00:00Z",
            user_id="mock_user_demo",
            device_id="mock_device_demo",
            is_dev=True,
        )
        assert "dev_access_secret_for_test" not in repr(token_bundle)
        assert "dev_refresh_secret_for_test" not in str(token_bundle)
        memory_token_store = InMemoryTokenStore()
        assert memory_token_store.describe_backend() == "memory"
        assert not memory_token_store.has_tokens()
        memory_token_store.save_tokens(token_bundle)
        assert memory_token_store.has_tokens()
        assert memory_token_store.load_tokens().user_id == "mock_user_demo"
        memory_token_store.clear_tokens()
        assert not memory_token_store.has_tokens()
        entitlement_snapshot = EntitlementSnapshot.from_cloud_response(
            user_id="mock_user_demo",
            device_id="mock_device_demo",
            response={"plan": "pro", "entitlements": {"max_signals_per_day": 10}},
        )
        entitlement_cache = InMemoryEntitlementCache()
        assert entitlement_cache.evaluate_offline_grace() == OfflineGraceDecision.FALLBACK_LOCAL
        entitlement_cache.save_snapshot(entitlement_snapshot)
        assert entitlement_cache.load_snapshot().plan == "pro"
        assert entitlement_cache.has_valid_snapshot()
        assert entitlement_cache.describe_status()["status"] == "valid"
        current = datetime.utcnow().replace(microsecond=0)
        grace_snapshot = EntitlementSnapshot.from_cloud_response(
            user_id="mock_user_demo",
            device_id="mock_device_demo",
            response={"plan": "pro", "entitlements": {"max_signals_per_day": 10}},
            now=current,
            ttl_hours=1,
            grace_days=3,
        )
        entitlement_cache.save_snapshot(grace_snapshot)
        assert entitlement_cache.evaluate_offline_grace(current + timedelta(hours=2)) == OfflineGraceDecision.USE_GRACE
        assert entitlement_cache.evaluate_offline_grace(current + timedelta(days=4)) == OfflineGraceDecision.FALLBACK_LOCAL
        entitlement_cache.clear_snapshot()
        assert entitlement_cache.describe_status()["status"] == "empty"
        try:
            keyring_store = KeyringTokenStore(service_name="LUMOS_TEST", username="smoke")
            keyring_store.save_tokens(token_bundle)
            loaded = keyring_store.load_tokens()
            assert loaded and loaded.user_id == "mock_user_demo"
            assert "dev_access_secret_for_test" not in repr(loaded)
            keyring_store.clear_tokens()
        except TokenStoreUnavailable:
            assert True

        initialize_cloud_db()
        cloud_test_client = TestClient(cloud_app)
        response = cloud_test_client.get("/health")
        assert response.status_code == 200, response.text
        assert response.json()["db_path"].endswith("cloud_lumos.db")
        response = cloud_test_client.post(
            "/auth/dev-login",
            json={"email": "demo@lumos.local", "name": "Demo User", "plan": "pro"},
        )
        assert response.status_code == 200, response.text
        dev_tokens = response.json()
        assert dev_tokens["access_token"].startswith("dev_access_")
        assert dev_tokens["refresh_token"].startswith("dev_refresh_")
        assert dev_tokens["user"]["plan"] == "pro"
        auth_headers = {"Authorization": f"Bearer {dev_tokens['access_token']}"}
        response = cloud_test_client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["user"]["email"] == "demo@lumos.local"
        response = cloud_test_client.post(
            "/devices/register",
            json={
                "device_name": "Demo PC",
                "os": "Windows",
                "app_version": "0.1.0",
                "device_fingerprint_hash": "placeholder_hash",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        first_device_id = response.json()["id"]
        response = cloud_test_client.post(
            "/devices/register",
            json={
                "device_name": "Demo PC",
                "os": "Windows",
                "app_version": "0.1.0",
                "device_fingerprint_hash": "placeholder_hash",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["id"] == first_device_id
        response = cloud_test_client.get("/devices", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["devices"]
        response = cloud_test_client.get("/entitlements/me", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["plan"] == "pro"
        assert response.json()["entitlements"]["max_signals_per_day"] > 3
        response = cloud_test_client.post(
            "/usage/events",
            json={"event_type": "signal_generated", "quantity": 1, "metadata": {"mode": "mock"}},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True
        response = cloud_test_client.post("/auth/refresh", json={"refresh_token": dev_tokens["refresh_token"]})
        assert response.status_code == 200, response.text
        assert response.json()["access_token"].startswith("dev_access_")
        refreshed_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        response = cloud_test_client.post("/auth/logout", headers=refreshed_headers)
        assert response.status_code == 200, response.text
        response = cloud_test_client.get("/auth/me", headers=refreshed_headers)
        assert response.status_code == 401, response.text
        response = client.get("/api/v1/product/gates/status")
        assert response.status_code == 200, response.text
        gate_status = response.json()
        assert gate_status["is_enforced"] is False
        assert gate_status["gates"]
        response = client.post("/api/v1/product/gates/evaluate", json={"feature_key": "today_signal_count", "current_value": 5})
        assert response.status_code == 200, response.text
        assert response.json()["allowed"] is True
        assert response.json()["is_enforced"] is False
        bridge_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.cloud.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8019",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(3)
            response = client.get("/api/v1/product/cloud/status")
            assert response.status_code == 200, response.text
            assert response.json()["mode"] == "local"
            response = client.post(
                "/api/v1/product/cloud/dev-connect",
                json={
                    "email": "demo@lumos.local",
                    "name": "Demo User",
                    "plan": "pro",
                    "cloud_base_url": "http://127.0.0.1:8019",
                },
            )
            assert response.status_code == 200, response.text
            bridge_body = response.json()
            assert bridge_body["connected"] is True, bridge_body
            assert bridge_body["mode"] == "cloud_dev", bridge_body
            assert bridge_body["plan"] == "pro", bridge_body
            assert bridge_body["token_storage"] in {"memory", "keyring_unavailable_memory", "keyring"}, bridge_body
            assert bridge_body["entitlement_cache"]["status"] == "valid", bridge_body
            assert bridge_body["entitlement_cache"]["decision"] == "use_cache", bridge_body
            assert bridge_body["entitlement_summary"]["daily_signals"].startswith("오늘 신호"), bridge_body
            assert bridge_body["user"]["email"] == "demo@lumos.local", bridge_body
            assert bridge_body["device"]["status"] == "active", bridge_body
            assert bridge_body["entitlements"]["max_signals_per_day"] > 3, bridge_body
            response = client.get("/api/v1/product/gates/status")
            assert response.status_code == 200, response.text
            connected_gate_status = response.json()
            assert connected_gate_status["plan"] == "pro"
            assert connected_gate_status["is_enforced"] is False
            assert "access_token" not in bridge_body
            assert "refresh_token" not in bridge_body
            response = client.get("/api/v1/product/cloud/account")
            assert response.status_code == 200, response.text
            assert response.json()["connected"] is True
            response = client.post("/api/v1/product/cloud/usage-test")
            assert response.status_code == 200, response.text
            assert response.json()["usage_event"]["success"] is True
            response = client.post(
                "/api/v1/product/cloud/dev-connect",
                json={"cloud_base_url": "http://127.0.0.1:8999"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["connected"] is False
            assert response.json()["entitlement_cache"]["status"] == "valid"
            response = client.post("/api/v1/product/cloud/dev-disconnect")
            assert response.status_code == 200, response.text
            assert response.json()["mode"] == "local"
            assert response.json()["entitlement_cache"]["status"] == "empty"
            response = client.post(
                "/api/v1/product/cloud/dev-connect",
                json={"cloud_base_url": "http://127.0.0.1:8999"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["connected"] is False
            assert response.json()["error_code"] == "cloud_unavailable"
        finally:
            bridge_process.terminate()
            try:
                bridge_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge_process.kill()
        assert CompanionWindow
        assert callable(is_server_running)
        assert web_tab_url("http://127.0.0.1:8000", "today") == "http://127.0.0.1:8000/app#today"
        assert web_tab_url("http://127.0.0.1:8000", "signals") == "http://127.0.0.1:8000/app#today"
        assert web_tab_url("http://127.0.0.1:8000", "settings") == "http://127.0.0.1:8000/app#settings"
        assert web_tab_url("http://127.0.0.1:8000", "activity") == "http://127.0.0.1:8000/app#activity"
        assert web_tab_url("http://127.0.0.1:8000", "unknown") == "http://127.0.0.1:8000/app#today"
        web_files = [
            ROOT / "src" / "web" / "static" / "index.html",
            ROOT / "src" / "web" / "static" / "styles.css",
            ROOT / "src" / "web" / "static" / "app.js",
            ROOT / "src" / "web" / "landing" / "index.html",
            ROOT / "src" / "web" / "landing" / "pricing.html",
            ROOT / "src" / "web" / "landing" / "download.html",
            ROOT / "src" / "web" / "landing" / "beta.html",
            ROOT / "src" / "web" / "landing" / "landing.css",
            ROOT / "src" / "web" / "landing" / "landing.js",
            ROOT / "docs" / "qa" / "mvp_reality_check.md",
            ROOT / "docs" / "qa" / "korean_briefing_quality.md",
            ROOT / "docs" / "qa" / "desktop_companion_mvp.md",
            ROOT / "docs" / "qa" / "account_ui_shell_qa.md",
            ROOT / "docs" / "qa" / "cloud_auth_service_qa.md",
            ROOT / "docs" / "qa" / "local_cloud_dev_connection_qa.md",
            ROOT / "docs" / "qa" / "entitlement_cache_offline_grace_qa.md",
            ROOT / "docs" / "qa" / "entitlement_gate_integration_qa.md",
            ROOT / "docs" / "demo" / "demo_flow.md",
            ROOT / "docs" / "demo" / "pitch_demo_script.md",
            ROOT / "docs" / "demo" / "user_test_script.md",
            ROOT / "docs" / "demo" / "manual_demo_checklist.md",
            ROOT / "docs" / "demo" / "demo_data_strategy.md",
            ROOT / "docs" / "demo" / "next_priorities_after_user_test.md",
            ROOT / "docs" / "demo" / "demo_rehearsal_report.md",
            ROOT / "docs" / "demo" / "screenshots" / "README.md",
            ROOT / "docs" / "product" / "production_readiness_architecture.md",
            ROOT / "docs" / "product" / "account_device_subscription_design.md",
            ROOT / "docs" / "product" / "auth_api_contract.md",
            ROOT / "docs" / "product" / "local_token_storage_policy.md",
            ROOT / "docs" / "product" / "auth_ui_wireframe.md",
            ROOT / "docs" / "product" / "cloud_local_split.md",
            ROOT / "docs" / "product" / "distribution_packaging_plan.md",
            ROOT / "docs" / "product" / "landing_pricing_legal_plan.md",
            ROOT / "docs" / "product" / "implementation_roadmap.md",
            ROOT / "docs" / "product" / "entitlement_cache_offline_grace.md",
            ROOT / "docs" / "product" / "entitlement_gate_policy.md",
            ROOT / "docs" / "product" / "pricing_validation_plan.md",
            ROOT / "docs" / "product" / "landing_copy.md",
            ROOT / "docs" / "product" / "closed_beta_intake_plan.md",
            ROOT / "docs" / "product" / "beta_email_templates.md",
            ROOT / "docs" / "product" / "download_readiness_checklist.md",
            ROOT / "docs" / "product" / "release_notes_template.md",
            ROOT / "docs" / "product" / "known_issues_template.md",
            ROOT / "docs" / "product" / "beta_feedback_tracker.md",
            ROOT / "docs" / "product" / "windows_portable_build_plan.md",
            ROOT / "docs" / "product" / "cohort1_launch_pack.md",
            ROOT / "docs" / "product" / "canary_feedback_form.md",
            ROOT / "docs" / "product" / "canary_run_checklist.md",
            ROOT / "docs" / "qa" / "closed_beta_intake_download_readiness_qa.md",
            ROOT / "docs" / "qa" / "windows_portable_build_qa.md",
            ROOT / "docs" / "qa" / "closed_beta_portable_manual_qa.md",
            ROOT / "docs" / "qa" / "closed_beta_cohort1_launch_readiness.md",
            ROOT / "docs" / "qa" / "cohort1_canary_run.md",
            ROOT / "packaging" / "windows" / "build_portable.ps1",
            ROOT / "packaging" / "windows" / "build_portable.py",
            ROOT / "packaging" / "windows" / "lumos_portable.spec",
            ROOT / "packaging" / "windows" / "README.md",
            ROOT / "packaging" / "windows" / "beta_package" / "README_FIRST.md",
            ROOT / "packaging" / "windows" / "beta_package" / "RELEASE_NOTES.md",
            ROOT / "packaging" / "windows" / "beta_package" / "KNOWN_ISSUES.md",
            ROOT / "packaging" / "windows" / "beta_package" / "PRIVACY_NOTES.md",
            ROOT / "packaging" / "windows" / "beta_package" / "FEEDBACK_GUIDE.md",
        ]
        assert all(path.exists() for path in web_files), web_files
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "상용 제품화 로드맵" in readme
        assert "계정 상태" in readme
        assert "로컬 모드" in readme
        assert "docs/product/production_readiness_architecture.md" in readme
        assert "docs/product/auth_api_contract.md" in readme
        assert "docs/product/local_token_storage_policy.md" in readme
        assert "docs/product/auth_ui_wireframe.md" in readme
        assert "docs/product/implementation_roadmap.md" in readme
        assert "안정 데모 모드" in readme
        assert "python run.py cloud" in readme
        assert "data/cloud_lumos.db" in readme
        assert "/auth/dev-login" in readme
        assert "docs/qa/cloud_auth_service_qa.md" in readme
        assert "docs/qa/local_cloud_dev_connection_qa.md" in readme
        assert "docs/qa/entitlement_cache_offline_grace_qa.md" in readme
        assert "docs/product/entitlement_cache_offline_grace.md" in readme
        assert "docs/qa/entitlement_gate_integration_qa.md" in readme
        assert "docs/product/entitlement_gate_policy.md" in readme
        assert "docs/product/pricing_validation_plan.md" in readme
        assert "docs/product/landing_copy.md" in readme
        assert "Closed Beta & Download Readiness" in readme
        assert "docs/product/closed_beta_intake_plan.md" in readme
        assert "docs/product/download_readiness_checklist.md" in readme
        assert "docs/qa/closed_beta_intake_download_readiness_qa.md" in readme
        assert "Windows Portable Build Prototype" in readme
        assert "packaging/windows/build_portable.ps1" in readme
        assert "src/app/portable_entry.py" in readme
        assert "docs/product/windows_portable_build_plan.md" in readme
        assert "docs/qa/windows_portable_build_qa.md" in readme
        assert "Closed Beta Portable Manual QA" in readme
        assert "docs/qa/closed_beta_portable_manual_qa.md" in readme
        assert "Closed Beta Cohort 1 Launch Readiness" in readme
        assert "docs/product/cohort1_launch_pack.md" in readme
        assert "docs/qa/closed_beta_cohort1_launch_readiness.md" in readme
        assert "Closed Beta Cohort 1 Canary Run" in readme
        assert "docs/product/canary_feedback_form.md" in readme
        assert "docs/product/canary_run_checklist.md" in readme
        assert "docs/qa/cohort1_canary_run.md" in readme
        assert "현재 판단: pending" in readme
        assert "http://127.0.0.1:8000/pricing" in readme
        assert "/api/v1/product/gates/status" in readme
        assert "/api/v1/product/cloud/dev-connect" in readme
        assert "python run.py demo-reset" in readme
        assert "python run.py demo-seed" in readme
        assert "python run.py demo-companion" in readme
        response = client.get("/app")
        assert response.status_code == 200, response.text
        assert "오늘 꼭 봐야 할 신호" in response.text
        assert "30초만 설정하면 바로 시작할 수 있어요" in response.text
        assert "오늘의 신호 받기" in response.text
        assert "계정" in response.text
        assert "로컬 모드" in response.text
        assert "개발용 Cloud 연결 테스트" in response.text
        assert "사용량 이벤트 테스트" in response.text
        assert "토큰 저장" in response.text
        assert "권한 확인" in response.text
        assert "Grace 만료" in response.text
        assert "요금제별 기능 안내" in response.text
        assert "signal-count-gate-note" in response.text
        response = client.get("/")
        assert response.status_code == 200, response.text
        assert "오늘 봐야 할 3개의 신호" in response.text
        assert "실제 결제" in response.text
        assert 'href="/beta"' in response.text
        assert 'href="/pricing"' in response.text
        assert 'href="/app"' in response.text
        response = client.get("/pricing")
        assert response.status_code == 200, response.text
        assert "월 9,900원" in response.text
        assert "실제 결제 버튼은 아직 제공하지 않습니다" in response.text
        assert "Pro 관심 있음" in response.text
        assert "checkout" not in response.text.lower()
        response = client.get("/download")
        assert response.status_code == 200, response.text
        assert "Windows portable alpha build" in response.text
        assert "실제 다운로드 파일을 제공하지 않습니다" in response.text
        assert "canary tester 1명" in response.text
        assert "code signing" in response.text
        response = client.get("/beta")
        assert response.status_code == 200, response.text
        assert "이메일 수집 backend는 없습니다" in response.text
        assert "신청 질문 복사하기" in response.text
        assert "LUMOS Closed Beta 신청" in response.text
        assert "mailto:" in response.text
        assert "canary tester 1명" in response.text
        assert "SmartScreen" in response.text
        package_readme = (ROOT / "packaging" / "windows" / "beta_package" / "README_FIRST.md").read_text(encoding="utf-8")
        package_known = (ROOT / "packaging" / "windows" / "beta_package" / "KNOWN_ISSUES.md").read_text(encoding="utf-8")
        package_privacy = (ROOT / "packaging" / "windows" / "beta_package" / "PRIVACY_NOTES.md").read_text(encoding="utf-8")
        beta_templates = (ROOT / "docs" / "product" / "beta_email_templates.md").read_text(encoding="utf-8")
        feedback_tracker = (ROOT / "docs" / "product" / "beta_feedback_tracker.md").read_text(encoding="utf-8")
        launch_pack = (ROOT / "docs" / "product" / "cohort1_launch_pack.md").read_text(encoding="utf-8")
        readiness = (ROOT / "docs" / "qa" / "closed_beta_cohort1_launch_readiness.md").read_text(encoding="utf-8")
        canary_form = (ROOT / "docs" / "product" / "canary_feedback_form.md").read_text(encoding="utf-8")
        canary_checklist = (ROOT / "docs" / "product" / "canary_run_checklist.md").read_text(encoding="utf-8")
        canary_qa = (ROOT / "docs" / "qa" / "cohort1_canary_run.md").read_text(encoding="utf-8")
        assert "http://127.0.0.1:8000/app" in package_readme
        assert "SmartScreen" in package_known
        assert "data/" in package_privacy
        assert "token" in package_privacy
        assert "[LUMOS Canary] 첫 실행 테스트 부탁드립니다" in beta_templates
        assert "Cohort 1 선정 및 다운로드 안내" in beta_templates
        assert "설치 문제 발생 시 답장 템플릿" in beta_templates
        assert "3일 후 follow-up" in beta_templates
        assert "7일 후 가격/재사용 의향 follow-up" in beta_templates
        assert "canary_id" in feedback_tracker
        assert "artifact_sha256" in feedback_tracker
        assert "python_installed" in feedback_tracker
        assert "install_notes" in feedback_tracker
        assert "must_fix_before_cohort1" in feedback_tracker
        assert "cohort1_ready" in feedback_tracker
        assert "pass_to_cohort1" in feedback_tracker
        assert "smartscreen_seen" in feedback_tracker
        assert "antivirus_warning" in feedback_tracker
        assert "cohort_decision" in feedback_tracker
        assert "2074F5780806D71703D6A5D581A5708B10A41A1C1479EF60C021D143621084C5" in launch_pack
        assert "Canary Before Cohort 1" in launch_pack
        assert "actual canary result: not received" in launch_pack
        assert "Almost ready" in readiness
        assert "Python이 설치되어 있나요?" in canary_form
        assert "최신 SHA256 확인" in canary_checklist
        assert "Pending actual canary result" in canary_qa
        assert "actual canary tester result has not been provided yet" in canary_qa.lower()
        response = client.get("/landing-static/landing.js")
        assert response.status_code == 200, response.text
        assert "data-copy-template" in response.text
        assert "navigator.clipboard" in response.text
        response = client.get("/static/styles.css")
        assert response.status_code == 200, response.text
        assert "--color-primary" in response.text
        app_js = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        assert "detectFirstRun" in app_js
        assert "display_title_ko" in app_js
        assert "display_summary_ko" in app_js
        assert "원문 제목" in app_js
        assert "원문 snippet" in app_js
        assert "브리핑 참고 정보" in app_js
        assert "아직 오늘의 신호가 없어요." in app_js
        assert "아직 추천 기준이 충분하지 않아요." in app_js
        assert "안정 모드" in app_js
        assert "혼합 모드" in app_js
        assert "실제 소스 모드" in app_js
        assert "#settings" in app_js
        assert "#activity" in app_js
        assert "#sources" in app_js
        assert "#interests" in app_js
        assert "#today" in app_js
        assert "#signals" in app_js
        assert "hashchange" in app_js
        assert "tabFromHash" in app_js
        assert "setActiveTab" in app_js
        assert "mockAuth" in app_js
        assert "Mock Free 계정" in app_js
        assert "Mock Pro 계정" in app_js
        assert "renderAccountShell" in app_js
        assert "/api/v1/product/cloud/dev-connect" in app_js
        assert "/api/v1/product/cloud/dev-disconnect" in app_js
        assert "/api/v1/product/cloud/usage-test" in app_js
        assert "python run.py cloud" in app_js
        assert "formatTokenStorage" in app_js
        assert "formatEntitlementCacheStatus" in app_js
        assert "/api/v1/product/gates/status" in app_js
        assert "renderGateSummary" in app_js
        assert "renderSignalCountGateNote" in app_js
        assert "is_enforced=false" not in app_js
        assert "localStorage" not in app_js
        assert "sessionStorage" not in app_js
        assert "history.replaceState(null, \"\", tabToHash.signals)" in app_js
        assert "mock mode" not in app_js.lower()
        assert "hybrid mode" not in app_js.lower()
        assert "live mode" not in app_js.lower()
        companion_source = (ROOT / "src" / "desktop" / "companion_window.py").read_text(encoding="utf-8")
        assert "LUMOS Companion" in companion_source
        assert "Cloud 연결은 설정 화면에서 확인할 수 있어요." in companion_source
        assert "계정: 로컬 모드" in companion_source
        assert "작은 도우미" in companion_source
        assert "오늘의 신호 열기" in companion_source
        assert "새 신호 준비하기" in companion_source
        assert "개인 맥락 동기화" in companion_source
        assert "설정 화면 열기" in companion_source
        assert "활동 기록 보기" in companion_source
        assert "Companion 닫기" in companion_source
        assert "서버 상태" not in companion_source
        assert "pipeline run started" not in companion_source
        assert "connection error" not in companion_source
        assert "generate mode" not in companion_source.lower()

        response = client.get("/api/v1/settings")
        assert response.status_code == 200, response.text
        assert response.json()["settings"]["signal_count"] == 3

        response = client.post("/api/v1/sources/configs/seed-defaults", json={"overwrite": False})
        assert response.status_code == 200, response.text
        seeded_configs = response.json()["configs"]
        assert any(config["source_id"] == "hackernews" and config["enabled"] for config in seeded_configs)

        response = client.get("/api/v1/sources/catalog")
        assert response.status_code == 200, response.text
        catalog = response.json()["sources"]
        hn_catalog = next(item for item in catalog if item["source_id"] == "hackernews")
        assert hn_catalog["implemented_status"] == "implemented"
        assert "current_enabled" in hn_catalog

        response = client.get("/api/v1/sources/configs")
        assert response.status_code == 200, response.text
        configs = response.json()["configs"]
        assert any(config["source_id"] == "rss" for config in configs)
        assert any(config["source_id"] == "github" and config["enabled"] for config in configs)

        response = client.put("/api/v1/settings", json={"signal_count": 5})
        assert response.status_code == 200, response.text
        assert response.json()["settings"]["signal_count"] == 5
        response = client.put(
            "/api/v1/settings",
            json={"sync_before_briefing": True, "context_sync_interval_minutes": 15, "max_interest_keywords": 12},
        )
        assert response.status_code == 200, response.text
        sync_settings = response.json()["settings"]
        assert sync_settings["sync_before_briefing"] is True
        assert sync_settings["context_sync_interval_minutes"] == 15
        assert sync_settings["max_interest_keywords"] == 12

        response = client.post(
            "/api/v1/onboarding",
            json={
                "role": "founder",
                "role_detail": "building LUMOS",
                "goals": ["daily trend signals"],
                "interest_types": ["AI agent", "developer tools"],
                "keywords": ["AI agent", "productivity", "workflow automation"],
                "preferred_signal_count": 4,
                "briefing_time": "08:30",
                "connectors": {"browser_history": True, "local_files": False},
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["settings"]["signal_count"] == 4

        sample_browser = [
            {"id": "b1", "title": "AI agent workflow automation research", "url": "https://example.com/ai-agent"},
            {"id": "b2", "title": "Productivity startup briefing tools", "url": "https://example.com/productivity"},
        ]
        browser_result = BrowserHistoryConnector().sync({"sample_items": sample_browser}, limit=10)
        assert browser_result.items and browser_result.keywords

        sample_folder = Path(tmpdir.name) / "context_docs"
        sample_folder.mkdir()
        sample_file = sample_folder / "notes.md"
        sample_file.write_text("AI agent research automation and personalized briefing workflow", encoding="utf-8")
        file_result = LocalFilesConnector().sync({"folders": [str(sample_folder)]}, limit=10)
        assert file_result.items and file_result.keywords

        response = client.put(
            "/api/v1/connectors/browser_history",
            json={"enabled": True, "config": {"sample_items": sample_browser}},
        )
        assert response.status_code == 200, response.text
        response = client.put(
            "/api/v1/connectors/local_files",
            json={"enabled": True, "config": {"folders": [str(sample_folder)]}},
        )
        assert response.status_code == 200, response.text
        response = client.post("/api/v1/context/sync", json={"connector_types": ["browser_history", "local_files"], "limit": 20})
        assert response.status_code == 200, response.text
        sync_body = response.json()["result"]
        assert sync_body["item_count"] >= 3, sync_body
        assert sync_body["keyword_count"] > 0, sync_body

        response = client.get("/api/v1/context/items")
        assert response.status_code == 200, response.text
        context_items = response.json()["items"]
        assert context_items and all(len(item["text_snippet"]) <= 1000 for item in context_items)
        item_count_before = len(store.get_context_items(limit=100))
        response = client.post("/api/v1/context/sync/local_files", json={"limit": 20})
        assert response.status_code == 200, response.text
        assert len(store.get_context_items(limit=100)) == item_count_before

        response = client.get("/api/v1/context/sync-runs")
        assert response.status_code == 200, response.text
        assert response.json()["runs"]

        response = client.get("/api/v1/interests")
        assert response.status_code == 200, response.text
        interests_after_sync = response.json()["interests"]
        assert any("agent" in item["keyword"] or "automation" in item["keyword"] for item in interests_after_sync)
        store.upsert_interest("mutedonlykeyword", "personal_context", 9.0, "manual", {"from": "smoke"})
        muted_keyword = "mutedonlykeyword"
        response = client.post(f"/api/v1/interests/{muted_keyword}/mute")
        assert response.status_code == 200, response.text
        assert response.json()["interest"]["status"] == "muted"
        response = client.post("/api/v1/routes/preview")
        assert response.status_code == 200, response.text
        planned_queries = " ".join(query["query"] for route in response.json()["routes"] for query in route["queries"])
        assert muted_keyword not in planned_queries
        response = client.post("/api/v1/context/sync", json={"connector_types": ["browser_history"], "limit": 20})
        assert response.status_code == 200, response.text
        response = client.get("/api/v1/interests", params={"include_muted": True, "limit": 200})
        muted_rows = [item for item in response.json()["interests"] if item["keyword"] == muted_keyword]
        assert muted_rows and muted_rows[0]["status"] == "muted"
        response = client.post(f"/api/v1/interests/{muted_keyword}/unmute")
        assert response.status_code == 200, response.text
        assert response.json()["interest"]["status"] == "active"

        response = client.put(
            "/api/v1/sources/configs/rss",
            json={
                "enabled": True,
                "priority": 85,
                "config_json": {
                    "feed_urls": ["https://example.com/feed.xml"],
                    "keywords": ["AI agent", "workflow automation"],
                    "language": "en",
                    "region": "global",
                },
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["config"]["config_json"]["feed_urls"] == ["https://example.com/feed.xml"]

        response = client.put("/api/v1/sources/configs/github", json={"enabled": False})
        assert response.status_code == 200, response.text
        assert response.json()["config"]["enabled"] is False

        response = client.post("/api/v1/routes/preview")
        assert response.status_code == 200, response.text
        route_body = response.json()
        selected_sources = set(route_body["selected_sources"])
        assert selected_sources.intersection({"github", "hackernews", "official_ai_blogs"}), route_body
        assert "github" not in selected_sources
        assert all(route.get("reason") for route in route_body["routes"])
        assert all(route.get("queries") for route in route_body["routes"])
        rss_routes = [route for route in route_body["routes"] if route["source"] == "rss"]
        assert rss_routes
        assert rss_routes[0]["queries"][0]["params"]["feed_urls"] == ["https://example.com/feed.xml"]

        assert desktop_main
        assert BriefingWindow
        assert SettingsWindow

        scheduler = DailyBriefingScheduler(store, notifier=lambda count: {"sent": False, "count": count})
        scheduled_result = scheduler.run_once(force=True, show_notification=False)
        assert scheduled_result["ran"] is True, scheduled_result
        assert scheduled_result["context_sync"]["ran"] is True, scheduled_result
        assert len(scheduled_result["signals"]) == 4, scheduled_result
        assert all(signal["status"] == "active" for signal in scheduled_result["signals"])
        scheduled_run = store.get_last_scheduled_briefing_run()
        assert scheduled_run and scheduled_run["triggered_by"] == "scheduler", scheduled_run

        second_scheduled_result = scheduler.run_once(force=True, show_notification=False)
        assert second_scheduled_result["ran"] is False, second_scheduled_result
        assert second_scheduled_result["reason"] == "already_completed"

        service = BriefingService(store)
        service.record_lifecycle_event("briefing_shown", {"pipeline_run_id": scheduled_run["id"], "signal_count": 4})
        service.record_lifecycle_event("briefing_dismissed", {"pipeline_run_id": scheduled_run["id"]})
        generated_by_service = service.generate_now(mode="mock")
        assert generated_by_service["generated"] is True
        service_feedback = service.record_feedback(scheduled_result["signals"][0]["id"], "opened", {"from": "service_smoke"})
        assert service_feedback["event_id"]
        assert service_feedback["updated_keywords"]
        tracked_signal = scheduled_result["signals"][0]
        tracked_keyword = tracked_signal["category"]
        store.mute_interest(tracked_keyword)
        tracked_feedback = service.record_feedback(tracked_signal["id"], "tracked", {"from": "reactivate_smoke"})
        assert tracked_feedback["updated_keywords"]
        assert any(item["keyword"] == tracked_keyword and item["status"] == "active" for item in store.get_interests(include_muted=True, limit=500))
        updated_settings = service.update_settings({"signal_count": 3, "briefing_time": "09:15", "generate_mode": "hybrid"})
        assert updated_settings["signal_count"] == 3
        assert updated_settings["briefing_time"] == "09:15"
        assert updated_settings["generate_mode"] == "hybrid"
        context = service.get_latest_briefing_context()
        assert "warnings" in context
        with store.connect() as conn:
            lifecycle_count = conn.execute(
                """
                SELECT COUNT(*) FROM feedback_events
                WHERE event_type IN ('briefing_ready', 'briefing_shown', 'briefing_dismissed', 'briefing_generate_clicked')
                """
            ).fetchone()[0]
        assert lifecycle_count >= 4
        service.update_settings({"signal_count": 4, "generate_mode": "mock"})
        prune_result = store.prune_interests(5)
        assert "muted" in prune_result

        response = client.post("/api/v1/collect/mock")
        assert response.status_code == 200, response.text
        collect_body = response.json()
        assert collect_body["pipeline_run_id"], collect_body
        assert collect_body["route_count"] > 0, collect_body
        assert collect_body["source_item_count"] > 0, collect_body
        first_item = collect_body["source_items"][0]
        assert first_item["pipeline_run_id"] == collect_body["pipeline_run_id"]
        assert first_item["dedupe_key"]
        assert first_item["source"]
        assert first_item["title"]
        assert first_item["metrics_json"]

        response = client.post("/api/v1/signals/generate")
        assert response.status_code == 200, response.text
        generated_body = response.json()
        first_generate_run_id = generated_body["pipeline_run_id"]
        assert first_generate_run_id, generated_body
        assert generated_body["generated_signal_count"] == 4, generated_body
        assert generated_body["top_candidates"], generated_body
        assert all(signal.get("why_it_matters") for signal in generated_body["signals"])
        assert all(signal.get("display_title_ko") for signal in generated_body["signals"])
        assert all(signal.get("display_summary_ko") for signal in generated_body["signals"])
        assert all(signal.get("why_it_matters_ko") for signal in generated_body["signals"])
        assert all(signal.get("recommendation_reason_ko") for signal in generated_body["signals"])
        assert all(signal.get("recommended_action_ko") for signal in generated_body["signals"])
        assert all(signal.get("original_title") for signal in generated_body["signals"])
        assert all("metadata_json" in signal for signal in generated_body["signals"])
        assert all(signal.get("pipeline_run_id") == first_generate_run_id for signal in generated_body["signals"])
        assert all(candidate.get("pipeline_run_id") == first_generate_run_id for candidate in generated_body["top_candidates"])

        source_item_count_after_first_generate = len(store.get_recent_source_items(limit=1000))
        candidate_count_after_first_generate = len(store.get_candidates(limit=1000))

        response = client.get("/api/v1/pipeline/runs")
        assert response.status_code == 200, response.text
        run_list = response.json()["runs"]
        assert any(run["id"] == first_generate_run_id for run in run_list), run_list

        response = client.get(f"/api/v1/pipeline/runs/{first_generate_run_id}")
        assert response.status_code == 200, response.text
        run_detail = response.json()["run"]
        assert run_detail["status"] == "completed", run_detail
        assert run_detail["route_count"] > 0, run_detail
        assert run_detail["source_item_count"] > 0, run_detail
        assert run_detail["candidate_count"] > 0, run_detail
        assert run_detail["signal_count"] == 4, run_detail

        response = client.post("/api/v1/signals/generate")
        assert response.status_code == 200, response.text
        second_generate_body = response.json()
        assert second_generate_body["generated_signal_count"] == 4, second_generate_body
        assert len(store.get_recent_source_items(limit=1000)) == source_item_count_after_first_generate
        assert len(store.get_candidates(limit=1000)) == candidate_count_after_first_generate

        COLLECTOR_OVERRIDES.clear()
        COLLECTOR_OVERRIDES.update({"hackernews": FakeCollector("hackernews"), "rss": FakeCollector("rss"), "github": FakeCollector("github")})
        response = client.put("/api/v1/sources/configs/hackernews", json={"enabled": True, "priority": 90})
        assert response.status_code == 200, response.text
        response = client.put("/api/v1/sources/configs/github", json={"enabled": True, "priority": 95})
        assert response.status_code == 200, response.text
        response = client.put("/api/v1/sources/configs/official_ai_blogs", json={"enabled": True, "config_json": {"feed_urls": []}})
        assert response.status_code == 200, response.text
        response = client.post("/api/v1/signals/generate", json={"mode": "hybrid", "replace_today": True})
        assert response.status_code == 200, response.text
        hybrid_body = response.json()
        assert hybrid_body["generated_signal_count"] == 4, hybrid_body
        assert "github" in hybrid_body["attempted_sources"], hybrid_body
        assert "github" in hybrid_body["successful_sources"], hybrid_body
        assert "official_ai_blogs" in hybrid_body["missing_config_sources"], hybrid_body
        hybrid_run = store.get_pipeline_run(hybrid_body["pipeline_run_id"])
        assert hybrid_run["summary_json"]["successful_sources"], hybrid_run
        assert "errors_by_source" in hybrid_run["summary_json"], hybrid_run
        assert "official_ai_blogs" in hybrid_run["summary_json"]["errors_by_source"], hybrid_run
        COLLECTOR_OVERRIDES.clear()

        signal_id = generated_body["signals"][0]["id"]
        response = client.get("/api/v1/signals/today")
        assert response.status_code == 200, response.text
        today_signals = response.json()["signals"]
        assert len([signal for signal in today_signals if signal["status"] != "archived"]) == 4

        response = client.post("/api/v1/signals/generate-mock")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == 4, body
        assert all(signal.get("display_title_ko") for signal in body["signals"])
        assert all(signal.get("display_summary_ko") for signal in body["signals"])

        response = client.post(
            f"/api/v1/signals/{signal_id}/feedback",
            json={"event_type": "tracked", "payload": {"from": "smoke"}},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["signal"]["status"] == "tracked"
        assert response.json()["data"]["updated_keywords"]

        response = client.get("/api/v1/interests")
        assert response.status_code == 200, response.text
        assert any(item["source"] == "feedback" for item in response.json()["interests"])

        print({
            "health": "ok",
            "selected_sources": sorted(selected_sources),
            "generated_count": generated_body["generated_signal_count"],
            "pipeline_run_id": first_generate_run_id,
            "hybrid_generated_count": hybrid_body["generated_signal_count"],
            "direct_mock_count": body["count"],
            "feedback": "tracked",
        })
    finally:
        app.dependency_overrides.clear()
        tmpdir.cleanup()


class FakeCollector(BaseCollector):
    def __init__(self, source_id: str):
        self.source_id = source_id

    def collect(self, queries: list[SourceQuery], limit: int) -> CollectorResult:
        items = []
        for index in range(max(1, limit)):
            query = queries[0] if queries else SourceQuery(source=self.source_id, query="AI agent")
            items.append(
                CollectedItem(
                    source=self.source_id,
                    source_item_id=f"{self.source_id}-{query.route_id}-{index}",
                    url=f"https://example.com/{self.source_id}/{index}",
                    title=f"AI agent workflow signal from {self.source_id} {index}",
                    summary="A fake collector item for hybrid pipeline testing.",
                    author="fake",
                    metrics_json={"score": 100 + index, "comments": 10 + index},
                    raw_json={"fake": True, "route": {"category": query.category}},
                    route_id=query.route_id,
                )
            )
        return CollectorResult(source=self.source_id, items=items)


def assert_collector_contracts():
    mock_result = MockCollector().collect(
        [SourceQuery(source="github", query="AI agent", route_id=1, route_date="2026-06-20", category="DEVELOPER_TECH")],
        limit=2,
    )
    mock_item = mock_result.item_dicts()[0]
    required = {
        "source",
        "source_item_id",
        "url",
        "title",
        "summary",
        "author",
        "published_at",
        "metrics_json",
        "raw_json",
        "collected_at",
        "dedupe_key",
    }
    assert required.issubset(mock_item.keys()), mock_item

    rss_xml = """<?xml version="1.0"?>
    <rss><channel><title>Sample Feed</title><item>
      <title>AI agent updates move into workflow automation</title>
      <link>https://example.com/rss/ai-agent</link>
      <description>Short summary for RSS testing.</description>
      <pubDate>Sat, 20 Jun 2026 00:00:00 GMT</pubDate>
      <author>sample-author</author>
    </item></channel></rss>"""
    rss = RSSCollector(fetch_text=lambda url, timeout: rss_xml)
    rss_result = rss.collect([SourceQuery(source="rss", query="https://example.com/feed.xml")], limit=1)
    assert not rss_result.errors, rss_result.errors
    rss_item = rss_result.item_dicts()[0]
    assert required.issubset(rss_item.keys()), rss_item
    assert rss_item["source"] == "rss"

    def flaky_feed(url, timeout):
        if "bad" in url:
            raise RuntimeError("sample feed failure")
        return rss_xml

    rss_partial = RSSCollector(fetch_text=flaky_feed)
    partial_result = rss_partial.collect(
        [
            SourceQuery(source="rss", query="https://example.com/bad.xml"),
            SourceQuery(source="rss", query="https://example.com/good.xml"),
        ],
        limit=2,
    )
    assert partial_result.items, partial_result
    assert partial_result.warnings, partial_result

    story_time = 1781913600
    payloads = {
        "topstories.json": [101],
        "item/101.json": {
            "id": 101,
            "type": "story",
            "title": "AI agent tools gain developer traction",
            "url": "https://example.com/hn/101",
            "score": 123,
            "descendants": 45,
            "by": "hn-user",
            "time": story_time,
        },
    }

    def fake_hn_fetch(url, timeout):
        key = url.rsplit("/", 1)[-1]
        if key in payloads:
            return payloads[key]
        key = "/".join(url.rstrip("/").split("/")[-2:])
        return payloads[key]

    hn = HackerNewsCollector(fetch_json=fake_hn_fetch)
    hn_result = hn.collect([SourceQuery(source="hackernews", query="AI agent")], limit=1)
    assert not hn_result.errors, hn_result.errors
    hn_item = hn_result.item_dicts()[0]
    assert required.issubset(hn_item.keys()), hn_item
    assert hn_item["metrics_json"]["score"] == 123

    github_payload = {
        "items": [
            {
                "id": 42,
                "full_name": "example/ai-agent-toolkit",
                "html_url": "https://github.com/example/ai-agent-toolkit",
                "description": "Workflow automation tools for AI agents.",
                "owner": {"login": "example"},
                "pushed_at": "2026-06-19T00:00:00Z",
                "updated_at": "2026-06-19T00:00:00Z",
                "stargazers_count": 321,
                "forks_count": 12,
                "language": "Python",
                "open_issues_count": 3,
                "default_branch": "main",
                "archived": False,
            }
        ]
    }

    github = GitHubCollector(fetch_json=lambda url, timeout, headers: github_payload)
    github_result = github.collect([SourceQuery(source="github", query="AI agent")], limit=1)
    assert github_result.items, github_result
    github_item = github_result.item_dicts()[0]
    assert required.issubset(github_item.keys()), github_item
    assert github_item["metrics_json"]["stars"] == 321

    rate_limited = GitHubCollector(fetch_json=lambda url, timeout, headers: {"message": "API rate limit exceeded"})
    rate_result = rate_limited.collect([SourceQuery(source="github", query="AI agent")], limit=1)
    assert not rate_result.items
    assert rate_result.warnings


if __name__ == "__main__":
    main()
