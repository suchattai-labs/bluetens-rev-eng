"""WebSocket-aware BLE device manager.

Bridges the bluetens_control BLE library with FastAPI/WebSocket clients.
Broadcasts
events over WebSocket connections.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from bleak.exc import BleakError

from scripts.bluetens_control import (
    BluetensDevice,
    ScriptFile,
    ShellNotify,
    scan_devices,
)

from .ws import manager as ws_manager

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    CONNECTED = "connected"


@dataclass
class WebDeviceInfo:
    address: str = ""
    firmware: str = ""
    battery_mv: int = 0
    battery_level: int = 0
    intensity: int = 0
    status: str = ""
    state: ConnectionState = ConnectionState.DISCONNECTED


KEEPALIVE_INTERVAL_S = 8  # seconds between keepalive polls (device auto-off after 15s)


class DeviceManager:
    """Manages a single BLE connection and broadcasts events via WebSocket."""

    def __init__(self):
        self._device: BluetensDevice | None = None
        self.info = WebDeviceInfo()
        self._lock = asyncio.Lock()       # connect/disconnect lock
        self._cmd_lock = asyncio.Lock()    # serializes all BLE commands
        self._keepalive_task: asyncio.Task | None = None

    # -- Broadcasting helpers --------------------------------------------------

    async def _broadcast(self, event: str, data: dict[str, Any] | None = None):
        await ws_manager.broadcast({"event": event, **(data or {})})

    async def _broadcast_state(self):
        await self._broadcast("state", {
            "address": self.info.address,
            "firmware": self.info.firmware,
            "battery_mv": self.info.battery_mv,
            "battery_level": self.info.battery_level,
            "intensity": self.info.intensity,
            "status": self.info.status,
            "connection": self.info.state.value,
        })

    # -- Notification handler --------------------------------------------------

    def _on_notification(self, ntype: ShellNotify, params: list[str]):
        """Called by BluetensDevice on BLE notifications."""
        if ntype == ShellNotify.INTENSITY and params:
            try:
                self.info.intensity = int(params[0])
            except (ValueError, IndexError):
                pass
        asyncio.create_task(self._broadcast("notification", {
            "type": ntype.name,
            "params": params,
        }))

    # -- Keepalive -------------------------------------------------------------

    async def _keepalive_loop(self):
        """Periodically poll device status to keep the BLE connection alive."""
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_S)
            if not self._device:
                break
            try:
                async with self._cmd_lock:
                    status = await asyncio.wait_for(
                        self._device.get_status(), timeout=10.0
                    )
                self.info.intensity = status.intensity
                self.info.status = f"tick={status.tick}"
                await self._broadcast_state()
            except (BleakError, OSError, asyncio.TimeoutError) as e:
                logger.warning("Keepalive failed: %s", e)
                await self._handle_disconnect()
                break
            except Exception as e:
                logger.error("Keepalive unexpected error: %s", e)
                await self._handle_disconnect()
                break

    def _start_keepalive(self):
        self._stop_keepalive()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    def _stop_keepalive(self):
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            self._keepalive_task = None

    # -- Disconnection handler -------------------------------------------------

    async def _handle_disconnect(self):
        """Called when BLE connection is lost unexpectedly."""
        logger.warning("BLE connection lost")
        self._stop_keepalive()
        self._device = None
        self.info = WebDeviceInfo()
        await self._broadcast_state()
        await self._broadcast("notification", {
            "type": "DISCONNECTED",
            "params": ["connection lost"],
        })

    async def _ble_call(self, coro):
        """Wrap a BLE coroutine with disconnect detection."""
        try:
            return await coro
        except BleakError as e:
            if "Not connected" in str(e):
                await self._handle_disconnect()
            raise
        except OSError as e:
            await self._handle_disconnect()
            raise BleakError(f"Connection lost: {e}") from e

    # -- Public API ------------------------------------------------------------

    async def scan(self, timeout: float = 10.0) -> list[dict]:
        self.info.state = ConnectionState.SCANNING
        await self._broadcast_state()
        try:
            results = await scan_devices(duration=timeout)
            await self._broadcast("scan_results", {"devices": results})
            return results
        finally:
            if self.info.state == ConnectionState.SCANNING:
                self.info.state = ConnectionState.DISCONNECTED
                await self._broadcast_state()

    async def connect(self, address: str):
        async with self._lock:
            self.info.state = ConnectionState.CONNECTING
            self.info.address = address
            await self._broadcast_state()

            self._device = BluetensDevice(address)
            self._device._notify_callbacks.append(self._on_notification)
            dev_info = await self._device.connect()

            self.info.firmware = dev_info.version_str
            self.info.battery_mv = dev_info.battery_mv
            self.info.battery_level = dev_info.battery_level
            self.info.intensity = dev_info.status.intensity
            self.info.state = ConnectionState.CONNECTED
            await self._broadcast_state()
            self._start_keepalive()

    async def disconnect(self):
        async with self._lock:
            self._stop_keepalive()
            if self._device:
                await self._device.disconnect()
                self._device = None
            self.info = WebDeviceInfo()
            await self._broadcast_state()

    async def set_intensity(self, value: int):
        if self._device:
            async with self._cmd_lock:
                actual = await self._ble_call(self._device.set_intensity(value))
            self.info.intensity = actual
            await self._broadcast_state()

    async def stop(self):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.stop())
            self.info.intensity = 0
            await self._broadcast_state()

    async def start_script(self, filename: str):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.start_script(filename))

    async def refresh_status(self):
        if self._device:
            async with self._cmd_lock:
                bat_mv = await self._ble_call(self._device.get_battery())
                self.info.battery_mv = bat_mv
                self.info.battery_level = self._device.info.battery_level
                status = await self._ble_call(self._device.get_status())
            self.info.intensity = status.intensity
            self.info.status = f"tick={status.tick}"
            await self._broadcast_state()

    async def list_files(self) -> list[dict]:
        if not self._device:
            return []
        async with self._cmd_lock:
            raw = await self._ble_call(self._device.list_files())
        return self._parse_file_listing(raw)

    async def remove_file(self, filename: str):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.remove_file(filename))

    async def upload_script(self, filename: str, script: ScriptFile):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.upload_script(filename, script))
            await self._broadcast("upload_progress", {
                "filename": filename,
                "done": True,
            })

    async def upload_and_start(self, filename: str, script: ScriptFile):
        await self.upload_script(filename, script)
        await self.start_script(filename)

    async def set_default_file(self, filename: str):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.set_default_file(filename))

    async def format_fs(self):
        if self._device:
            async with self._cmd_lock:
                await self._ble_call(self._device.format_filesystem())

    async def send_raw(self, command: str) -> list[str]:
        if self._device:
            cmd = command if command.startswith(">") else f">{command}"
            async with self._cmd_lock:
                await self._ble_call(self._device._send_command(cmd))
                lines = []
                try:
                    while True:
                        line = await asyncio.wait_for(
                            self._device._line_queue.get(), timeout=5.0
                        )
                        if self._device._is_status_retval(line):
                            break
                        lines.append(line)
                except asyncio.TimeoutError:
                    pass
            await self._broadcast("command_response", {
                "command": command,
                "lines": lines,
            })
            return lines
        return []

    async def shutdown_device(self):
        self._stop_keepalive()
        if self._device:
            await self._device.shutdown()
            self._device = None
            self.info = WebDeviceInfo()
            await self._broadcast_state()

    async def reset_device(self):
        self._stop_keepalive()
        if self._device:
            await self._device.reset()
            self._device = None
            self.info = WebDeviceInfo()
            await self._broadcast_state()

    async def get_state(self) -> dict:
        return {
            "address": self.info.address,
            "firmware": self.info.firmware,
            "battery_mv": self.info.battery_mv,
            "battery_level": self.info.battery_level,
            "intensity": self.info.intensity,
            "status": self.info.status,
            "connection": self.info.state.value,
        }

    async def shutdown(self):
        """Cleanup on app shutdown."""
        self._stop_keepalive()
        if self._device:
            try:
                await self._device.disconnect()
            except Exception:
                pass
            self._device = None

    # -- Helpers ---------------------------------------------------------------

    @staticmethod
    def _parse_file_listing(raw: str) -> list[dict]:
        """Parse the raw 'ls' output into structured file entries."""
        files = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Typical format: "filename.txt 1234" or "filename.txt 1234 *"
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                try:
                    size = int(parts[1])
                except ValueError:
                    size = 0
                is_default = "*" in line
                files.append({"name": name, "size": size, "default": is_default})
        return files
