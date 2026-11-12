"""Offline regressions for reader-first GitHub/HN card copy.

The fixtures mirror the five GitHub source records that produced vague cards
in local-live.  They deliberately contain metadata only; no network or LLM
client is involved.
"""
from __future__ import annotations

import pytest

from src.signals.llm_briefing_validator import validate_content_briefing, validate_personalization


CASES = [
    {
        "raw_title": "thedotmack/claude-mem",
        "raw_summary": "Persistent Context Across Sessions for Every Agent – Captures everything your agent does during sessions, compresses it with AI, and injects relevant context back into future sessions.",
        "old_title": "thedotmack/claude-mem 세션 간 지속형 컨텍스트 저장 기능 소개",
        "old_reason": "인접 주제 관점에서 검토할 수 있습니다.",
        "title": "이전 작업 기록을 다음 세션에 다시 넣는 에이전트 도구",
        "summary": "claude-mem은 에이전트 세션의 활동을 기록·압축해 이후 세션에 필요한 이전 작업 정보를 다시 넣는다고 설명합니다.",
        "interest": "AI 에이전트",
        "reason": "AI 에이전트 관심사에서 세션 사이에 어떤 기록을 넘길지 비교할 때, claude-mem이 설명한 기록·압축·재주입 방식을 살필 수 있습니다.",
        "quote": "injects relevant context back into future sessions",
    },
    {
        "raw_title": "heygen-com/hyperframes",
        "raw_summary": "Write HTML. Render video. Built for agents.",
        "old_title": "heygen-com/hyperframes: HTML 작성과 비디오 렌더링 기능 소개",
        "old_reason": "관련 자료를 검토할 수 있습니다.",
        "title": "HTML로 작성한 내용을 비디오로 만드는 에이전트용 도구",
        "summary": "hyperframes는 HTML을 작성한 뒤 비디오로 만드는 기능을 에이전트용으로 제공한다고 설명합니다.",
        "interest": "AI 에이전트",
        "reason": "AI 에이전트 관심사에서 HTML 결과를 비디오로 바꿔야 하는 작업인지 판단할 때, hyperframes가 밝힌 작업 범위를 살필 수 있습니다.",
        "quote": "Write HTML. Render video. Built for agents.",
    },
    {
        "raw_title": "hesreallyhim/awesome-claude-code",
        "raw_summary": "A hand-picked collection of resources for Claude Code (no affiliation), including skills, agents, developer tooling, and plugins.",
        "old_title": "hesreallyhim/awesome-claude-code 리포지토리 소개",
        "old_reason": "인접 주제 관점에서 검토할 수 있습니다.",
        "title": "Claude Code용 스킬·플러그인 자료를 모아 둔 비공식 목록",
        "summary": "awesome-claude-code는 Claude Code 관련 스킬, 에이전트, 개발자 도구, 플러그인을 모은 비공식 자료 목록입니다.",
        "interest": "개발자 도구",
        "reason": "개발자 도구 관심사에서 Claude Code용 확장 자료를 찾을 때, awesome-claude-code가 모은 스킬·플러그인 범위를 비공식 자료라는 점과 함께 비교할 수 있습니다.",
        "quote": "skills, agents, developer tooling, and plugins",
    },
    {
        "raw_title": "PostHog/posthog",
        "raw_summary": "Developer tools – AI observability, analytics, session replay, flags, experiments, error tracking, logs, and more – capture all the context agents need to diagnose problems.",
        "old_title": "PostHog 플랫폼 소개 및 개발자 도구 구성",
        "old_reason": "관련 자료를 검토할 수 있습니다.",
        "title": "AI 관련 작업의 상태와 오류를 살피는 개발 도구",
        "summary": "PostHog은 AI 관련 작업의 상태를 살피는 기능, 분석, 세션 재생, 오류 추적, 로그 등 개발자 도구를 제공한다고 설명합니다.",
        "interest": "개발자 도구",
        "reason": "개발자 도구 관심사에서 분석·오류 추적을 함께 다룰지 비교할 때, PostHog이 열거한 기능 범위를 살필 수 있습니다.",
        "quote": "analytics, session replay, flags, experiments, error tracking, logs",
    },
    {
        "raw_title": "pipecat-ai/pipecat",
        "raw_summary": "Open Source framework for voice agents, multimodal apps, and realtime AI.",
        "old_title": "pipecat-ai/pipecat 음성 에이전트 오픈소스 프레임워크 소개",
        "old_reason": "인접 주제 관점에서 검토할 수 있습니다.",
        "title": "음성·실시간 대화 기능을 만들 때 쓰는 오픈소스 도구",
        "summary": "pipecat은 음성 에이전트, 여러 입력 방식을 함께 쓰는 앱, 실시간 AI 기능을 만들 때 쓰는 오픈소스 도구라고 설명합니다.",
        "interest": "AI 에이전트",
        "reason": "AI 에이전트 관심사에서 음성 대화 기능을 다뤄야 하는지 판단할 때, pipecat이 명시한 실시간·여러 입력 처리 범위를 살필 수 있습니다.",
        "quote": "voice agents, multimodal apps, and realtime AI",
    },
]


def _content(case: dict, *, title: str, summary: str):
    return {
        "display_title_ko": title,
        "display_summary_ko": summary,
        "content_type_label": "오픈소스 도구",
        "is_new_event": False,
        "key_entities": [case["raw_title"].split("/", 1)[1]],
        "limitation_ko": "저장소 설명에 명시된 정보만 반영합니다.",
        "grounded_facts": [{
            "claim": summary,
            "source_quote": case["quote"],
            "type": "direct_fact",
        }],
    }


@pytest.mark.parametrize("case", CASES, ids=[case["raw_title"] for case in CASES])
def test_existing_generic_repository_copy_is_rejected(case):
    result = validate_content_briefing(
        _content(case, title=case["old_title"], summary=case["summary"]),
        {"source": "github", "title": case["raw_title"], "summary": case["raw_summary"]},
    )
    assert result["valid"] is False
    assert result["checks"]["repository_presentation"]["pass"] is False


@pytest.mark.parametrize("case", CASES, ids=[case["raw_title"] for case in CASES])
def test_reader_first_repository_copy_and_concrete_reason_pass(case):
    content = _content(case, title=case["title"], summary=case["summary"])
    content_result = validate_content_briefing(
        content,
        {"source": "github", "title": case["raw_title"], "summary": case["raw_summary"]},
    )
    assert content_result["valid"], content_result
    assert not content["display_title_ko"].startswith(case["raw_title"])

    personalization = {
        "source_facts_ko": case["summary"],
        "user_relevance_ko": f"{case['interest']} 관심사와 원문 정보 유형이 직접 맞닿아 있습니다.",
        "recommendation_reason_ko": case["reason"],
        "why_it_matters_ko": "원문이 밝힌 기능 범위만 확인할 수 있습니다.",
        "recommended_action_ko": "공식 저장소 설명을 확인하세요.",
        "relevance_confidence": "high",
    }
    person_result = validate_personalization(
        personalization, content, registered_interests=[case["interest"]],
    )
    assert person_result["valid"], person_result


@pytest.mark.parametrize("case", CASES, ids=[case["raw_title"] for case in CASES])
def test_generic_recommendation_reason_is_rejected_even_when_source_exists(case):
    content = _content(case, title=case["title"], summary=case["summary"])
    personalization = {
        "source_facts_ko": case["summary"],
        "user_relevance_ko": f"{case['interest']} 관심사와 관련이 있습니다.",
        "recommendation_reason_ko": case["old_reason"],
        "why_it_matters_ko": "원문을 확인할 수 있습니다.",
        "recommended_action_ko": "원문을 확인하세요.",
        "relevance_confidence": "low",
    }
    result = validate_personalization(personalization, content, registered_interests=[case["interest"]])
    assert result["valid"] is False
    assert result["checks"]["not_boilerplate"]["pass"] is False


def test_unexplained_technical_language_is_rejected_but_a_plain_explanation_passes():
    source = {"source": "github", "title": "owner/video-tool", "summary": "Write HTML. Render video. Built for agents."}
    unexplained = _content(
        CASES[1], title="에이전트용 비디오 렌더링 프레임워크",
        summary="렌더링과 프레임워크 기능을 제공합니다.",
    )
    rejected = validate_content_briefing(unexplained, source)
    assert rejected["valid"] is False
    assert rejected["checks"]["reader_language"]["pass"] is False

    explained = _content(
        CASES[1], title="HTML 내용을 비디오로 만드는 에이전트용 도구",
        summary="HTML을 작성한 뒤 비디오로 만드는 기능을 제공하는 개발 도구입니다.",
    )
    accepted = validate_content_briefing(explained, source)
    assert accepted["valid"], accepted
    assert accepted["checks"]["reader_language"]["pass"] is True


def test_reason_needs_a_real_decision_not_just_a_source_check():
    content = _content(CASES[0], title=CASES[0]["title"], summary=CASES[0]["summary"])
    reason = {
        "source_facts_ko": CASES[0]["summary"],
        "user_relevance_ko": "AI 에이전트 관심사와 직접 연결됩니다.",
        "recommendation_reason_ko": "AI 에이전트 관심사에서 claude-mem의 세션 기록 방식을 원문 기준으로 확인할 수 있습니다.",
        "why_it_matters_ko": "세션 기록 기능이 있습니다.",
        "recommended_action_ko": "공식 저장소 설명을 확인하세요.",
        "relevance_confidence": "medium",
    }
    result = validate_personalization(reason, content, registered_interests=["AI 에이전트"])
    assert result["valid"] is False
    assert result["checks"]["recommendation_usefulness"]["empty_ending"] is True


@pytest.mark.parametrize(
    "interest, entity, reason",
    [
        ("신입 개발자 취업", "채용공고", "신입 개발자 취업 관심사에서 채용공고의 직무와 접수 마감일이 맞는지 판단할 때 확인할 수 있습니다."),
        ("창업 지원사업", "지원사업", "창업 지원사업 관심사에서 지원 대상과 신청 기간을 비교할 때 확인할 수 있습니다."),
        ("서울 문화행사", "문화행사", "서울 문화행사 관심사에서 행사 일정과 장소가 방문 계획에 맞는지 판단할 때 확인할 수 있습니다."),
        ("관심 기업 공시", "기업공시", "관심 기업 공시 관심사에서 기업공시 유형과 접수일을 비교할 때 확인할 수 있습니다."),
    ],
)
def test_non_technical_cards_use_the_same_concrete_reason_rule(interest, entity, reason):
    content = {"key_entities": [entity], "grounded_facts": []}
    personalization = {
        "source_facts_ko": f"{entity}의 공식 일정 또는 상태를 안내합니다.",
        "user_relevance_ko": f"{interest} 관심사와 정보 유형이 맞습니다.",
        "recommendation_reason_ko": reason,
        "why_it_matters_ko": "원문에 표시된 조건만 반영합니다.",
        "recommended_action_ko": "공식 링크에서 세부 조건을 확인하세요.",
        "relevance_confidence": "high",
    }
    result = validate_personalization(personalization, content, registered_interests=[interest])
    assert result["valid"], result
