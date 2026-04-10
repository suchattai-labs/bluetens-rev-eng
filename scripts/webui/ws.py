"""WebSocket connection manager for real-time BLE event broadcasting."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts messages."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def accept(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def remove(self, ws: WebSocket):
        self._connections.remove(ws)
        logger.info("WebSocket client disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: dict[str, Any]):
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.accept(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            # Client-to-server messages can be handled here
            dm = ws.app.state.dm
            action = msg.get("action")
            if action == "get_state":
                state = await dm.get_state()
                await ws.send_text(json.dumps({"event": "state", **state}))
    except WebSocketDisconnect:
        manager.remove(ws)
