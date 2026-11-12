from datetime import date

from src.engine.config import EngineConfig
from src.engine.evaluation.scorer import evaluate_candidates
from src.engine.models import Period, RawCandidate


def test_upcoming_event_is_eligible_by_event_schedule_not_article_date():
    event = RawCandidate(
        dedupe_key="event", title="\uc9c0\uc5ed \ucd95\uc81c", published_at="2026-12-01T00:00:00",
        metrics={"content_kind": "culture_event", "event_status": "upcoming", "event_start_at": "2026-12-01", "event_end_at": "2026-12-03"},
    )
    scored = evaluate_candidates([event], Period.DAILY, ["\uc9c0\uc5ed \ubb38\ud654\ud589\uc0ac"], EngineConfig(), reference_date=date(2026, 11, 8))
    assert [item.candidate.dedupe_key for item in scored] == ["event"]


def test_ended_event_and_closed_opportunity_do_not_become_news_cards():
    candidates = [
        RawCandidate(dedupe_key="ended", title="\uc885\ub8cc \ucd95\uc81c", published_at="2026-11-08", metrics={"content_kind": "culture_event", "event_status": "ended"}),
        RawCandidate(dedupe_key="closed", title="\ub9c8\uac10 \uacf5\uace0", published_at="2026-11-08", metrics={"content_kind": "government_rnd_announcement", "application_window_status": "closed"}),
    ]
    assert evaluate_candidates(candidates, Period.DAILY, ["R&D"], EngineConfig(), reference_date=date(2026, 11, 8)) == []


def test_unknown_government_application_window_is_not_described_as_open():
    announcement = RawCandidate(
        dedupe_key="unknown", title="R&D \uc9c0\uc6d0\uc0ac\uc5c5 \uacf5\uace0", published_at="2026-11-08",
        metrics={"content_kind": "government_rnd_announcement", "application_window_status": "unknown"},
    )
    scored = evaluate_candidates([announcement], Period.DAILY, ["R&D"], EngineConfig(), reference_date=date(2026, 11, 8))
    assert scored
    assert scored[0].candidate.metrics["application_window_status"] == "unknown"
