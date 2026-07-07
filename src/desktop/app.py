import argparse

from src.app.runtime import create_runtime
from src.app.scheduler import DailyBriefingScheduler
from src.delivery.briefing_service import BriefingService
from src.desktop.briefing_window import BriefingWindow
from src.desktop.settings_window import SettingsWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="LUMOS desktop app")
    parser.add_argument("--show-briefing", action="store_true")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--no-scheduler", action="store_true")
    args = parser.parse_args(argv)

    runtime = create_runtime()
    service = BriefingService(runtime.store)

    if args.run_once:
        result = DailyBriefingScheduler(runtime.store).run_once(force=True, show_notification=False)
        print(
            {
                "ran": result.get("ran"),
                "reason": result.get("reason"),
                "pipeline_run_id": result.get("pipeline_run_id"),
                "signal_count": len(result.get("signals", [])),
            }
        )
        return result
    if args.settings:
        SettingsWindow(service=service).run()
        return None

    if service.is_first_run() and not args.show_briefing:
        SettingsWindow(service=service).run()

    window = BriefingWindow(service=service)
    scheduler = None
    if not args.no_scheduler:
        scheduler = DailyBriefingScheduler(
            runtime.store,
            mode=service.get_settings().get("generate_mode", "mock"),
            on_ready=lambda result: window.root.after(0, lambda: window.load_result(result)),
        )
        scheduler.start()
    try:
        window.run()
    finally:
        if scheduler:
            scheduler.stop()


if __name__ == "__main__":
    main()
