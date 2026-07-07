import tkinter as tk
from tkinter import ttk
import webbrowser
from typing import List, Optional

from src.app.runtime import create_runtime
from src.delivery.briefing_service import BriefingService


class BriefingWindow:
    def __init__(self, service: Optional[BriefingService] = None, initial_signals: Optional[List[dict]] = None):
        self.service = service or BriefingService(create_runtime().store)
        self.root = tk.Tk()
        self.root.title("LUMOS - Today's Signals")
        self.root.geometry("820x680")
        self.signals = initial_signals or self.service.get_today_signals()
        self.status_text = tk.StringVar(value="")
        self.interests_text = tk.StringVar(value="")
        self.warning_text = tk.StringVar(value="")
        self.action_text = tk.StringVar(value="")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.service.record_lifecycle_event("briefing_opened", {"surface": "desktop"})
        if self.signals:
            self.service.record_lifecycle_event("briefing_shown", {"signal_count": len(self.signals), "surface": "desktop"})
        self._build()

    def run(self):
        self.root.mainloop()

    def _build(self):
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Generate Now", command=self.generate_now).pack(side="left")
        ttk.Button(toolbar, text="Refresh Signals", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Settings", command=self.open_settings).pack(side="right")
        ttk.Label(self.root, textvariable=self.status_text, padding=(10, 4)).pack(fill="x")
        ttk.Label(self.root, textvariable=self.interests_text, padding=(10, 4), wraplength=780).pack(fill="x")
        ttk.Label(self.root, textvariable=self.warning_text, foreground="#9a5b00", padding=(10, 4), wraplength=780).pack(fill="x")
        ttk.Label(self.root, textvariable=self.action_text, foreground="#1f6f43", padding=(10, 4)).pack(fill="x")

        self.canvas = tk.Canvas(self.root, borderwidth=0)
        self.content = ttk.Frame(self.canvas, padding=10)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.render_signals()

    def render_signals(self):
        self._render_status()
        for child in self.content.winfo_children():
            child.destroy()
        if not self.signals:
            ttk.Label(self.content, text="No Signals yet. Use Generate Now to create today's briefing.").pack(anchor="w")
            return
        for signal in self.signals:
            self._render_card(signal)

    def _render_card(self, signal: dict):
        frame = ttk.LabelFrame(self.content, text=f"Rank {signal.get('rank', '-')}: {signal.get('category') or 'Signal'}", padding=10)
        frame.pack(fill="x", pady=8)
        ttk.Label(frame, text=signal.get("title", ""), font=("Segoe UI", 11, "bold"), wraplength=720).pack(anchor="w")
        ttk.Label(frame, text=signal.get("summary", ""), wraplength=720).pack(anchor="w", pady=(6, 0))
        ttk.Label(frame, text=f"Why: {signal.get('why_it_matters', '')}", wraplength=720).pack(anchor="w", pady=(6, 0))
        meta = (
            f"Source: {signal.get('source_name') or 'source'} | "
            f"Confidence: {float(signal.get('confidence') or 0):.2f} | "
            f"Status: {signal.get('status', 'active')}"
        )
        ttk.Label(frame, text=meta).pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(frame)
        actions.pack(anchor="w", pady=(8, 0))
        ttk.Button(actions, text="Save", command=lambda: self.feedback(signal, "saved")).pack(side="left")
        ttk.Button(actions, text="Not interested", command=lambda: self.feedback(signal, "ignored")).pack(side="left", padx=4)
        ttk.Button(actions, text="Track", command=lambda: self.feedback(signal, "tracked")).pack(side="left", padx=4)
        ttk.Button(actions, text="Open", command=lambda: self.open_signal(signal)).pack(side="left", padx=4)

    def generate_now(self):
        self.load_result(self.service.generate_now())

    def refresh(self):
        self.service.record_lifecycle_event("briefing_refreshed", {"surface": "desktop"})
        self.signals = self.service.get_today_signals()
        self.action_text.set("Refreshed.")
        self.render_signals()

    def feedback(self, signal: dict, event_type: str):
        self.service.record_feedback(signal["id"], event_type, {"surface": "desktop_briefing"})
        messages = {
            "saved": "Saved.",
            "ignored": "Marked as not interested.",
            "tracked": "Tracking.",
        }
        self.action_text.set(messages.get(event_type, "Feedback recorded."))
        self.signals = self.service.get_today_signals()
        self.render_signals()

    def open_signal(self, signal: dict):
        self.service.record_feedback(signal["id"], "opened", {"surface": "desktop_briefing"})
        self.action_text.set("Open event recorded.")
        if signal.get("source_url"):
            webbrowser.open(signal["source_url"])
        self.render_signals()

    def open_settings(self):
        from src.desktop.settings_window import SettingsWindow

        SettingsWindow(service=self.service).run()
        self.render_signals()

    def load_result(self, result: dict):
        self.signals = result.get("signals", self.service.get_today_signals())
        self.action_text.set("Signals generated." if result.get("generated") else "Signals ready.")
        self.render_signals()

    def close(self):
        self.service.record_lifecycle_event(
            "briefing_dismissed",
            {"surface": "desktop", "signal_count": len(self.signals)},
        )
        self.root.destroy()

    def _render_status(self):
        context = self.service.get_latest_briefing_context()
        self.status_text.set(
            " | ".join(
                [
                    f"Signals: {context['signal_count']}",
                    f"Last generated: {context.get('last_generated_at') or 'not yet'}",
                    f"Pipeline run: {context.get('pipeline_run_id') or '-'}",
                    f"Mode: {context.get('generate_mode') or 'mock'}",
                ]
            )
        )
        warnings = context.get("warnings") or {}
        if warnings:
            parts = [f"{source}: {'; '.join(messages)}" for source, messages in warnings.items()]
            self.warning_text.set("Source status: " + " | ".join(parts))
        else:
            self.warning_text.set("Source status: ok")
        interests = self.service.get_interests(limit=5)
        self.interests_text.set(
            "Briefing interests: " + (", ".join(item["keyword"] for item in interests[:5]) or "none yet")
        )
