import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.routes import router
from src.app.lifecycle import initialize_app
from src.app.resource_paths import bundled_root, web_landing_dir, web_static_dir
from src.app.version import APP_VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_app()
    yield


app = FastAPI(
    title="LUMOS",
    description="Personalized trend briefing app",
    version=APP_VERSION,
    lifespan=lifespan,
)

# ── Security headers ─────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add minimal security response headers to every response.

    Deliberately avoids a strict CSP so that Supabase CDN scripts, Pretendard
    fonts, and other external resources continue to work without modification.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Rule: never combine allow_origins=["*"] with allow_credentials=True —
# browsers reject this per the CORS spec.
#
# LUMOS_ALLOWED_ORIGINS (comma-separated) overrides the default in all modes.
# Default:
#   supabase mode  → [] (same-origin only; no cross-origin API access needed)
#   local mode     → localhost variants for desktop/dev tooling

_allowed_origins_raw = os.environ.get("LUMOS_ALLOWED_ORIGINS", "").strip()
if _allowed_origins_raw:
    _cors_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]
else:
    _auth_mode = os.environ.get("LUMOS_AUTH_MODE", "local").strip().lower()
    if _auth_mode == "supabase":
        # Production: same-origin only.  No cross-origin API consumers expected.
        _cors_origins = []
    else:
        # Local / desktop dev: allow common localhost ports.
        _cors_origins = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # credentials only when specific origins are whitelisted (never with *)
    allow_credentials=bool(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

WEB_STATIC_DIR = web_static_dir()
WEB_LANDING_DIR = web_landing_dir()
app.mount("/static", StaticFiles(directory=WEB_STATIC_DIR), name="static")
app.mount("/landing-static", StaticFiles(directory=WEB_LANDING_DIR), name="landing-static")


@app.get("/health")
def health():
    return {"status": "ok", "product": "LUMOS"}


@app.get("/app")
def web_app():
    return FileResponse(WEB_STATIC_DIR / "index.html")


@app.get("/login")
def login_page():
    return FileResponse(WEB_STATIC_DIR / "login.html")


@app.get("/icon.png")
def chat_icon():
    return FileResponse(bundled_root() / "icon.png")


@app.get("/")
def landing_home():
    return FileResponse(WEB_LANDING_DIR / "index.html")


@app.get("/pricing")
def landing_pricing():
    return FileResponse(WEB_LANDING_DIR / "pricing.html")


@app.get("/download")
def landing_download():
    return FileResponse(WEB_LANDING_DIR / "download.html")


@app.get("/beta")
def landing_beta():
    return FileResponse(WEB_LANDING_DIR / "beta.html")
