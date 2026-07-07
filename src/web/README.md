# LUMOS Web UI

이 디렉터리는 FastAPI가 직접 서빙하는 로컬 Web UI를 담고 있습니다.

실행:

```bash
python run.py app
```

주소:

```text
http://127.0.0.1:8000/app
```

구성은 순수 HTML, CSS, JavaScript입니다. 기존 `/api/v1/*` API를 사용하며, 내부 기록과 고급 정보는 기본 화면에서 숨기고 `자세히 보기` 안에서만 확인할 수 있게 구성했습니다.
