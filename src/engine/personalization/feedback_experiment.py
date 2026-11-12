"""Offline-only ranking experiment for accumulated card feedback.

This module is deliberately not imported by the production Engine service.
It consumes only the structured details recorded after a reader explicitly
rates a card and produces an explainable score comparison for evaluation.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from src.engine.models import KoreanBriefing, RawCandidate, ScoredCandidate
from src.engine.personalization.ranker import personalise_rankings
from src.storage.sqlite_store import SQLiteStore


MIN_DISTINCT_SIGNALS = 3
MAX_SCORE_ADJUSTMENT = 0.12
RECENT_DAYS = 90
# This experiment is intentionally not wired into Engine v2.  A future
# approved rollout must opt in explicitly rather than inheriting a default.
FEEDBACK_RANKING_EXPERIMENT_ENABLED = False


def feedback_experiment_opt_in_allowed(user_id: int, env: Mapping[str, str] | None = None) -> bool:
    """Future Canary gate only; no Engine path calls this in Stage 3.

    Both the global flag and an explicit, comma-separated user allow-list must
    be present.  A user control by itself never enables production ranking.
    """
    values = env if env is not None else os.environ
    enabled = str(values.get("LUMOS_FEEDBACK_RANKING_EXPERIMENT_ENABLED", "")).strip().lower()
    allowed = {item.strip() for item in str(values.get("LUMOS_FEEDBACK_RANKING_EXPERIMENT_USER_IDS", "")).split(",") if item.strip()}
    return enabled in {"1", "true", "yes", "on"} and str(user_id) in allowed


@dataclass(frozen=True)
class FeedbackPreferenceRule:
    feature: str
    value: str
    adjustment: float
    evidence_count: int
    reason_codes: tuple[str, ...]


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _recency_weight(value: object, now: datetime) -> float:
    recorded = _parse_timestamp(value)
    if not recorded:
        return 0.35
    age_days = max(0.0, (now - recorded).total_seconds() / 86400)
    if age_days <= 30:
        return 1.0
    if age_days >= RECENT_DAYS:
        return 0.25
    return 1.0 - (age_days - 30) * (0.75 / (RECENT_DAYS - 30))


def _candidate_values(candidate: RawCandidate) -> Dict[str, set[str]]:
    metrics = candidate.metrics or {}
    topics = metrics.get("topic_tags") or metrics.get("matched_keywords") or candidate.matched_interests or []
    if isinstance(topics, str):
        topics = [topics]
    information_types = metrics.get("information_type_ids") or []
    if isinstance(information_types, str):
        information_types = [information_types]
    return {
        "topic": {str(item).casefold() for item in topics if str(item).strip()},
        "difficulty": {str(metrics.get("difficulty") or metrics.get("difficulty_level") or "unknown").casefold()},
        "information_type": {str(item).casefold() for item in information_types if str(item).strip()},
        "novelty": {str(metrics.get("novelty") or "unknown").casefold()},
        "specificity": {str(metrics.get("specificity") or "unknown").casefold()},
    }


def _rule_targets(detail: Dict[str, Any]) -> Iterable[tuple[str, str, float]]:
    """Return only feature-specific effects; broad interests are never targets."""
    preference = detail.get("preference")
    reason = detail.get("reason_code")
    sign = 1.0 if preference == "tracked" else -1.0
    topics = [str(value).casefold() for value in detail.get("topic_tags_json") or [] if str(value).strip()]
    types = [str(value).casefold() for value in detail.get("information_type_ids_json") or [] if str(value).strip()]
    if reason == "unrelated_subtopic":
        yield from (("topic", value, -1.0) for value in topics)
    elif reason == "too_technical":
        yield "difficulty", "advanced", -1.0
    elif reason == "already_known":
        yield "novelty", "new", 1.0
    elif reason == "not_needed_now":
        yield from (("information_type", value, -1.0) for value in types)
    elif reason == "too_general":
        yield "specificity", "specific", 1.0
    elif reason in {"directly_relevant", "practical_useful"}:
        yield from (("topic", value, sign) for value in topics)
    elif reason == "easy_to_understand":
        yield "difficulty", "beginner", sign
    elif reason == "timely":
        yield "novelty", "new", sign


def derive_feedback_rules(
    details: Sequence[Dict[str, Any]], *, now: datetime | None = None,
    min_distinct_signals: int = MIN_DISTINCT_SIGNALS,
    reset_at: object = None,
    rule_resets: Sequence[Dict[str, Any]] = (),
) -> List[FeedbackPreferenceRule]:
    """Create conservative rules only from repeated, non-conflicting evidence."""
    now = now or datetime.now(timezone.utc)
    evidence: Dict[tuple[str, str], List[tuple[float, str, str, str]]] = {}
    global_reset = _parse_timestamp(reset_at)
    reset_markers = {
        (str(marker.get("feature") or "").casefold(), str(marker.get("value") or "").casefold()): _parse_timestamp(marker.get("reset_at"))
        for marker in rule_resets
    }
    for detail in details:
        signal_id = str(detail.get("signal_id") or "")
        if not signal_id:
            continue
        evaluated_at = detail.get("updated_at") or detail.get("evaluated_at")
        evaluated = _parse_timestamp(evaluated_at)
        if global_reset and (not evaluated or evaluated <= global_reset):
            continue
        recency = _recency_weight(evaluated_at, now)
        for feature, value, direction in _rule_targets(detail):
            if not value or value == "unknown":
                continue
            key = (feature.casefold(), value.casefold())
            rule_reset = reset_markers.get(key)
            if rule_reset and (not evaluated or evaluated <= rule_reset):
                continue
            # Reactions to a cluster of very similar cards in one briefing do
            # not carry the same confidence as reactions across separate runs.
            unit = str(detail.get("pipeline_run_id") or f"signal:{signal_id}")
            evidence.setdefault(key, []).append((direction * recency, signal_id, str(detail.get("reason_code") or ""), unit))

    rules = []
    for (feature, value), values in evidence.items():
        distinct = {signal_id for _, signal_id, _, _ in values}
        if len(distinct) < min_distinct_signals:
            continue
        by_unit: Dict[str, List[float]] = {}
        for score, _, _, unit in values:
            by_unit.setdefault(unit, []).append(score)
        # Cap a briefing unit at one vote.  We retain distinct-card minimums,
        # but prevent a single run from producing a max-strength adjustment.
        total = sum(max(-1.0, min(1.0, sum(scores))) for scores in by_unit.values())
        magnitude = sum(min(1.0, sum(abs(score) for score in scores)) for scores in by_unit.values())
        # Mixed positive/negative evidence is inconclusive.  Do not invent a
        # preference just because one side happened slightly more often.
        if magnitude <= 0 or abs(total) / magnitude < 0.6:
            continue
        adjustment = max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, 0.04 * total))
        if abs(adjustment) < 0.01:
            continue
        rules.append(FeedbackPreferenceRule(
            feature=feature,
            value=value,
            adjustment=adjustment,
            evidence_count=len(distinct),
            reason_codes=tuple(sorted({reason for _, _, reason, _ in values if reason})),
        ))
    return sorted(rules, key=lambda rule: (-abs(rule.adjustment), rule.feature, rule.value))


def apply_feedback_experiment(
    scored_candidates: Sequence[ScoredCandidate], rules: Sequence[FeedbackPreferenceRule], *, enabled: bool = FEEDBACK_RANKING_EXPERIMENT_ENABLED,
) -> tuple[List[ScoredCandidate], List[Dict[str, Any]]]:
    """Return copies, preserving production scores unless explicitly enabled."""
    adjusted = [copy(item) for item in scored_candidates]
    diagnostics: List[Dict[str, Any]] = []
    if not enabled:
        return adjusted, diagnostics
    for scored in adjusted:
        values = _candidate_values(scored.candidate)
        effects = [rule for rule in rules if rule.value.casefold() in values.get(rule.feature, set())]
        raw_delta = sum(rule.adjustment for rule in effects)
        delta = max(-MAX_SCORE_ADJUSTMENT, min(MAX_SCORE_ADJUSTMENT, raw_delta))
        if delta:
            scored.importance_score += delta
            diagnostics.append({
                "dedupe_key": scored.candidate.dedupe_key,
                "score_delta": round(delta, 4),
                "evidence": [
                    {"feature": rule.feature, "value": rule.value, "count": rule.evidence_count,
                     "reason_codes": list(rule.reason_codes)}
                    for rule in effects
                ],
            })
    return adjusted, diagnostics


def compare_feedback_rankings(
    store: SQLiteStore,
    user_id: int,
    scored_candidates: Sequence[ScoredCandidate],
    user_interests: List[str],
    *,
    ignored_dedupe_keys: set[str] | None = None,
    tracked_dedupe_keys: set[str] | None = None,
    briefings: Dict[str, KoreanBriefing] | None = None,
    display_limit: int = 5,
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Offline A/B comparison.  It never writes store state or activates sources."""
    ignored = ignored_dedupe_keys or set()
    tracked = tracked_dedupe_keys or set()
    briefing_map = briefings or {}
    baseline_input, _ = apply_feedback_experiment(scored_candidates, [], enabled=False)
    settings = store.get_feedback_learning_settings(user_id=user_id)
    rules = derive_feedback_rules(
        store.get_feedback_preference_details(user_id=user_id), now=now,
        reset_at=settings.get("reset_at"), rule_resets=store.get_feedback_learning_rule_resets(user_id=user_id),
    ) if settings.get("enabled", True) else []
    learned_input, diagnostics = apply_feedback_experiment(scored_candidates, rules, enabled=True)
    baseline = personalise_rankings(baseline_input, user_interests, ignored, tracked, briefing_map, display_limit=display_limit)
    learned = personalise_rankings(learned_input, user_interests, ignored, tracked, briefing_map, display_limit=display_limit)
    before = {item["dedupe_key"]: item["rank"] for item in baseline}
    after = {item["dedupe_key"]: item["rank"] for item in learned}
    return {
        "enabled": False,  # Backward-compatible: never live ranking.
        "production_enabled": False,
        "user_learning_enabled": bool(settings.get("enabled", True)),
        "experiment_applied": True,
        "rules": [rule.__dict__ for rule in rules],
        "baseline": baseline,
        "feedback_ranked": learned,
        "rank_changes": [
            {"dedupe_key": key, "before_rank": before.get(key), "after_rank": after.get(key)}
            for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)
        ],
        "diagnostics": diagnostics,
    }
