#!/usr/bin/env python3
"""
Bluetens TENS Unit BLE Control Script

Reverse-engineered from Bluetens Android app v7.0.59.
Uses the bleak library for cross-platform BLE communication.

Protocol: Text-based shell commands over BLE serial profile (service FFE0, char FFE1).
Commands are UTF-8 strings prefixed with '>', responses are line-delimited with \\r\\n.

Usage:
    python bluetens_control.py scan
    python bluetens_control.py connect <address>
    python bluetens_control.py shell <address>

Requires: pip install bleak
"""

import argparse
import asyncio
import hashlib
import logging
import math
import re
import struct
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError:
    print("Error: bleak library not installed. Run: pip install bleak", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# BLE Protocol Constants
# ---------------------------------------------------------------------------

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

MTU = 20
MIN_WRITE_INTERVAL_S = 0.027  # 27ms between write-without-response packets
REQUEST_TIMEOUT_S = 120.0
CONNECTION_TIMEOUT_S = 240.0
LINE_BREAK = "\r\n"

# Device advertising name patterns
CLASSIC_NAMES = re.compile(r"(bluetens|\.blt)", re.IGNORECASE)
SPORT_NAMES = re.compile(r"(duo|sport)", re.IGNORECASE)
KNOWN_PREFIXES = ("blt", "bluetensx", "bluetensq", "bluetens", "pkt", "bst",
                   "bluetens2", "duosport2")

# Intensity limits
INTENSITY_MIN = 1
INTENSITY_MAX = 60

# Script file constants
MAX_FREQ = 1200
MAX_IMPULSE = 400
MIN_IMPULSE = 20
DEF_FREQ = 54
DEF_IMPULSE = 100
DEF_CLUSTER = 1
DEF_REPEAT = 1
DEF_INTERVAL = 0

log = logging.getLogger("bluetens")


# ---------------------------------------------------------------------------
# CRC16 (CRC-CCITT, polynomial 0x1021, seed 0)
# ---------------------------------------------------------------------------

def crc16(data: bytes, seed: int = 0) -> int:
    """CRC16-CCITT as used by the Bluetens OTA protocol."""
    crc = seed
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

class ShellNotify(IntEnum):
    SHUTDOWN = 0
    DISCONNECTED = 1
    NO_LOAD = 2
    STOPPED = 3
    INTENSITY = 4
    BATTERY = 5
    HARDWARE_ERROR = 6
    LOW_BATTERY = 7
    FULL_SPACE = 8


@dataclass
class DeviceStatus:
    tick: int = 0           # elapsed seconds
    intensity: int = 0      # current strength 1-60
    default_md5: str = ""   # MD5 of default file
    last_md5: str = ""      # MD5 of last/current file


@dataclass
class DeviceInfo:
    version_str: str = ""
    version_num: int = 0
    battery_mv: int = 0
    battery_level: int = 0  # 1-4
    default_file: str = ""
    status: DeviceStatus = field(default_factory=DeviceStatus)
    is_v2: bool = False


# ---------------------------------------------------------------------------
# Script File Builder
# ---------------------------------------------------------------------------

class ScriptBlock:
    """A single stimulation block within a section."""

    def __init__(self, freq: float = DEF_FREQ, impulse: int = DEF_IMPULSE,
                 cluster: int = DEF_CLUSTER, interval: int = DEF_INTERVAL,
                 repeat: int = DEF_REPEAT):
        self.freq = freq
        self.impulse = impulse
        self.cluster = cluster
        self.interval = interval
        self.repeat = repeat

    def time_est_ms(self) -> float:
        """Estimated duration in milliseconds."""
        return (1000.0 / self.freq * self.cluster + self.interval) * self.repeat

    def serialize(self, digit_base: int = 16, prev: Optional["ScriptBlock"] = None) -> str:
        """Serialize to token string. Only emits values that differ from prev."""
        parts = ["|"]  # block separator

        def _fmt(val: int) -> str:
            if digit_base == 16:
                return format(val, "x")
            return str(val)

        if prev is None:
            parts.append(f"R{_fmt(self.repeat)}")
            if self.interval != DEF_INTERVAL:
                parts.append(f"I{_fmt(self.interval)}")
            parts.append(f"P{_fmt(self.impulse)}")
            if self.freq == int(self.freq):
                parts.append(f"F{_fmt(int(self.freq))}")
            else:
                parts.append(f"T{_fmt(int(self.freq * 10))}")
            if self.cluster != DEF_CLUSTER:
                parts.append(f"C{_fmt(self.cluster)}")
        else:
            if self.repeat != prev.repeat:
                parts.append(f"R{_fmt(self.repeat)}")
            if self.interval != prev.interval:
                parts.append(f"I{_fmt(self.interval)}")
            if self.impulse != prev.impulse:
                parts.append(f"P{_fmt(self.impulse)}")
            if self.freq != prev.freq:
                if self.freq == int(self.freq):
                    parts.append(f"F{_fmt(int(self.freq))}")
                else:
                    parts.append(f"T{_fmt(int(self.freq * 10))}")
            if self.cluster != prev.cluster:
                parts.append(f"C{_fmt(self.cluster)}")

        return "".join(parts)


class ScriptSection:
    """A section containing one or more blocks."""

    def __init__(self, repeat: int = DEF_REPEAT, interval: int = DEF_INTERVAL):
        self.repeat = repeat
        self.interval = interval
        self.blocks: list[ScriptBlock] = []

    def add_block(self, block: ScriptBlock) -> "ScriptSection":
        self.blocks.append(block)
        return self

    def time_est_ms(self) -> float:
        block_time = sum(b.time_est_ms() for b in self.blocks)
        return (block_time + self.interval) * self.repeat

    def serialize(self, digit_base: int = 16) -> str:
        parts = ["{"]

        def _fmt(val: int) -> str:
            if digit_base == 16:
                return format(val, "x")
            return str(val)

        if self.repeat != 1:
            parts.append(f"R{_fmt(self.repeat)}")
        if self.interval != 0:
            parts.append(f"I{_fmt(self.interval)}")

        prev = None
        for block in self.blocks:
            parts.append(block.serialize(digit_base, prev))
            prev = block

        parts.append("}")
        return "".join(parts)


class ScriptFile:
    """A complete Bluetens script file."""

    VERSION = 1

    def __init__(self, digit_base: int = 16):
        self.digit_base = digit_base
        self.sections: list[ScriptSection] = []
        self.loop_indices: list[int] = []  # 0-based section indices to loop

    def add_section(self, section: ScriptSection) -> "ScriptFile":
        self.sections.append(section)
        return self

    def add_loop(self, *section_indices: int) -> "ScriptFile":
        """Add section loop references (0-based indices)."""
        self.loop_indices.extend(section_indices)
        return self

    def time_est_ms(self) -> float:
        base = sum(s.time_est_ms() for s in self.sections)
        loop = sum(self.sections[i].time_est_ms() for i in self.loop_indices
                    if i < len(self.sections))
        return base + loop

    def serialize(self) -> str:
        if not self.sections:
            return ""

        parts = [f"V{self.VERSION}", f"D{self.digit_base}"]
        for section in self.sections:
            parts.append(section.serialize(self.digit_base))

        if self.loop_indices:
            parts.append("<")
            for idx in self.loop_indices:
                parts.append(f"S{idx + 1}")  # 1-based in wire format
            parts.append(">")

        return "".join(parts)

    def content_bytes(self) -> bytes:
        return self.serialize().encode("utf-8")

    def md5(self) -> str:
        return hashlib.md5(self.content_bytes()).hexdigest().upper()


# ---------------------------------------------------------------------------
# Pattern Generator — pre-bake time-varying stimulation scripts
# ---------------------------------------------------------------------------

class PatternGenerator:
    """
    Generates ScriptFile objects with time-varying parameters.

    All durations are in seconds. Frequency in Hz, impulse in microseconds.
    The device runs these autonomously — no BLE traffic during playback.

    Constraints from the protocol:
      - Frequency: 0.1 - 1200 Hz  (FreqT token allows 0.1 Hz resolution)
      - Impulse:   20 - 400 us
      - Cluster:   1+
      - Intensity:  controlled separately via >str (not in scripts)
      - Filesystem: 60 KB total — keep scripts compact
    """

    @staticmethod
    def _calc_repeat(freq: float, cluster: int, interval: int,
                     target_duration_ms: float) -> int:
        """Calculate repeat count to fill a target duration."""
        cycle_ms = 1000.0 / freq * cluster + interval
        if cycle_ms <= 0:
            return 1
        r = max(1, round(target_duration_ms / cycle_ms))
        return r

    @staticmethod
    def _clamp_freq(f: float) -> float:
        return max(0.1, min(MAX_FREQ, f))

    @staticmethod
    def _clamp_impulse(p: int) -> int:
        return max(MIN_IMPULSE, min(MAX_IMPULSE, p))

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    @staticmethod
    def _log_lerp(a: float, b: float, t: float) -> float:
        """Logarithmic interpolation — perceptually even for frequency sweeps."""
        if a <= 0:
            a = 0.1
        return a * (b / a) ** t

    # -- High-level generators ------------------------------------------------

    @classmethod
    def freq_sweep(cls, start_hz: float, end_hz: float, duration_s: float,
                   steps: int = 50, impulse: int = DEF_IMPULSE,
                   cluster: int = DEF_CLUSTER, log_scale: bool = True,
                   loop: bool = False) -> ScriptFile:
        """
        Sweep frequency from start_hz to end_hz over duration_s.

        Args:
            start_hz:  Starting frequency
            end_hz:    Ending frequency
            duration_s: Total sweep duration
            steps:     Number of discrete frequency steps
            impulse:   Pulse width in us (constant)
            cluster:   Pulses per burst (constant)
            log_scale: Use logarithmic interpolation (True) or linear (False)
            loop:      Loop the sweep indefinitely
        """
        sf = ScriptFile()
        section = ScriptSection()
        step_ms = (duration_s * 1000.0) / steps
        interp = cls._log_lerp if log_scale else cls._lerp

        for i in range(steps):
            t = i / max(1, steps - 1)
            freq = cls._clamp_freq(interp(start_hz, end_hz, t))
            repeat = cls._calc_repeat(freq, cluster, 0, step_ms)
            section.add_block(ScriptBlock(
                freq=freq, impulse=cls._clamp_impulse(impulse),
                cluster=cluster, repeat=repeat
            ))

        sf.add_section(section)
        if loop:
            sf.add_loop(0)
        return sf

    @classmethod
    def impulse_sweep(cls, start_us: int, end_us: int, duration_s: float,
                      steps: int = 50, freq: float = DEF_FREQ,
                      cluster: int = DEF_CLUSTER,
                      loop: bool = False) -> ScriptFile:
        """Sweep pulse width from start_us to end_us over duration_s."""
        sf = ScriptFile()
        section = ScriptSection()
        step_ms = (duration_s * 1000.0) / steps

        for i in range(steps):
            t = i / max(1, steps - 1)
            imp = cls._clamp_impulse(round(cls._lerp(start_us, end_us, t)))
            repeat = cls._calc_repeat(freq, cluster, 0, step_ms)
            section.add_block(ScriptBlock(
                freq=freq, impulse=imp, cluster=cluster, repeat=repeat
            ))

        sf.add_section(section)
        if loop:
            sf.add_loop(0)
        return sf

    @classmethod
    def alternating(cls, freq_a: float, freq_b: float,
                    cycle_s: float, total_s: float,
                    impulse_a: int = DEF_IMPULSE, impulse_b: int = DEF_IMPULSE,
                    cluster: int = DEF_CLUSTER,
                    loop: bool = False) -> ScriptFile:
        """Alternate between two parameter sets on a fixed cycle."""
        sf = ScriptFile()
        half_ms = cycle_s * 500.0  # half cycle in ms
        n_cycles = max(1, round(total_s / cycle_s))

        section = ScriptSection(repeat=n_cycles)
        section.add_block(ScriptBlock(
            freq=cls._clamp_freq(freq_a),
            impulse=cls._clamp_impulse(impulse_a),
            cluster=cluster,
            repeat=cls._calc_repeat(freq_a, cluster, 0, half_ms)
        ))
        section.add_block(ScriptBlock(
            freq=cls._clamp_freq(freq_b),
            impulse=cls._clamp_impulse(impulse_b),
            cluster=cluster,
            repeat=cls._calc_repeat(freq_b, cluster, 0, half_ms)
        ))

        sf.add_section(section)
        if loop:
            sf.add_loop(0)
        return sf

    @classmethod
    def burst(cls, freq: float, on_s: float, off_s: float,
              n_bursts: int, impulse: int = DEF_IMPULSE,
              cluster: int = DEF_CLUSTER,
              loop: bool = False) -> ScriptFile:
        """Burst mode: on_s seconds of stimulation, off_s seconds pause, repeat."""
        sf = ScriptFile()
        section = ScriptSection(repeat=n_bursts)

        on_ms = on_s * 1000.0
        off_ms = off_s * 1000.0

        section.add_block(ScriptBlock(
            freq=cls._clamp_freq(freq),
            impulse=cls._clamp_impulse(impulse),
            cluster=cluster,
            repeat=cls._calc_repeat(freq, cluster, 0, on_ms)
        ))
        # Off period: lowest possible freq with interval to fill the gap
        # Use 1 pulse at a low freq + interval for the remainder
        section.add_block(ScriptBlock(
            freq=1.0, impulse=MIN_IMPULSE, cluster=1,
            interval=max(0, round(off_ms - 1000)), repeat=1
        ))

        sf.add_section(section)
        if loop:
            sf.add_loop(0)
        return sf

    @classmethod
    def custom(cls, param_fn: Callable[[float], dict], duration_s: float,
               steps: int = 50, loop: bool = False) -> ScriptFile:
        """
        Generate a script from a custom parameter function.

        param_fn(t) receives normalized time 0.0-1.0 and returns a dict with
        any subset of: freq, impulse, cluster. Missing keys use defaults.

        Example — sinusoidal frequency modulation:
            PatternGenerator.custom(
                lambda t: {"freq": 50 + 30 * math.sin(2 * math.pi * t)},
                duration_s=30, steps=100
            )
        """
        sf = ScriptFile()
        section = ScriptSection()
        step_ms = (duration_s * 1000.0) / steps

        for i in range(steps):
            t = i / max(1, steps - 1)
            params = param_fn(t)
            freq = cls._clamp_freq(params.get("freq", DEF_FREQ))
            impulse = cls._clamp_impulse(params.get("impulse", DEF_IMPULSE))
            cluster = max(1, params.get("cluster", DEF_CLUSTER))
            repeat = cls._calc_repeat(freq, cluster, 0, step_ms)
            section.add_block(ScriptBlock(
                freq=freq, impulse=impulse, cluster=cluster, repeat=repeat
            ))

        sf.add_section(section)
        if loop:
            sf.add_loop(0)
        return sf

    @classmethod
    def multi_phase(cls, phases: list[dict], loop: bool = False) -> ScriptFile:
        """
        Build a multi-phase program from a list of phase descriptors.

        Each phase dict:
          freq, impulse, cluster: stimulation parameters
          duration_s: how long this phase lasts
          repeat: (optional) section repeat count, default 1

        Example — warmup / main / cooldown:
            PatternGenerator.multi_phase([
                {"freq": 5,   "impulse": 100, "duration_s": 60},   # warmup
                {"freq": 100, "impulse": 200, "duration_s": 600},  # main
                {"freq": 5,   "impulse": 100, "duration_s": 60},   # cooldown
            ])
        """
        sf = ScriptFile()
        for phase in phases:
            freq = cls._clamp_freq(phase.get("freq", DEF_FREQ))
            impulse = cls._clamp_impulse(phase.get("impulse", DEF_IMPULSE))
            cluster = max(1, phase.get("cluster", DEF_CLUSTER))
            dur_ms = phase["duration_s"] * 1000.0
            sec_repeat = phase.get("repeat", 1)

            repeat = cls._calc_repeat(freq, cluster, 0, dur_ms / sec_repeat)
            section = ScriptSection(repeat=sec_repeat)
            section.add_block(ScriptBlock(
                freq=freq, impulse=impulse, cluster=cluster, repeat=repeat
            ))
            sf.add_section(section)

        if loop:
            sf.add_loop(*range(len(phases)))
        return sf


# ---------------------------------------------------------------------------
# Bluetens Device Controller
# ---------------------------------------------------------------------------

class BluetensDevice:
    """
    High-level controller for a Bluetens TENS unit over BLE.

    Usage:
        async with BluetensDevice(address) as dev:
            info = await dev.connect_and_init()
            await dev.set_intensity(15)
            await dev.start_script("MyFile")
            await dev.stop()
    """

    def __init__(self, address: str):
        self.address = address
        self.client: Optional[BleakClient] = None
        self.info = DeviceInfo()
        self._rx_buffer = bytearray()
        self._line_queue: asyncio.Queue[str] = asyncio.Queue()
        self._notify_callbacks: list = []
        self._strict_write = False
        self._connected = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    # -- Connection ---------------------------------------------------------

    async def connect(self) -> DeviceInfo:
        """Connect to the device and run the initialization sequence."""
        self.client = BleakClient(self.address, timeout=CONNECTION_TIMEOUT_S)
        await self.client.connect()
        self._connected = True
        log.info("Connected to %s", self.address)

        # Enable notifications on the shell characteristic
        await self.client.start_notify(CHAR_UUID, self._on_notification)
        log.debug("Notifications enabled on %s", CHAR_UUID)

        # Check write-without-response support
        char = self.client.services.get_characteristic(CHAR_UUID)
        if char and "write-without-response" not in char.properties:
            self._strict_write = True
            log.warning("Device does not support write-without-response, using strict write")

        # Run init sequence: version -> battery -> status
        await self._init_sequence()
        return self.info

    async def disconnect(self):
        """Disconnect from the device."""
        if self.client and self._connected:
            try:
                await self.client.stop_notify(CHAR_UUID)
            except Exception:
                pass
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self._connected = False
            log.info("Disconnected from %s", self.address)

    async def _init_sequence(self):
        """Post-connection initialization: version, battery, status."""
        # 1. Version
        ver_line = await self._execute(">ver", lambda l: "v." in l or "ver" in l)
        self._parse_version(ver_line)

        # 2. Battery
        try:
            bat_line = await self._execute(
                ">bat",
                lambda l: (" mv" in l) or (len(l.split(":")) > 1 and l.split(":")[0] == "32769")
            )
            self._parse_battery(bat_line)
        except asyncio.TimeoutError:
            log.warning("Battery request timed out")

        # 3. Status
        try:
            stat_line = await self._execute(
                ">stat",
                lambda l: "tick" in l or "md5" in l
            )
            self._parse_status(stat_line)
        except asyncio.TimeoutError:
            log.warning("Status request timed out")

    # -- Shell Commands -----------------------------------------------------

    async def get_version(self) -> str:
        """Query firmware version. Returns version string like 'v.2.0.27'."""
        line = await self._execute(">ver", lambda l: "v." in l or "ver" in l)
        self._parse_version(line)
        return self.info.version_str

    async def get_battery(self) -> int:
        """Query battery level in millivolts."""
        line = await self._execute(
            ">bat",
            lambda l: " mv" in l or (len(l.split(":")) > 1 and l.split(":")[0] == "32769")
        )
        self._parse_battery(line)
        return self.info.battery_mv

    async def get_status(self) -> DeviceStatus:
        """Query device status (tick, intensity, file MD5s)."""
        line = await self._execute(">stat", lambda l: "tick" in l or "md5" in l)
        self._parse_status(line)
        return self.info.status

    async def set_intensity(self, value: int) -> int:
        """Set stimulation intensity (1-60). Returns actual intensity set."""
        if value < INTENSITY_MIN or value > INTENSITY_MAX:
            raise ValueError(f"Intensity must be {INTENSITY_MIN}-{INTENSITY_MAX}, got {value}")

        line = await self._execute(
            f">str {value}",
            lambda l: "str=" in l or l.strip().isdigit()
        )

        if "str=" in line:
            actual = int(line.split("=")[1])
        else:
            actual = int(line.strip())

        self.info.status.intensity = actual
        return actual

    async def start_script(self, filename: str) -> None:
        """Start running a script file on the device."""
        await self._execute(
            f">ssta {filename}",
            self._is_status_retval
        )
        self.info.status.intensity = 1
        log.info("Started script: %s", filename)

    async def stop(self) -> None:
        """Stop current stimulation output."""
        await self._execute(">osto", self._is_status_retval)
        self.info.status.intensity = 0
        log.info("Stimulation stopped")

    async def set_default_file(self, filename: str) -> None:
        """Set the default script file."""
        await self._execute(
            f">sdef {filename}",
            lambda l: "sdef" in l or filename in l
        )
        self.info.default_file = filename
        log.info("Default file set to: %s", filename)

    async def file_md5(self, filename: str) -> str:
        """Get the MD5 hash of a file on the device."""
        line = await self._execute(f">md5 {filename}", lambda _: True)
        return line.strip().upper()

    async def remove_file(self, filename: str) -> None:
        """Delete a file from the device."""
        await self._execute(f">rm {filename}", self._is_status_retval)
        log.info("Removed file: %s", filename)

    async def list_files(self) -> str:
        """List files on the device. Returns raw response text."""
        # ls may return multiple lines; collect until a status line or timeout
        lines = []
        await self._send_command(">ls")
        try:
            while True:
                line = await asyncio.wait_for(self._line_queue.get(), timeout=5.0)
                if self._is_status_retval(line):
                    break
                lines.append(line)
        except asyncio.TimeoutError:
            pass
        return "\n".join(lines)

    async def set_bluetooth_name(self, name: str) -> str:
        """Set the device's Bluetooth advertising name."""
        line = await self._execute(
            f">btnm {name}",
            lambda l: "AT+NAME" in l or "btnm=" in l
        )
        return line.replace("AT+NAME", "").replace("btnm=", "").strip()

    async def shutdown(self) -> None:
        """Power off the device."""
        try:
            await self._send_command(">shdn")
            await asyncio.sleep(0.5)
        except Exception:
            pass
        await self.disconnect()
        log.info("Device shut down")

    async def reset(self) -> None:
        """Reboot the device."""
        try:
            await self._send_command(">rst")
            await asyncio.sleep(0.5)
        except Exception:
            pass
        await self.disconnect()
        log.info("Device reset")

    async def format_filesystem(self) -> None:
        """Format the device filesystem."""
        if self.info.version_num >= 30000000:
            cmd = ">format . ultrafs"
        else:
            cmd = ">fmt BBFS"
        await self._execute(cmd, self._is_status_retval, timeout=REQUEST_TIMEOUT_S)
        log.info("Filesystem formatted")

    async def upload_file(self, filename: str, content: bytes) -> None:
        """
        Upload a file to the device.

        Uses the CAT protocol: checks MD5 first, skips if unchanged,
        otherwise sends the file content as raw bytes.
        """
        content_md5 = hashlib.md5(content).hexdigest().upper()

        # Check if file already exists with same content
        try:
            device_md5 = await self.file_md5(filename)
            if device_md5 == content_md5:
                log.info("File %s unchanged (MD5 match), skipping upload", filename)
                return
        except (asyncio.TimeoutError, Exception):
            pass  # File doesn't exist or MD5 failed, proceed with upload

        # Drain any stale lines from previous commands (e.g. failed md5)
        while not self._line_queue.empty():
            try:
                self._line_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Send cat command
        await self._send_command(f">cat {filename} -l={len(content)}")

        # Send file content
        await self._send_raw(content)

        # Wait for completion — skip empty or non-status lines
        deadline = asyncio.get_event_loop().time() + REQUEST_TIMEOUT_S
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"Upload timed out for {filename}")
            line = await asyncio.wait_for(self._line_queue.get(), timeout=remaining)
            if not line.strip():
                continue  # skip empty lines
            parts = line.split(":")
            if len(parts) > 1 and parts[0].strip() == "3":
                log.info("File %s uploaded successfully (%d bytes)", filename, len(content))
                return
            if self._is_status_retval(line):
                continue  # skip status echoes
            raise RuntimeError(f"Unexpected cat response: {line}")

    async def upload_script(self, filename: str, script: ScriptFile) -> None:
        """Upload a ScriptFile object to the device."""
        await self.upload_file(filename, script.content_bytes())

    # -- OTA Firmware Update ------------------------------------------------

    async def ota_update(self, firmware: bytes) -> None:
        """
        Perform an OTA firmware update.

        WARNING: This will flash new firmware. Use with extreme caution.
        Incorrect firmware can brick the device.
        """
        # Split firmware into 16-byte packets with CRC headers
        packets = []
        overall_crc = 0

        for offset in range(0, len(firmware), 16):
            chunk = firmware[offset:offset + 16]
            overall_crc = crc16(chunk, overall_crc)

            # Pad to 16 bytes if needed
            padded = chunk.ljust(16, b'\x00')

            # Build 20-byte packet: [uint16 offset, uint16 chunk_crc, uint8[16] data]
            chunk_crc = crc16(padded)
            packet = struct.pack("<HH", offset, chunk_crc) + padded
            packets.append(packet)

        # Force strict write for OTA
        old_strict = self._strict_write
        self._strict_write = True

        try:
            # Initiate OTA
            await self._send_command(f">ota -s={len(firmware)} -c={overall_crc}")

            # Wait for ready signal (status 0)
            line = await asyncio.wait_for(self._line_queue.get(), timeout=REQUEST_TIMEOUT_S)
            parts = line.split(":")
            if not (len(parts) > 1 and parts[0].strip() == "0"):
                if "crc error" in line.lower():
                    raise RuntimeError("OTA CRC error during initiation")
                raise RuntimeError(f"OTA not ready: {line}")

            # Send packets
            for i, packet in enumerate(packets):
                await self._send_raw(packet)
                if (i + 1) % 100 == 0:
                    log.info("OTA progress: %d/%d packets (%.1f%%)",
                             i + 1, len(packets), (i + 1) / len(packets) * 100)

            # Wait for completion
            line = await asyncio.wait_for(self._line_queue.get(), timeout=REQUEST_TIMEOUT_S)
            parts = line.split(":")
            if len(parts) > 1 and parts[0].strip() == "0":
                log.info("OTA firmware update complete")
            elif "crc error" in line.lower():
                raise RuntimeError("OTA CRC validation failed")
            else:
                status = int(parts[0]) if parts[0].strip().isdigit() else -1
                if status & 0x8000:
                    raise RuntimeError(f"OTA failure (status: {status:#06x})")
                raise RuntimeError(f"Unexpected OTA response: {line}")

        finally:
            self._strict_write = old_strict

    # -- Notification Callbacks ---------------------------------------------

    def on_notify(self, callback):
        """Register a callback for device notifications: callback(ShellNotify, params)."""
        self._notify_callbacks.append(callback)

    # -- Internal Methods ---------------------------------------------------

    def _on_notification(self, _char: BleakGATTCharacteristic, data: bytearray):
        """BLE notification handler -- accumulates bytes into lines."""
        self._rx_buffer.extend(data)

        while True:
            idx = self._rx_buffer.find(b"\r\n")
            if idx == -1:
                break
            line = self._rx_buffer[:idx].decode("utf-8", errors="replace")
            self._rx_buffer = self._rx_buffer[idx + 2:]

            log.debug("RX: %s", line)

            if line.startswith("NOTIFY "):
                self._handle_device_notification(line)
            else:
                self._line_queue.put_nowait(line)

    def _handle_device_notification(self, line: str):
        """Parse and dispatch device-initiated notifications."""
        parts = line.split(" ")
        if len(parts) < 2:
            return

        event = parts[1].lower()
        notify_type = None

        if event == "disconnect":
            notify_type = ShellNotify.DISCONNECTED
        elif event == "shutdown":
            notify_type = ShellNotify.SHUTDOWN
        elif event == "low":
            notify_type = ShellNotify.LOW_BATTERY
        elif event == "error":
            notify_type = ShellNotify.HARDWARE_ERROR
        elif event == "noload":
            notify_type = ShellNotify.NO_LOAD
        elif event == "stop":
            notify_type = ShellNotify.STOPPED
        elif event == "strength" and len(parts) > 2:
            notify_type = ShellNotify.INTENSITY
            try:
                self.info.status.intensity = int(parts[2])
            except ValueError:
                pass
        elif event == "insufficient" and len(parts) > 2 and parts[2] == "space":
            notify_type = ShellNotify.FULL_SPACE

        if notify_type is not None:
            log.info("Device notification: %s", notify_type.name)
            for cb in self._notify_callbacks:
                try:
                    cb(notify_type, parts[2:] if len(parts) > 2 else [])
                except Exception as e:
                    log.error("Notification callback error: %s", e)

    async def _send_command(self, command: str):
        """Send a text command (auto-appends \\r\\n), split into MTU chunks."""
        data = (command + LINE_BREAK).encode("utf-8")
        await self._send_raw(data)

    async def _send_raw(self, data: bytes):
        """Send raw bytes, split into MTU-sized chunks."""
        if not self.client or not self._connected:
            raise RuntimeError("Not connected")

        for offset in range(0, len(data), MTU):
            chunk = data[offset:offset + MTU]
            response = self._strict_write
            await self.client.write_gatt_char(CHAR_UUID, chunk, response=response)
            if not self._strict_write:
                await asyncio.sleep(MIN_WRITE_INTERVAL_S)

    async def _execute(self, command: str, match_fn, timeout: float = REQUEST_TIMEOUT_S) -> str:
        """
        Send a command and wait for a matching response line.

        match_fn(line) -> bool: called for each received line until True.
        Returns the matching line.
        """
        # Drain any stale lines from previous commands
        while not self._line_queue.empty():
            try:
                self._line_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self._send_command(command)

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError(f"Command timed out: {command}")

            line = await asyncio.wait_for(self._line_queue.get(), timeout=remaining)

            if match_fn(line):
                return line
            # Non-matching lines are logged and discarded
            log.debug("Skipping non-matching response: %s", line)

    @staticmethod
    def _is_status_retval(line: str) -> bool:
        """Check if a line is a status return value (format: 'N:text')."""
        parts = line.split(":")
        if len(parts) > 1:
            try:
                int(parts[0])
                return True
            except ValueError:
                pass
        return False

    def _parse_version(self, line: str):
        """Parse version response: 'v.X.Y.Z' or 'ver=v.X.Y.Z'."""
        kv = line.split("=")
        if len(kv) == 1:
            parts = kv[0].split(".")
        else:
            parts = kv[1].split(".")

        if len(parts) >= 4:
            self.info.version_str = ".".join(parts)
            try:
                x, y, z = int(parts[1]), int(parts[2]), int(parts[3])
                self.info.version_num = (x * 1000 + y) * 10000 + z
            except (ValueError, IndexError):
                pass

        # Force strict write for old firmware
        if self.info.version_num < 20000000:
            self._strict_write = True
            log.warning("Old firmware (< v2.0.0), forcing strict write")

    def _parse_battery(self, line: str):
        """Parse battery response: 'NNNN mv' or '32769:...'."""
        parts = line.split(":")
        if len(parts) > 1 and parts[0].strip() == "32769":
            self.info.battery_mv = 5000
        else:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "mv":
                self.info.battery_mv = int(parts[0])

        # Map to 4-level indicator
        mv = self.info.battery_mv
        if self.info.is_v2:
            if mv <= 1025:
                self.info.battery_level = 1
            elif mv <= 2050:
                self.info.battery_level = 2
            elif mv <= 3075:
                self.info.battery_level = 3
            else:
                self.info.battery_level = 4
        else:
            if mv <= 3800:
                self.info.battery_level = 1
            elif mv <= 4400:
                self.info.battery_level = 2
            elif mv <= 4700:
                self.info.battery_level = 3
            else:
                self.info.battery_level = 4

    def _parse_status(self, line: str):
        """Parse status response: 'tick=X,str=X,dmd5=X,md5=X'."""
        for pair in line.split(","):
            kv = pair.split("=")
            if len(kv) != 2:
                continue
            key, val = kv[0].strip(), kv[1].strip()
            if key == "tick":
                self.info.status.tick = int(val)
            elif key == "str":
                self.info.status.intensity = int(val)
            elif key == "dmd5":
                self.info.status.default_md5 = val.upper()
            elif key in ("md5", "lmd5"):
                self.info.status.last_md5 = val.upper()


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def identify_device(name: str) -> str:
    """Identify a Bluetens device type from its advertising name."""
    if name is None:
        return "Unknown"
    lower = name.lower()
    if any(lower.startswith(p) for p in KNOWN_PREFIXES):
        if SPORT_NAMES.search(name):
            return "Bluetens Sport"
        return "Bluetens Classic"
    if CLASSIC_NAMES.search(name):
        return "Bluetens Classic"
    if SPORT_NAMES.search(name):
        return "Bluetens Sport"
    return "Unknown"


async def scan_devices(duration: float = 10.0) -> list[dict]:
    """
    Scan for Bluetens devices.

    Returns list of dicts: {address, name, rssi, product}
    """
    print(f"Scanning for Bluetens devices ({duration}s)...")
    devices = await BleakScanner.discover(
        timeout=duration,
        service_uuids=[SERVICE_UUID],
    )

    results = []
    for d in devices:
        product = identify_device(d.name)
        results.append({
            "address": d.address,
            "name": d.name or "(unknown)",
            "rssi": 99,
            "product": product,
        })

    return results


# ---------------------------------------------------------------------------
# Interactive Shell
# ---------------------------------------------------------------------------

async def interactive_shell(address: str):
    """Simple interactive shell for sending raw commands to the device."""
    async with BluetensDevice(address) as dev:
        info = await dev.connect()

        print(f"\nConnected to {address}")
        print(f"  Firmware: {info.version_str} (numeric: {info.version_num})")
        print(f"  Battery:  {info.battery_mv} mv (level {info.battery_level}/4)")
        print(f"  Status:   intensity={info.status.intensity}, tick={info.status.tick}")
        print(f"\nType shell commands (without '>' prefix) or use shortcuts:")
        print(f"  ver, bat, stat, str <N>, ssta <file>, osto, ls, shutdown, quit")
        print()

        def on_notify(notify_type, params):
            print(f"\n  [NOTIFY] {notify_type.name} {' '.join(params)}")

        dev.on_notify(on_notify)

        while True:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("bluetens> ")
                )
            except (EOFError, KeyboardInterrupt):
                print("\nDisconnecting...")
                break

            cmd = raw.strip()
            if not cmd:
                continue
            if cmd.lower() in ("quit", "exit", "q"):
                break

            # Handle shortcuts
            if cmd.lower() == "shutdown":
                await dev.shutdown()
                break
            elif cmd.lower() == "reset":
                await dev.reset()
                break

            # Send as shell command
            if not cmd.startswith(">"):
                cmd = f">{cmd}"

            try:
                await dev._send_command(cmd)
                # Collect response lines for 3 seconds
                while True:
                    try:
                        line = await asyncio.wait_for(dev._line_queue.get(), timeout=3.0)
                        print(f"  < {line}")
                    except asyncio.TimeoutError:
                        break
            except Exception as e:
                print(f"  Error: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def cmd_scan(args):
    results = await scan_devices(args.duration)
    if not results:
        print("No Bluetens devices found.")
        return

    print(f"\nFound {len(results)} device(s):\n")
    print(f"  {'Address':<20} {'Name':<20} {'RSSI':>6}  {'Product'}")
    print(f"  {'-'*20} {'-'*20} {'-'*6}  {'-'*20}")
    for r in results:
        print(f"  {r['address']:<20} {r['name']:<20} {r['rssi']:>4} dBm  {r['product']}")


async def cmd_connect(args):
    async with BluetensDevice(args.address) as dev:
        info = await dev.connect()
        print(f"\nDevice Information:")
        print(f"  Address:      {args.address}")
        print(f"  Firmware:     {info.version_str}")
        print(f"  Version (num): {info.version_num}")
        print(f"  Battery:      {info.battery_mv} mv (level {info.battery_level}/4)")
        print(f"  Intensity:    {info.status.intensity}")
        print(f"  Tick:         {info.status.tick}")
        print(f"  Default MD5:  {info.status.default_md5}")
        print(f"  Last MD5:     {info.status.last_md5}")


async def cmd_shell(args):
    await interactive_shell(args.address)


async def cmd_intensity(args):
    async with BluetensDevice(args.address) as dev:
        await dev.connect()
        actual = await dev.set_intensity(args.value)
        print(f"Intensity set to: {actual}")


async def cmd_start(args):
    async with BluetensDevice(args.address) as dev:
        await dev.connect()
        await dev.start_script(args.filename)
        print(f"Started script: {args.filename}")


async def cmd_stop(args):
    async with BluetensDevice(args.address) as dev:
        await dev.connect()
        await dev.stop()
        print("Stimulation stopped.")


async def cmd_generate(args):
    """Generate a script file from a pattern preset."""
    pattern = args.pattern

    if pattern == "freq-sweep":
        script = PatternGenerator.freq_sweep(
            start_hz=args.start, end_hz=args.end,
            duration_s=args.duration, steps=args.steps,
            impulse=args.impulse, log_scale=not args.linear,
            loop=args.loop,
        )
    elif pattern == "impulse-sweep":
        script = PatternGenerator.impulse_sweep(
            start_us=int(args.start), end_us=int(args.end),
            duration_s=args.duration, steps=args.steps,
            freq=args.freq, loop=args.loop,
        )
    elif pattern == "alternating":
        script = PatternGenerator.alternating(
            freq_a=args.start, freq_b=args.end,
            cycle_s=args.cycle, total_s=args.duration,
            loop=args.loop,
        )
    elif pattern == "burst":
        script = PatternGenerator.burst(
            freq=args.freq, on_s=args.on_time, off_s=args.off_time,
            n_bursts=args.bursts, impulse=args.impulse,
            loop=args.loop,
        )
    else:
        print(f"Unknown pattern: {pattern}", file=sys.stderr)
        sys.exit(1)

    content = script.serialize()
    size = len(script.content_bytes())
    est = script.time_est_ms() / 1000.0

    print(f"Pattern:   {pattern}")
    print(f"Duration:  {est:.1f}s (estimated)")
    print(f"Size:      {size} bytes")
    print(f"Token str: {content[:200]}{'...' if len(content) > 200 else ''}")

    if args.output:
        with open(args.output, "w") as f:
            f.write(content)
        print(f"Saved to:  {args.output}")

    if args.upload:
        name = args.name or "custom"
        async with BluetensDevice(args.upload) as dev:
            await dev.connect()
            await dev.upload_script(name, script)
            print(f"Uploaded as '{name}' to {args.upload}")
            if args.start_after:
                await dev.start_script(name)
                print(f"Script started. Use >str to control intensity.")


def main():
    parser = argparse.ArgumentParser(
        description="Bluetens TENS Unit BLE Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s scan                       Scan for nearby devices
  %(prog)s connect AA:BB:CC:DD:EE:FF  Connect and show device info
  %(prog)s shell AA:BB:CC:DD:EE:FF    Interactive command shell
  %(prog)s intensity AA:BB:CC:DD:EE:FF 20   Set intensity to 20
  %(prog)s start AA:BB:CC:DD:EE:FF MyProg   Start a script file
  %(prog)s stop AA:BB:CC:DD:EE:FF          Stop stimulation
"""
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = sub.add_parser("scan", help="Scan for Bluetens devices")
    p_scan.add_argument("-d", "--duration", type=float, default=10.0,
                        help="Scan duration in seconds (default: 10)")
    p_scan.set_defaults(func=cmd_scan)

    # connect
    p_conn = sub.add_parser("connect", help="Connect and show device info")
    p_conn.add_argument("address", help="BLE device address")
    p_conn.set_defaults(func=cmd_connect)

    # shell
    p_shell = sub.add_parser("shell", help="Interactive command shell")
    p_shell.add_argument("address", help="BLE device address")
    p_shell.set_defaults(func=cmd_shell)

    # intensity
    p_int = sub.add_parser("intensity", help="Set stimulation intensity")
    p_int.add_argument("address", help="BLE device address")
    p_int.add_argument("value", type=int, help="Intensity (1-60)")
    p_int.set_defaults(func=cmd_intensity)

    # start
    p_start = sub.add_parser("start", help="Start a script file")
    p_start.add_argument("address", help="BLE device address")
    p_start.add_argument("filename", help="Script filename on device")
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = sub.add_parser("stop", help="Stop stimulation")
    p_stop.add_argument("address", help="BLE device address")
    p_stop.set_defaults(func=cmd_stop)

    # generate
    p_gen = sub.add_parser("generate", help="Generate a pre-baked stimulation script",
                           formatter_class=argparse.RawDescriptionHelpFormatter,
                           epilog="""\
Patterns:
  freq-sweep      Sweep frequency over time (log scale by default)
  impulse-sweep   Sweep pulse width over time
  alternating     Alternate between two frequencies on a fixed cycle
  burst           On/off burst mode

Examples:
  %(prog)s freq-sweep --start 2 --end 150 --duration 60 -o sweep.txt
  %(prog)s burst --freq 80 --on 5 --off 3 --bursts 10 -o burst.txt
  %(prog)s freq-sweep --start 2 --end 100 -d 30 --upload AA:BB:CC:DD:EE:FF --start-after
""")
    p_gen.add_argument("pattern", choices=["freq-sweep", "impulse-sweep", "alternating", "burst"])
    p_gen.add_argument("--start", type=float, default=2.0, help="Start value (Hz or us)")
    p_gen.add_argument("--end", type=float, default=100.0, help="End value (Hz or us)")
    p_gen.add_argument("-d", "--duration", type=float, default=30.0, help="Duration in seconds")
    p_gen.add_argument("--steps", type=int, default=50, help="Number of discrete steps")
    p_gen.add_argument("--freq", type=float, default=DEF_FREQ, help="Frequency for impulse-sweep/burst")
    p_gen.add_argument("--impulse", type=int, default=DEF_IMPULSE, help="Pulse width in us")
    p_gen.add_argument("--cycle", type=float, default=2.0, help="Cycle time for alternating (seconds)")
    p_gen.add_argument("--on", dest="on_time", type=float, default=5.0, help="Burst on time (seconds)")
    p_gen.add_argument("--off", dest="off_time", type=float, default=3.0, help="Burst off time (seconds)")
    p_gen.add_argument("--bursts", type=int, default=10, help="Number of bursts")
    p_gen.add_argument("--linear", action="store_true", help="Use linear scale (default: log)")
    p_gen.add_argument("--loop", action="store_true", help="Loop the pattern indefinitely")
    p_gen.add_argument("-o", "--output", help="Save script token string to file")
    p_gen.add_argument("--upload", metavar="ADDRESS", help="Upload to device at this BLE address")
    p_gen.add_argument("--name", default="custom", help="Filename on device (default: custom)")
    p_gen.add_argument("--start-after", action="store_true", help="Start script after upload")
    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
