"""Device filesystem management endpoints."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class FileActionRequest(BaseModel):
    filename: str


async def _safe(coro):
    try:
        return await coro, None
    except Exception as e:
        logger.error("Files error: %s", e)
        return None, JSONResponse(status_code=502, content={"error": str(e)})


@router.get("/")
async def list_files(request: Request):
    dm = request.app.state.dm
    result, err = await _safe(dm.list_files())
    if err: return err
    return {"files": result}


@router.delete("/{filename}")
async def remove_file(filename: str, request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.remove_file(filename))
    if err: return err
    return {"ok": True}


@router.post("/default")
async def set_default(req: FileActionRequest, request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.set_default_file(req.filename))
    if err: return err
    return {"ok": True}


@router.post("/format")
async def format_fs(request: Request):
    dm = request.app.state.dm
    _, err = await _safe(dm.format_fs())
    if err: return err
    return {"ok": True}
