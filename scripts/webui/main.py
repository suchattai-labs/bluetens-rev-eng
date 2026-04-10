"""FastAPI application for Bluetens Web UI."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from bleak.exc import BleakError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .device_manager import DeviceManager
from .routers import device, files, scripts
from .ws import router as ws_router

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except BleakError as e:
            logger.error("BLE error: %s", e)
            return JSONResponse(status_code=502, content={"error": str(e)})
        except Exception as e:
            logger.error("Unhandled error: %s", e, exc_info=True)
            return JSONResponse(status_code=500, content={"error": str(e)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dm = DeviceManager()
    yield
    await app.state.dm.shutdown()


app = FastAPI(title="Bluetens Control", lifespan=lifespan)
app.add_middleware(ErrorHandlingMiddleware)

app.include_router(ws_router)
app.include_router(device.router, prefix="/api/device", tags=["device"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
