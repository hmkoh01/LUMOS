# Engine v2 — 오프라인 최종 통합 검증 보고서

## 검증 일자: 2026-10-16

---

## 1. Period Eligibility (적격성 분리)

**발견된 결함**: `evaluate_candidates()`가 기간 범위 밖 후보도 점수를 매겨, DAILY에서 20일 전 항목이 engagement(0.93) + interest_match(1.00) 합산으로 최소 임계값(0.1)을 통과.

**수정 내용**: `is_within_period()` 함수 추가. `evaluate_candidates()`에서 점수 산정 전에 날짜 기반 적격성 필터를 실행.
- known date → `ref_start ≤ pub_date ≤ ref_end` 여부
- unknown date (None/"") → eligible (증명 불가 → 포함)

**검증 테스트: 13건 전부 통과**

| 테스트 | 검증 내용 |
|--------|----------|
| `test_daily_excludes_yesterday` | 어제 23:59:59 → DAILY 제외 |
| `test_daily_includes_today` | 오늘 00:01:00 → DAILY 포함 |
| `test_daily_includes_end_of_day` | 오늘 23:59:59 → DAILY 포함 |
| `test_weekly_boundary_monday` | 월요일 포함, 그 전 일요일 제외 |
| `test_weekly_boundary_sunday` | 일요일 포함, 다음 월요일 제외 |
| `test_monthly_boundary_first_last` | 10/1 포함, 9/30 및 11/1 제외 |
| `test_unknown_date_eligible` | None/"" → eligible (None 반환) |
| `test_unknown_date_scored_with_default_recency` | 날짜 없는 후보 recency=0.3 |
| `test_utc_vs_kst_date_boundary` | UTC/KST 같은 날짜로 파싱 확인 |
| `test_utc_late_night_crosses_kst_boundary` | UTC 10/15 23:00 → date=10/15 (제외) |
| `test_evaluate_empty_candidates` | 빈 리스트 → 빈 결과 |
| `test_evaluate_all_ineligible` | 전부 범위 밖 → 빈 결과 |
| `test_pushed_at_vs_published_at_awareness` | pushed_at ≠ published_at 구분 |

---

## 2. Diverse Interest + SQLite WAL

**시나리오**: 100명 사용자 × 고유 관심사, 인기/니치 혼합, file-based SQLite WAL.

**검증 테스트: 10건 전부 통과**

| 테스트 | 검증 내용 | 수치 |
|--------|----------|------|
| `test_100_unique_interests` | 100개 고유 키워드 그룹화 | groups ≥ 50 |
| `test_100_unique_capped_by_budget` | 예산 제한 시 job 제한 | max_collection_jobs_per_run=10 적용 |
| `test_new_users_burst` | 신규 50명 동시 유입 | 중복 없이 처리 |
| `test_no_starvation_popular_vs_niche` | 인기 vs 니치 관심사 공존 | 니치도 job 생성 확인 |
| `test_file_based_queue_basic` | 파일 기반 SQLite 큐 | WAL mode 확인 |
| `test_file_based_dedup` | 파일 기반 중복 제거 | 100회 enqueue → 10개 |
| `test_file_based_concurrent_connections` | 별도 connection 읽기 | 동시 읽기 정합성 |
| `test_file_based_concurrent_claims` | 동시 claim 원자성 | N claims → N unique jobs |
| `test_file_based_lease_expiry` | 리스 만료 후 재시도 | lease_timeout_seconds=1 |
| `test_different_sources_per_user` | 사용자별 소스 선택 | 소스별 job 분리 |

---

## 3. LLM Batch + Budget Edge Cases

**검증 테스트: 9건 전부 통과**

| 테스트 | 검증 내용 |
|--------|----------|
| `test_batch_5_items_get_5_results` | 5개 후보 배치 → 5개 결과 |
| `test_partial_response_only_matched_items_cached` | 3/5 응답 → 3개만 캐시 |
| `test_malformed_json_graceful_fallback` | 잘못된 JSON → 에러 없이 빈 결과 |
| `test_markdown_wrapped_json_parsed` | ` ```json...``` ` 래핑 → 정상 파싱 |
| `test_no_cross_contamination_between_items` | 후보 간 데이터 오염 없음 |
| `test_cache_no_duplicate_generation` | 캐시 적중 → LLM 호출 0회 |
| `test_token_count_tracked_separately` | input/output 토큰 분리 추적 |
| `test_sequential_budget_enforcement` | 예산 초과 시 차단 |
| `test_mixed_event_types_independent` | llm_cheap/collection 비용 독립 합산 |

---

## 4. Dismiss/Backfill API Integration

**검증 테스트: 11건 전부 통과** (5 advanced + 6 API integration)

| 테스트 | 검증 내용 |
|--------|----------|
| `test_cross_period_dismiss_independence` | DAILY dismiss가 WEEKLY에 영향 없음 |
| `test_rapid_dismiss_undo_cycle` | 5회 dismiss↔undo 반복 → 상태 정합 |
| `test_backfill_picks_highest_scoring_reserve` | 정렬된 reserve에서 최상위 선택 |
| `test_async_generation_marker` | 캐시 없는 교체 → needs_generation=True |
| `test_replacement_with_cached_briefing_immediate` | 캐시 있는 교체 → 즉시 표시 |
| `test_single_dismiss_and_backfill` | 단일 카드 제외 → reserve 보충 |
| `test_sequential_multi_dismiss` | 5장 연속 제외 → 5개 다른 reserve |
| `test_dismiss_then_undo` | 제외 → 실행 취소 → 원래 상태 복원 |
| `test_dismiss_exhaust_reserves` | reserve 소진 → replaced=False |
| `test_saved_state_independent_of_dismiss` | 저장 상태와 dismiss 독립 |
| `test_dismiss_undo_then_dismiss_again` | 제외→취소→재제외 정상 동작 |

**Frontend 연결 현황**:
- 기존: `setRecommendationPreference` → `PUT /api/v1/signals/{id}/recommendation-preference`
- Engine v2: `POST /engine/briefing/dismiss` → `FeedbackService` 위임 (flag-gated)
- `POST /engine/briefing/undo-dismiss` → preference 복원
- Engine 활성화 시 frontend에서 engine API로 전환만 하면 됨

---

## 5. Feature Flag + Collector Reuse

**검증 테스트: 11건 전부 통과** (6 flag safety + 5 adapter)

### 안전 장치 3중 레이어

| 레이어 | 메커니즘 | 테스트 |
|--------|---------|--------|
| 1 | `LUMOS_BLOCK_EXTERNAL_CALLS=true` (env) | `test_safety_guard_three_layers` |
| 2 | `config.external_calls_allowed=False` | 동일 |
| 3 | `config.enabled=False` | 동일 |

### 기존 Collector 재사용

| v1 Collector | 소스 | 재사용 가능 | 비고 |
|-------------|------|:----------:|------|
| `GitHubCollector` | github | ✅ | `CollectedItem` → `RawCandidate` adapter |
| `HackerNewsCollector` | hackernews | ✅ | 동일 |
| `RSSCollector` | rss, official_ai_blogs 등 6종 | ✅ | 동일 |
| `YouTubeCollector` | youtube | ✅ | 동일 |
| `MockCollector` | mock | ✅ | 테스트 전용 |

**Adapter 구현**: `src/engine/collection/adapter.py`
- `collected_item_to_candidate()`: `CollectedItem` → `RawCandidate` 1:1 변환
- `batch_convert()`: 배치 변환
- 필드 매핑: `metrics_json` → `metrics`, 나머지 동일명
- 테스트로 검증: 변환 정확성, 배치, scorer 호환성, 빈 필드 처리

---

## 6. 최종 수치 요약

| 항목 | 수치 |
|------|------|
| **엔진 모듈 파일** | 28 (.py) |
| **테스트 파일** | 10 |
| **총 엔진 테스트** | **230** (전부 통과) |
| — 기본 단위 테스트 | 110 |
| — 운영 전환 검증 | 66 |
| — 최종 통합 검증 | 54 |
| **기간별 적격성 테스트** | 13 |
| **다양성/WAL 테스트** | 10 |
| **LLM/예산 엣지 테스트** | 9 |
| **Dismiss/backfill 테스트** | 11 |
| **Flag/adapter 테스트** | 11 |
| **외부 API 호출** | 0 |
| **실제 LLM 호출** | 0 |
| **스케줄러 활성화** | 0 |
| **feature flag 상태** | `LUMOS_ENGINE_V2=false` 유지 |

---

## 7. 발견 및 수정한 결함

| # | 결함 | 심각도 | 수정 |
|---|------|--------|------|
| 1 | DAILY에서 기간 외 후보가 engagement으로 통과 | **높음** | `is_within_period()` 적격성 필터 추가 |
| 2 | backfill이 replacement를 displayed에 미추가 → 중복 선택 | 중간 | `currently_displayed.add(replacement_key)` |
| 3 | MockLLMProvider가 배치 5개 요청에 단일 응답 반환 | 중간 | `[N]` marker 감지하여 배열 응답 |
| 4 | 50-user 테스트가 keyword pool 일부만 사용 | 낮음 | `3 + uid % len(kw_pool)` 로 변경 |

---

## 8. 전환 준비 상태

| 체크리스트 | 상태 |
|-----------|:----:|
| 기간별 평가 독립성 | ✅ |
| 50-100 동시 요청 중복 없음 | ✅ |
| 예산 초과 시 외부 호출 차단 | ✅ |
| 한국어 요약 캐시 공유 | ✅ |
| Dismiss → backfill → undo 전체 흐름 | ✅ |
| GET 엔드포인트 부작용 없음 | ✅ |
| 기존 설정 보존 | ✅ |
| 기존 Collector 재사용 가능 | ✅ |
| Feature flag으로 안전하게 격리 | ✅ |
| 테스트 환경에서 API 키 무시 | ✅ |

**결론**: 엔진 v2의 핵심 로직은 230개 오프라인 테스트로 검증 완료. 기간별 적격성 결함을 수정하여 DAILY 브리핑이 당일 항목만 표시하도록 보장. 기존 v1 Collector는 adapter를 통해 재사용 가능. `LUMOS_ENGINE_V2=true` 전환 시 추가 구현 없이 활성화할 수 있는 상태.
