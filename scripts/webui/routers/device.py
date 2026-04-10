"""Device scan, connect, disconnect, and control endpoints."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectRequest(BaseModel):
    address: str


class IntensityRequest(BaseModel):
    value: int


class RawCommandRequest(BaseModel):
    command: str


async def _safe(coro):
    """Run a coroutine and return (result, None) or (None, error_response)."""
    try:
        return await coro, None
    except Exception as e:
        logger.error("Device error: %s", e)
        return None, JSONResponse(status_code=502, content={"error": str(e)})


@router.get("/state")
async def get_state(request: Request):
    dm = request.app.state.dm
    return await dm.get_state()


@router.post("/scan")
async def scan_devices(request: Request):
    dm = request.app.state.dm
    result, err = await _safe(dm.scan())
    if err: return err
    return {"devices": result}


@router.post("/connect")
async def connect(req: ConnectRequest, request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.connect(req.address))
    if err: return err
    return {"ok": True}


@router.post("/disconnect")
async def disconnect(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.disconnect())
    if err: return err
    return {"ok": True}


@router.post("/intensity")
async def set_intensity(req: IntensityRequest, request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.set_intensity(req.value))
    if err: return err
    return {"ok": True, "value": req.value}


@router.post("/stop")
async def stop(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.stop())
    if err: return err
    return {"ok": True}


@router.post("/start/{filename}")
async def start_script(filename: str, request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.start_script(filename))
    if err: return err
    return {"ok": True}


@router.post("/refresh")
async def refresh_status(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.refresh_status())
    if err: return err
    return {"ok": True}


@router.post("/shutdown")
async def shutdown_device(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.shutdown_device())
    if err: return err
    return {"ok": True}


@router.post("/reset")
async def reset_device(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.reset_device())
    if err: return err
    return {"ok": True}


@router.post("/raw")
async def send_raw(req: RawCommandRequest, request: Request):
    dm = request.app.state.dm
    result, err = await _safe(dm.send_raw(req.command))
    if err: return err
    return {"command": req.command, "lines": result}
