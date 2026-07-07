import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.app.runtime import create_runtime
from src.delivery.briefing_service import BriefingService


class SettingsWindow:
    def __init__(self, service: Optional[BriefingService] = None):
        self.service = service or BriefingService(create_runtime().store)
        self.root = tk.Toplevel() if tk._default_root else tk.Tk()
        self.root.title("LUMOS Settings")
        self.root.geometry("760x620")
        self.source_vars = {}
        self.feed_entries = {}
        self.connector_vars = {}
        self.connector_config_vars = {}
        self.status_text = tk.StringVar(value="")
        self.sync_status_text = tk.StringVar(value="")
        self.interests_text = tk.StringVar(value="")
        self.evidence_text = tk.StringVar(value="")
        self.interests_frame = None
        self._build()

    def run(self):
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()

    def _build(self):
        settings = self.service.get_settings()
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        basic = ttk.LabelFrame(main, text="Briefing", padding=10)
        basic.pack(fill="x")
        ttk.Label(basic, text="Signal count").grid(row=0, column=0, sticky="w")
        self.signal_count = tk.IntVar(value=int(settings.get("signal_count", 3)))
        ttk.Spinbox(basic, from_=1, to=20, textvariable=self.signal_count, width=8).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(basic, text="Briefing time").grid(row=1, column=0, sticky="w", pady=6)
        self.briefing_time = tk.StringVar(value=settings.get("briefing_time", "08:00"))
        ttk.Entry(basic, textvariable=self.briefing_time, width=12).grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(basic, text="Generate mode").grid(row=2, column=0, sticky="w")
        self.generate_mode = tk.StringVar(value=settings.get("generate_mode", "mock"))
        ttk.Combobox(basic, textvariable=self.generate_mode, values=("mock", "hybrid", "live"), width=10, state="readonly").grid(row=2, column=1, sticky="w", padx=8)

        self.desktop_push_enabled = tk.BooleanVar(value=bool(settings.get("desktop_push_enabled", True)))
        ttk.Checkbutton(basic, text="Desktop popup enabled", variable=self.desktop_push_enabled).grid(row=3, column=0, columnspan=2, sticky="w")
        self.sync_before_briefing = tk.BooleanVar(value=bool(settings.get("sync_before_briefing", True)))
        ttk.Checkbutton(basic, text="Sync context before briefing", variable=self.sync_before_briefing).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(basic, text="Sync interval minutes").grid(row=5, column=0, sticky="w")
        self.context_sync_interval = tk.IntVar(value=int(settings.get("context_sync_interval_minutes", 360)))
        ttk.Spinbox(basic, from_=5, to=1440, textvariable=self.context_sync_interval, width=8).grid(row=5, column=1, sticky="w", padx=8)

        sources = ttk.LabelFrame(main, text="Sources", padding=10)
        sources.pack(fill="both", expand=True, pady=10)
        ttk.Label(sources, text="GitHub token is optional. Set GITHUB_TOKEN in the environment for higher rate limits.").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(sources, text="Source").grid(row=1, column=0, sticky="w")
        ttk.Label(sources, text="RSS feed URLs, comma separated").grid(row=1, column=1, sticky="w")
        ttk.Label(sources, text="Status").grid(row=1, column=2, sticky="w")

        for row, config in enumerate(self.service.list_source_configs(), start=2):
            source_id = config["source_id"]
            enabled_var = tk.BooleanVar(value=config["enabled"])
            self.source_vars[source_id] = enabled_var
            ttk.Checkbutton(sources, text=source_id, variable=enabled_var).grid(row=row, column=0, sticky="w")
            config_json = config.get("config_json", {})
            feed_value = ", ".join(config_json.get("feed_urls", []))
            feed_var = tk.StringVar(value=feed_value)
            self.feed_entries[source_id] = feed_var
            ttk.Entry(sources, textvariable=feed_var, width=46).grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Label(sources, text=self._source_status(config)).grid(row=row, column=2, sticky="w")
        sources.columnconfigure(1, weight=1)

        context = ttk.LabelFrame(main, text="Personal Context", padding=10)
        context.pack(fill="x", pady=10)
        connectors = {item["connector_type"]: item for item in self.service.get_connectors()}
        for row, connector_type in enumerate(["browser_history", "local_files"]):
            connector = connectors.get(connector_type, {"enabled": False, "config_json": {}})
            enabled_var = tk.BooleanVar(value=connector["enabled"])
            self.connector_vars[connector_type] = enabled_var
            ttk.Checkbutton(context, text=connector_type, variable=enabled_var).grid(row=row, column=0, sticky="w")
            config = connector.get("config_json", {})
            value = ", ".join(config.get("folders", [])) if connector_type == "local_files" else ""
            config_var = tk.StringVar(value=value)
            self.connector_config_vars[connector_type] = config_var
            label = "folders" if connector_type == "local_files" else "sample/history path optional"
            ttk.Entry(context, textvariable=config_var, width=52).grid(row=row, column=1, padx=8, sticky="ew")
            ttk.Label(context, text=label).grid(row=row, column=2, sticky="w")
        row = 2
        for connector_type in ["notion", "google_drive", "chatgpt_export", "claude_export"]:
            ttk.Label(context, text=f"{connector_type}: coming later").grid(row=row, column=0, columnspan=3, sticky="w")
            row += 1
        ttk.Button(context, text="Sync Now", command=self.sync_now).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Label(context, textvariable=self.sync_status_text).grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Label(context, textvariable=self.interests_text, wraplength=680).grid(row=row + 1, column=0, columnspan=3, sticky="w")
        context.columnconfigure(1, weight=1)

        interests_box = ttk.LabelFrame(main, text="My Interests", padding=10)
        interests_box.pack(fill="both", expand=True, pady=10)
        self.interests_frame = ttk.Frame(interests_box)
        self.interests_frame.pack(fill="both", expand=True)
        ttk.Button(interests_box, text="Refresh interests", command=self.refresh_interests).pack(anchor="w")
        ttk.Label(interests_box, textvariable=self.evidence_text, wraplength=700).pack(anchor="w", pady=6)

        ttk.Label(main, textvariable=self.status_text, foreground="#1f6f43").pack(anchor="w")
        footer = ttk.Frame(main)
        footer.pack(fill="x")
        ttk.Button(footer, text="Save", command=self.save).pack(side="right")

    def save(self):
        self.service.update_settings(
            {
                "signal_count": self.signal_count.get(),
                "briefing_time": self.briefing_time.get(),
                "desktop_push_enabled": self.desktop_push_enabled.get(),
                "generate_mode": self.generate_mode.get(),
                "sync_before_briefing": self.sync_before_briefing.get(),
                "context_sync_interval_minutes": self.context_sync_interval.get(),
            }
        )
        configs = {item["source_id"]: item for item in self.service.list_source_configs()}
        for source_id, enabled_var in self.source_vars.items():
            current = configs[source_id]
            config_json = dict(current.get("config_json", {}))
            feed_urls = [item.strip() for item in self.feed_entries[source_id].get().split(",") if item.strip()]
            if "feed_urls" in config_json or feed_urls:
                config_json["feed_urls"] = feed_urls
            self.service.update_source_config(source_id, enabled=enabled_var.get(), config_json=config_json)
        for connector_type, enabled_var in self.connector_vars.items():
            config_json = {}
            if connector_type == "local_files":
                folders = [item.strip() for item in self.connector_config_vars[connector_type].get().split(",") if item.strip()]
                config_json = {"folders": folders}
            self.service.update_connector(connector_type, enabled_var.get(), config_json)
        self.status_text.set("Saved. The scheduler will use these settings on the next tick.")
        self.refresh_interests()

    def _source_status(self, config: dict) -> str:
        config_json = config.get("config_json", {})
        if not config.get("enabled"):
            return "disabled"
        if config.get("source_id") in {"rss", "official_ai_blogs", "company_newsroom"} and not config_json.get("feed_urls"):
            return "missing feed URL"
        if config.get("source_id") == "github":
            return "ready, token optional"
        return "ready"

    def sync_now(self):
        self.save()
        result = self.service.sync_context(connector_types=["browser_history", "local_files"], limit=100)
        self.sync_status_text.set(
            f"Synced {result['item_count']} items, updated {result['keyword_count']} keyword groups."
        )
        self.refresh_interests()

    def refresh_interests(self):
        interests = self.service.get_interests(limit=20, include_muted=True)
        text = ", ".join(f"{item['keyword']} ({item['weight']:.1f})" for item in interests[:10])
        self.interests_text.set(f"Top interests: {text or 'none yet'}")
        if not self.interests_frame:
            return
        for child in self.interests_frame.winfo_children():
            child.destroy()
        headers = ["Keyword", "Weight", "Category", "Source", "Status", "Actions"]
        for col, header in enumerate(headers):
            ttk.Label(self.interests_frame, text=header).grid(row=0, column=col, sticky="w")
        for row, item in enumerate(interests, start=1):
            keyword = item["keyword"]
            ttk.Label(self.interests_frame, text=keyword[:22]).grid(row=row, column=0, sticky="w")
            ttk.Label(self.interests_frame, text=f"{item['weight']:.1f}").grid(row=row, column=1, sticky="w")
            ttk.Label(self.interests_frame, text=str(item.get("category") or "")[:16]).grid(row=row, column=2, sticky="w")
            ttk.Label(self.interests_frame, text=str(item.get("source") or "")[:16]).grid(row=row, column=3, sticky="w")
            ttk.Label(self.interests_frame, text=item.get("status", "active")).grid(row=row, column=4, sticky="w")
            actions = ttk.Frame(self.interests_frame)
            actions.grid(row=row, column=5, sticky="w")
            ttk.Button(actions, text="-", width=3, command=lambda kw=keyword, w=item["weight"]: self.change_weight(kw, w - 0.5)).pack(side="left")
            ttk.Button(actions, text="+", width=3, command=lambda kw=keyword, w=item["weight"]: self.change_weight(kw, w + 0.5)).pack(side="left")
            ttk.Button(actions, text="mute", command=lambda kw=keyword: self.mute_interest(kw)).pack(side="left")
            ttk.Button(actions, text="unmute", command=lambda kw=keyword: self.unmute_interest(kw)).pack(side="left")
            ttk.Button(actions, text="delete", command=lambda kw=keyword: self.delete_interest(kw)).pack(side="left")
            ttk.Button(actions, text="evidence", command=lambda kw=keyword: self.show_evidence(kw)).pack(side="left")

    def change_weight(self, keyword: str, weight: float):
        self.service.update_interest(keyword, weight=max(0.0, weight))
        self.refresh_interests()

    def mute_interest(self, keyword: str):
        self.service.mute_interest(keyword)
        self.refresh_interests()

    def unmute_interest(self, keyword: str):
        self.service.unmute_interest(keyword)
        self.refresh_interests()

    def delete_interest(self, keyword: str):
        self.service.delete_interest(keyword)
        self.refresh_interests()

    def show_evidence(self, keyword: str):
        evidence = self.service.get_interest_evidence(keyword)
        self.evidence_text.set(f"Evidence for {keyword}: {evidence[:3]}")
