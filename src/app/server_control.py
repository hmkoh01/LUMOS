import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from src.app.config import API_HOST, API_PORT


BASE_URL = f"http://{API_HOST}:{API_PORT}"


@dataclass
class ServerHandle:
    server: Optional[uvicorn.Server] = None
    thread: Optional[threading.Thread] = None
    started_by_companion: bool = False

    def stop(self):
        if self.server and self.started_by_companion:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive() and self.started_by_companion:
            self.thread.join(timeout=3)


def is_server_running(timeout: float = 0.6) -> bool:
    try:
        with urlopen(f"{BASE_URL}/health", timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def wait_for_server(timeout_seconds: float = 8.0, interval_seconds: float = 0.25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_server_running(timeout=0.8):
            return True
        time.sleep(interval_seconds)
    return False


def start_server_if_needed() -> ServerHandle:
    if is_server_running():
        return ServerHandle(started_by_companion=False)

    from src.app.main import app as local_app

    config = uvicorn.Config(
        local_app,
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="lumos-api-server", daemon=True)
    thread.start()
    if not wait_for_server():
        server.should_exit = True
        raise RuntimeError("LUMOS 서버를 시작하지 못했어요. 포트가 이미 사용 중인지 확인해주세요.")
    return ServerHandle(server=server, thread=thread, started_by_companion=True)
