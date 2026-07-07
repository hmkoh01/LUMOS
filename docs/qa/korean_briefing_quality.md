# Korean Briefing Quality QA

Date: 2026-06-25

## 평가 기준

각 샘플은 다음 기준으로 확인했다.

- 제목만 보고 무슨 신호인지 이해되는가?
- 요약이 번역투처럼 딱딱하지 않은가?
- `왜 중요한가`가 너무 뻔하지 않은가?
- `왜 나에게 추천됐나요?`가 개인화처럼 느껴지는가?
- `다음에 볼 것`이 실제 행동으로 이어지는가?
- 원문 제목과 snippet이 details에 보존되는가?
- 영어 원문이 기본 카드에 과하게 노출되지 않는가?

평가는 `좋음`, `보통`, `나쁨`으로 기록했다.

## 샘플 평가

| # | source | original_title | display_title_ko | 이해 | 자연스러움 | 개인화 | 행동 | 문제 | 수정 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Mock | AI agent tools are moving toward proactive workflow automation | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 반복 문장 가능 | 수정 |
| 2 | Mock | Signal-first UX is becoming more important for productivity tools | 생산성 툴 관련 신호를 확인해볼 만해요 | 보통 | 보통 | 보통 | 보통 | topic이 일반적 | 부분 수정 |
| 3 | Mock | Early products test personalized research automation | 스타트업 제품 관련 신호를 확인해볼 만해요 | 보통 | 보통 | 보통 | 보통 | 제목 구체성 부족 | 보류 |
| 4 | Hacker News | Show HN: Browser agent that completes repetitive web tasks | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 5 | Hacker News | Ask HN: Are personal AI assistants finally useful? | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | assistant/agent 통합 적절 | 불필요 |
| 6 | Hacker News | Open source workflow automation with local models | 업무 자동화 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 수정 |
| 7 | Hacker News | The hidden cost of agentic coding tools | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 보통 | 좋음 | 보통 | 보통 | 비용/리스크 뉘앙스 약함 | 보류 |
| 8 | GitHub | microsoft/autogen releases new multi-agent workflow features | GitHub에서 볼 만한 구현 흐름이 감지됐어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 9 | GitHub | langchain-ai/langgraph adds durable execution support | LangGraph 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | 기능 변화 구체성 약함 | 보류 |
| 10 | GitHub | openai/openai-python updates realtime API helpers | OpenAI 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | API update 맥락 약함 | 보류 |
| 11 | GitHub | browser-use/browser-use gains traction for web automation | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 12 | GitHub | crewAIInc/crewAI improves process orchestration | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 13 | RSS | OpenAI announces new tools for building agents | OpenAI 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | 제목이 너무 넓음 | 보류 |
| 14 | RSS | Anthropic shares guidance on effective AI agents | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 15 | RSS | GitHub Blog: Copilot updates for enterprise workflows | GitHub에서 볼 만한 구현 흐름이 감지됐어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |
| 16 | RSS | Vercel introduces AI SDK improvements for streaming interfaces | AI SDK 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | frontend/streaming 맥락 약함 | 보류 |
| 17 | RSS | Hugging Face releases a guide to small agentic systems | Hugging Face 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | guide 성격 약함 | 보류 |
| 18 | RSS | LangChain publishes patterns for reliable agent workflows | LangChain 관련 신호를 확인해볼 만해요 | 보통 | 좋음 | 보통 | 보통 | reliability 맥락 약함 | 보류 |
| 19 | Hacker News | Why RSS still matters for product teams | 공식 업데이트 관련 신호를 확인해볼 만해요 | 보통 | 보통 | 보통 | 보통 | RSS topic 매핑은 개선됨 | 수정 |
| 20 | GitHub | supabase/supabase adds AI assistant examples | AI 에이전트 흐름이 실제 업무 적용 쪽으로 움직이고 있어요 | 좋음 | 좋음 | 보통 | 좋음 | 없음 | 불필요 |

## 자주 발견된 어색한 패턴

1. `오늘은 X 흐름이 내 관심사와 어떻게 이어지는지 확인해보세요.` 문장이 반복됐다.
2. `생산성 툴`, `업무 자동화`, `RSS`, `GitHub 트렌드` 같은 topic을 그대로 처리하지 못하면 제목이 넓거나 어색해졌다.
3. summary에 `원문은 영어일 수 있지만` 문구가 반복되어 기본 카드가 방어적으로 느껴졌다.
4. GitHub/RSS/Hacker News source별 차이가 summary에 충분히 드러나지 않았다.

## 이번 Phase에서 수정한 패턴

- common topic normalization 추가
  - `agent`, `assistant` → `AI 에이전트`
  - `github`, `repository` → `GitHub 트렌드`
  - `workflow`, `automation`, `자동화` → `업무 자동화`
  - `productivity`, `생산성` → `생산성 툴`
  - `rss`, `blog`, `블로그` → `공식 업데이트`
- summary에서 반복적인 `원문은 영어일 수 있지만` 표현 제거
- source별 summary angle 추가
  - GitHub: 구현 사례/저장소 움직임
  - Hacker News: 개발자 커뮤니티 반응
  - RSS/Official Blogs: 공식 발표/제품 업데이트
- action 문장을 topic별로 조금 더 행동 지향적으로 수정

## 남은 한계

- 현재 방식은 rule-based 요약이므로 원문 의미를 깊게 해석하지 않는다.
- `OpenAI 관련 신호`, `LangGraph 관련 신호`처럼 고유명사 중심 제목은 이해 가능하지만 구체성은 부족하다.
- 위험/비용/논쟁성 같은 nuance는 아직 잘 드러나지 않는다.
- 개인화 문장은 interest keyword 기반이라 실제 맥락이 많을수록 좋아진다.

## 추후 개선 지점

- source item title/summary에서 동사와 변화 유형을 추출해 제목을 더 구체화한다.
- GitHub release, discussion, official announcement, guide 등 content type별 template을 추가한다.
- 외부 LLM을 쓰기 전에도 30~50개 fixture 기반 품질 테스트를 만들 수 있다.
- 실제 사용자 피드백을 받아 `왜 나에게 추천됐나요?` 문장을 더 개인화한다.
