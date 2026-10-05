from typing import Any, Dict, List

from src.context.keyword_extraction import extract_keywords
from src.storage.sqlite_store import SQLiteStore


FEEDBACK_DELTAS = {
    "saved": 0.5,
    "tracked": 1.0,
    "ignored": -0.5,
    "opened": 0.2,
}


def keywords_from_signal(signal: Dict[str, Any], max_keywords: int = 8) -> List[Dict[str, Any]]:
    source_items = signal.get("source_items_json") or []
    source_titles = " ".join(str(item.get("title", "")) for item in source_items)
    text = " ".join(
        [
            signal.get("title", ""),
            signal.get("summary", ""),
            signal.get("why_it_matters", ""),
            signal.get("category", ""),
            signal.get("source_name", ""),
            source_titles,
        ]
    )
    return extract_keywords(text, max_keywords=max_keywords)


def apply_feedback_learning(
    store: SQLiteStore,
    signal_id: int,
    event_type: str,
    payload: Dict[str, Any] = None,
    multiplier: float = 1.0,
) -> List[str]:
    if event_type not in FEEDBACK_DELTAS or signal_id <= 0:
        return []
    signal = store.get_signal(signal_id)
    if not signal:
        return []
    delta = FEEDBACK_DELTAS[event_type] * multiplier
    updated = []
    evidence = {
        "event_type": event_type,
        "signal_id": signal_id,
        "category": signal.get("category"),
        "payload": payload or {},
    }
    keyword_scores = {
        str(item.get("keyword", "")).strip().casefold(): float(item.get("score", 1.0))
        for item in keywords_from_signal(signal)
        if str(item.get("keyword", "")).strip()
    }
    for value in (signal.get("category"), signal.get("source_name")):
        if value:
            keyword_scores.setdefault(str(value).strip().casefold(), 1.0)

    for interest in store.get_interests(status="active", limit=None):
        score = keyword_scores.get(str(interest.get("keyword", "")).casefold())
        if score is None:
            continue
        next_weight = max(0.1, min(10.0, float(interest.get("weight") or 1.0) + delta * score))
        store.update_interest(interest["keyword"], weight=next_weight)
        updated.append(interest["keyword"])
    return updated
