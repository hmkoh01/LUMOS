from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.cloud.config import CLOUD_DB_PATH
from src.cloud.database import initialize_cloud_db
from src.cloud.routes import auth, devices, entitlements, usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_cloud_db()
    yield


app = FastAPI(
    title="LUMOS Cloud Backend",
    description="Development-only cloud auth skeleton for LUMOS",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(entitlements.router)
app.include_router(usage.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "lumos-cloud",
        "db_path": str(CLOUD_DB_PATH),
        "dev_only": True,
    }

