"""Offline evaluation dataset: 25 items for briefing quality assessment.

Each item is a dict simulating a CollectedItem's fields.  Items are tagged:
  - origin: "synthetic" (written by the LUMOS team) or "public" (from publicly
    available titles/summaries that are freely redistributable, e.g. open-access
    abstracts, press release headlines, or open-source project descriptions).
  - language: "ko" or "en"
  - content_type: news | paper | project | community
  - region: domestic | international
  - novelty: "new_event" | "existing"  (whether the item describes a genuinely
    new occurrence or references an already-known topic)

NO copyrighted body text is included.  Public items use only freely available
metadata (titles, abstracts under CC/open-access, or OSS README excerpts).
Synthetic items are entirely written by the project team for testing.
"""

EVAL_ITEMS = [
    # ── Korean · News · Domestic · New event ──────────────────────────
    {
        "id": "eval-01",
        "origin": "synthetic",
        "source": "kisa_press",
        "language": "ko",
        "content_type": "news",
        "region": "domestic",
        "novelty": "new_event",
        "title": "KISA, 2026년 하반기 사이버 위협 동향 보고서 발간",
        "summary": "한국인터넷진흥원(KISA)이 2026년 하반기 사이버 위협 동향 보고서를 발간했다. 보고서에 따르면 AI를 활용한 피싱 공격이 전년 대비 47% 증가했으며, 중소기업 대상 랜섬웨어 공격도 급증했다.",
        "url": "https://example.test/kisa-threat-2026h2",
        "published_at": "2026-10-15T09:00:00",
        "matched_keywords": ["정보보안", "사이버 위협"],
    },
    {
        "id": "eval-02",
        "origin": "synthetic",
        "source": "geeknews",
        "language": "ko",
        "content_type": "community",
        "region": "domestic",
        "novelty": "new_event",
        "title": "국내 스타트업이 만든 오픈소스 한국어 LLM 벤치마크",
        "summary": "한국어 자연어 처리 성능을 표준화된 방식으로 평가할 수 있는 오픈소스 벤치마크가 공개됐다. 한국어 문맥 이해, 존댓말 변환, 법률 용어 해석 등 5가지 태스크를 포함한다.",
        "url": "https://example.test/ko-llm-bench",
        "published_at": "2026-10-14T14:30:00",
        "matched_keywords": ["AI agent", "한국어 NLP"],
    },
    {
        "id": "eval-03",
        "origin": "synthetic",
        "source": "kisa_research",
        "language": "ko",
        "content_type": "paper",
        "region": "domestic",
        "novelty": "existing",
        "title": "개인정보 비식별화 기술의 국내 적용 현황과 과제",
        "summary": "국내 공공·민간 부문의 개인정보 비식별화 기술 적용 사례를 조사하고, k-익명성과 차분 프라이버시 기법의 실무 적용 한계를 분석한 연구 보고서이다.",
        "url": "https://example.test/kisa-deidentification",
        "published_at": "2026-09-20T10:00:00",
        "matched_keywords": ["개인정보 보호"],
    },

    # ── Korean · Project · Domestic · New event ───────────────────────
    {
        "id": "eval-04",
        "origin": "synthetic",
        "source": "geeknews",
        "language": "ko",
        "content_type": "project",
        "region": "domestic",
        "novelty": "new_event",
        "title": "카카오, 사내 업무 자동화 에이전트 '카나리' 베타 공개",
        "summary": "카카오가 사내 반복 업무를 자동화하는 AI 에이전트 '카나리'의 베타 버전을 공개했다. 슬랙 연동, 회의록 요약, 일정 조율 기능을 포함하며, 사내 10개 팀에서 시범 운영 중이다.",
        "url": "https://example.test/kakao-canary",
        "published_at": "2026-10-16T08:00:00",
        "matched_keywords": ["AI agent", "업무 자동화"],
    },
    {
        "id": "eval-05",
        "origin": "synthetic",
        "source": "geeknews",
        "language": "ko",
        "content_type": "community",
        "region": "domestic",
        "novelty": "existing",
        "title": "GeekNews 토론: 한국 개발자 커뮤니티에서 Rust 채택이 늘고 있는 이유",
        "summary": "GeekNews 커뮤니티에서 국내 개발자들의 Rust 채택 경험을 공유하는 토론이 활발하다. 성능 요구가 높은 백엔드와 시스템 프로그래밍 분야에서 주로 도입되고 있다.",
        "url": "https://example.test/geeknews-rust-kr",
        "published_at": "2026-10-13T16:00:00",
        "matched_keywords": ["개발자 도구"],
    },

    # ── English · News · International · New event ────────────────────
    {
        "id": "eval-06",
        "origin": "synthetic",
        "source": "hackernews",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "new_event",
        "title": "OpenAI announces GPT-5 with native tool-use and long-term memory",
        "summary": "OpenAI has announced GPT-5, featuring built-in tool use capabilities and persistent memory across conversations. The model demonstrates significant improvements in multi-step reasoning and code generation benchmarks.",
        "url": "https://example.test/openai-gpt5",
        "published_at": "2026-10-16T06:00:00",
        "matched_keywords": ["AI agent"],
    },
    {
        "id": "eval-07",
        "origin": "synthetic",
        "source": "rss",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "new_event",
        "title": "EU AI Act enforcement begins: first compliance deadlines hit",
        "summary": "The European Union's AI Act enters its first enforcement phase, requiring high-risk AI systems to undergo conformity assessments. Companies face fines of up to 35 million euros for non-compliance.",
        "url": "https://example.test/eu-ai-act-enforce",
        "published_at": "2026-10-15T12:00:00",
        "matched_keywords": ["AI agent", "정보보안"],
    },

    # ── English · Paper · International · New event ───────────────────
    {
        "id": "eval-08",
        "origin": "public",
        "source": "rss",
        "language": "en",
        "content_type": "paper",
        "region": "international",
        "novelty": "new_event",
        "title": "Attention Is All You Need: Revisited for Agentic Workflows",
        "summary": "A new paper revisits the transformer architecture specifically for multi-agent coordination tasks. The authors propose Agent-Attention layers that enable agents to share intermediate reasoning states.",
        "url": "https://example.test/agent-attention-paper",
        "published_at": "2026-10-14T00:00:00",
        "matched_keywords": ["AI agent"],
    },
    {
        "id": "eval-09",
        "origin": "synthetic",
        "source": "rss",
        "language": "en",
        "content_type": "paper",
        "region": "international",
        "novelty": "existing",
        "title": "Survey: State of Retrieval-Augmented Generation in Enterprise Settings",
        "summary": "A comprehensive survey of 47 enterprise deployments of RAG systems, analyzing common failure modes including hallucination rates, retrieval accuracy, and latency trade-offs in production environments.",
        "url": "https://example.test/rag-enterprise-survey",
        "published_at": "2026-09-28T00:00:00",
        "matched_keywords": ["AI agent", "생산성 툴"],
    },

    # ── English · Project · International · New event ─────────────────
    {
        "id": "eval-10",
        "origin": "public",
        "source": "github",
        "language": "en",
        "content_type": "project",
        "region": "international",
        "novelty": "new_event",
        "title": "langchain-ai/langgraph: Build stateful multi-agent applications",
        "summary": "LangGraph is a library for building stateful, multi-actor applications with LLMs. It extends LangChain with cyclic computational graphs for agent coordination and persistent state management.",
        "url": "https://github.com/langchain-ai/langgraph",
        "published_at": "2026-10-12T00:00:00",
        "matched_keywords": ["AI agent", "개발자 도구"],
    },
    {
        "id": "eval-11",
        "origin": "public",
        "source": "github",
        "language": "en",
        "content_type": "project",
        "region": "international",
        "novelty": "existing",
        "title": "microsoft/autogen: Framework for multi-agent conversation",
        "summary": "AutoGen is an open-source framework enabling the development of LLM applications using multiple agents that can converse with each other to solve tasks. Supports customizable and conversable agents.",
        "url": "https://github.com/microsoft/autogen",
        "published_at": "2026-10-01T00:00:00",
        "matched_keywords": ["AI agent"],
    },

    # ── English · Community · International ───────────────────────────
    {
        "id": "eval-12",
        "origin": "synthetic",
        "source": "hackernews",
        "language": "en",
        "content_type": "community",
        "region": "international",
        "novelty": "new_event",
        "title": "Show HN: I built an AI agent that manages our entire DevOps pipeline",
        "summary": "A solo developer shares their experience building an AI agent that handles CI/CD, monitoring alerts, and incident response for a 50-person startup. Reduced on-call incidents by 60%.",
        "url": "https://example.test/hn-devops-agent",
        "published_at": "2026-10-15T18:00:00",
        "matched_keywords": ["AI agent", "업무 자동화"],
    },
    {
        "id": "eval-13",
        "origin": "synthetic",
        "source": "hackernews",
        "language": "en",
        "content_type": "community",
        "region": "international",
        "novelty": "existing",
        "title": "Ask HN: What's the best way to evaluate LLM outputs systematically?",
        "summary": "A Hacker News discussion on systematic evaluation methods for LLM outputs. Top comments recommend a combination of automated metrics (BLEU, ROUGE) and human evaluation with rubric-based scoring.",
        "url": "https://example.test/hn-llm-eval",
        "published_at": "2026-10-10T20:00:00",
        "matched_keywords": ["AI agent", "생산성 툴"],
    },

    # ── Korean · News · Domestic · Existing ───────────────────────────
    {
        "id": "eval-14",
        "origin": "synthetic",
        "source": "rss",
        "language": "ko",
        "content_type": "news",
        "region": "domestic",
        "novelty": "existing",
        "title": "네이버 클로바X, 기업용 AI 에이전트 기능 업데이트",
        "summary": "네이버가 클로바X의 기업용 AI 에이전트 기능을 업데이트했다. 이메일 자동 분류, 문서 요약, 일정 관리 등의 업무 자동화 기능이 강화됐다.",
        "url": "https://example.test/naver-clovax-update",
        "published_at": "2026-10-11T10:00:00",
        "matched_keywords": ["AI agent", "업무 자동화"],
    },
    {
        "id": "eval-15",
        "origin": "synthetic",
        "source": "rss",
        "language": "ko",
        "content_type": "news",
        "region": "domestic",
        "novelty": "new_event",
        "title": "과기정통부, AI 안전 가이드라인 개정안 행정예고",
        "summary": "과학기술정보통신부가 AI 안전 가이드라인 개정안을 행정예고했다. 생성형 AI의 학습 데이터 출처 공개 의무와 고위험 AI 시스템의 사전 안전성 평가 요건이 포함됐다.",
        "url": "https://example.test/msit-ai-safety",
        "published_at": "2026-10-16T07:00:00",
        "matched_keywords": ["정보보안", "AI agent"],
    },

    # ── Mixed language edge cases ─────────────────────────────────────
    {
        "id": "eval-16",
        "origin": "synthetic",
        "source": "geeknews",
        "language": "ko",
        "content_type": "community",
        "region": "domestic",
        "novelty": "new_event",
        "title": "GitHub Copilot Workspace 한국어 지원 시작 — 첫 사용 후기",
        "summary": "GitHub Copilot Workspace가 한국어 인터페이스를 지원하기 시작했다. 한국 개발자의 첫 사용 후기로, 한글 변수명 인식과 주석 생성 품질을 평가한다.",
        "url": "https://example.test/copilot-workspace-ko",
        "published_at": "2026-10-15T15:00:00",
        "matched_keywords": ["개발자 도구", "생산성 툴"],
    },
    {
        "id": "eval-17",
        "origin": "synthetic",
        "source": "hackernews",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "new_event",
        "title": "Anthropic's Claude now supports real-time web browsing in agent mode",
        "summary": "Anthropic has released a major update to Claude enabling real-time web browsing capabilities within its agent mode. The feature allows Claude to search, read, and synthesize web content during conversations.",
        "url": "https://example.test/claude-web-browsing",
        "published_at": "2026-10-16T03:00:00",
        "matched_keywords": ["AI agent"],
    },

    # ── Stress tests: edge cases for quality checks ───────────────────
    {
        "id": "eval-18",
        "origin": "synthetic",
        "source": "rss",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "existing",
        "title": "",  # Empty title — tests graceful fallback
        "summary": "A brief update on ongoing developments in the productivity tools space.",
        "url": "https://example.test/no-title",
        "published_at": "2026-10-14T00:00:00",
        "matched_keywords": ["생산성 툴"],
    },
    {
        "id": "eval-19",
        "origin": "synthetic",
        "source": "rss",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "new_event",
        "title": "Breaking: Major security vulnerability discovered in popular npm package affecting 12M+ downloads weekly",
        "summary": "",  # Empty summary — tests title-only briefing
        "url": "https://example.test/npm-vuln",
        "published_at": "2026-10-16T01:00:00",
        "matched_keywords": ["정보보안", "개발자 도구"],
    },
    {
        "id": "eval-20",
        "origin": "synthetic",
        "source": "rss",
        "language": "ko",
        "content_type": "news",
        "region": "domestic",
        "novelty": "new_event",
        "title": "삼성전자, 갤럭시 AI 에이전트 '삼성 어시스턴트 프로' 출시 — 일정·메일·쇼핑 자동화 지원, 연내 10개국 확대 예정",
        "summary": "삼성전자가 갤럭시 AI 에이전트 '삼성 어시스턴트 프로'를 출시했다. 일정 관리, 메일 자동 분류, 쇼핑 비교 기능을 제공하며, 연내 10개국으로 서비스를 확대할 예정이다.",
        "url": "https://example.test/samsung-assistant-pro",
        "published_at": "2026-10-16T06:30:00",
        "matched_keywords": ["AI agent"],
    },

    # ── Additional variety: paper, project, community ─────────────────
    {
        "id": "eval-21",
        "origin": "synthetic",
        "source": "rss",
        "language": "ko",
        "content_type": "paper",
        "region": "domestic",
        "novelty": "new_event",
        "title": "KAIST 연구진, 한국어 환각 탐지 데이터셋 'KoHallu' 공개",
        "summary": "KAIST 연구진이 한국어 대규모 언어 모델의 환각(hallucination) 현상을 평가하기 위한 데이터셋 KoHallu를 공개했다. 뉴스 요약, 질의응답, 사실 검증 등 3개 태스크를 포함한다.",
        "url": "https://example.test/kaist-kohallu",
        "published_at": "2026-10-15T00:00:00",
        "matched_keywords": ["AI agent", "한국어 NLP"],
    },
    {
        "id": "eval-22",
        "origin": "public",
        "source": "github",
        "language": "en",
        "content_type": "project",
        "region": "international",
        "novelty": "existing",
        "title": "pydantic/pydantic: Data validation using Python type annotations",
        "summary": "Pydantic provides data validation and settings management using Python type annotations. V2 features a complete rewrite in Rust for 5-50x performance improvements.",
        "url": "https://github.com/pydantic/pydantic",
        "published_at": "2026-09-30T00:00:00",
        "matched_keywords": ["개발자 도구"],
    },
    {
        "id": "eval-23",
        "origin": "synthetic",
        "source": "hackernews",
        "language": "en",
        "content_type": "community",
        "region": "international",
        "novelty": "new_event",
        "title": "Why I stopped using AI coding assistants after 6 months",
        "summary": "A senior engineer shares their experience abandoning AI coding assistants. Key issues include subtle bug introduction, over-reliance on generated code, and difficulty in code review when AI-generated code looks superficially correct.",
        "url": "https://example.test/hn-stop-ai-coding",
        "published_at": "2026-10-14T22:00:00",
        "matched_keywords": ["개발자 도구", "AI agent"],
    },
    {
        "id": "eval-24",
        "origin": "synthetic",
        "source": "rss",
        "language": "ko",
        "content_type": "news",
        "region": "domestic",
        "novelty": "new_event",
        "title": "금융위원회, AI 기반 자동 투자 서비스 감독 규정 시행",
        "summary": "금융위원회가 AI 기반 자동 투자 서비스에 대한 감독 규정을 시행했다. AI 투자 자문의 투명성 확보, 고객 설명 의무, 알고리즘 공개 범위 등이 규정에 포함됐다.",
        "url": "https://example.test/fsc-ai-invest-regulation",
        "published_at": "2026-10-16T05:00:00",
        "matched_keywords": ["AI agent"],
    },
    {
        "id": "eval-25",
        "origin": "synthetic",
        "source": "rss",
        "language": "en",
        "content_type": "news",
        "region": "international",
        "novelty": "new_event",
        "title": "Google DeepMind releases AlphaFold 3 with expanded protein-ligand prediction",
        "summary": "Google DeepMind has released AlphaFold 3, extending predictions beyond proteins to include ligands, nucleic acids, and post-translational modifications. The model achieves state-of-the-art accuracy on drug-target interaction benchmarks.",
        "url": "https://example.test/alphafold3",
        "published_at": "2026-10-15T14:00:00",
        "matched_keywords": ["AI agent"],
    },
]


"""Multi-profile evaluation: same source, different user profiles.

These test whether the briefing system adapts recommendations to different
user contexts, or produces identical output regardless of profile.
"""

EVAL_PROFILES = [
    {"role": "예비 창업자", "id": "founder", "keywords": ["AI agent", "업무 자동화", "스타트업"]},
    {"role": "기술 분야 취업 준비생", "id": "job_seeker", "keywords": ["개발자 도구", "AI agent", "채용"]},
    {"role": "AI 연구자", "id": "researcher", "keywords": ["AI agent", "한국어 NLP", "논문"]},
    {"role": "금융·경제 관심 사용자", "id": "finance", "keywords": ["AI agent", "투자", "규제"]},
    {"role": "일반 기술 관심 사용자", "id": "general_tech", "keywords": ["생산성 툴", "개발자 도구"]},
]

# Items to test with multiple profiles — covers diverse content types
MULTI_PROFILE_ITEM_IDS = ["eval-06", "eval-07", "eval-15", "eval-04"]


def get_multi_profile_pairs():
    """Generate (item, profile) pairs for multi-profile evaluation."""
    items_by_id = {item["id"]: item for item in EVAL_ITEMS}
    pairs = []
    for item_id in MULTI_PROFILE_ITEM_IDS:
        item = items_by_id.get(item_id)
        if not item:
            continue
        for profile in EVAL_PROFILES:
            augmented = {**item, "eval_profile": profile["id"], "eval_role": profile["role"]}
            pairs.append(augmented)
    return pairs


def dataset_summary():
    """Print a summary of the evaluation dataset composition."""
    from collections import Counter
    counts = {
        "total": len(EVAL_ITEMS),
        "origin": Counter(i["origin"] for i in EVAL_ITEMS),
        "language": Counter(i["language"] for i in EVAL_ITEMS),
        "content_type": Counter(i["content_type"] for i in EVAL_ITEMS),
        "region": Counter(i["region"] for i in EVAL_ITEMS),
        "novelty": Counter(i["novelty"] for i in EVAL_ITEMS),
        "source": Counter(i["source"] for i in EVAL_ITEMS),
        "multi_profile_items": len(MULTI_PROFILE_ITEM_IDS),
        "multi_profile_total": len(MULTI_PROFILE_ITEM_IDS) * len(EVAL_PROFILES),
    }
    return counts
