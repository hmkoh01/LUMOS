# Known Issues Template

## Scope

이 문서는 closed beta build에 포함할 known issues 초안이다.

## Known Issues

- Windows 우선 검증 단계다.
- 아직 installer가 없다.
- 아직 auto-update가 없다.
- 아직 code signing이 없다.
- cloud login은 production 기능이 아니다.
- payment와 subscription 검증은 연결되지 않았다.
- 일부 source 품질은 mock/hybrid 상태에 따라 달라질 수 있다.
- OS 보안 저장소는 prototype 단계다.
- 외부 source 연결이 불안정하면 안정 모드 또는 demo mode로 확인해야 한다.
- 오류 보고와 crash reporting은 아직 수동이다.

## User Data Notes

- 민감한 개인 데이터는 피드백에 포함하지 않는다.
- 브라우저 기록이나 로컬 파일 원문을 그대로 공유하지 않는다.
- 문제가 생기면 화면 설명, 실행 단계, 오류 문구 중심으로 전달한다.

## Workarounds

- Companion이 열리지 않으면 `python run.py app` 또는 안내받은 대체 실행 방식을 사용한다.
- source 수집이 실패하면 안정 모드/mock 기반 신호로 확인한다.
- deep link가 이동하지 않으면 Web UI의 탭을 직접 클릭한다.

## Must Fix Before Wider Beta

- Python 없이 실행 가능한 portable build
- 첫 실행 안정성
- 오류 문구 한국어화
- 데이터 저장/삭제 안내
- 릴리즈 노트와 privacy note 동봉
