from datetime import date
from typing import Any, Dict, List

from src.signals.korean_briefing import build_korean_briefing
from src.storage.sqlite_store import SQLiteStore
from src.signals.identity import article_key
from src.signals.provenance import source_metadata
from src.sources.article_content import article_context
from src.signals.commercial_filter import commercial_context_reason


class SignalGenerator:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def generate_from_candidates(
        self,
        ranked_candidates: List[Dict[str, Any]],
        replace_today: bool = True,
        pipeline_run_id: int = None,
        archive_reason: str = None,
    ) -> List[Dict[str, Any]]:
        settings = self.store.get_settings()
        profile = self.store.get_profile() or {}
        interests = self.store.get_interests(limit=50)
        signal_count = max(1, int(settings.get("signal_count", 3)))

        if replace_today:
            self.store.archive_today_signals(reason=archive_reason)

        selected = []
        seen = set()
        for candidate in ranked_candidates:
            identity = article_key(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(candidate)
        selected = self._diversify_interest_matches(selected)
        if not replace_today:
            shown = {article_key(item) for item in self.store.get_today_active_signals()}
            selected = [item for item in selected if article_key(item) not in shown]
        active_interest_count = len({
            str(interest.get("keyword", "")).strip().casefold()
            for interest in interests
            if interest.get("status", "active") == "active" and str(interest.get("keyword", "")).strip()
        })
        primary_selected = self._select_distinct_interest_candidates(
            selected,
            signal_count,
            allow_repeats=active_interest_count <= 1,
        )
        # Diversity is a preference, not a reason to return fewer cards than
        # the user explicitly requested. When one interest has most of the
        # relevant evidence, fill the remaining slots with its next-best,
        # already de-duplicated candidates.
        if len(primary_selected) < signal_count:
            selected_ids = {id(candidate) for candidate in primary_selected}
            for candidate in selected:
                if id(candidate) in selected_ids:
                    continue
                primary_selected.append(candidate)
                selected_ids.add(id(candidate))
                if len(primary_selected) >= signal_count:
                    break
        primary_selected, excluded_ids = self._exclude_commercial_primary_candidates(
            primary_selected, selected, signal_count
        )
        primary_ids = {id(candidate) for candidate in primary_selected}
        reserve_candidates = [
            candidate for candidate in selected
            if id(candidate) not in primary_ids and id(candidate) not in excluded_ids
        ]
        if pipeline_run_id is not None:
            self.store.save_signal_reserves(pipeline_run_id, reserve_candidates, len(primary_selected))
        generated = []
        for rank, candidate in enumerate(primary_selected, start=1):
            signal_id = self.store.create_signal(
                self._build_signal(candidate, profile, interests, rank),
                pipeline_run_id=pipeline_run_id,
            )
            signal = self.store.get_signal(signal_id)
            if signal:
                generated.append(signal)
        return generated

    @staticmethod
    def _candidate_with_article_context(candidate: Dict[str, Any]) -> Dict[str, Any]:
        raw = candidate.get("raw_json") or {}
        context = article_context(candidate, allow_fetch=bool(raw.get("data_kind") == "live"))
        return {**candidate, "raw_json": {**raw, "article_context": context}}

    def _exclude_commercial_primary_candidates(
        self, primary: List[Dict[str, Any]], candidates: List[Dict[str, Any]], limit: int
    ) -> tuple[List[Dict[str, Any]], set]:
        """Read only proposed cards, then replace any product landing page.

        This keeps network use bounded to the requested number of cards plus
        replacements, instead of fetching every search candidate.
        """
        accepted, excluded_ids, considered = [], set(), set()
        for candidate in [*primary, *candidates]:
            candidate_id = id(candidate)
            if candidate_id in considered:
                continue
            considered.add(candidate_id)
            prepared = self._candidate_with_article_context(candidate)
            reason = commercial_context_reason(prepared, prepared["raw_json"]["article_context"])
            if reason:
                excluded_ids.add(candidate_id)
                continue
            accepted.append(prepared)
            if len(accepted) >= limit:
                break
        return accepted, excluded_ids

    @staticmethod
    def _diversify_interest_matches(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Keep score order where possible, while giving each interest a turn first."""
        remaining = list(candidates)
        selected = []
        covered_keywords = set()
        while remaining:
            next_index = next(
                (
                    index
                    for index, candidate in enumerate(remaining)
                    if any(keyword not in covered_keywords for keyword in SignalGenerator._matched_interest_keys(candidate))
                ),
                None,
            )
            candidate = remaining.pop(0 if next_index is None else next_index)
            selected.append(candidate)
            covered_keywords.update(SignalGenerator._matched_interest_keys(candidate))
        return selected

    @staticmethod
    def _select_distinct_interest_candidates(
        candidates: List[Dict[str, Any]], limit: int, allow_repeats: bool = False
    ) -> List[Dict[str, Any]]:
        selected = []
        covered_keywords = set()
        for candidate in candidates:
            matched = SignalGenerator._matched_interest_keys(candidate)
            if not allow_repeats and matched and matched.issubset(covered_keywords):
                continue
            selected.append(candidate)
            covered_keywords.update(matched)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _matched_interest_keys(candidate: Dict[str, Any]) -> set:
        matched = candidate.get("matched_keywords_json") or candidate.get("matched_keywords") or []
        return {str(keyword).strip().casefold() for keyword in matched if str(keyword).strip()}

    def _build_signal(
        self,
        candidate: Dict[str, Any],
        profile: Dict[str, Any],
        interests: List[Dict[str, Any]],
        rank: int,
    ) -> Dict[str, Any]:
        matched = candidate.get("matched_keywords_json") or []
        role = profile.get("role") or "your work"
        source = candidate.get("source", "mock")
        category = candidate.get("route_category") or candidate.get("category") or "trend"
        keyword_text = ", ".join(matched[:3]) if matched else "your saved interests"
        title = self._title(candidate)
        summary = self._summary(candidate)
        action = self._action(candidate, matched)
        context = article_context(candidate, allow_fetch=bool((candidate.get("raw_json") or {}).get("data_kind") == "live"))
        candidate = {**candidate, "raw_json": {**(candidate.get("raw_json") or {}), "article_context": context}}
        metadata = build_korean_briefing(
            title=title,
            summary=summary,
            source=source,
            category=category,
            matched_keywords=matched,
            role=role,
            action_hint=action,
            content_context=context,
        )
        metadata.update(source_metadata(candidate))
        return {
            "signal_date": date.today().isoformat(),
            "title": title,
            "summary": summary,
            "why_it_matters": (
                f"This matters for {role} because it matches {keyword_text} "
                f"and came from {source}, which was selected for {category} monitoring."
            ),
            "category": category,
            "recommended_action": action,
            "source_name": source,
            "source_url": candidate.get("url", ""),
            "source_items_json": [
                {
                    "source_item_id": candidate.get("source_item_id"),
                    "source": source,
                    "title": candidate.get("title"),
                    "summary": candidate.get("summary"),
                    "url": candidate.get("url"),
                    "score": candidate.get("score"),
                    "score_breakdown": candidate.get("score_breakdown_json"),
                    **source_metadata(candidate),
                }
            ],
            "metadata_json": metadata,
            "confidence": min(0.95, max(0.1, float(candidate.get("score", 0.5)))),
            "rank": rank,
            "status": "active",
        }

    def _title(self, candidate: Dict[str, Any]) -> str:
        return candidate.get("title") or "New signal detected"

    def _summary(self, candidate: Dict[str, Any]) -> str:
        summary = candidate.get("summary") or ""
        return summary[:500]

    def _action(self, candidate: Dict[str, Any], matched: List[str]) -> str:
        if matched:
            return f"Review this through the lens of {matched[0]} and decide whether to keep tracking it."
        return "Review this source item and decide whether it should become a tracked interest."
