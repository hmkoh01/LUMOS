from typing import Any, Dict, List

from src.context.keyword_extraction import extract_keywords
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore


def keywords_from_signal(signal: Dict[str, Any], max_keywords: int = 8) -> List[Dict[str, Any]]:
    """Legacy diagnostic helper; it does not persist or learn from text."""
    source_items = signal.get("source_items_json") or []
    source_titles = " ".join(str(item.get("title", "")) for item in source_items)
    text = " ".join(
        str(value) for value in (
            signal.get("title"), signal.get("summary"), signal.get("why_it_matters"),
            signal.get("category"), signal.get("source_name"), source_titles,
        ) if value
    )
    return extract_keywords(text, max_keywords=max_keywords)


def apply_feedback_learning(
    store: SQLiteStore,
    signal_id: int,
    event_type: str,
    payload: Dict[str, Any] = None,
    multiplier: float = 1.0,
    user_id: int = DEFAULT_LOCAL_USER_ID,
) -> List[str]:
    """Compatibility no-op while Stage 3 collects structured evidence.

    Explicit interests are user-owned.  Earlier versions adjusted their
    weights directly from one card reaction; that made a single accidental
    tap alter routing.  The feedback-preference detail store now retains
    evidence for a later, separately approved ranker instead.
    """
    return []
