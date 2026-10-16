"""WinError 10014 reproduction conditions and analysis.

This documents the socket error encountered during testing, separating
environment issues from potential code issues.

ERROR:
    OSError: [WinError 10014] The system detected an invalid pointer address
    in attempting to use a pointer argument in a call.

CONTEXT:
    - Python 3.9.21 (Anaconda distribution on Windows 11 Pro 10.0.26200)
    - Both system Python and venv Python (lumos/Scripts/python.exe) affected
    - Occurs in asyncio event loop initialization, specifically socket.socketpair()

REPRODUCTION CONDITIONS:
    1. Platform: Windows 11 Pro (build 26200)
    2. Python: 3.9.21 via Anaconda
    3. Trigger: Any code that calls asyncio.new_event_loop() under the default
       WindowsProactorEventLoopPolicy, when socket.socketpair() fails.
    4. Confirmed affected operations:
       - playwright.sync_api (sync_playwright context manager)
       - Any TestClient that creates new event loops (FastAPI/Starlette)
    5. Workaround attempted:
       - asyncio.WindowsSelectorEventLoopPolicy() → fixes socketpair but
         breaks subprocess support (Playwright needs subprocess_exec)
       - asyncio.WindowsProactorEventLoopPolicy() + asyncio.run() in a
         script file → WORKS (the script-based approach avoids the issue)

ANALYSIS:
    - Root cause: Anaconda Python 3.9.21 on Windows 11 build 26200 has a
      known interaction issue with socket.socketpair() in certain terminal
      environments (e.g., Git Bash under ConPTY, or when many sockets are
      already open from parent processes like Claude Code).
    - This is an ENVIRONMENT issue, not a LUMOS code bug.
    - The same code works when run as a standalone .py script via asyncio.run()
      but fails when run inline via `python -c "..."` in certain shells.

EVIDENCE:
    - tests/test_security_hardening.py avoids this by calling handlers directly
      (no HTTP client portals, documented in MEMORY.md).
    - tests/test_runtime_smoke.py uses a single shared TestClient via
      setUpClass/tearDownClass pattern to minimize socket creation.
    - The screenshot script (screenshots/take_screenshots.py) works when run
      as `python screenshots/take_screenshots.py` with asyncio.run().

IMPACT ON SOURCE PILOT:
    - Does NOT affect source collection (RSS collector uses synchronous HTTP).
    - Does NOT affect briefing generation (no async event loops involved).
    - Only affects test infrastructure that creates HTTP test clients or
      browser automation (Playwright).
    - Existing test patterns (direct function calls, shared TestClient)
      successfully avoid triggering the issue.

RECOMMENDATIONS:
    1. Keep the setUpClass/tearDownClass TestClient pattern for HTTP tests.
    2. For browser automation, use script files with asyncio.run() rather
       than inline python -c commands.
    3. Consider upgrading to Python 3.12+ which has improved Windows asyncio.
    4. Document this in test README if one is created.
"""

import sys
import platform


def get_environment_info():
    """Collect environment details for WinError 10014 diagnosis."""
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "windows_build": platform.version(),
        "anaconda": "anaconda" in sys.version.lower() or "conda" in sys.executable.lower(),
        "event_loop_policy": type(
            __import__("asyncio").get_event_loop_policy()
        ).__name__,
    }


if __name__ == "__main__":
    info = get_environment_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
