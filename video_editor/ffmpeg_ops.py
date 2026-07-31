"""ffprobe/ffmpeg wrappers: media probing and the export/render pipeline.

Functionally identical to the original single-file script - only split out
into its own module. `build_cmd` and `run_job` are unchanged in behavior:
same quality/target-size/volume/mute/preset handling, same single-segment
fast path, same concat filter-graph construction for multi-clip timelines.
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from pathlib import Path

from . import state


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:400])
    d = json.loads(r.stdout)
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration": float(d.get("format", {}).get("duration", 0)),
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def build_cmd(sources: list, dst: Path, settings: dict) -> list[str]:
    """
    sources: [{fileId, path, meta: {duration, width, height, has_audio},
               segments: [{start, end}]}]
    Segments are sorted and used as-is; empty list = full clip.
    """
    quality = max(1, min(100, int(settings.get("quality", 70))))
    target_mb = float(settings["targetMb"]) if settings.get("targetMb") else None
    volume = float(settings.get("volume", 100))
    muted = bool(settings.get("muted", False))
    preset = settings.get("preset", "veryfast")

    any_audio = any(s["meta"].get("has_audio", True) for s in sources)
    if not any_audio:
        muted = True

    all_segs = []
    for i, src in enumerate(sources):
        segs = src.get("segments") or []
        if not segs:
            segs = [{"start": 0, "end": float(src["meta"]["duration"])}]
        for seg in segs:
            all_segs.append({"inp": i, "start": float(seg["start"]), "end": float(seg["end"])})

    eff = sum(s["end"] - s["start"] for s in all_segs)
    eff = max(eff, 0.1)

    crf = max(18, min(40, round(40 - quality * 22 / 100)))

    if target_mb:
        bits = float(target_mb) * 8 * 1024 * 1024
        abits = 0 if muted else 96000 * eff
        vbps = max(int((bits - abits) / eff), 50_000)
        enc = ["-c:v", "libx264", "-preset", preset,
               "-b:v", str(vbps), "-maxrate", str(int(vbps * 1.5)), "-bufsize", str(vbps * 2)]
    else:
        enc = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]

    vol_f = f"volume={volume / 100:.4f}" if (not muted and abs(volume - 100) > 0.5) else None

    cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats"]
    for src in sources:
        cmd += ["-i", src["path"]]

    tw = sources[0]["meta"].get("width") or 1280
    th = sources[0]["meta"].get("height") or 720
    tw += tw % 2
    th += th % 2
    multi_res = any(
        (s["meta"].get("width") or tw) != tw or (s["meta"].get("height") or th) != th
        for s in sources[1:]
    )
    scale_f = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1"

    n = len(all_segs)
    fp = []
    for idx, seg in enumerate(all_segs):
        inp = seg["inp"]
        s, e = seg["start"], seg["end"]
        v_trim = f"[{inp}:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS"
        if multi_res or len(sources) > 1:
            v_trim += f",{scale_f}"
        fp.append(f"{v_trim}[v{idx}]")
        if not muted:
            fp.append(f"[{inp}:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{idx}]")

    if n == 1 and not multi_res:
        fp.clear()
        seg = all_segs[0]
        inp, s, e = seg["inp"], seg["start"], seg["end"]
        cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats",
               "-ss", str(s), "-to", str(e), "-i", sources[inp]["path"]] + enc
        if muted:
            cmd += ["-an"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "96k"]
            if vol_f:
                cmd += ["-af", vol_f]
    else:
        if muted:
            vin = "".join(f"[v{i}]" for i in range(n))
            fp.append(f"{vin}concat=n={n}:v=1:a=0[vout]")
            cmd += ["-filter_complex", ";".join(fp), "-map", "[vout]"] + enc + ["-an"]
        else:
            via = "".join(f"[v{i}][a{i}]" for i in range(n))
            if vol_f:
                fp.append(f"{via}concat=n={n}:v=1:a=1[vout][ac];[ac]{vol_f}[aout]")
            else:
                fp.append(f"{via}concat=n={n}:v=1:a=1[vout][aout]")
            cmd += ["-filter_complex", ";".join(fp),
                    "-map", "[vout]", "-map", "[aout]"] + enc + ["-c:a", "aac", "-b:a", "96k"]

    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def run_job(job_id: str, sources: list, dst: Path, settings: dict) -> None:
    """Runs one ffmpeg export in the calling thread, streaming progress into
    state.JOBS[job_id] as it goes. Meant to be called via
    `threading.Thread(target=run_job, ...)` - see server.py's /process handler."""
    with state.LOCK:
        state.JOBS[job_id] = {"status": "processing", "progress": 0.0,
                               "error": None, "output_id": None, "size": 0}
    try:
        cmd = build_cmd(sources, dst, settings)
        print(f"  ffmpeg [{' '.join(cmd[6:9])}...]")
        total_dur = sum(
            sum(s["end"] - s["start"] for s in (src.get("segments") or [{"start": 0, "end": src["meta"]["duration"]}]))
            for src in sources
        )
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=lambda: [_ for _ in proc.stderr], daemon=True).start()
        for raw in proc.stdout:
            k, _, v = raw.decode(errors="replace").strip().partition("=")
            if k == "out_time_ms" and v.lstrip("-").isdigit():
                pct = min(max(int(v), 0) / 1000 / max(total_dur, 0.1), 0.99)
                with state.LOCK:
                    state.JOBS[job_id]["progress"] = pct
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg exit {proc.returncode}")
        out_id = uuid.uuid4().hex
        sz = dst.stat().st_size
        with state.LOCK:
            state.FILES[out_id] = {"path": str(dst), "name": dst.name,
                                    "duration": total_dur, "size": sz,
                                    "has_audio": not settings.get("muted")}
            state.JOBS[job_id].update({"status": "done", "progress": 1.0, "output_id": out_id, "size": sz})
        print(f"  done: {sz // 1024} KB")
    except Exception as exc:
        print(f"  job error: {exc}")
        with state.LOCK:
            state.JOBS[job_id].update({"status": "error", "error": str(exc)})
