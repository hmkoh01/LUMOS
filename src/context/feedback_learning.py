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


def apply_feedback_learning(store: SQLiteStore, signal_id: int, event_type: str, payload: Dict[str, Any] = None) -> List[str]:
    if not store.get_settings().get("auto_expand_interests", False):
        return []
    if event_type not in FEEDBACK_DELTAS or signal_id <= 0:
        return []
    signal = store.get_signal(signal_id)
    if not signal:
        return []
    delta = FEEDBACK_DELTAS[event_type]
    reactivate = event_type == "tracked"
    updated = []
    evidence = {
        "event_type": event_type,
        "signal_id": signal_id,
        "category": signal.get("category"),
        "payload": payload or {},
    }
    if signal.get("category"):
        store.adjust_interest_weight(
            signal["category"],
            delta=delta,
            category="signal_category",
            source="feedback",
            evidence=evidence,
            reactivate=reactivate,
        )
        updated.append(signal["category"])
    if signal.get("source_name"):
        store.adjust_interest_weight(
            signal["source_name"],
            delta=delta * 0.5,
            category="signal_source",
            source="feedback",
            evidence=evidence,
            reactivate=reactivate,
        )
        updated.append(signal["source_name"])
    for item in keywords_from_signal(signal):
        keyword = item["keyword"]
        store.adjust_interest_weight(
            keyword,
            delta=delta * float(item.get("score", 1.0)),
            category="feedback_keyword",
            source="feedback",
            evidence={**evidence, "keyword": item},
            reactivate=reactivate,
        )
        updated.append(keyword)
    return updated
