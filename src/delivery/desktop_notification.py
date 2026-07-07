from typing import List, Optional


def notify_signals_ready(count: int, title: str = "LUMOS", message: str = None):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        text = message or f"오늘 볼 신호 {count}개를 골랐어요."
        messagebox.showinfo(title, text)
        root.destroy()
        return {"sent": True, "count": count, "method": "tkinter_messagebox"}
    except Exception as exc:
        return {"sent": False, "count": count, "reason": str(exc)}


def show_briefing_window(signals: Optional[List[dict]] = None, service=None):
    from src.desktop.briefing_window import BriefingWindow

    window = BriefingWindow(service=service, initial_signals=signals)
    window.run()
    return window


class DesktopNotification:
    def send(self, title: str, message: str):
        return notify_signals_ready(1, title=title, message=message)
