from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.app.lifecycle import initialize_app
from src.app.resource_paths import web_landing_dir, web_static_dir
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
