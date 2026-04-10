"""Script building, upload, and preset endpoints."""

from __future__ import annotations

import math

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scripts.bluetens_control import (
    DEF_CLUSTER,
    DEF_FREQ,
    DEF_IMPULSE,
    MIN_IMPULSE,
    PatternGenerator,
    ScriptBlock,
    ScriptFile,
    ScriptSection,
)

router = APIRouter()


class BlockModel(BaseModel):
    frequency: float = 100.0
    impulse: int = 200
    cluster: int = 1
    repeat: int = 1
    interval: int = 0


class SectionModel(BaseModel):
    blocks: list[BlockModel]
    repeat: int = 1
    interval: int = 0


class ScriptModel(BaseModel):
    name: str
    sections: list[SectionModel]
    loop_indices: list[int] = []


class UploadRequest(BaseModel):
    script: ScriptModel
    start: bool = False


def _build_script(model: ScriptModel) -> ScriptFile:
    sf = ScriptFile()
    for sec_m in model.sections:
        sec = ScriptSection()
        sec.repeat = sec_m.repeat
        sec.interval = sec_m.interval
        for blk_m in sec_m.blocks:
            blk = ScriptBlock()
            blk.freq = blk_m.frequency
            blk.impulse = blk_m.impulse
            blk.cluster = blk_m.cluster
            blk.repeat = blk_m.repeat
            blk.interval = blk_m.interval
            sec.blocks.append(blk)
        sf.sections.append(sec)
    sf.loop_indices = model.loop_indices
    return sf


@router.post("/preview")
async def preview_script(model: ScriptModel):
    sf = _build_script(model)
    raw = sf.serialize()
    return {"raw": raw, "byte_size": len(raw)}


@router.post("/upload")
async def upload_script(req: UploadRequest, request: Request):
    dm = request.app.state.dm
    sf = _build_script(req.script)
    if req.start:
        await dm.upload_and_start(req.script.name, sf)
    else:
        await dm.upload_script(req.script.name, sf)
    return {"ok": True, "filename": req.script.name}


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS = [
    {"id": "freq_sweep",    "name": "Frequency Sweep",       "desc": "Smoothly sweep frequency from start to end over time."},
    {"id": "impulse_sweep", "name": "Impulse Sweep",         "desc": "Sweep pulse width (impulse) from start to end over time."},
    {"id": "alternating",   "name": "Alternating",           "desc": "Alternate between two frequency/impulse settings on a cycle."},
    {"id": "burst",         "name": "Burst",                 "desc": "Stimulation bursts with rest periods between."},
    {"id": "multi_phase",   "name": "Multi-Phase (3-phase)", "desc": "Three-phase program: warmup, main treatment, cooldown."},
    {"id": "beat_freq",     "name": "Beat Frequency",        "desc": "Two close frequencies alternating rapidly to create a pulsing beat sensation."},
    {"id": "ems",           "name": "Strength Training (EMS)","desc": "Muscle stimulation: warmup ramp, work bursts with rest, cooldown ramp."},
    {"id": "pain_gate",     "name": "Pain Gate TENS",        "desc": "Continuous high-frequency TENS to block pain signals (gate control theory)."},
    {"id": "endorphin",     "name": "Endorphin Release",     "desc": "Low-frequency burst TENS to trigger natural endorphin release."},
    {"id": "anti_habit",    "name": "Anti-Habituation",      "desc": "Varying frequency pattern that prevents neural accommodation."},
]

PRESET_DEFAULTS: dict[str, dict] = {
    "freq_sweep": {
        "start_hz": 2, "end_hz": 100, "duration_s": 30,
        "steps": 50, "impulse": DEF_IMPULSE,
    },
    "impulse_sweep": {
        "start_us": 20, "end_us": 300, "duration_s": 30,
        "steps": 50, "freq": DEF_FREQ,
    },
    "alternating": {
        "freq_a": 5, "freq_b": 100, "cycle_s": 2,
        "total_s": 60, "impulse": DEF_IMPULSE,
    },
    "burst": {
        "freq": DEF_FREQ, "on_s": 5, "off_s": 3,
        "n_bursts": 10, "impulse": DEF_IMPULSE,
    },
    "multi_phase": {
        "warmup_freq": 5, "warmup_impulse": 100, "warmup_dur": 60,
        "main_freq": 100, "main_impulse": 200, "main_dur": 600,
        "cooldown_freq": 5, "cooldown_impulse": 100, "cooldown_dur": 60,
    },
    "beat_freq": {
        "base_freq": 100, "beat_hz": 4, "duration_s": 60,
        "impulse": 200,
    },
    "ems": {
        "work_freq": 35, "impulse": 200,
        "warmup_dur": 60, "on_s": 5, "off_s": 5,
        "n_bursts": 10, "cooldown_dur": 60,
    },
    "pain_gate": {
        "freq": 100, "impulse": 200, "duration_s": 1200,
    },
    "endorphin": {
        "freq": 2, "impulse": 300, "on_s": 3, "off_s": 3,
        "n_bursts": 100,
    },
    "anti_habit": {
        "center_freq": 50, "freq_range": 40,
        "impulse": 200, "duration_s": 120, "steps": 60,
    },
}

PRESET_FIELDS: dict[str, list[dict]] = {
    "freq_sweep": [
        {"key": "start_hz",   "label": "Start Hz",       "hint": "0.1-1200"},
        {"key": "end_hz",     "label": "End Hz",         "hint": "0.1-1200"},
        {"key": "duration_s", "label": "Duration (s)",   "hint": "seconds"},
        {"key": "steps",      "label": "Steps",          "hint": "10-200"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "20-400"},
    ],
    "impulse_sweep": [
        {"key": "start_us",   "label": "Start us",       "hint": "20-400"},
        {"key": "end_us",     "label": "End us",         "hint": "20-400"},
        {"key": "duration_s", "label": "Duration (s)",   "hint": "seconds"},
        {"key": "steps",      "label": "Steps",          "hint": "10-200"},
        {"key": "freq",       "label": "Freq (Hz)",      "hint": "0.1-1200"},
    ],
    "alternating": [
        {"key": "freq_a",     "label": "Freq A (Hz)",    "hint": "0.1-1200"},
        {"key": "freq_b",     "label": "Freq B (Hz)",    "hint": "0.1-1200"},
        {"key": "cycle_s",    "label": "Cycle (s)",      "hint": "seconds per cycle"},
        {"key": "total_s",    "label": "Total (s)",      "hint": "total seconds"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "20-400"},
    ],
    "burst": [
        {"key": "freq",       "label": "Freq (Hz)",      "hint": "0.1-1200"},
        {"key": "on_s",       "label": "On time (s)",    "hint": "seconds"},
        {"key": "off_s",      "label": "Off time (s)",   "hint": "seconds"},
        {"key": "n_bursts",   "label": "Bursts",         "hint": "number of bursts"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "20-400"},
    ],
    "multi_phase": [
        {"key": "warmup_freq",    "label": "Warmup freq",     "hint": "Hz"},
        {"key": "warmup_impulse", "label": "Warmup impulse",  "hint": "us"},
        {"key": "warmup_dur",     "label": "Warmup dur (s)",  "hint": "seconds"},
        {"key": "main_freq",      "label": "Main freq",       "hint": "Hz"},
        {"key": "main_impulse",   "label": "Main impulse",    "hint": "us"},
        {"key": "main_dur",       "label": "Main dur (s)",    "hint": "seconds"},
        {"key": "cooldown_freq",  "label": "Cool freq",       "hint": "Hz"},
        {"key": "cooldown_impulse","label": "Cool impulse",   "hint": "us"},
        {"key": "cooldown_dur",   "label": "Cool dur (s)",    "hint": "seconds"},
    ],
    "beat_freq": [
        {"key": "base_freq",  "label": "Base freq (Hz)", "hint": "carrier, e.g. 100"},
        {"key": "beat_hz",    "label": "Beat freq (Hz)", "hint": "modulation, 1-20"},
        {"key": "duration_s", "label": "Duration (s)",   "hint": "seconds"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "20-400"},
    ],
    "ems": [
        {"key": "work_freq",  "label": "Work freq (Hz)", "hint": "30-50 typical"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "150-300"},
        {"key": "warmup_dur", "label": "Warmup (s)",     "hint": "ramp-up seconds"},
        {"key": "on_s",       "label": "On time (s)",    "hint": "contraction"},
        {"key": "off_s",      "label": "Off time (s)",   "hint": "rest"},
        {"key": "n_bursts",   "label": "Bursts",         "hint": "work cycles"},
        {"key": "cooldown_dur","label": "Cooldown (s)",  "hint": "ramp-down seconds"},
    ],
    "pain_gate": [
        {"key": "freq",       "label": "Freq (Hz)",      "hint": "80-120 typical"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "100-250"},
        {"key": "duration_s", "label": "Duration (s)",   "hint": "1200 = 20min"},
    ],
    "endorphin": [
        {"key": "freq",       "label": "Freq (Hz)",      "hint": "2-4 typical"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "200-400"},
        {"key": "on_s",       "label": "On time (s)",    "hint": "stim burst"},
        {"key": "off_s",      "label": "Off time (s)",   "hint": "rest"},
        {"key": "n_bursts",   "label": "Bursts",         "hint": "total cycles"},
    ],
    "anti_habit": [
        {"key": "center_freq","label": "Center freq (Hz)","hint": "mid-point"},
        {"key": "freq_range", "label": "Range (Hz)",     "hint": "variation +/-"},
        {"key": "impulse",    "label": "Impulse (us)",   "hint": "20-400"},
        {"key": "duration_s", "label": "Duration (s)",   "hint": "seconds"},
        {"key": "steps",      "label": "Steps",          "hint": "frequency changes"},
    ],
}


class PresetRequest(BaseModel):
    preset: str
    params: dict = {}


def _script_to_json(sf: ScriptFile) -> dict:
    """Convert a ScriptFile to the JSON format used by the builder store."""
    sections = []
    for sec in sf.sections:
        blocks = []
        for blk in sec.blocks:
            blocks.append({
                "frequency": blk.freq,
                "impulse": blk.impulse,
                "cluster": blk.cluster,
                "repeat": blk.repeat,
                "interval": blk.interval,
            })
        sections.append({
            "blocks": blocks,
            "repeat": sec.repeat,
            "interval": sec.interval,
        })
    return {"sections": sections, "loop_indices": sf.loop_indices}


def _generate_preset(preset: str, p: dict) -> ScriptFile:
    """Generate a ScriptFile from a preset name and parameters."""
    if preset == "freq_sweep":
        return PatternGenerator.freq_sweep(
            start_hz=float(p.get("start_hz", 2)),
            end_hz=float(p.get("end_hz", 100)),
            duration_s=float(p.get("duration_s", 30)),
            steps=int(float(p.get("steps", 50))),
            impulse=int(float(p.get("impulse", DEF_IMPULSE))),
        )
    elif preset == "impulse_sweep":
        return PatternGenerator.impulse_sweep(
            start_us=int(float(p.get("start_us", 20))),
            end_us=int(float(p.get("end_us", 300))),
            duration_s=float(p.get("duration_s", 30)),
            steps=int(float(p.get("steps", 50))),
            freq=float(p.get("freq", DEF_FREQ)),
        )
    elif preset == "alternating":
        imp = int(float(p.get("impulse", DEF_IMPULSE)))
        return PatternGenerator.alternating(
            freq_a=float(p.get("freq_a", 5)),
            freq_b=float(p.get("freq_b", 100)),
            cycle_s=float(p.get("cycle_s", 2)),
            total_s=float(p.get("total_s", 60)),
            impulse_a=imp, impulse_b=imp,
        )
    elif preset == "burst":
        return PatternGenerator.burst(
            freq=float(p.get("freq", DEF_FREQ)),
            on_s=float(p.get("on_s", 5)),
            off_s=float(p.get("off_s", 3)),
            n_bursts=int(float(p.get("n_bursts", 10))),
            impulse=int(float(p.get("impulse", DEF_IMPULSE))),
        )
    elif preset == "multi_phase":
        phases = [
            {"freq": float(p.get("warmup_freq", 5)),
             "impulse": int(float(p.get("warmup_impulse", 100))),
             "duration_s": float(p.get("warmup_dur", 60))},
            {"freq": float(p.get("main_freq", 100)),
             "impulse": int(float(p.get("main_impulse", 200))),
             "duration_s": float(p.get("main_dur", 600))},
            {"freq": float(p.get("cooldown_freq", 5)),
             "impulse": int(float(p.get("cooldown_impulse", 100))),
             "duration_s": float(p.get("cooldown_dur", 60))},
        ]
        return PatternGenerator.multi_phase(phases)
    elif preset == "beat_freq":
        base = float(p.get("base_freq", 100))
        beat = float(p.get("beat_hz", 4))
        dur = float(p.get("duration_s", 60))
        imp = int(float(p.get("impulse", 200)))
        cycle_s = 1.0 / max(0.5, beat)
        return PatternGenerator.alternating(
            freq_a=base, freq_b=base + beat,
            cycle_s=cycle_s, total_s=dur,
            impulse_a=imp, impulse_b=imp,
        )
    elif preset == "ems":
        work_freq = float(p.get("work_freq", 35))
        imp = int(float(p.get("impulse", 200)))
        warmup_s = float(p.get("warmup_dur", 60))
        on_s = float(p.get("on_s", 5))
        off_s = float(p.get("off_s", 5))
        n_bursts = int(float(p.get("n_bursts", 10)))
        cooldown_s = float(p.get("cooldown_dur", 60))
        imp_c = PatternGenerator._clamp_impulse(imp)

        sf = ScriptFile()
        ramp_steps = 8

        warmup = ScriptSection()
        for i in range(ramp_steps):
            t = i / max(1, ramp_steps - 1)
            freq = PatternGenerator._clamp_freq(
                PatternGenerator._log_lerp(5.0, work_freq, t)
            )
            rep = PatternGenerator._calc_repeat(
                freq, DEF_CLUSTER, 0, warmup_s * 1000 / ramp_steps
            )
            warmup.add_block(ScriptBlock(freq=freq, impulse=imp_c, repeat=rep))
        sf.add_section(warmup)

        work = ScriptSection(repeat=n_bursts)
        on_rep = PatternGenerator._calc_repeat(
            work_freq, DEF_CLUSTER, 0, on_s * 1000
        )
        work.add_block(ScriptBlock(freq=work_freq, impulse=imp_c, repeat=on_rep))
        off_ms = max(0, round(off_s * 1000 - 1000))
        work.add_block(ScriptBlock(
            freq=1.0, impulse=MIN_IMPULSE, cluster=1,
            interval=off_ms, repeat=1,
        ))
        sf.add_section(work)

        cooldown = ScriptSection()
        for i in range(ramp_steps):
            t = i / max(1, ramp_steps - 1)
            freq = PatternGenerator._clamp_freq(
                PatternGenerator._log_lerp(work_freq, 5.0, t)
            )
            rep = PatternGenerator._calc_repeat(
                freq, DEF_CLUSTER, 0, cooldown_s * 1000 / ramp_steps
            )
            cooldown.add_block(ScriptBlock(freq=freq, impulse=imp_c, repeat=rep))
        sf.add_section(cooldown)
        return sf

    elif preset == "pain_gate":
        freq = float(p.get("freq", 100))
        imp = int(float(p.get("impulse", 200)))
        dur = float(p.get("duration_s", 1200))
        sf = ScriptFile()
        section = ScriptSection()
        rep = PatternGenerator._calc_repeat(freq, DEF_CLUSTER, 0, dur * 1000)
        section.add_block(ScriptBlock(
            freq=PatternGenerator._clamp_freq(freq),
            impulse=PatternGenerator._clamp_impulse(imp),
            repeat=rep,
        ))
        sf.add_section(section)
        sf.add_loop(0)
        return sf

    elif preset == "endorphin":
        return PatternGenerator.burst(
            freq=float(p.get("freq", 2)),
            on_s=float(p.get("on_s", 3)),
            off_s=float(p.get("off_s", 3)),
            n_bursts=int(float(p.get("n_bursts", 100))),
            impulse=int(float(p.get("impulse", 300))),
        )

    elif preset == "anti_habit":
        center = float(p.get("center_freq", 50))
        frange = float(p.get("freq_range", 40))
        imp = int(float(p.get("impulse", 200)))
        dur = float(p.get("duration_s", 120))
        steps = int(float(p.get("steps", 60)))

        sf = ScriptFile()
        section = ScriptSection()
        step_ms = dur * 1000.0 / steps

        for i in range(steps):
            t = i / max(1, steps - 1)
            mod = (
                math.sin(2 * math.pi * 3.0 * t)
                + 0.5 * math.sin(2 * math.pi * 7.0 * t)
                + 0.3 * math.sin(2 * math.pi * 13.0 * t)
            ) / 1.8
            freq = PatternGenerator._clamp_freq(center + mod * frange)
            rep = PatternGenerator._calc_repeat(freq, DEF_CLUSTER, 0, step_ms)
            section.add_block(ScriptBlock(
                freq=freq,
                impulse=PatternGenerator._clamp_impulse(imp),
                repeat=rep,
            ))
        sf.add_section(section)
        sf.add_loop(0)
        return sf

    raise ValueError(f"Unknown preset: {preset}")


# ---------------------------------------------------------------------------
# Funscript converter
# ---------------------------------------------------------------------------

class FunscriptRequest(BaseModel):
    actions: list[dict]
    freq_low: float = 2.0       # freq at max intensity (high speed)
    freq_high: float = 150.0    # freq at min intensity (low speed)
    impulse_low: int = 50       # impulse at min intensity
    impulse_high: int = 300     # impulse at max intensity


def _convert_funscript(req: FunscriptRequest) -> ScriptFile:
    """Convert funscript actions to a ScriptFile.

    Intensity is derived from the speed of position changes.
    High speed → low frequency + high impulse (strong).
    Low speed  → high frequency + low impulse (gentle).
    """
    actions = sorted(req.actions, key=lambda a: a.get("at", 0))
    if len(actions) < 2:
        raise ValueError("Funscript needs at least 2 actions")

    # Build segments with speed
    segments: list[dict] = []
    for i in range(len(actions) - 1):
        t0 = float(actions[i].get("at", 0))
        t1 = float(actions[i + 1].get("at", 0))
        dt = t1 - t0
        if dt <= 0:
            continue
        dp = abs(float(actions[i + 1].get("pos", 0)) - float(actions[i].get("pos", 0)))
        segments.append({"duration_ms": dt, "speed": dp / dt})

    if not segments:
        raise ValueError("No valid segments in funscript")

    max_speed = max(s["speed"] for s in segments) or 1.0

    freq_lo = PatternGenerator._clamp_freq(req.freq_low)
    freq_hi = PatternGenerator._clamp_freq(req.freq_high)
    imp_lo = PatternGenerator._clamp_impulse(req.impulse_low)
    imp_hi = PatternGenerator._clamp_impulse(req.impulse_high)

    sf = ScriptFile()
    section = ScriptSection()
    prev_freq = None
    prev_imp = None
    prev_blk: ScriptBlock | None = None

    for seg in segments:
        t = seg["speed"] / max_speed  # 0 = calm, 1 = max intensity

        # High intensity → low freq, high impulse
        freq = freq_hi + (freq_lo - freq_hi) * t
        impulse = imp_lo + (imp_hi - imp_lo) * t

        # Quantize for merging (0.5 Hz steps, 5 us steps)
        freq = PatternGenerator._clamp_freq(round(freq * 2) / 2)
        impulse = PatternGenerator._clamp_impulse(round(impulse / 5) * 5)

        rep = PatternGenerator._calc_repeat(freq, DEF_CLUSTER, 0, seg["duration_ms"])

        if freq == prev_freq and impulse == prev_imp and prev_blk is not None:
            prev_blk.repeat += rep
        else:
            blk = ScriptBlock(freq=freq, impulse=impulse, repeat=rep)
            section.add_block(blk)
            prev_blk = blk
            prev_freq = freq
            prev_imp = impulse

    sf.add_section(section)
    return sf


@router.post("/funscript")
async def convert_funscript(req: FunscriptRequest):
    try:
        sf = _convert_funscript(req)
        result = _script_to_json(sf)
        n_blocks = sum(len(s["blocks"]) for s in result["sections"])
        result["block_count"] = n_blocks
        return result
    except (ValueError, TypeError, KeyError) as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/presets")
async def list_presets():
    return {
        "presets": PRESETS,
        "defaults": PRESET_DEFAULTS,
        "fields": PRESET_FIELDS,
    }


@router.post("/preset")
async def generate_preset(req: PresetRequest):
    try:
        merged = {**PRESET_DEFAULTS.get(req.preset, {}), **req.params}
        sf = _generate_preset(req.preset, merged)
        result = _script_to_json(sf)
        return result
    except (ValueError, TypeError, KeyError) as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
