import argparse
import threading
import time
import webbrowser

import uvicorn

from src.app.config import API_HOST, API_PORT
from src.app.runtime import create_runtime
from src.app.scheduler import DailyBriefingScheduler


def run_api():
    uvicorn.run("src.app.main:app", host=API_HOST, port=API_PORT, reload=False)


def run_cloud():
    from src.cloud.config import CLOUD_HOST, CLOUD_PORT, CLOUD_DB_PATH

    print(f"LUMOS Cloud Backend: http://{CLOUD_HOST}:{CLOUD_PORT}")
    print(f"Cloud DB: {CLOUD_DB_PATH}")
    print("개발용 최소 cloud auth skeleton입니다. 실제 로그인/결제 서버가 아닙니다.")
    uvicorn.run("src.cloud.app:app", host=CLOUD_HOST, port=CLOUD_PORT, reload=False)


def run_web_app():
    url = f"http://{API_HOST}:{API_PORT}/app"

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"LUMOS Web UI: {url}")
    run_api()


def run_companion():
    from src.app.server_control import BASE_URL, start_server_if_needed
    from src.desktop.companion_window import CompanionWindow, web_tab_url

    handle = start_server_if_needed()
    webbrowser.open(web_tab_url(BASE_URL, "today"))
    CompanionWindow(server_handle=handle).run()


def _warn_if_server_running_for_demo() -> bool:
    from src.app.server_control import is_server_running

    if is_server_running():
        print("이미 127.0.0.1:8000에서 LUMOS가 실행 중이에요.")
        print("데모 DB를 보장하려면 기존 LUMOS 서버를 종료한 뒤 다시 실행해주세요.")
        print("기존 사용자 DB를 실수로 데모처럼 보여주지 않기 위해 실행을 중단했어요.")
        return True
    return False


def run_demo_reset():
    from src.app.demo_seed import reset_demo_db

    path = reset_demo_db()
    print(f"데모 DB를 초기화했어요: {path}")
    print("기존 사용자 DB는 건드리지 않았어요.")


def run_demo_seed():
    from src.app.demo_seed import seed_demo_db

    result = seed_demo_db(generate_signals=True)
    print(f"데모 DB를 준비했어요: {result['db_path']}")
    print("역할: 예비 창업자 / PM")
    print(f"관심사: {len(result['interests'])}개")
    print(f"오늘의 신호: {len(result['signals'])}개")
    print("생성 방식: 안정 모드")


def run_demo_web_app():
    from src.app.demo_seed import demo_db_exists, demo_db_path, set_demo_db_environment
    from src.desktop.companion_window import web_tab_url

    if not demo_db_exists():
        print(f"데모 DB가 아직 없어요: {demo_db_path()}")
        print("먼저 다음 명령을 실행해주세요.")
        print("python run.py demo-reset")
        print("python run.py demo-seed")
        return
    if _warn_if_server_running_for_demo():
        return

    set_demo_db_environment()
    url = web_tab_url(f"http://{API_HOST}:{API_PORT}", "today")

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"데모 DB로 LUMOS Web UI를 실행해요: {demo_db_path()}")
    print(f"LUMOS Web UI: {url}")
    run_api()


def run_demo_companion():
    from src.app.demo_seed import demo_db_exists, demo_db_path, set_demo_db_environment
    from src.app.server_control import BASE_URL, start_server_if_needed
    from src.desktop.companion_window import CompanionWindow, web_tab_url

    if not demo_db_exists():
        print(f"데모 DB가 아직 없어요: {demo_db_path()}")
        print("먼저 다음 명령을 실행해주세요.")
        print("python run.py demo-reset")
        print("python run.py demo-seed")
        return
    if _warn_if_server_running_for_demo():
        return

    set_demo_db_environment()
    print(f"데모 DB로 LUMOS Companion을 실행해요: {demo_db_path()}")
    handle = start_server_if_needed()
    webbrowser.open(web_tab_url(BASE_URL, "today"))
    CompanionWindow(server_handle=handle).run()


def main():
    parser = argparse.ArgumentParser(description="LUMOS")
    parser.add_argument(
        "command",
        nargs="?",
        default="api",
        choices=[
            "api",
            "cloud",
            "app",
            "companion",
            "demo-reset",
            "demo-seed",
            "demo",
            "demo-companion",
            "desktop",
            "briefing",
            "settings",
            "scheduler-once",
        ],
    )
    parser.add_argument("--no-scheduler", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.command == "api":
        run_api()
    elif args.command == "cloud":
        run_cloud()
    elif args.command == "app":
        run_web_app()
    elif args.command == "companion":
        run_companion()
    elif args.command == "demo-reset":
        run_demo_reset()
    elif args.command == "demo-seed":
        run_demo_seed()
    elif args.command == "demo":
        run_demo_web_app()
    elif args.command == "demo-companion":
        run_demo_companion()
    elif args.command == "desktop":
        from src.desktop.app import main as desktop_main

        desktop_args = ["--no-scheduler"] if args.no_scheduler else []
        desktop_main(desktop_args)
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
        print(
            {
                "ran": result.get("ran"),
                "reason": result.get("reason"),
                "pipeline_run_id": result.get("pipeline_run_id"),
                "signal_count": len(result.get("signals", [])),
            }
        )


if __name__ == "__main__":
    main()
