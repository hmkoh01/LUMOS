"""
Retrieval service for LUMOS Assistant.

Uses SQLite FTS5 for text search (with LIKE-based fallback).
Separated from LLM so it can be replaced with vector/embedding search.

Swap point: implement the RetrievalService Protocol with a
VectorRetrievalService that accepts the same interface.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Protocol, runtime_checkable


@dataclass
class RetrievedContext:
    signal_id: int
    title: str
    summary: str
    why_it_matters: str
    source_name: str
    source_url: str
    published_at: Optional[str]
    relevance_score: float       # signal's own confidence/relevance
    retrieval_score: float = 0.0  # combined ranking score
    is_selected: bool = False


@runtime_checkable
class RetrievalService(Protocol):
    def retrieve(
        self,
        query: str,
        user_id: int,
        period: str,
        selected_signal_id: Optional[int] = None,
        limit: int = 5,
    ) -> List[RetrievedContext]: ...


class SQLiteRetrievalService:
    """
    Retrieval using SQLite FTS5 + signal metadata ranking.

    Score = 0.4 * text_relevance + 0.3 * signal_confidence + 0.3 * recency

    Replace this class with VectorRetrievalService for embedding search.
    Both implement the RetrievalService Protocol.
    """

    _PERIOD_DAYS: dict = {"today": 1, "week": 7, "month": 30, "all": 3650}

    def __init__(self, store) -> None:
        self._store = store
        self._fts_ok: bool = self._check_fts()

    def _check_fts(self) -> bool:
        with self._store.connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE name='signals_fts' AND type='table'"
            ).fetchone()
            return row is not None

    # ── public ────────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        user_id: int,
        period: str,
        selected_signal_id: Optional[int] = None,
        limit: int = 5,
    ) -> List[RetrievedContext]:
        days = self._PERIOD_DAYS.get(period, 7)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        with self._store.connect() as conn:
            if period == "all":
                rows = conn.execute(
                    "SELECT * FROM signals WHERE user_id = ? AND status != 'archived'",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM signals
                    WHERE user_id = ?
                      AND status != 'archived'
                      AND created_at >= ?
                    """,
                    (user_id, cutoff),
                ).fetchall()

        if not rows:
            # period returned nothing; include selected signal regardless
            if selected_signal_id is not None:
                row = self._fetch_signal_for_user(selected_signal_id, user_id)
                if row:
                    return [self._to_context(dict(row), selected=True)]
            return []

        signals = {row["id"]: dict(row) for row in rows}
        signal_ids = list(signals.keys())

        text_scores = self._text_scores(query, signal_ids, signals)

        now = datetime.now(timezone.utc)
        results: List[RetrievedContext] = []
        for sid, signal in signals.items():
            t_score = text_scores.get(sid, 0.0)
            conf = float(signal.get("confidence") or 0.5)
            rec = self._recency_score(signal, now, days)
            combined = 0.4 * t_score + 0.3 * conf + 0.3 * rec

            # skip signals with no text relevance unless selected
            if t_score == 0.0 and sid != selected_signal_id:
                continue

            ctx = self._to_context(
                signal,
                selected=(sid == selected_signal_id),
                retrieval_score=combined,
            )
            results.append(ctx)

        # Guarantee selected signal is included even if outside period
        selected_present = any(x.is_selected for x in results)
        if selected_signal_id is not None and not selected_present:
            row = self._fetch_signal_for_user(selected_signal_id, user_id)
            if row:
                results.insert(0, self._to_context(dict(row), selected=True, retrieval_score=1.0))

        # If nothing passed the text-relevance filter, fall back to top-N by
        # recency + confidence so general queries ("이번 주 소식 알려줘") still
        # get context rather than returning empty.
        if not results:
            for sid, signal in signals.items():
                if sid == selected_signal_id:
                    continue
                conf = float(signal.get("confidence") or 0.5)
                rec = self._recency_score(signal, now, days)
                ctx = self._to_context(signal, retrieval_score=0.3 * conf + 0.7 * rec)
                results.append(ctx)

        results.sort(key=lambda x: (0 if x.is_selected else 1, -x.retrieval_score))
        return results[:limit]

    # ── internal helpers ──────────────────────────────────────────────────────

    def _fetch_signal_for_user(self, signal_id: int, user_id: int):
        with self._store.connect() as conn:
            return conn.execute(
                "SELECT * FROM signals WHERE id = ? AND user_id = ?",
                (signal_id, user_id),
            ).fetchone()

    def _text_scores(self, query: str, signal_ids: List[int], signals: dict) -> dict:
        if not query.strip():
            return {sid: 0.5 for sid in signal_ids}
        if self._fts_ok:
            scores = self._fts_scores(query, signal_ids)
            if scores:
                return scores
        return self._keyword_scores(query, signal_ids, signals)

    def _fts_scores(self, query: str, signal_ids: List[int]) -> dict:
        safe = self._sanitize_fts_query(query)
        if not safe or not signal_ids:
            return {}
        placeholders = ",".join("?" * len(signal_ids))
        try:
            with self._store.connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT rowid, bm25(signals_fts) AS score
                    FROM signals_fts
                    WHERE signals_fts MATCH ?
                      AND rowid IN ({placeholders})
                    ORDER BY bm25(signals_fts)
                    LIMIT 20
                    """,
                    [safe] + list(signal_ids),
                ).fetchall()
        except Exception:
            return {}
        if not rows:
            return {}
        raw = {row["rowid"]: float(row["score"]) for row in rows}
        min_s, max_s = min(raw.values()), max(raw.values())
        span = abs(min_s - max_s)
        if span < 1e-9:
            # All results scored identically (or only one result) — equally relevant
            return {sid: 1.0 for sid in raw}
        return {sid: abs(score - max_s) / span for sid, score in raw.items()}

    def _keyword_scores(self, query: str, signal_ids: List[int], signals: dict) -> dict:
        terms = self._terms(query)
        if not terms:
            return {}
        scores: dict = {}
        for sid in signal_ids:
            sig = signals.get(sid, {})
            # include Korean metadata fields in text pool
            meta = self._parse_json(sig.get("metadata_json"), {})
            text = " ".join([
                sig.get("title") or "",
                sig.get("summary") or "",
                sig.get("why_it_matters") or "",
                sig.get("source_name") or "",
                meta.get("display_title_ko") or "",
                meta.get("headline_summary_ko") or "",
                meta.get("original_title") or "",
            ])
            hits = len(terms & self._terms(text))
            if hits:
                scores[sid] = min(hits / max(len(terms), 1), 1.0)
        return scores

    @staticmethod
    def _terms(text: str) -> set:
        return {t.casefold() for t in re.findall(r"[\w가-힣]{2,}", text or "")}

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        clean = re.sub(r'["\'()\-*+:^~]', " ", query).strip()
        terms = [t for t in clean.split() if len(t) >= 2][:10]
        return " OR ".join(f'"{t}"' for t in terms) if terms else ""

    @staticmethod
    def _recency_score(signal: dict, now: datetime, window_days: int) -> float:
        raw = signal.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (now - dt).total_seconds() / 86400
            return max(0.0, 1.0 - age / max(window_days, 1))
        except (ValueError, TypeError):
            return 0.5

    def _to_context(
        self,
        signal: dict,
        selected: bool = False,
        retrieval_score: float = 0.0,
    ) -> RetrievedContext:
        meta = self._parse_json(signal.get("metadata_json"), {})
        return RetrievedContext(
            signal_id=signal["id"],
            title=(
                meta.get("display_title_ko")
                or signal.get("title")
                or ""
            ),
            summary=(
                meta.get("headline_summary_ko")
                or signal.get("summary")
                or ""
            ),
            why_it_matters=signal.get("why_it_matters") or "",
            source_name=signal.get("source_name") or "",
            source_url=signal.get("source_url") or "",
            published_at=self._published_at(signal),
            relevance_score=float(signal.get("confidence") or 0.5),
            retrieval_score=retrieval_score,
            is_selected=selected,
        )

    @staticmethod
    def _published_at(signal: dict) -> Optional[str]:
        meta = SQLiteRetrievalService._parse_json(signal.get("metadata_json"), {})
        if meta.get("published_at"):
            return str(meta["published_at"])
        items = SQLiteRetrievalService._parse_json(signal.get("source_items_json"), [])
        for item in items:
            if isinstance(item, dict) and item.get("published_at"):
                return str(item["published_at"])
        return signal.get("created_at")

    @staticmethod
    def _parse_json(raw, default):
        if not raw:
            return default
        if isinstance(raw, (dict, list)):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
