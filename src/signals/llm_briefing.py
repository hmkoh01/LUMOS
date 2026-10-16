"""LLM-based briefing generation — pilot v2.

Two-stage generation:
  A. Content briefing (user-agnostic): factual description with source grounding
  B. Personalized reason (user-specific): role-aware recommendation

Feature flag: LUMOS_LLM_BRIEFING env var
  - "off" (default): disabled
  - "pilot": enabled for evaluation/comparison only

Does NOT modify existing template briefings or operational data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Prompt schema version — bump when prompt structure changes.
_PROMPT_VERSION = "v2"

# ---------------------------------------------------------------------------
# Source permission gate
# ---------------------------------------------------------------------------
_BLOCKED_SOURCES = {"geeknews", "kisa_press", "kisa_research"}


def _source_allowed(source: str) -> bool:
    return source not in _BLOCKED_SOURCES


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
def llm_briefing_enabled() -> bool:
    return os.environ.get("LUMOS_LLM_BRIEFING", "off").strip().lower() == "pilot"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_content_cache: Dict[str, Dict[str, Any]] = {}


def _cache_key(title: str, summary: str, model: str) -> str:
    raw = f"{_PROMPT_VERSION}|{model}|{title.strip()}||{summary.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def clear_cache():
    _content_cache.clear()


# ---------------------------------------------------------------------------
# Model pricing (USD per 1M tokens, as of 2026-10)
# ---------------------------------------------------------------------------
_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "thinking": 0.35},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30, "thinking": 0.0},
    "gemini-3.5-flash": {"input": 0.15, "output": 0.60, "thinking": 0.35},
    "gemini-3.5-flash-lite": {"input": 0.075, "output": 0.30, "thinking": 0.0},
}

_DEFAULT_PRICING = {"input": 0.15, "output": 0.60, "thinking": 0.35}


def _get_pricing(model: str) -> Dict[str, float]:
    return _MODEL_PRICING.get(model, _DEFAULT_PRICING)


# ---------------------------------------------------------------------------
# Token / cost tracking
# ---------------------------------------------------------------------------
class CostTracker:
    """Accumulates token usage and cost across calls, separated by call_type."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int,
        model: str,
        latency_ms: float,
        call_type: str = "unknown",
        retries: int = 0,
        error_code: str = "",
    ):
        pricing = _get_pricing(model)
        cost = (
            input_tokens * pricing["input"] / 1_000_000
            + output_tokens * pricing["output"] / 1_000_000
            + thinking_tokens * pricing["thinking"] / 1_000_000
        )
        self.calls.append({
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "model": model,
            "latency_ms": latency_ms,
            "call_type": call_type,
            "retries": retries,
            "error_code": error_code,
            "cost_usd": cost,
        })

    def _sum(self, key: str, call_type: str = None) -> int:
        calls = self.calls if call_type is None else [c for c in self.calls if c["call_type"] == call_type]
        return sum(c.get(key, 0) for c in calls)

    @property
    def total_input_tokens(self) -> int:
        return self._sum("input_tokens")

    @property
    def total_output_tokens(self) -> int:
        return self._sum("output_tokens")

    @property
    def total_thinking_tokens(self) -> int:
        return self._sum("thinking_tokens")

    @property
    def total_cost_usd(self) -> float:
        return sum(c["cost_usd"] for c in self.calls)

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def avg_latency_ms(self) -> float:
        if not self.calls:
            return 0
        return sum(c["latency_ms"] for c in self.calls) / len(self.calls)

    def summary(self) -> Dict[str, Any]:
        successful = [c for c in self.calls if not c["error_code"]]
        failed = [c for c in self.calls if c["error_code"]]
        content_calls = [c for c in successful if c["call_type"] == "content"]
        person_calls = [c for c in successful if c["call_type"] == "personalize"]
        return {
            "total_calls": self.total_calls,
            "successful_calls": len(successful),
            "failed_calls": len(failed),
            "total_retries": sum(c["retries"] for c in self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_thinking_tokens": self.total_thinking_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "content_calls": len(content_calls),
            "content_cost_usd": round(sum(c["cost_usd"] for c in content_calls), 6),
            "personalize_calls": len(person_calls),
            "personalize_cost_usd": round(sum(c["cost_usd"] for c in person_calls), 6),
            "error_codes": dict(_count_errors(failed)),
        }


def _count_errors(calls: list) -> list:
    from collections import Counter
    return Counter(c["error_code"] for c in calls).most_common()


# ---------------------------------------------------------------------------
# LLM client wrapper
# ---------------------------------------------------------------------------
class BriefingLLMClient:
    """Thin wrapper around google-genai for structured briefing generation."""

    def __init__(self, api_key: str = None, model: str = None):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self._model = model or os.environ.get("LUMOS_LLM_MODEL", "gemini-2.5-flash").strip()
        self._client = None
        self.tracker = CostTracker()

    def _ensure_client(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY not set")
            from google import genai
            self._client = genai.Client(api_key=self._api_key)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        call_type: str = "unknown",
        max_retries: int = 3,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Call LLM, parse JSON, retry on transient errors.

        Returns (parsed_json_or_None, metadata_dict).
        """
        self._ensure_client()
        from google.genai import types

        start = time.time()
        metadata: Dict[str, Any] = {
            "model": self._model,
            "error": None,
            "error_code": "",
            "raw_text": "",
            "retries": 0,
            "call_type": call_type,
        }

        last_error_code = ""

        for attempt in range(max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        temperature=0.3,
                    ),
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part(text=user_prompt)],
                    )],
                )
                elapsed_ms = (time.time() - start) * 1000
                metadata["latency_ms"] = round(elapsed_ms, 1)
                metadata["retries"] = attempt

                raw = response.text.strip() if response.text else ""
                metadata["raw_text"] = raw

                # Token usage
                usage = getattr(response, "usage_metadata", None)
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                thinking_tokens = getattr(usage, "thinking_token_count", 0) or 0
                metadata["input_tokens"] = input_tokens
                metadata["output_tokens"] = output_tokens
                metadata["thinking_tokens"] = thinking_tokens

                # Model version from response
                model_version = getattr(response, "model_version", None)
                if model_version:
                    metadata["model_version"] = model_version

                self.tracker.record(
                    input_tokens, output_tokens, thinking_tokens,
                    self._model, elapsed_ms, call_type, attempt,
                )

                parsed = json.loads(raw)
                return parsed, metadata

            except json.JSONDecodeError as e:
                metadata["error"] = f"JSON parse error: {e}"
                metadata["error_code"] = "json_error"
                metadata["latency_ms"] = round((time.time() - start) * 1000, 1)
                self.tracker.record(0, 0, 0, self._model, metadata["latency_ms"],
                                    call_type, attempt, "json_error")
                return None, metadata

            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    last_error_code = "503"
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    last_error_code = "429"
                else:
                    last_error_code = "other"

                is_transient = last_error_code in ("503", "429")
                if is_transient and attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.info("Retry %d/%d after %ds (%s): %s",
                                attempt + 1, max_retries, wait, last_error_code, err_str[:60])
                    time.sleep(wait)
                    metadata["retries"] = attempt + 1
                    continue

                metadata["error"] = err_str
                metadata["error_code"] = last_error_code
                metadata["latency_ms"] = round((time.time() - start) * 1000, 1)
                metadata["retries"] = attempt
                self.tracker.record(0, 0, 0, self._model, metadata["latency_ms"],
                                    call_type, attempt, last_error_code)
                logger.error("LLM call failed (%s): %s", last_error_code, err_str[:100])
                return None, metadata

        return None, metadata


# ---------------------------------------------------------------------------
# Prompts — v2 with fact grounding
# ---------------------------------------------------------------------------
_CONTENT_SYSTEM = """당신은 LUMOS 뉴스 브리핑 시스템의 콘텐츠 분석기입니다.

주어진 원문 제목과 요약을 정확하게 한국어로 설명하세요.

규칙:
- 원문에 있는 사실만 사용하세요. 없는 기능, 수치, 날짜, 기업의 주장, 시장 영향, 인과관계를 만들지 마세요.
- 고유명사(제품명, 기업명, 기술명, 인물명)는 원문 표기를 보존하세요. 영문 고유명사는 영문 그대로 쓰거나 널리 쓰이는 한글 표기를 사용하세요.
- 원문 정보가 부족하면 "확인 불가" 또는 "원문에 명시되지 않음"으로 표시하세요.
- 자연스러운 한국어를 사용하세요. 번역체("~것입니다", "~할 수 있게 됩니다")를 피하세요.
- 각 핵심 사실에 대해 원문에서 해당 내용이 나온 부분을 정확히 인용하세요.
- 출력은 반드시 JSON 형식이어야 합니다."""

_CONTENT_USER_TEMPLATE = """원문 정보:
- 제목: {title}
- 요약: {summary}
- 출처 유형: {source}
- 언어: {language}
- 콘텐츠 유형: {content_type}
- 지역: {region}
- 발행일: {published_at}

다음 JSON 형식으로 출력하세요:
{{
  "display_title_ko": "한국어 표시 제목 (원문 의미를 정확히 전달, 52자 이내)",
  "display_summary_ko": "쉬운 한국어 핵심 요약 (원문의 핵심 사실 2-3개, 200자 이내)",
  "content_type_label": "뉴스|연구|프로젝트|커뮤니티 토론|교육 자료|채용·기회 중 하나",
  "is_new_event": true 또는 false,
  "new_event_basis": "새로운 사건으로 판단한 근거 또는 기존 사안인 이유 (1문장)",
  "grounded_facts": [
    {{
      "claim": "브리핑에 포함된 주장",
      "source_quote": "원문에서 이 주장의 근거가 되는 정확한 문구",
      "type": "direct_fact 또는 interpretation"
    }}
  ],
  "key_entities": ["원문에 등장하는 주요 고유명사들"],
  "key_numbers": ["원문에 등장하는 주요 수치들 (없으면 빈 배열)"],
  "information_gaps": "원문만으로는 확인할 수 없는 내용 (없으면 빈 문자열)",
  "limitation_ko": "이 브리핑의 한계 설명 (어떤 정보를 확인하지 못했는지)"
}}"""

_PERSONALIZE_SYSTEM = """당신은 LUMOS 뉴스 브리핑 시스템의 추천 이유 생성기입니다.

콘텐츠 브리핑과 사용자 프로필을 받아, 이 사용자에게 이 소식이 왜 관련되는지 구체적으로 설명하세요.

규칙:
- 사용자의 명시된 관심 키워드와 역할만 사용하세요. 실제 직업, 수준, 계획, 자격 등을 임의로 추정하지 마세요.
- 원문에 없는 사실을 추측하지 마세요.
- 관련성이 약하면 솔직하게 "직접적 관련성은 낮지만"이라고 쓰세요. 억지로 연결하지 마세요.
- 같은 소식이라도 사용자 역할에 따라 관점이 달라야 합니다. 단, 차이를 만들 근거가 없으면 비슷해도 됩니다.
- "~분야의 최근 변화를 다뤄" 같은 범용 표현을 쓰지 마세요.
- 출력은 반드시 JSON 형식이어야 합니다."""

_PERSONALIZE_USER_TEMPLATE = """콘텐츠 브리핑:
- 제목: {display_title_ko}
- 요약: {display_summary_ko}
- 핵심 사실: {key_facts}
- 고유명사: {key_entities}
- 콘텐츠 유형: {content_type_label}

사용자 프로필:
- 역할: {role}
- 관심 키워드: {keywords}

다음 JSON 형식으로 출력하세요:
{{
  "recommendation_reason_ko": "이 사용자에게 이 소식을 추천하는 구체적 이유 (2-3문장, 원문 내용과 사용자 관심 키워드의 연결점 포함)",
  "why_it_matters_ko": "이 사용자에게 왜 중요한지 (1-2문장, 사용자의 역할 관점에서)",
  "recommended_action_ko": "다음에 할 수 있는 구체적 행동 (1문장, 원문에서 언급된 자료/도구/사이트 기반)",
  "relevance_confidence": "high, medium, 또는 low (이 사용자와의 관련성에 대한 확신도)"
}}"""


# ---------------------------------------------------------------------------
# Core generation functions
# ---------------------------------------------------------------------------
def generate_content_briefing(
    item: Dict[str, Any],
    client: BriefingLLMClient,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Generate user-agnostic content briefing with fact grounding."""
    source = item.get("source", "")
    if not _source_allowed(source):
        return {
            "status": "blocked",
            "content_briefing": None,
            "metadata": {"reason": f"Source '{source}' is under permission review"},
        }

    title = item.get("title", "").strip()
    summary = item.get("summary", "").strip()

    if use_cache:
        ck = _cache_key(title, summary, client._model)
        if ck in _content_cache:
            return {"status": "cached", "content_briefing": _content_cache[ck], "metadata": {"cache_key": ck}}

    prompt = _CONTENT_USER_TEMPLATE.format(
        title=title or "(제목 없음)",
        summary=summary or "(요약 없음)",
        source=item.get("source", "unknown"),
        language=item.get("language", "unknown"),
        content_type=item.get("content_type", "unknown"),
        region=item.get("region", "unknown"),
        published_at=item.get("published_at", "unknown"),
    )

    parsed, metadata = client.generate_json(_CONTENT_SYSTEM, prompt, call_type="content")

    if parsed is None:
        return {"status": "failed", "content_briefing": None, "metadata": metadata}

    # Backward compat: extract key_facts from grounded_facts if needed
    if "grounded_facts" in parsed and "key_facts" not in parsed:
        parsed["key_facts"] = [f["claim"] for f in parsed["grounded_facts"]]

    from src.signals.llm_briefing_validator import validate_content_briefing
    validation = validate_content_briefing(parsed, item)
    parsed["_validation"] = validation

    if use_cache:
        _content_cache[_cache_key(title, summary, client._model)] = parsed

    return {"status": "success", "content_briefing": parsed, "metadata": metadata}


def generate_personalized_reason(
    content_briefing: Dict[str, Any],
    role: str,
    keywords: List[str],
    client: BriefingLLMClient,
) -> Dict[str, Any]:
    """Generate user-specific recommendation reason."""
    # Extract facts for the prompt
    grounded = content_briefing.get("grounded_facts", [])
    key_facts = [f["claim"] for f in grounded] if grounded else content_briefing.get("key_facts", [])
    key_entities = content_briefing.get("key_entities", [])

    prompt = _PERSONALIZE_USER_TEMPLATE.format(
        display_title_ko=content_briefing.get("display_title_ko", ""),
        display_summary_ko=content_briefing.get("display_summary_ko", ""),
        key_facts=", ".join(key_facts) if key_facts else "(없음)",
        key_entities=", ".join(key_entities) if key_entities else "(없음)",
        content_type_label=content_briefing.get("content_type_label", ""),
        role=role,
        keywords=", ".join(keywords) if keywords else "(지정 안 됨)",
    )

    parsed, metadata = client.generate_json(_PERSONALIZE_SYSTEM, prompt, call_type="personalize")

    if parsed is None:
        return {"status": "failed", "personalization": None, "metadata": metadata}

    return {"status": "success", "personalization": parsed, "metadata": metadata}


# ---------------------------------------------------------------------------
# Combined generation with safe fallback
# ---------------------------------------------------------------------------
def generate_llm_briefing(
    item: Dict[str, Any],
    role: str = "예비 창업자",
    keywords: List[str] = None,
    client: BriefingLLMClient = None,
) -> Dict[str, Any]:
    """Generate a full LLM briefing (content + personalization)."""
    if client is None:
        client = BriefingLLMClient()

    keywords = keywords or item.get("matched_keywords", [])
    result: Dict[str, Any] = {"_generation": {"item_id": item.get("id", "")}}

    # Stage A: Content briefing
    content_result = generate_content_briefing(item, client)
    result["_generation"]["content_status"] = content_result["status"]
    result["_generation"]["content_metadata"] = content_result.get("metadata", {})

    if content_result["status"] in ("success", "cached"):
        cb = content_result["content_briefing"]
        result.update(cb)
    else:
        result.update(_safe_fallback(item))
        result["_generation"]["personalize_status"] = "skipped"
        return result

    # Stage B: Personalized reason
    person_result = generate_personalized_reason(cb, role, keywords, client)
    result["_generation"]["personalize_status"] = person_result["status"]
    result["_generation"]["personalize_metadata"] = person_result.get("metadata", {})

    if person_result["status"] == "success":
        result.update(person_result["personalization"])
    else:
        result["recommendation_reason_ko"] = ""
        result["why_it_matters_ko"] = ""
        result["recommended_action_ko"] = "원문을 직접 확인해보세요."
        result["relevance_confidence"] = ""
        result["_generation"]["personalize_fallback"] = True

    return result


def _safe_fallback(item: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal safe output when LLM fails — no fabrication."""
    title = item.get("title", "").strip()
    summary = item.get("summary", "").strip()
    return {
        "display_title_ko": title or "제목 없는 소식",
        "display_summary_ko": summary[:200] if summary else "요약을 생성하지 못했습니다.",
        "content_type_label": item.get("content_type", ""),
        "is_new_event": None,
        "new_event_basis": "",
        "grounded_facts": [],
        "key_facts": [],
        "key_entities": [],
        "key_numbers": [],
        "information_gaps": "LLM 호출 실패로 분석하지 못했습니다.",
        "limitation_ko": "자동 분석에 실패하여 원문 제목과 요약만 표시합니다.",
        "recommendation_reason_ko": "",
        "why_it_matters_ko": "",
        "recommended_action_ko": "원문을 직접 확인해보세요.",
        "relevance_confidence": "",
    }
