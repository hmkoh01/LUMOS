import argparse
import asyncio
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

# Python 3.9 on Windows: socket.socketpair() is a pure-Python fallback that
# exhausts handles after heavy test runs.  The SelectorEventLoop uses a different
# mechanism and avoids the issue entirely.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load .env file before any src imports so env vars are available at import time.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # don't override vars already set in the shell
except ImportError:
    pass

from src.app.config import API_HOST, API_PORT
from src.app.runtime import create_runtime
from src.app.scheduler import DailyBriefingScheduler


def _assert_port_free(host: str, port: int) -> None:
    """Exit with a friendly message if the port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            print(f"\n[LUMOS] Port {port} is already in use.")
            print(f"        Stop the existing LUMOS server before starting a new one.")
            print(f"\n  Find the process (Windows):")
            print(f"    netstat -ano | findstr :{port}")
            print(f"    taskkill /PID <PID> /F")
            print(f"\n  Verify the running server:")
            print(f"    http://{host}:{port}/health")
            sys.exit(1)


def run_api(reload: bool = False):
    _assert_port_free(API_HOST, API_PORT)
    uvicorn.run("src.app.main:app", host=API_HOST, port=API_PORT, reload=reload, loop="none")


def run_cloud():
    from src.cloud.config import CLOUD_HOST, CLOUD_PORT, CLOUD_DB_PATH

    print(f"LUMOS Cloud Backend: http://{CLOUD_HOST}:{CLOUD_PORT}")
    print(f"Cloud DB: {CLOUD_DB_PATH}")
    uvicorn.run("src.cloud.app:app", host=CLOUD_HOST, port=CLOUD_PORT, reload=False)


def run_web_app(reload: bool = False):
    url = f"http://{API_HOST}:{API_PORT}/app"

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"LUMOS Web UI: {url}")
    run_api(reload=reload)


def run_demo_reset():
    from src.app.demo_seed import reset_demo_db

    print(f"Demo database reset: {reset_demo_db()}")


def run_demo_seed():
    from src.app.demo_seed import seed_demo_db

    result = seed_demo_db(generate_signals=True)
    print(f"Demo database ready: {result['db_path']}")


def run_demo_web_app():
    from src.app.demo_seed import demo_db_exists, demo_db_path, set_demo_db_environment

    if not demo_db_exists():
        print(f"Demo database is missing: {demo_db_path()}")
        print("Run: python run.py demo-reset && python run.py demo-seed")
        return
    set_demo_db_environment()
    url = f"http://{API_HOST}:{API_PORT}/app#today"

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"LUMOS demo Web UI: {url}")
    run_api()


def main():
    parser = argparse.ArgumentParser(description="LUMOS")
    parser.add_argument(
        "command", nargs="?", default="api",
        choices=["api", "cloud", "app", "demo-reset", "demo-seed", "demo",
                 "desktop", "briefing", "settings", "scheduler-once"],
    )
    parser.add_argument("--no-scheduler", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload on file changes (dev only)")
    args = parser.parse_args()

    if args.command == "api":
        run_api(reload=args.reload)
    elif args.command == "cloud":
        run_cloud()
    elif args.command == "app":
        run_web_app(reload=args.reload)
    elif args.command == "demo-reset":
        run_demo_reset()
    elif args.command == "demo-seed":
        run_demo_seed()
    elif args.command == "demo":
        run_demo_web_app()
    elif args.command == "desktop":
        from src.desktop.app import main as desktop_main
        desktop_main(["--no-scheduler"] if args.no_scheduler else [])
    elif args.command == "briefing":
        from src.desktop.briefing_window import BriefingWindow
        from src.delivery.briefing_service import BriefingService

        runtime = create_runtime()
        service = BriefingService(runtime.store)
        if args.generate:
            service.generate_now()
        BriefingWindow(service=service).run()
    elif args.command == "settings":
        from src.desktop.settings_window import SettingsWindow
        from src.delivery.briefing_service import BriefingService

        runtime = create_runtime()
        SettingsWindow(service=BriefingService(runtime.store)).run()
    elif args.command == "scheduler-once":
        runtime = create_runtime()
        result = DailyBriefingScheduler(runtime.store).run_once(force=args.force, show_notification=False)
        print({"ran": result.get("ran"), "reason": result.get("reason"),
               "pipeline_run_id": result.get("pipeline_run_id"),
               "signal_count": len(result.get("signals", []))})


if __name__ == "__main__":
    main()
