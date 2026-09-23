import json
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import ttk

from src.app.resource_paths import package_docs_dir, packaged_root
from src.app.server_control import BASE_URL, ServerHandle


WEB_TAB_HASHES = {
    "today": "today",
    "signals": "today",
    "interests": "interests",
    "sources": "sources",
    "activity": "activity",
    "settings": "settings",
}


def web_tab_url(base_url: str = BASE_URL, tab_name: str = "today") -> str:
    tab_hash = WEB_TAB_HASHES.get(tab_name, "today")
    return f"{base_url.rstrip('/')}/app#{tab_hash}"


class CompanionWindow:
    def __init__(self, server_handle: Optional[ServerHandle] = None, base_url: str = BASE_URL):
        self.server_handle = server_handle or ServerHandle()
        self.base_url = base_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title("LUMOS Companion")
        self.root.geometry("460x590")
        self.root.minsize(420, 540)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.run_status = tk.StringVar(value="LUMOS 실행 상태: 확인 중")
        self.signal_status = tk.StringVar(value="오늘의 소식: 확인 중")
        self.account_status = tk.StringVar(value="계정: 로컬 모드")
        self.last_updated = tk.StringVar(value="마지막 확인: 아직 없음")
        self.message = tk.StringVar(value="LUMOS를 실행하고 브라우저 화면으로 연결할 준비가 되었어요.")

        self.generate_button = None
        self.sync_button = None
        self._build()
        self.refresh_status()
        self.root.after(450, self._bring_to_front)

    def _build(self):
        self.root.configure(bg="#F6F7FB")
        frame = ttk.Frame(self.root, padding=22)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="LUMOS Companion", font=("Segoe UI", 21, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            frame,
            text="LUMOS를 실행하고 오늘의 소식 화면으로 연결해주는 작은 도우미예요.",
            wraplength=400,
        )
        subtitle.pack(anchor="w", pady=(4, 6))
        helper = ttk.Label(
            frame,
            text="오늘의 소식는 브라우저 화면에서 확인하고, 이 창에서는 빠른 실행만 도와드려요.",
            wraplength=400,
        )
        helper.pack(anchor="w", pady=(0, 20))

        status_frame = ttk.LabelFrame(frame, text="상태", padding=14)
        status_frame.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(status_frame, textvariable=self.run_status).pack(anchor="w", pady=2)
        ttk.Label(status_frame, textvariable=self.signal_status).pack(anchor="w", pady=2)
        ttk.Label(status_frame, textvariable=self.account_status).pack(anchor="w", pady=2)
        ttk.Label(status_frame, text="Cloud 연결은 설정 화면에서 확인할 수 있어요.").pack(anchor="w", pady=2)
        ttk.Label(status_frame, textvariable=self.last_updated).pack(anchor="w", pady=2)

        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, pady=(0, 14))
        ttk.Button(action_frame, text="오늘의 소식 열기", command=lambda: self.open_web_tab("today")).pack(fill=tk.X, pady=5)
        self.generate_button = ttk.Button(action_frame, text="새 소식 준비하기", command=self.generate_signals)
        self.generate_button.pack(fill=tk.X, pady=5)
        self.sync_button = ttk.Button(action_frame, text="개인 맥락 동기화", command=self.sync_context)
        self.sync_button.pack(fill=tk.X, pady=5)
        ttk.Button(action_frame, text="설정 화면 열기", command=lambda: self.open_web_tab("settings")).pack(fill=tk.X, pady=5)

        secondary_frame = ttk.Frame(frame)
        secondary_frame.pack(fill=tk.X, pady=(0, 14))
        ttk.Button(secondary_frame, text="활동 기록 보기", command=lambda: self.open_web_tab("activity")).pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
            padx=(0, 5),
        )
        ttk.Button(secondary_frame, text="도움말", command=self.open_readme).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        message_frame = ttk.LabelFrame(frame, text="안내", padding=14)
        message_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))
        ttk.Label(message_frame, textvariable=self.message, wraplength=380, justify=tk.LEFT).pack(anchor="nw")

        ttk.Button(frame, text="Companion 닫기", command=self.close).pack(fill=tk.X)

    def run(self):
        self.root.mainloop()

    def refresh_status(self):
        self._run_background(self._refresh_status_worker)

    def _refresh_status_worker(self):
        try:
            self._get("/health")
            signals = self._get("/api/v1/signals/today").get("signals", [])
            active = [signal for signal in signals if signal.get("status") != "archived"]
            self._ui(lambda: self.run_status.set("LUMOS 실행 상태: 실행 중"))
            if active:
                self._ui(lambda: self.signal_status.set(f"오늘의 소식: {len(active)}개 준비됨"))
                self._ui(lambda: self.message.set("오늘의 소식이 준비돼 있어요. 브라우저에서 확인해보세요."))
            else:
                self._ui(lambda: self.signal_status.set("오늘의 소식: 아직 없음"))
                self._ui(lambda: self.message.set("아직 오늘의 소식이 없어요. 새 소식을 준비할 수 있어요."))
            self._update_time()
        except Exception:
            self._ui(lambda: self.run_status.set("LUMOS 실행 상태: 연결 불안정"))
            self._ui(lambda: self.signal_status.set("오늘의 소식: 확인 중"))
            self._ui(lambda: self.message.set("잠시 연결이 불안정해요. 다시 시도해보세요."))

    def open_web_tab(self, tab_name: str = "today", message: Optional[str] = None):
        url = web_tab_url(self.base_url, tab_name)
        webbrowser.open(url)
        if message:
            self.message.set(message)
        elif WEB_TAB_HASHES.get(tab_name, "today") == "settings":
            self.message.set("설정 화면을 열었어요.")
        elif WEB_TAB_HASHES.get(tab_name, "today") == "activity":
            self.message.set("활동 기록을 열었어요.")
        else:
            self.message.set("오늘의 소식 화면을 열었어요.")

    def open_web(self, tab: str = "today"):
        self.open_web_tab(tab)

    def open_readme(self):
        candidates = [
            packaged_root() / "README_FIRST.md",
            package_docs_dir() / "README_FIRST.md",
            Path(__file__).resolve().parents[2] / "README.md",
        ]
        for candidate in candidates:
            if candidate.exists():
                webbrowser.open(candidate.as_uri())
                self.message.set("도움말 문서를 열었어요.")
                return
        self.message.set("도움말 문서를 찾지 못했어요. 실행 폴더의 README_FIRST.md를 확인해 주세요.")

    def generate_signals(self):
        self._set_button_state(self.generate_button, False, "새 소식을 준비하는 중")
        self.message.set("새 소식을 준비하고 있어요.")
        self._run_background(self._generate_worker)

    def _generate_worker(self):
        try:
            settings = self._get("/api/v1/settings").get("settings", {})
            mode = settings.get("generate_mode", "hybrid")
            result = self._post("/api/v1/signals/generate", {"mode": mode, "replace_today": True})
            count = result.get("generated_signal_count", 0)
            self._ui(lambda: self.signal_status.set(f"오늘의 소식: {count}개 준비됨"))
            self._ui(lambda: self.open_web_tab("today", "오늘의 소식이 준비됐어요. 브라우저에서 확인할 수 있어요."))
            self._notify_ready(count)
        except Exception:
            self._ui(lambda: self.message.set("잠시 연결이 불안정해요. 다시 시도해보세요."))
        finally:
            self._ui(lambda: self._set_button_state(self.generate_button, True, "새 소식 준비하기"))
            self._update_time()

    def sync_context(self):
        self._set_button_state(self.sync_button, False, "동기화하는 중")
        self.message.set("개인 맥락을 살펴보고 있어요.")
        self._run_background(self._sync_worker)

    def _sync_worker(self):
        try:
            self._post("/api/v1/context/sync", {"limit": 100})
            self._ui(lambda: self.message.set("개인 맥락을 동기화했어요. 활동 기록에서 확인할 수 있어요."))
        except Exception:
            self._ui(lambda: self.message.set("잠시 연결이 불안정해요. 다시 시도해보세요."))
        finally:
            self._ui(lambda: self._set_button_state(self.sync_button, True, "개인 맥락 동기화"))
            self._update_time()

    def _get(self, path: str) -> Dict[str, Any]:
        with urlopen(f"{self.base_url}{path}", timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def _notify_ready(self, count: int):
        try:
            from src.delivery.desktop_notification import DesktopNotification

            DesktopNotification().send("LUMOS", f"오늘 볼 소식 {count}개를 골랐어요.")
        except Exception:
            pass

    def _set_button_state(self, button, enabled: bool, text: str):
        if not button:
            return
        button.configure(text=text, state=tk.NORMAL if enabled else tk.DISABLED)

    def _update_time(self):
        text = datetime.now().strftime("마지막 확인: %H:%M")
        self._ui(lambda: self.last_updated.set(text))

    def _bring_to_front(self):
        try:
            self.root.lift()
            self.root.focus_force()
            self.root.attributes("-topmost", True)
            self.root.after(1500, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _run_background(self, target):
        threading.Thread(target=target, daemon=True).start()

    def _ui(self, callback):
        self.root.after(0, callback)

    def close(self):
        try:
            self.server_handle.stop()
        finally:
            self.root.destroy()


def main(server_handle: Optional[ServerHandle] = None):
    window = CompanionWindow(server_handle=server_handle)
    window.run()
    return window
