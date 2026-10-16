# Engine v2 Production Transition Checklist

이 문서는 v2 하이브리드 브리핑 엔진을 실제 운영 환경에서 활성화하기 위해 필요한 단계를 정리합니다.
현재 모든 엔진 코드는 `LUMOS_ENGINE_V2=false` (기본값)로 비활성 상태이며,
테스트는 100% 오프라인 mock 데이터로만 동작합니다.

---

## 1. 환경 변수 설정

| 변수 | 값 | 설명 |
|------|-----|------|
| `LUMOS_ENGINE_V2` | `true` | 엔진 기능 플래그 활성화 |
| `LUMOS_ENGINE_EXTERNAL_CALLS` | `true` | 외부 API 호출 허용 |
| `GEMINI_API_KEY` | `<key>` | Gemini Flash (cheap tier) API 키 |
| `LUMOS_BLOCK_EXTERNAL_CALLS` | 삭제 또는 `false` | 테스트용 차단 해제 |
| `LUMOS_TEST_MODE` | 삭제 | 운영 환경에서 제거 |

## 2. 데이터베이스 준비

- [ ] `engine_jobs` 테이블 생성 확인 (SQLiteQueueStore 초기화 시 자동 생성)
- [ ] `briefing_cache` 테이블 생성 확인 (BriefingCache 초기화 시 자동 생성)
- [ ] `engine_usage` 테이블 생성 확인 (BudgetTracker 초기화 시 자동 생성)
- [ ] 운영 DB 경로 설정 (`:memory:` 대신 파일 경로 지정)
- [ ] SQLite WAL 모드 활성화 확인 (코드에서 자동 설정)
- [ ] 기존 사용자 설정(signal_count 등) 보존 확인

## 3. LLM 프로바이더 구현

- [ ] `GeminiFlashProvider` 구현 (cheap tier — 한국어 요약, 제목 번역)
- [ ] `GeminiProProvider` 또는 대안 구현 (expensive tier — 복잡한 분석)
- [ ] 프로바이더 응답 형식 검증 (validator.py의 `validate_briefing()` 기준)
- [ ] 비용 추정 로직 구현 (토큰 수 × 단가 → UsageRecord)
- [ ] Rate limit 및 재시도 로직 추가

## 4. 수집 커넥터 연동

- [ ] GitHub Trending 수집기 구현 (`CollectionCoordinator` 핸들러 등록)
- [ ] 기타 소스 수집기 구현 (Hacker News, Product Hunt 등)
- [ ] 수집기 핸들러를 `register_handler()` 로 등록
- [ ] 수집 결과 → `RawCandidate` 변환 로직 구현
- [ ] 수집기별 Rate limit 준수 확인

## 5. 스케줄러 활성화

- [ ] `EngineConfig.collection.scheduler_enabled = True` 설정
- [ ] 스케줄 간격 설정 (기본: 3600초)
- [ ] WorkerPool `max_workers` 확인 (기본: 3)
- [ ] 리스 만료 복구 주기 확인
- [ ] 스케줄러 시작/종료 로그 확인

## 6. 예산 한도 조정

- [ ] `daily_budget_usd` 운영 값 설정 (기본: $1.00)
- [ ] `monthly_budget_usd` 운영 값 설정 (기본: $10.00)
- [ ] `max_chat_requests_per_day` 확인 (기본: 50)
- [ ] `max_daily_collection_jobs` 확인 (기본: 100)
- [ ] `max_daily_briefing_generations` 확인 (기본: 200)
- [ ] `max_daily_expensive_llm_calls` 확인 (기본: 20)
- [ ] `max_briefing_display_count` 플랜별 설정 (free: 5, pro: 10)
- [ ] 예산 초과 시 알림 메커니즘 구현

## 7. API 엔드포인트 검증

- [ ] `GET /engine/briefing` — 읽기 전용 동작 확인 (LLM 호출 없음)
- [ ] `POST /engine/briefing/dismiss` — 카드 제거 + 백필 동작 확인
- [ ] `POST /engine/briefing/undo-dismiss` — 되돌리기 동작 확인
- [ ] `GET /engine/status` — 엔진 상태 반환 확인
- [ ] 기존 `/api/v1/signals` 엔드포인트와의 호환성 확인

## 8. 프론트엔드 연동

- [ ] 카드 "이런 소식 줄이기" 버튼 → dismiss API 연결
- [ ] 되돌리기 토스트 → undo-dismiss API 연결
- [ ] 백필 카드 로딩 애니메이션 구현
- [ ] 엔진 v2 상태 표시 (선택적)

## 9. 모니터링

- [ ] 예산 사용량 대시보드 (`BudgetTracker.get_usage_summary()`)
- [ ] 큐 상태 모니터링 (pending/running/failed 카운트)
- [ ] LLM 호출 성공/실패율 로깅
- [ ] 캐시 적중률 측정
- [ ] 수집 작업 소요 시간 추적

## 10. 안전 장치 확인

- [ ] `ExternalCallBlocked` 예외가 적절히 처리되는지 확인
- [ ] 예산 초과 시 캐시된 콘텐츠는 계속 서비스되는지 확인
- [ ] 리스 만료된 작업이 올바르게 복구되는지 확인
- [ ] max_retries 초과 시 FAILED 상태로 전환되는지 확인
- [ ] 스케줄러 비활성 시 수동 트리거만 작동하는지 확인

## 11. 단계적 전환 계획

1. **Phase 0 (현재)**: 엔진 코드 병합, 플래그 OFF, 모든 테스트 오프라인
2. **Phase 1**: 개발 환경에서 `LUMOS_ENGINE_V2=true` + mock 프로바이더로 통합 테스트
3. **Phase 2**: 스테이징에서 실제 Gemini API 연결, 소수 테스트 사용자
4. **Phase 3**: 프로덕션 롤아웃 — 기존 v1 파이프라인과 병렬 운영
5. **Phase 4**: v1 파이프라인 비활성화, v2 단독 운영

## 12. 롤백 계획

- `LUMOS_ENGINE_V2=false` 설정으로 즉시 v1 복귀 가능
- 엔진 DB 테이블은 기존 테이블과 독립적 (삭제 불필요)
- 프론트엔드 설정 UI는 v1/v2 모두 호환
