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

from src.llm_safety import check_external_llm_allowed
from src.signals.agent_platform import AgentPlatformConfig

logger = logging.getLogger(__name__)

# Prompt schema version — bump when prompt structure changes.
_PROMPT_VERSION = "v4"

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


_CANONICAL_PROJECT_NAMES = {"langgraph": "LangGraph"}

_DIRECT_INTEREST_TERMS = {"langgraph"}
_TOPIC_TERMS = {"agent", "agents", "ai", "mcp", "workflow", "interrupt", "tool"}


def _canonical_project_name(title: str) -> str:
    """Use a known display name without changing the original source title."""
    package_name = title.strip().split("==", 1)[0].strip().lower()
    return _CANONICAL_PROJECT_NAMES.get(package_name, "")


def assess_relevance(item: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
    """Classify relevance without claiming deployment compatibility."""
    source_text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    # A product/proper noun is direct only when it appears in the source.
    # This handles mixed Korean/English interest labels without inferring
    # compatibility between unrelated tools.
    for keyword in keywords:
        normalized = keyword.strip().lower()
        terms = [part for part in normalized.replace("-", " ").split() if len(part) >= 3]
        if normalized in source_text or any(term in source_text for term in terms if term not in _TOPIC_TERMS):
            return {"level": "direct", "basis": f"source explicitly mentions registered interest: {keyword}"}
    direct = sorted(term for term in _DIRECT_INTEREST_TERMS if term in source_text)
    if direct:
        return {"level": "direct", "basis": f"관심 기술의 실제 변경: {', '.join(direct)}"}
    topic = sorted(term for term in _TOPIC_TERMS if term in source_text)
    if topic:
        return {"level": "topic", "basis": f"인접 기술 주제: {', '.join(topic)}"}
    return {"level": "insufficient", "basis": "명시된 관심사와 구체적 연결을 확인하지 못함"}


def clear_cache():
    _content_cache.clear()


# ---------------------------------------------------------------------------
# Model pricing (USD per 1M tokens, as of 2026-10)
# ---------------------------------------------------------------------------
_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "thinking": 0.35},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30, "thinking": 0.0},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "thinking": 9.00},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50, "thinking": 2.50},
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75, "thinking": 3.75},
}

_CONTENT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": ["display_title_ko", "display_summary_ko", "content_type_label", "is_new_event",
                 "new_event_basis", "grounded_facts", "key_entities", "key_numbers",
                 "information_gaps", "limitation_ko"],
    "properties": {
        "display_title_ko": {"type": "STRING"}, "display_summary_ko": {"type": "STRING"},
        "content_type_label": {"type": "STRING"}, "is_new_event": {"type": "BOOLEAN"},
        "new_event_basis": {"type": "STRING"}, "key_entities": {"type": "ARRAY", "items": {"type": "STRING"}},
        "key_numbers": {"type": "ARRAY", "items": {"type": "STRING"}}, "information_gaps": {"type": "STRING"},
        "limitation_ko": {"type": "STRING"},
        "grounded_facts": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["claim", "source_quote", "type"], "properties": {
            "claim": {"type": "STRING"}, "source_quote": {"type": "STRING"}, "type": {"type": "STRING"},
        }}},
    },
}

_PERSONALIZATION_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": ["source_facts_ko", "user_relevance_ko", "recommendation_reason_ko", "why_it_matters_ko",
                 "recommended_action_ko", "relevance_confidence"],
    "properties": {
        "source_facts_ko": {"type": "STRING"}, "user_relevance_ko": {"type": "STRING"},
        "recommendation_reason_ko": {"type": "STRING"}, "why_it_matters_ko": {"type": "STRING"},
        "recommended_action_ko": {"type": "STRING"}, "relevance_confidence": {"type": "STRING"},
    },
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
CONTENT_PROMPT_VERSION = "v4"
PERSONALIZATION_PROMPT_VERSION = "v5"
BRIEFING_VALIDATOR_VERSION = "v5"


class BriefingLLMClient:
    """Thin wrapper around google-genai for structured briefing generation."""

    def __init__(self, api_key: str = None, model: str = None, access_channel: str = "briefing_experiment"):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self._model = model or os.environ.get("LUMOS_LLM_MODEL", "gemini-2.5-flash").strip()
        self._client = None
        self._access_channel = access_channel
        self.tracker = CostTracker()

    def _ensure_client(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY not set")
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        call_type: str = "unknown",
        max_retries: int = 0,
        max_output_tokens: int = 512,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Call LLM, parse JSON, retry on transient errors.

        Returns (parsed_json_or_None, metadata_dict).
        """
        check_external_llm_allowed(self._access_channel)
        if max_retries != 0:
            raise ValueError("The briefing experiment permits no retries")
        max_allowed = 768 if call_type == "personalize" else 1024
        if not 1 <= max_output_tokens <= max_allowed:
            raise ValueError(f"max_output_tokens must be between 1 and {max_allowed} for {call_type}")
        self._ensure_client()
        from google.genai import types

        start = time.time()
        metadata: Dict[str, Any] = {
            "model": self._model,
            "error": None,
            "error_code": "",
            "retries": 0,
            "call_type": call_type,
            "max_output_tokens": max_output_tokens,
        }

        last_error_code = ""

        for attempt in range(max_retries + 1):
            try:
                response_schema = (
                    _PERSONALIZATION_RESPONSE_SCHEMA if call_type == "personalize" else _CONTENT_RESPONSE_SCHEMA
                )
                response = self._client.models.generate_content(
                    model=self._model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                        temperature=0.3,
                        max_output_tokens=max_output_tokens,
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

                # Token usage
                usage = getattr(response, "usage_metadata", None)
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                thinking_tokens = getattr(usage, "thinking_token_count", 0) or 0
                metadata["input_tokens"] = input_tokens
                metadata["output_tokens"] = output_tokens
                metadata["thinking_tokens"] = thinking_tokens

                candidates = getattr(response, "candidates", None) or []
                candidate = candidates[0] if candidates else None
                finish_reason = getattr(candidate, "finish_reason", "") if candidate else ""
                metadata["finish_reason"] = getattr(finish_reason, "name", str(finish_reason))

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
                finish_reason = str(metadata.get("finish_reason", "")).upper()
                truncated = "MAX_TOKENS" in finish_reason or (
                    (metadata.get("output_tokens") or 0) >= max_output_tokens
                )
                metadata["error"] = "JSON response was incomplete" if truncated else "JSON response was invalid"
                metadata["error_code"] = "json_error"
                metadata["json_parse_failure_type"] = "truncated_output" if truncated else "invalid_json"
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


class AgentPlatformBriefingLLMClient(BriefingLLMClient):
    """Briefing client bound to Agent Platform, never Developer API."""

    def __init__(self, config: AgentPlatformConfig, model: str, client_factory=None, access_channel: str = "briefing_experiment"):
        super().__init__(api_key=config.api_key, model=model, access_channel=access_channel)
        self._agent_platform_config = config
        self._client_factory = client_factory

    def _ensure_client(self):
        if self._client is None:
            self._client = self._agent_platform_config.create_client(self._client_factory)


# ---------------------------------------------------------------------------
# Prompts — v3: facts and user-context in separate fields
# ---------------------------------------------------------------------------
_CONTENT_SYSTEM = """당신은 LUMOS 뉴스 브리핑 시스템의 콘텐츠 분석기입니다.

주어진 원문 제목과 요약을 정확하게 한국어로 설명하세요. 이 단계는
사용자 개인화나 예상 효과를 다루지 않는 사실 추출 단계입니다.

규칙:
- 원문에 있는 사실만 사용하세요. 없는 기능, 수치, 날짜, 기업의 주장, 시장 영향, 인과관계나 출시 효과를 만들지 마세요.
- 성능 향상, 안정성 개선, 오류 해결, 보안 강화처럼 결과를 말할 때에는 원문의 인용 문구가 그 결과를 명시적으로 뒷받침할 때만 쓰세요.
- 고유명사(제품명, 기업명, 기술명, 인물명)는 원문 표기를 보존하세요. 영문 고유명사는 영문 그대로 쓰거나 널리 쓰이는 한글 표기를 사용하세요.
- 원문 정보가 부족하면 "확인 불가" 또는 "원문에 명시되지 않음"으로 표시하세요.
- 자연스러운 한국어를 사용하세요. 번역체("~것입니다", "~할 수 있게 됩니다")를 피하세요.
- 원문에 확인 가능한 핵심 변경이 있으면 제목에 프로젝트명·버전과 가장 중요한 변경 하나를 함께 넣으세요. 단순 "프로젝트명 + 버전 출시" 제목은 쓰지 마세요. 확인 가능한 변경이 없을 때만 중립적 출시 제목을 쓰세요.
- 각 핵심 사실에 대해 원문에서 해당 내용이 나온 부분을 정확히 인용하세요.
- JSON은 카드와 검증에 필요한 정보만 담으세요. 핵심 사실은 최대 3개, 고유명사는 최대 4개, 수치는 최대 3개로 제한하고 같은 내용을 다른 필드에서 반복하지 마세요.
- 출력은 반드시 JSON 형식이어야 합니다."""

_CONTENT_USER_TEMPLATE = """원문 정보:
- 제목: {title}
- 프로젝트 공식 표기: {canonical_project_name}
- 요약: {summary}
- 출처 유형: {source}
- 언어: {language}
- 콘텐츠 유형: {content_type}
- 지역: {region}
- 발행일: {published_at}

다음 JSON 형식으로 출력하세요:
{{
  "display_title_ko": "한국어 표시 제목 (프로젝트 공식 대소문자 유지, 확인된 핵심 변경 1개 포함, 목표 45자·절대 52자 이내)",
  "display_summary_ko": "핵심 사실 2-3개, 160자 이내",
  "content_type_label": "뉴스|연구|프로젝트|커뮤니티 토론|교육 자료|채용·기회 중 하나",
  "is_new_event": true 또는 false,
  "new_event_basis": "새 사건 판단 근거, 30자 이내",
  "grounded_facts": [
    {{
      "claim": "브리핑 주장, 45자 이내",
      "source_quote": "근거가 되는 원문 인용, 90자 이내",
      "type": "direct_fact 또는 source_bound_interpretation (추측한 효과 금지)"
    }}
  ],
  "key_entities": ["주요 고유명사 최대 4개"],
  "key_numbers": ["주요 수치 최대 3개"],
  "information_gaps": "확인 불가 정보, 35자 이내",
  "limitation_ko": "분석 한계, 35자 이내"
}}"""

_PERSONALIZE_SYSTEM = """당신은 LUMOS 뉴스 브리핑 시스템의 추천 이유 생성기입니다.

콘텐츠 브리핑과 사용자 프로필을 받아, 원문 사실과 사용자에게 유용할 수 있는 활용 맥락을 구분해 설명하세요.

규칙:
- 사용자의 명시된 관심 키워드와 역할만 사용하세요. 실제 직업, 수준, 계획, 자격 등을 임의로 추정하지 마세요.
- 먼저 원문에 명시된 기능 또는 변경점과 사용자의 구체적 워크플로 맥락을 연결하세요. "요청하신 분야의 소식입니다" 같은 일반적인 도입부로 시작하지 마세요.
- 원문 사실: grounded_facts에 있는 주장만 사용하세요. 원문에 없는 사실을 추측하지 마세요.
- 활용 맥락: 사용자가 검토할 수 있는 설계·운영 관점을 설명할 수 있지만, 이것은 예상되는 유용성일 뿐 입증된 결과가 아닙니다. "검토할 만합니다", "확인할 항목입니다"처럼 조건부로 표현하세요.
- 관련성 등급이 topic이면 인접 주제라는 점을 분명히 하고, 다른 제품 기능을 사용자의 워크플로에 적용·도입·최적화할 수 있다고 단정하지 마세요. insufficient이면 추천 이유를 만들지 마세요.
- 성능 향상, 안정성 개선·보장, 오류 해결, 출시 효과는 원문 인용이 그 효과를 명시적으로 입증할 때만 단정적으로 쓰세요.
- 환경·호환성·배포 상태를 알 수 없으므로 "업데이트하세요", "도입하세요", "적용하세요" 같은 직접 지시를 하지 마세요. 릴리스 노트·호환성·변경점을 확인하거나 검토하라고만 제안하세요.
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

관련성 판정:
- 등급: {relevance_level} (direct=관심 기술의 실제 변경, topic=인접 주제, insufficient=연결 부족)
- 근거: {relevance_basis}

추천 이유 작성 추가 규칙:
- `recommendation_reason_ko`에는 원문의 구체적인 변경 한 가지를 먼저 적으세요. 예: 보안 수정 범주, 의존성 버전 요구 사항, 도구 등록 규칙, 인터럽트 처리 규칙.
- 그 변경과 사용자의 관심사를 조건부로 연결하세요. 사용자의 실제 환경에 이미 적용되었거나 영향을 준다고 단정하지 마세요.
- `topic` 등급에서는 다른 제품의 기능을 사용자의 워크플로에 직접 적용할 수 있다고 쓰지 말고, 검토할 변경 범위를 구체적으로 설명하세요.
- “관련 기술 환경”, “인접 주제 관점”, “참고할 만합니다”만으로 추천 이유를 끝내지 마세요.

다음 JSON 형식으로 출력하세요:
{{
  "source_facts_ko": "원문 사실만, 45자 이내",
  "user_relevance_ko": "등급에 맞는 조건부 관련성만, 45자 이내",
  "recommendation_reason_ko": "앞의 두 필드를 반복하지 않고 연결한 추천 이유, 90자 이내",
  "why_it_matters_ko": "사용자가 확인할 설계·운영 질문, 45자 이내",
  "recommended_action_ko": "원문 기반 다음 행동, 35자 이내",
  "relevance_confidence": "high, medium, 또는 low (이 사용자와의 관련성에 대한 확신도)"
}}"""


# Safety rules appended to structured prompts without changing user content.
_CONTENT_SAFETY_ADDENDUM = """
For an internal engineering case study, describe it as an internal system or
technical introduction. Do not imply it is a publicly available product,
release, or an adoption recommendation unless the source explicitly says so.
Use release/launch/public-availability wording only when the source confirms it.
For an internal case study, prefer the meaning of \uC18C\uAC1C (technical introduction)
over \uACF5\uAC1C or \uCD9C\uC2DC when public availability is not established.
"""


def _personalization_anchor_contract(content_briefing: Dict[str, Any], relevance: Dict[str, str]) -> str:
    """Require a source fact in the reason without adding new facts."""
    anchors = [str(value).strip() for value in content_briefing.get("key_entities", []) if str(value).strip()]
    for fact in content_briefing.get("grounded_facts", []):
        claim = str(fact.get("claim", "")).strip()
        if claim:
            anchors.append(claim)
    rendered = "; ".join(list(dict.fromkeys(anchors))[:5]) or "(no usable source-specific anchor)"
    return (
        "\nSOURCE-ANCHOR CONTRACT:\n"
        f"- Relevance tier: {relevance.get('level', 'topic')}.\n"
        f"- recommendation_reason_ko must use one source-specific anchor: {rendered}\n"
        "- Do not manufacture a profile connection. For topic, say direct relevance is unconfirmed; "
        "for insufficient, return no recommendation.\n"
        "- Do not present an internal engineering system as a public product release or deployable user product.\n"
    )


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
        canonical_project_name=_canonical_project_name(title) or "원문 표기 사용",
        summary=summary or "(요약 없음)",
        source=item.get("source", "unknown"),
        language=item.get("language", "unknown"),
        content_type=item.get("content_type", "unknown"),
        region=item.get("region", "unknown"),
        published_at=item.get("published_at", "unknown"),
    )

    parsed, metadata = client.generate_json(
        _CONTENT_SYSTEM + _CONTENT_SAFETY_ADDENDUM, prompt, call_type="content", max_output_tokens=1024,
    )

    if parsed is None:
        return {"status": "failed", "content_briefing": None, "metadata": metadata}

    # Backward compat: extract key_facts from grounded_facts if needed
    if "grounded_facts" in parsed and "key_facts" not in parsed:
        parsed["key_facts"] = [f["claim"] for f in parsed["grounded_facts"]]

    from src.signals.llm_briefing_validator import validate_content_briefing
    validation = validate_content_briefing(parsed, item)
    presentation = validation["checks"].get("title_presentation", {})
    if presentation.get("shortened"):
        parsed["display_title_ko"] = presentation["display_title_ko"]
    parsed["title_display_mode"] = presentation.get("display_mode", "single_line")
    parsed["_validation"] = validation

    if not validation["valid"]:
        metadata["validation_issues"] = validation["issues"]
        return {"status": "validation_failed", "content_briefing": None, "metadata": metadata}
    if use_cache:
        _content_cache[_cache_key(title, summary, client._model)] = parsed
    return {"status": "success", "content_briefing": parsed, "metadata": metadata}


def generate_personalized_reason(
    content_briefing: Dict[str, Any],
    role: str,
    keywords: List[str],
    client: BriefingLLMClient,
    relevance: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Generate user-specific recommendation reason."""
    # Extract facts for the prompt
    grounded = content_briefing.get("grounded_facts", [])
    key_facts = [f["claim"] for f in grounded] if grounded else content_briefing.get("key_facts", [])
    key_entities = content_briefing.get("key_entities", [])
    relevance = relevance or {"level": "topic", "basis": "관련성 근거가 별도로 제공되지 않음"}
    if relevance["level"] == "insufficient":
        return {"status": "skipped_relevance", "personalization": None,
                "metadata": {"relevance_level": "insufficient", "retries": 0}}

    prompt = _PERSONALIZE_USER_TEMPLATE.format(
        display_title_ko=content_briefing.get("display_title_ko", ""),
        display_summary_ko=content_briefing.get("display_summary_ko", ""),
        key_facts=", ".join(key_facts) if key_facts else "(없음)",
        key_entities=", ".join(key_entities) if key_entities else "(없음)",
        content_type_label=content_briefing.get("content_type_label", ""),
        role=role,
        keywords=", ".join(keywords) if keywords else "(지정 안 됨)",
        relevance_level=relevance["level"],
        relevance_basis=relevance["basis"],
    )
    prompt += _personalization_anchor_contract(content_briefing, relevance)

    parsed, metadata = client.generate_json(
        _PERSONALIZE_SYSTEM, prompt, call_type="personalize", max_output_tokens=768,
    )

    if parsed is None:
        return {"status": "failed", "personalization": None, "metadata": metadata}

    from src.signals.llm_briefing_validator import validate_personalization
    validation = validate_personalization(parsed, content_briefing)
    parsed["_validation"] = validation
    if not validation["valid"]:
        metadata["validation_issues"] = validation["issues"]
        return {"status": "validation_failed", "personalization": None, "metadata": metadata}
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
