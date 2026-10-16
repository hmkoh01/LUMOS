# Engine v2 Completion Report

## 1. 구현 모듈 목록

| 모듈 | 경로 | 파일 수 | 설명 |
|------|------|---------|------|
| engine core | `src/engine/` | 4 | `__init__`, `config`, `models`, `safety` |
| queue | `src/engine/queue/` | 5 | `store` (ABC), `sqlite_store`, `worker`, `scheduler`, `__init__` |
| collection | `src/engine/collection/` | 3 | `planner`, `coordinator`, `__init__` |
| evaluation | `src/engine/evaluation/` | 3 | `periods`, `scorer`, `__init__` |
| llm | `src/engine/llm/` | 5 | `providers`, `cache`, `validator`, `router`, `__init__` |
| personalization | `src/engine/personalization/` | 3 | `ranker`, `backfill`, `__init__` |
| budget | `src/engine/budget/` | 3 | `tracker`, `limits`, `__init__` |
| api | `src/api/engine.py` | 1 | 엔진 v2 전용 API 라우터 |
| **합계** | | **27** | |

## 2. 큐 구조

**테이블**: `engine_jobs` (SQLite, WAL mode)

```
id, job_type, dedupe_key (UNIQUE), status, priority,
payload_json, result_json, error_message,
retry_count, max_retries, lease_owner, lease_expires_at,
created_at, updated_at
```

**핵심 연산**:
- **Enqueue**: `dedupe_key` 기준 중복 방지 — PENDING/RUNNING 상태의 동일 키 존재 시 기존 job 반환
- **Claim**: `UPDATE ... WHERE id = (SELECT id FROM engine_jobs WHERE status='pending' ORDER BY priority DESC LIMIT 1)` — 원자적 할당
- **Fail**: `retry_count < max_retries`면 PENDING 복귀, 아니면 FAILED
- **Lease 복구**: `lease_expires_at < now`인 RUNNING job을 PENDING으로 복귀

## 3. 중복 제거 방식

```
dedupe_key = SHA-256(normalised_keyword | source_type | date_start | date_end)
```

- 키워드 정규화: 소문자 변환 + 공백 제거 + 동의어 사전 매핑 (`INTEREST_SYNONYMS`)
  - 예: "AI agent" → "ai agent", "인공지능" → "ai"
- 50명이 같은 관심사를 등록해도 수집 job은 1개
- COMPLETED/FAILED/CANCELLED 상태의 job은 중복 검사에서 제외 → 재수집 가능

## 4. 기간별 독립 평가

| 기간 | recency | engagement | interest_match | source_trust |
|------|---------|------------|----------------|--------------|
| DAILY | 0.40 | 0.25 | 0.25 | 0.10 |
| WEEKLY | 0.15 | 0.35 | 0.35 | 0.15 |
| MONTHLY | 0.05 | 0.25 | 0.50 | 0.20 |

- **Daily**: 최신성 중시 — 24시간 이내 = 1.0, 48시간 이상 = 0.0
- **Weekly**: 관여도 + 관심 매칭 균형 — 7일 윈도우
- **Monthly**: 관심 일치도 최우선 — 30일 윈도우
- Weekly는 Daily의 집계가 **아님** — 별도 가중치로 독립 채점

## 5. LLM 라우팅

```
Rule-based → Cache hit → Cheap LLM → Expensive LLM
```

1. **Rule-based**: 제목에 한국어가 이미 포함되어 있으면 LLM 없이 바로 생성 (confidence: 0.5)
2. **Cache hit**: `briefing_cache` 테이블에서 `dedupe_key`로 조회 — 같은 콘텐츠는 사용자 간 공유
3. **Cheap LLM** (Gemini Flash): 5개씩 배치 프롬프트, JSON 응답 파싱
4. **Expensive LLM** (Gemini Pro): cheap 실패 시 fallback, 일일 호출 한도 별도 관리

**캐시 공유**: 동일 `dedupe_key`의 한국어 요약은 한 번만 생성 → 전 사용자 재사용.
캐시된 브리핑 표시는 LLM 사용량에 **포함되지 않음**.

## 6. 백필 메커니즘

```
사용자 "이런 소식 줄이기" 클릭
  → dismissed 목록에 추가
  → displayed 목록에서 제거
  → reserve 후보 중 상위 1개 선택 (ignored/displayed 제외)
  → 캐시에 한국어 브리핑 있으면 즉시 교체
  → 없으면 needs_generation=True 반환
  → 되돌리기(undo) 시 원래 상태 복원
```

- Reserve 후보: 메인 표시 개수 이후 순위 (importance_score 기준)
- Saved 상태는 preference와 독립 — dismissed 해도 saved 유지

## 7. 설정 UI 변경 사항

**제거됨**:
- "소식 새로 받기" 버튼 (hero-actions에서)
- 브리핑 시간 입력 (설정 탭 + 온보딩 3단계)
- 자동 브리핑 토글
- 모드 선택 (안정/혼합/실제 소스) — 설정 탭 + 온보딩 3단계

**유지됨**:
- 소식 개수 선택 (1/3/5/7개)
- 저장 버튼

**추가됨**:
- 안내 텍스트: "소식은 관심사를 기반으로 자동 수집되며, 매일 아침 새로운 브리핑이 준비됩니다."
- 무료 플랜 시 7개 옵션 비활성화 로직

## 8. 테스트 결과

**총 110개 테스트, 전체 통과** (`pytest tests/test_engine_*.py` — 1.45초)

| 파일 | 테스트 수 | 주요 검증 |
|------|-----------|----------|
| `test_engine_queue.py` | 14 | 큐 CRUD, 중복방지, 원자적 claim, 리스 만료, 50/100건 동시 |
| `test_engine_collection.py` | 14 | 동의어 정규화, 관심사 그룹핑, 예산 분배, job 생성 |
| `test_engine_evaluation.py` | 12 | 기간 범위, 독립 채점, 임계값 필터, 후보 제한 |
| `test_engine_llm.py` | 18 | 룰 기반 생성, 캐시 CRUD, 만료, 검증, JSON 파싱, 라우팅 |
| `test_engine_backfill.py` | 14 | 후보 선택, 백필, 되돌리기, saved 독립, 개인화 |
| `test_engine_budget.py` | 12 | 사용량 추적, 일일/월간 한도, 캐시 무료, 플랜 제한 |
| `test_engine_safety.py` | 9 | 기본 차단, 환경변수, API키 무시, 스케줄러 비활성 |
| `test_engine_integration.py` | 17 | 전체 파이프라인 통합, 설정 보존, GET 부작용 없음 |

## 9. 실행하지 않은 외부 테스트

다음 테스트는 **의도적으로 실행하지 않았으며** 실제 외부 호출이 필요합니다:

- Gemini Flash API 실제 호출 테스트
- Gemini Pro API 실제 호출 테스트
- GitHub Trending 실제 크롤링 테스트
- Hacker News API 실제 호출 테스트
- 운영 DB (파일 기반 SQLite) 동시성 테스트
- 스케줄러 실시간 동작 테스트 (cron 주기)
- 다중 프로세스 WAL 동시 쓰기 테스트

**이유**: 사양서 Section 11 "절대 하지 말 것" — 실제 API 호출, 외부 네트워크 요청, 운영 DB 변경, 스케줄러 활성화 금지.

## 10. 운영 전환 시 필요한 설정

```env
# 필수
LUMOS_ENGINE_V2=true
LUMOS_ENGINE_EXTERNAL_CALLS=true
GEMINI_API_KEY=<your-api-key>

# 제거
LUMOS_TEST_MODE=          # (삭제)
LUMOS_BLOCK_EXTERNAL_CALLS=  # (삭제)

# 선택
LUMOS_ENGINE_SCHEDULER=true
LUMOS_ENGINE_DAILY_BUDGET=1.00
LUMOS_ENGINE_MONTHLY_BUDGET=10.00
```

상세 내용: `docs/product/engine_v2_production_checklist.md` 참조.

## 11. 비활성 상태로 대기 중인 기능

| 기능 | 활성화 조건 | 현재 상태 |
|------|------------|----------|
| 수집 스케줄러 | `scheduler_enabled=True` + `enabled=True` | OFF |
| 외부 API 호출 | `external_calls_allowed=True` + env var 없음 | BLOCKED |
| LLM 실제 호출 | Gemini API 키 설정 + 예산 여유 | MockProvider 사용 중 |
| 백필 실시간 교체 | 엔진 활성화 후 reserve 후보 존재 시 | 구조만 구현 |
| 카드 dismiss UI | 프론트엔드 버튼 연결 필요 | API만 구현 |
| 예산 알림 | 모니터링 대시보드 구현 필요 | 데이터만 수집 |

**모든 코드는 병합 즉시 안전합니다.** `LUMOS_ENGINE_V2` 플래그가 `false`(기본값)인 한 기존 동작에 영향을 주지 않습니다.
