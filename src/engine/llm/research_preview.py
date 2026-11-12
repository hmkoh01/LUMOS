"""Offline-only, metadata-grounded previews for research cards."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional


_TITLE_TOPIC_RULES = (
    # Keep a source-title subject when it is explicit.  These are topic
    # translations, not claims about the paper's results.
    ("repeatability and reproducibility of large language models", "대규모 언어 모델 결과의 재현성 평가"),
    ("predicting properties with large language models", "대규모 언어 모델을 활용한 특성 예측"),
    ("large language models in geospatial science", "지리공간 과학에서의 대규모 언어 모델 활용"),
    ("large language models in personalized oncology", "개인 맞춤 종양학에서의 대규모 언어 모델 활용"),
    ("large language model", "\ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378"),
    ("generative language model", "\uc0dd\uc131\ud615 \uc5b8\uc5b4 \ubaa8\ub378"),
    ("retrieval-augmented generation", "\uac80\uc0c9\uc73c\ub85c \uc815\ubcf4\ub97c \ubcf4\uc644\ud558\ub294 \uc5b8\uc5b4 \ubaa8\ub378"),
    ("natural language processing", "\uc790\uc5f0\uc5b4 \ucc98\ub9ac"),
    ("language model", "\uc5b8\uc5b4 \ubaa8\ub378"),
    ("monetary policy", "\ud1b5\ud654 \uc815\ucc45"),
    ("job market", "\uace0\uc6a9 \uc2dc\uc7a5"),
    ("youth housing", "\uccad\ub144 \uc8fc\uac70"),
    ("cultural event", "\ubb38\ud654\ud589\uc0ac"),
)


def _reader_topic_from_title(source_title: str) -> str:
    """Use only source-supported, reader-friendly title topics.

    This intentionally is not a translator. Unknown English names or technical
    phrases are withheld for original-text review instead of becoming an
    invented Korean interpretation. The same rule can be reused by non-AI
    information types.
    """
    normalized = " ".join(source_title.casefold().split())
    for term, korean in _TITLE_TOPIC_RULES:
        if term in normalized:
            return korean
    if re.search(r"[\uac00-\ud7a3]", source_title):
        return re.sub(r"^(?:\uc5f0\uad6c|\ub17c\ubb38|\ub9ac\ubdf0)\s*[:\-]?\s*", "", source_title).strip()[:48]
    return ""


def _research_title(source_title: str, role: str) -> str:
    topic = _reader_topic_from_title(source_title)
    if not topic:
        return ""
    normalized = source_title.casefold()
    if role == "reference_review" or re.search(r"\b(?:survey|review|overview)\b", normalized):
        return f"{topic}\uc744 \uc815\ub9ac\ud55c \uc5f0\uad6c"
    if "repeatability and reproducibility" in normalized:
        return f"{topic}\ub97c \ub2e4\ub8ec \uc5f0\uad6c"
    if re.search(r"\b(?:evaluat\w*|benchmark|assessment)\b", normalized):
        return f"{topic}\uc758 \ud3c9\uac00\ub97c \ub2e4\ub8ec \uc5f0\uad6c"
    return f"{topic}\uc744 \ub2e4\ub8ec \uc5f0\uad6c"


def build_research_preview(item: Dict[str, Any], interests: Iterable[str]) -> Optional[Dict[str, str]]:
    """Build a non-generative preview from DOI/metadata only.

    Original title, DOI, date and URL are returned as details. A card is
    withheld when its title cannot be described safely without interpreting
    unverified research claims.
    """
    metrics = item.get("metrics_json") or item.get("metrics") or {}
    if metrics.get("content_kind") != "research_metadata":
        return None
    published = str(metrics.get("publication_date") or item.get("published_at") or "")[:10]
    source_title = str(item.get("title") or "").strip()
    if not source_title or not published:
        return None
    role = str(metrics.get("research_role") or "research_update")
    display_title = _research_title(source_title, role)
    if not display_title:
        return None
    interest = next((str(value).strip() for value in interests if str(value).strip()), "")
    topic = next((str(value).strip() for value in metrics.get("topics") or [] if str(value).strip()), "")
    doi = str(metrics.get("doi") or item.get("doi") or "").strip()
    source_url = str(item.get("url") or metrics.get("landing_page_url") or "").strip()
    if not source_url and not doi:
        return None
    publication_fact = f"{published}\uc5d0 \ubc1c\ud45c\ub41c \ub17c\ubb38"
    classification_fact = f"OpenAlex \uc8fc\uc81c \ubd84\ub958 '{topic}'" if topic else "DOI\uc640 \uc6d0\ubb38 \ub9c1\ud06c"
    recommendation_reason = (
        f"{classification_fact}\uac00 \ud655\uc778\ub41c \uc5f0\uad6c \ud6c4\ubcf4\ub85c, \ub4f1\ub85d\ud55c \uad00\uc2ec\uc0ac\uc640 \uac19\uc740 \uc5f0\uad6c \uc815\ubcf4 \uc720\ud615\uc5d0\uc11c \uc6d0\ubb38 \uac80\ud1a0 \ub300\uc0c1\uc73c\ub85c \ubd84\ub958\ub429\ub2c8\ub2e4."
        if interest else "\ub4f1\ub85d\ub41c \uad00\uc2ec\uc0ac\uc640\uc758 \uc9c1\uc811 \uc5f0\uacb0\uc740 \ud655\uc778\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4."
    )
    return {
        "display_title_ko": display_title,
        "headline_summary_ko": f"OpenAlex \uba54\ud0c0\ub370\uc774\ud130\uc0c1 {publication_fact}\uc785\ub2c8\ub2e4. \uc5f0\uad6c \uacb0\uacfc\ub294 \uc6d0\ubb38 \ud655\uc778 \uc804\uc5d0 \ub2e8\uc815\ud558지 \uc54a\uc2b5\ub2c8\ub2e4.",
        "recommendation_reason_ko": recommendation_reason,
        "source_title": source_title,
        "doi": doi,
        "source_url": source_url,
        "research_role": role,
        "published_at": published,
    }
