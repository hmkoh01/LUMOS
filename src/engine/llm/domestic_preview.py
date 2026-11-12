"""Offline, metadata-only previews for domestic opportunity cards."""
from __future__ import annotations

import re
from typing import Any, Dict

from src.context.interest_matching import matches_interest
from src.sources.domestic_collection_strategy import support_program_matches_information_types


# Festival and exhibition are intentional event-type selections, unlike the
# broad culture/event labels; retain them as matching terms.
_CULTURE_GENERIC_TERMS = ("문화", "행사", "지역", "공연", "여행", "일정", "culture", "event", "performance", "travel")
_CULTURE_TERM_ALIASES = {"축제": ("축제", "페스티벌", "festival"), "festival": ("축제", "페스티벌", "festival")}


def _culture_terms(interest: str, preferred_region: str) -> list[str]:
    """Return concrete culture terms; a broad category never becomes a match."""
    text = str(interest or "").casefold().replace("·", " ").replace("/", " ")
    if preferred_region:
        text = text.replace(str(preferred_region).casefold(), " ")
    for generic in _CULTURE_GENERIC_TERMS:
        text = text.replace(generic, " ")
    return [part for part in re.findall(r"[0-9a-zA-Z가-힣]{2,}", text) if part]


def evaluate_personalised_item(
    item: Dict[str, Any],
    interest: str,
    *,
    preferred_region: str = "",
    selected_information_types: tuple[str, ...] = (),
) -> Dict[str, str]:
    """Strict metadata-only eligibility; category membership is not enough."""
    data = item.get("metrics_json") or {}
    kind = data.get("content_kind") or ""
    text = f"{item.get('title', '')} {item.get('author', '')}".casefold()
    needle = interest.casefold().strip()
    if not item.get("url"):
        return {"eligible": "false", "reason": "official_source_url_missing"}
    if kind in {"culture_event", "performance"}:
        if data.get("event_status") not in {"upcoming", "ongoing"}:
            return {"eligible": "false", "reason": "event_not_active"}
        if kind == "performance" and not data.get("official_detail_content_verified"):
            return {"eligible": "false", "reason": "official_detail_content_unverified"}
        if preferred_region and preferred_region.casefold() not in str(data.get("region") or "").casefold():
            return {"eligible": "false", "reason": "region_mismatch"}
    if kind == "corporate_disclosure" and needle and needle not in text:
        return {"eligible": "false", "reason": "company_or_industry_mismatch"}
    if kind in {"startup_program", "government_rnd_announcement"} and needle:
        # A broad provider category alone is not enough for a person's
        # startup-interest card: require a direct title, target, purpose or
        # programme-type connection.
        haystack = " ".join((str(item.get("title") or ""), str(data.get("support_target") or ""), str(data.get("purpose") or ""), str(data.get("support_type") or ""), str(data.get("region") or ""))).casefold()
        if not matches_interest(haystack, interest):
            return {"eligible": "false", "reason": "support_interest_mismatch"}
        if selected_information_types and not support_program_matches_information_types(item, selected_information_types):
            return {"eligible": "false", "reason": "support_information_type_mismatch"}
    if kind in {"job_posting", "public_institution_job", "public_service_job"} and needle:
        haystack = " ".join((str(item.get("title") or ""), str(item.get("author") or ""), str(data.get("job_type") or ""), str(data.get("region") or ""), str(data.get("job_classification") or ""), str(data.get("recruitment_type") or ""))).casefold()
        developer_intent = any(term in needle for term in ("개발", "developer", "software", "programming", "coding"))
        developer_role = any(term in haystack for term in ("개발", "developer", "software", "programming", "coding"))
        if developer_intent and not developer_role:
            return {"eligible": "false", "reason": "career_role_mismatch"}
        if not matches_interest(haystack, interest):
            return {"eligible": "false", "reason": "career_interest_mismatch"}
    if kind in {"culture_event", "performance"}:
        haystack = f"{item.get('title', '')} {data.get('genre', '')}".casefold()
        terms = _culture_terms(interest, preferred_region)
        if terms and not any(any(alias in haystack for alias in _CULTURE_TERM_ALIASES.get(term, (term,))) for term in terms):
            return {"eligible": "false", "reason": "interest_mismatch"}
        # A concrete region plus a culture category is specific enough; a
        # category alone must not recommend every event from the source.
        if not terms and not preferred_region:
            return {"eligible": "false", "reason": "interest_too_broad"}
    return {"eligible": "true", "reason": "direct_metadata_match"}


def _date_range(data: Dict[str, Any]) -> str:
    start = data.get("event_start_at") or data.get("start_at") or data.get("application_start_at")
    end = data.get("event_end_at") or data.get("end_at") or data.get("application_end_at")
    if start and end:
        return f"{start}~{end}"
    return str(start or end or "일정 미확인")


def build_domestic_preview(item: Dict[str, Any], interest: str) -> Dict[str, str]:
    """Build a fact-first preview without inferring facts missing from metadata."""
    data = item.get("metrics_json") or {}
    kind = data.get("content_kind") or ""
    url = str(item.get("url") or "")
    if not url:
        return {"status": "withheld", "reason": "official_source_url_missing"}
    source_title = str(item.get("title") or "").strip()
    if kind == "public_institution_job":
        employer = str(item.get("author") or "").strip()
        display = " ".join(part for part in (employer, source_title or "공공기관 채용 공고") if part)
        # Do not render pbancEndYmd as a deadline or notice period: the public
        # list specification only documents it as a request-side query bound.
        # The start field, when supplied in an item, is presented narrowly as
        # the provider's notice date rather than a recruitment deadline.
        start = data.get("announcement_start_at")
        facts = f"공고 기준일: {start}" if start else "공고 기준일: 미확인"
        facts += " | 실제 접수 마감일과 지원 가능 여부는 공식 공고에서 확인 필요"
        reason = f"'{interest}' 관심사와 직무·채용구분·근무지역 정보가 직접 일치합니다."
    elif kind in {"job_posting", "public_service_job"}:
        display = source_title or "공식 채용 공고"
        facts = f"접수 기간: {_date_range(data)}"
        reason = f"'{interest}' 관심사에 맞는 채용 정보 유형입니다."
    elif kind in {"startup_program", "government_rnd_announcement"}:
        display = source_title or "정부지원사업 모집 안내"
        facts = f"지원 대상: {data.get('support_target') or data.get('target') or '미확인'}"
        reason = f"'{interest}' 관심사에 맞는 지원사업 정보 유형입니다."
    elif kind == "youth_policy":
        display = source_title or "청년정책 안내"
        facts = f"정책 기간: {_date_range(data)}"
        reason = f"'{interest}' 관심사에 맞는 청년정책 정보입니다."
    elif kind in {"culture_event", "performance"}:
        place = (data.get("region") or data.get("venue")) if kind == "culture_event" else (data.get("venue") or data.get("region"))
        display = source_title or "문화행사 일정"
        if place:
            display = f"{display} · {place}"
        facts = f"일정: {_date_range(data)}"
        if kind == "culture_event" and data.get("venue"):
            facts += f" | 장소: {data['venue']}"
        if data.get("genre"):
            facts += f" | 분야: {data['genre']}"
        reason = f"'{interest}' 관심사와 행사명·분야가 직접 일치합니다."
    elif kind == "corporate_disclosure":
        company = str(item.get("author") or "").strip()
        display = " ".join(part for part in (company, source_title or "기업 공시") if part)
        facts = f"접수일: {data.get('receipt_at') or '미확인'}"
        reason = f"'{interest}' 관심사와 공시 기업 또는 산업이 직접 일치합니다."
    else:
        return {"status": "withheld", "reason": "unsupported_content_kind"}
    # The old preview strings were intentionally narrow about application
    # dates, but they did not carry the verified role/region/source metadata
    # needed for a useful job Canary card. Rebuild this one branch from the
    # list fields only; no inferred deadline or "open" claim is introduced.
    if kind == "public_institution_job":
        employer = str(item.get("author") or "").strip()
        display = " ".join(part for part in (
            employer, source_title or "\uacf5\uacf5\uae30\uad00 \ucc44\uc6a9 \uacf5\uace0",
        ) if part)
        start = data.get("announcement_start_at")
        facts_parts = [
            f"\uacf5\uace0 \uae30\uc900\uc77c: {start}" if start else "\uacf5\uace0 \uae30\uc900\uc77c: \ubbf8\ud655\uc778",
        ]
        role = " / ".join(part for part in (
            str(data.get("job_type") or "").strip(),
            str(data.get("job_classification") or "").strip(),
        ) if part)
        region = str(data.get("region") or "").strip()
        if role:
            facts_parts.append(f"\ucc44\uc6a9 \uc815\ubcf4: {role}")
        if region:
            facts_parts.append(f"\uadfc\ubb34 \uc9c0\uc5ed: {region}")
        facts_parts.append("\uc2e4\uc81c \uc811\uc218 \ub9c8\uac10\uc77c\uacfc \uc9c0\uc6d0 \uac00\ub2a5 \uc5ec\ubd80\ub294 \uacf5\uc2dd \uacf5\uace0\uc5d0\uc11c \ud655\uc778 \ud544\uc694")
        facts = " | ".join(facts_parts)
        reason = f"'{interest}' \uad00\uc2ec\uc0ac\uc640 \ucc44\uc6a9 \uc9c1\ubb34\u00b7\ucc44\uc6a9\uad6c\ubd84\u00b7\uadfc\ubb34\uc9c0\uc5ed \uc815\ubcf4\uac00 \uc9c1\uc811 \uc77c\uce58\ud569\ub2c8\ub2e4."
    preview = {"status": "ready", "display_title_ko": display, "summary_ko": facts, "recommendation_reason_ko": reason, "source_title": source_title, "source_url": url}
    if kind == "public_institution_job":
        preview["source_name_ko"] = "\uc7ac\uc815\uacbd\uc81c\ubd80 \uacf5\uacf5\uae30\uad00 \ucc44\uc6a9\uc815\ubcf4 \uc870\ud68c\uc11c\ube44\uc2a4"
        preview["application_deadline_status"] = "unknown"
    return preview
