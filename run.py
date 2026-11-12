import argparse
import asyncio
import importlib.metadata
import os
import socket
import sys
import threading
import time
import webbrowser

# Keep the generic commands on Python's default loop.  local-live configures
# its own Windows policy below: the observed WinError 10014 came from
# ProactorEventLoop's self-pipe creation, not the application's listening
# socket.  This avoids changing desktop/cloud command behaviour.
if sys.platform == "win32" and os.environ.get("LUMOS_USE_SELECTOR_LOOP", "").lower() == "true":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Load .env file before any src imports so env vars are available at import time.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)  # don't override vars already set in the shell
except ImportError:
    pass

def _agent_platform_runtime_status() -> dict:
    """Return non-secret runtime facts needed before local-live starts workers.

    ``uvicorn.run`` and Engine's WorkerPool both stay in this interpreter, so
    checking here prevents a server launched through a system ``python`` from
    accepting briefing jobs that will inevitably fail later in a worker.
    """
    version = ""
    try:
        version = importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        pass

    def version_tuple(value: str) -> tuple:
        try:
            return tuple(int(part) for part in value.split(".")[:3])
        except ValueError:
            return ()

    sdk_ok = bool(version_tuple(version) and (2, 30, 1) <= version_tuple(version) < (3, 0, 0))
    python_ok = sys.version_info >= (3, 10)
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "executable": sys.executable,
        "google_genai": version or "not-installed",
        "ready": python_ok and sdk_ok,
    }


def _require_agent_platform_runtime() -> bool:
    status = _agent_platform_runtime_status()
    print(
        "[LUMOS] Runtime: "
        f"python={status['python']} executable={status['executable']} "
        f"google-genai={status['google_genai']}"
    )
    if status["ready"]:
        return True
    print(
        "[LUMOS] Agent Platform runtime is incompatible. "
        "Use Python 3.10+ with google-genai>=2.30.1,<3.0.0; "
        "local-live was not started."
    )
    return False


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


def _configure_local_live_event_loop() -> str:
    """Use the stable selector loop for the Windows local-live process only.

    The application previously reached Uvicorn startup and then failed in
    ``ProactorEventLoop._make_self_pipe`` with WinError 10014.  The server's
    TCP listener itself was not the failing operation.  Selector policy keeps
    local-live away from that Proactor-specific startup path while leaving all
    other launcher modes unchanged.
    """
    if sys.platform != "win32":
        return "default"
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return "selector"


def run_api(reload: bool = False):
    import uvicorn
    from src.app.config import API_HOST, API_PORT

    _assert_port_free(API_HOST, API_PORT)
    uvicorn.run("src.app.main:app", host=API_HOST, port=API_PORT, reload=reload, loop="none")


def run_cloud():
    import uvicorn
    from src.cloud.config import CLOUD_HOST, CLOUD_PORT, CLOUD_DB_PATH

    print(f"LUMOS Cloud Backend: http://{CLOUD_HOST}:{CLOUD_PORT}")
    print(f"Cloud DB: {CLOUD_DB_PATH}")
    uvicorn.run("src.cloud.app:app", host=CLOUD_HOST, port=CLOUD_PORT, reload=False)


def run_web_app(reload: bool = False):
    from src.app.config import API_HOST, API_PORT

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


def run_local_live_app():
    """Run an isolated, explicit real-collection/Gemini development service.

    This command is the only local path that relaxes the normally fail-closed
    guards.  It never alters .env or the default/production databases.
    """
    from pathlib import Path
    base = Path(os.environ.get(
        "LUMOS_LOCAL_LIVE_DATA_DIR",
        str(Path(__file__).resolve().parent / "data"),
    )).resolve()
    base.mkdir(parents=True, exist_ok=True)
    # The default remains the deliberately small, previously approved pilot.
    # An operator may opt into another already-approved collector (for example
    # Crossref after configuring its contact address) without changing Railway
    # or widening the default local-live surface.
    pilot_sources = os.environ.get("LUMOS_LOCAL_LIVE_PILOT_SOURCES", "hackernews,github")
    overrides = {
        # local-live keeps its application data locally isolated, but uses the
        # configured Supabase authentication flow so Google sign-in and the
        # first-run onboarding are exercised exactly as in deployment.
        "LUMOS_AUTH_MODE": os.environ.get("LUMOS_LOCAL_LIVE_AUTH_MODE", "supabase"),
        "LUMOS_DB_PATH": str(base / "lumos_live_v2.db"),
        "LUMOS_ENGINE_CACHE_DB_PATH": str(base / "lumos_live_v2_cache.sqlite"),
        "LUMOS_ENGINE_QUEUE_DB_PATH": str(base / "lumos_live_v2_queue.sqlite"),
        "LUMOS_ENGINE_V2": "true",
        "LUMOS_EXTERNAL_CALLS": "true",
        "LUMOS_ENGINE_LLM_PROVIDER": "agent_platform",
        "LUMOS_ENGINE_LLM": "approved",
        "LUMOS_SCHEDULER_ENABLED": "true",
        "LUMOS_ENGINE_PILOT_SOURCES": pilot_sources,
        "LUMOS_BLOCK_EXTERNAL_CALLS": "false",
    }
    os.environ.update(overrides)
    if not _require_agent_platform_runtime():
        return
    loop_policy = _configure_local_live_event_loop()
    # Non-secret startup evidence for the active card-copy policy.  This
    # proves the running interpreter loaded the intended version without
    # generating a briefing or inspecting user data.
    from src.signals.llm_briefing import (
        BRIEFING_VALIDATOR_VERSION,
        CONTENT_PROMPT_VERSION,
        PERSONALIZATION_PROMPT_VERSION,
    )
    print(
        "[LUMOS] Briefing copy policy: "
        f"content={CONTENT_PROMPT_VERSION} "
        f"personalization={PERSONALIZATION_PROMPT_VERSION} "
        f"validator={BRIEFING_VALIDATOR_VERSION}"
    )
    print(f"[LUMOS] Local-live event loop policy: {loop_policy}")
    import uvicorn

    port = int(os.environ.get("LUMOS_LOCAL_LIVE_PORT", "8001"))
    url = f"http://127.0.0.1:{port}/app"
    print("[LUMOS] Explicit local real-service mode")
    print(f"[LUMOS] Isolated DB/cache/queue; approved pilot sources: {pilot_sources}")
    print(f"[LUMOS] {url}")
    # A real-new-user environment must not consume an existing browser's
    # Supabase session merely because the server starts.  Open explicitly when
    # desired; the normal test flow is to paste the printed URL in a private tab.
    if os.environ.get("LUMOS_LOCAL_LIVE_OPEN_BROWSER", "false").lower() == "true":
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(url)), daemon=True).start()
    uvicorn.run("src.app.main:app", host="127.0.0.1", port=port, loop="none")


def main():
    parser = argparse.ArgumentParser(description="LUMOS")
    parser.add_argument(
        "command", nargs="?", default="api",
        choices=["api", "cloud", "app", "demo-reset", "demo-seed", "demo",
                 "desktop", "briefing", "settings", "scheduler-once", "local-live"],
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
    elif args.command == "local-live":
        run_local_live_app()
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
        from src.app.runtime import create_runtime
        from src.app.scheduler import DailyBriefingScheduler

        runtime = create_runtime()
        result = DailyBriefingScheduler(runtime.store).run_once(force=args.force, show_notification=False)
        print({"ran": result.get("ran"), "reason": result.get("reason"),
               "pipeline_run_id": result.get("pipeline_run_id"),
               "signal_count": len(result.get("signals", []))})


if __name__ == "__main__":
    main()
