"""Per-item public-content licence decisions.

This module deliberately does not fetch, cache, or persist page bodies.  It
turns an already-authorised, short-lived rights-page inspection into a small
provenance record that the collector and briefing gate can consume.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Optional


_KOGL = "\uacf5\uacf5\ub204\ub9ac"
_TYPE = "\uc81c"
_TYPE_SUFFIX = "\uc720\ud615"
_AI_TRAINING = "\uc778\uacf5\uc9c0\ub2a5 \ud559\uc2b5 \uac00\ub2a5"
_TYPE_PATTERN = re.compile(rf"{_TYPE}\s*([0-4])\s*{_TYPE_SUFFIX}", re.I)
_AI_MARKERS = (_AI_TRAINING, "AI \uc720\ud615", "AI\uc720\ud615")
_OPEN_MARK_PATTERN = re.compile(r"<div[^>]*class=[\"'][^\"']*open_mark[^\"']*[\"'][^>]*>([\s\S]{0,2400}?)</div>", re.I)
_PUBLICATION_LABELS = ("\ub4f1\ub85d\uc77c", "\uc791\uc131\uc77c", "\uac8c\uc2dc\uc77c", "\ubc1c\ud589\uc77c")
_MODIFIED_LABELS = ("\uc218\uc815\uc77c", "\ucd5c\uc885\uc218\uc815")
_NOT_NEW_OPPORTUNITY = ("\uc120\uc815\uacb0\uacfc", "\uc11c\ub958\uc804\ud615 \ud569\uaca9", "\uba74\uc811\uc77c\uc815", "\ud569\uaca9\uc790 \uacf5\uace0")


def decode_rights_document(payload: bytes, content_type: str = "") -> str:
    """Decode a rights page without persisting its body.

    Government sites may serve a legacy Korean charset.  Failing closed is
    essential here: an undecodable KOGL marker must never look like a missing
    restriction or turn into an approval.
    """
    candidates = []
    header = re.search(r"charset\s*=\s*['\"]?([^;'\"\s]+)", content_type or "", re.I)
    if header:
        candidates.append(header.group(1))
    declaration = re.search(br"<meta[^>]+charset=[\"']?([^\"'\s/>]+)", payload[:4096], re.I)
    if declaration:
        candidates.append(declaration.group(1).decode("ascii", errors="ignore"))
    candidates.extend(["utf-8", "euc-kr", "cp949"])
    for encoding in dict.fromkeys(value for value in candidates if value):
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def extract_msit_published_at(html: str) -> Optional[str]:
    """Extract an explicitly labelled MSIT publication date, never a revision.

    The function returns a date only when a publication label occurs in the
    same compact metadata area as the date.  Dates found in article prose,
    attachment filenames, or modification fields remain unknown.
    """
    plain = re.sub(r"<[^>]+>", " ", html or "")
    plain = re.sub(r"\s+", " ", plain)
    date_pattern = re.compile(r"(20\d{2})\s*(?:[.\-/]|\ub144)\s*(\d{1,2})\s*(?:[.\-/]|\uc6d4)\s*(\d{1,2})(?:\uc77c)?")
    for match in date_pattern.finditer(plain):
        context = plain[max(0, match.start() - 120):match.end() + 40]
        if any(label in context for label in _MODIFIED_LABELS):
            continue
        if any(label in context for label in _PUBLICATION_LABELS):
            year, month, day = map(int, match.groups())
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
    return None


def classify_opportunity_status(title: str) -> str:
    """Avoid presenting selection/interview notices as fresh opportunities."""
    normalized = " ".join(str(title or "").casefold().split())
    if any(term in normalized for term in _NOT_NEW_OPPORTUNITY):
        return "not_new_opportunity"
    return "unknown"


def assess_kogl_page(
    html: str,
    *,
    evidence_url: str,
    publisher: str,
    title: str,
    published_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a conservative, item-level decision from a public page.

    A KOGL AI mark is deliberately informational only.  It applies to AI
    *training data*, while LUMOS performs inference/summarisation; the normal
    KOGL type determines whether commercial derivative use is allowed.
    """
    raw_html = html or ""
    plain = re.sub(r"<[^>]+>", " ", raw_html)
    plain = re.sub(r"\s+", " ", plain)
    # MSIT's per-post licence lives in a dedicated ``open_mark`` block near
    # the article footer.  Looking elsewhere would mistake a site-wide footer
    # or menu explanation for this item's licence.
    licence_blocks = [block for block in _OPEN_MARK_PATTERN.findall(raw_html) if _KOGL.casefold() in block.casefold()]
    # The fallback exists for a compact fixture or a publisher that puts the
    # mark in a single image tag.  MSIT pages with ``open_mark`` never use it,
    # so their global footer text cannot qualify a post.
    evidence_text = " ".join(licence_blocks) if licence_blocks else raw_html
    match = _TYPE_PATTERN.search(evidence_text)
    license_type = match.group(1) if match else None
    ai_training_marked = any(marker.casefold() in evidence_text.casefold() for marker in _AI_MARKERS)
    year = (published_at or "")[:4] or str(date.today().year)
    attribution = (
        f"\ucd9c\ucc98: {publisher}, \u300c{title}\u300d ({year}), {evidence_url}, "
        f"{_KOGL} {_TYPE}{license_type}{_TYPE_SUFFIX}"
        if license_type is not None else None
    )

    decision: Dict[str, Any] = {
        "checked": True,
        "rights_evidence_url": evidence_url,
        "license_family": "KOGL" if license_type is not None else None,
        "license_type": int(license_type) if license_type is not None else None,
        "ai_training_marked": ai_training_marked,
        # This flag is not an inference/summarisation permission.
        "ai_training_scope": "training_data_only" if ai_training_marked else "not_marked",
        "attribution_required": license_type not in (None, "0"),
        "attribution_text": attribution,
        # Never include assets not separately assessed from the page itself.
        "excluded_assets": ["third_party_photos", "attachments", "embedded_external_materials"],
        "body_storage": "not_assessed",
        "llm_input": "not_allowed",
        "ai_summary": "not_allowed",
        "user_delivery": "metadata_link_only",
        "recommendation_eligible": False,
        "reason": "No item-level KOGL licence was found.",
    }
    if license_type == "0":
        decision.update({
            "llm_input": "allowed_for_inference_with_provider_review",
            "ai_summary": "allowed",
            "user_delivery": "allowed",
            "recommendation_eligible": True,
            "reason": "KOGL Type 0 found; no attribution condition is recorded.",
        })
    elif license_type == "1":
        decision.update({
            "llm_input": "allowed_for_inference_with_attribution_and_provider_review",
            "ai_summary": "allowed_with_attribution",
            "user_delivery": "allowed_with_attribution",
            "recommendation_eligible": True,
            "reason": "KOGL Type 1 permits commercial and derivative use with attribution.",
        })
    elif license_type in {"2", "3", "4"}:
        decision["reason"] = (
            f"KOGL Type {license_type} has a commercial-use and/or modification restriction; "
            "do not create an LLM summary without separate permission."
        )
    return decision


def item_allows_llm(item: Dict[str, Any]) -> bool:
    """Require an explicit per-item decision for sources that demand one."""
    raw = item.get("raw_json") or {}
    if not raw.get("requires_post_rights"):
        return True
    rights = raw.get("content_rights") or {}
    return bool(rights.get("recommendation_eligible")) and str(rights.get("llm_input", "")).startswith("allowed_")


def item_allows_delivery(item: Dict[str, Any]) -> bool:
    raw = item.get("raw_json") or {}
    if not raw.get("requires_post_rights"):
        return True
    rights = raw.get("content_rights") or {}
    return bool(rights.get("recommendation_eligible")) and str(rights.get("user_delivery", "")).startswith("allowed")
