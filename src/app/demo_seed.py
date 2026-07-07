import os
from pathlib import Path
from typing import Dict, List

from src.app.config import BASE_DIR, DEMO_DATABASE_PATH
from src.signals.pipeline import SignalPipeline
from src.storage.sqlite_store import SQLiteStore


DEMO_PERSONA = {
    "role": "예비 창업자 / PM",
    "role_detail": "AI와 생산성 툴 시장을 살피는 예비 창업자 / PM",
    "goals": ["창업 아이템 검증", "경쟁 서비스 탐색", "AI/생산성 툴 변화 감지"],
    "interest_types": ["AI agent", "생산성 툴", "스타트업", "GitHub 트렌드", "공식 블로그 업데이트"],
}

DEMO_INTERESTS = [
    ("AI agent", "AI_LLM_AGENT", 9.0),
    ("생산성 툴", "STARTUP_PRODUCT", 8.5),
    ("스타트업", "STARTUP_PRODUCT", 8.0),
    ("GitHub 트렌드", "DEVELOPER_TECH", 7.5),
    ("공식 블로그 업데이트", "COMPANY_TRACKING", 7.0),
    ("개인화 추천", "STARTUP_PRODUCT", 6.8),
    ("업무 자동화", "AI_LLM_AGENT", 6.5),
]

DEMO_ENABLED_SOURCES = ["official_ai_blogs", "hackernews", "github", "rss"]


def demo_db_path() -> Path:
    return DEMO_DATABASE_PATH


def set_demo_db_environment() -> Path:
    path = demo_db_path()
    os.environ["LUMOS_DB_PATH"] = str(path)
    return path


def reset_demo_db() -> Path:
    path = demo_db_path().resolve()
    data_dir = (BASE_DIR / "data").resolve()
    if data_dir not in path.parents:
        raise RuntimeError(f"데모 DB 경로가 data 폴더 밖에 있어 초기화를 중단했어요: {path}")

    for candidate in [path, Path(f"{path}-wal"), Path(f"{path}-shm")]:
        if candidate.exists():
            candidate.unlink()

    SQLiteStore(path)
    return path


def seed_demo_db(generate_signals: bool = True) -> Dict[str, object]:
    path = set_demo_db_environment()
    store = SQLiteStore(path)

    profile = store.upsert_profile(
        {
            **DEMO_PERSONA,
            "raw_onboarding": {
                "demo": True,
                "description": "발표/멘토링용 안정 데모 persona",
            },
        }
    )

    settings = store.update_settings(
        {
            "signal_count": 3,
            "briefing_time": "08:00",
            "generate_mode": "mock",
            "sync_before_briefing": False,
            "enabled_sources_json": DEMO_ENABLED_SOURCES,
            "enabled_connectors_json": {"browser_history": False, "local_files": False},
            "onboarding_completed": True,
            "mode_enabled": True,
        }
    )

    store.update_connector("browser_history", False, {})
    store.update_connector("local_files", False, {"folders": []})

    store.seed_default_source_configs(overwrite=True)
    for source_id in DEMO_ENABLED_SOURCES:
        store.upsert_source_config(source_id, enabled=True)
    for source_id in ["producthunt", "reddit", "youtube", "naver_news", "arxiv", "company_newsroom"]:
        store.upsert_source_config(source_id, enabled=False)

    for keyword, category, weight in DEMO_INTERESTS:
        store.upsert_interest(
            keyword=keyword,
            category=category,
            weight=weight,
            source="onboarding",
            evidence={
                "demo": True,
                "reason": "데모 persona가 매일 확인하고 싶은 주제로 설정했어요.",
            },
        )

    signals: List[Dict[str, object]] = []
    if generate_signals:
        result = SignalPipeline(store).generate_daily_signals(
            replace_today=True,
            triggered_by="demo_seed",
            mode="mock",
            run_type="demo_signal_generation",
        )
        signals = result.get("signals", [])

    return {
        "db_path": path,
        "profile": profile,
        "settings": settings,
        "interests": store.get_interests(limit=100),
        "sources": store.get_source_configs(),
        "signals": signals or store.get_today_signals(),
    }


def demo_db_exists() -> bool:
    return demo_db_path().exists()
