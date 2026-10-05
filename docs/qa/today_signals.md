# 오늘의 신호: 출처, 설명, 추가 보기

## 변경 범위

- 원문 URL·RSS 피드 메타데이터에 따른 출처 표시와 수집 경로 분리.
- 게시 형식 접두어 제거, 기존 번역 경로 재사용, 제한적인 한국어 질문 어투 정리.
- 제목·설명에 근거한 내용 정리와 정보 부족/번역 실패 안내. 새 외부 서비스나 개인 맥락 전송 없음.
- 생성 시 중복 제거한 후보를 `signal_reserves`에 순서대로 스냅샷 저장. 기본 개수 이후 후보는 요청 시 최대 3개씩 신호로 저장.
- 추가 후보 저장은 기존 DB에 테이블을 추가하는 방식이며 사용자 데이터 초기화 없음.
- 후보 목록은 생성 시점의 순서를 유지하고, 추가 요청 시 수집·재랭킹하지 않음. 동점은 후보 ID 순서로 고정.
- 기본 신호와 추가 신호에 동일한 원문·피드백 경로 사용. 반복 요청은 트랜잭션 안에서 중복 검사.
- 재생성된 회차나 날짜가 지난 회차의 추가 요청은 거절. 기존 브리핑의 추가 신호도 기존 교체 흐름에 따라 보관 처리.

## 자동 검증 명령

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe tests/smoke_test.py
node tests/web_signals_test.cjs
node tests/web_interests_test.cjs
node --check src/web/static/app.js
```

새 Python 테스트는 임시 DB와 주입된 번역 결과를 사용한다. 새 화면 테스트는 Node VM의 DOM 대역을 사용한다.

실행 결과 (2026-09-24):

- Python unittest: 21개 통과.
- 기존 `smoke_test.py`: 통과. health, 기본 생성 4개, hybrid 생성 4개, 직접 mock 생성 4개, 피드백 확인.
- `web_signals_test.cjs`, `web_interests_test.cjs`: 통과.
- JavaScript 문법 검사, Python compileall, `git diff --check`: 통과.
- 최초 실행은 Windows 임시 폴더 권한으로 실패했으며 권한 허용 후 재실행했다. 개발 중 발견한 번역 실패 안내 누락과 이전 화면 문구를 검사하던 스모크 assertion을 수정한 뒤 위 결과를 확인했다.
- 기존 datetime 및 TestClient 의존성의 deprecation 경고가 출력됐다.
- 실제 브라우저 클릭, 실시간 번역 품질, portable 빌드는 이번 작업에서 확인하지 않았다.

## 변경 파일

- `src/web/static/app.js`, `src/web/static/styles.css`: 카드·상세 설명·추가 보기 UI.
- `src/api/signals.py`: 추가 신호 API와 잔여 후보 상태.
- `src/signals/provenance.py`, `src/signals/korean_briefing.py`: 출처와 한국어 표시.
- `src/signals/generator.py`, `src/signals/mock_generator.py`, `src/signals/pipeline.py`: 후보 스냅샷과 수집 유형 전달.
- `src/signals/identity.py`, `src/signals/ranking.py`: 링크 중복 판별과 동점 순서 고정.
- `src/storage/migrations.py`, `src/storage/sqlite_store.py`: 후보 보존, 원자적 추가, 기존 표시 메타데이터 갱신.
- `tests/test_today_signals.py`, `tests/web_signals_test.cjs`, `tests/smoke_test.py`: 신규 검증과 변경 문구 반영.
- `README.md`, `docs/qa/today_signals.md`: 동작 설명과 검증 기록.

검증 대상: 출처 오인 방지, YouTube 링크 변형 중복, mock 표시, 게시 접두어 제거, 원문 보존, 설명 부족, 번역 실패, 추가 후보 순서, 소진, 부족한 후보, 반복·동시 요청, 회차 교체, 재시작 후 보존, 추가 자료 피드백, 기본 개수 설정 유지, HTML 이스케이프, 버튼 중복 클릭 및 실패 후 재시도.

## 수동 확인 절차 (별도 실행 필요)

1. 앱 서버를 재시작하고 브라우저를 새로고침한다.
2. 관심사에 맞는 자료를 기본 개수보다 많이 확보할 수 있는 소스로 신호를 생성한다.
3. 출처와 수집 경로, 샘플 표시, 생성 당시 모드를 확인한다.
4. 자세히 보기의 한국어 설명과 원문을 대조한다.
5. 추가 보기로 중복 없는 자료가 순서대로 늘어나는지 확인한다.
6. 추가 자료에서 저장·관심 없음·계속 추적·원문 열기를 확인한다.
7. 새로고침 후 유지, 후보 소진 안내, 새 생성 후 목록 교체를 확인한다.

## 한계

- 임의의 영어 제목을 편집자가 쓴 수준으로 재작성하는 기능은 아니다. 기존 번역 결과와 보수적인 표면 규칙을 사용한다.
- 기사 전문·영상·자막을 새로 가져오지 않으며, 자세히 보기는 확보된 제목과 설명의 범위에 한정된다.
- 이전 버전의 브리핑에는 추가 후보 스냅샷이 없다. 새 생성부터 추가 보기 지원.
- 출처 메타데이터가 없거나 URL로 확인할 수 없으면 출처 미확인으로 남긴다. 과거 수집 유형을 추정해 live로 표시하지 않는다.
- 실제 브라우저 클릭, 실시간 외부 서비스의 번역 품질, Windows portable 빌드는 자동 테스트만으로 검증되지 않는다.
