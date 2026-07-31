"""Project persistence: JSON project files + a copied-media store under
`projects_dir`, unchanged in behavior from the original script.

Every function here takes `projects_dir` explicitly (instead of reading a
module-level global) so the storage location is just a plain constructor
argument wired once in __main__.py / server.py, rather than hidden global
mutable state.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from . import state


def list_projects(projects_dir: Path) -> list:
    projects = []
    for f in sorted(projects_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            projects.append({
                "projectId": data["id"],
                "name": data["name"],
                "created": data["created"],
                "updated": data["updated"],
                "clipCount": len(data.get("clips", []))
            })
        except Exception:
            pass
    return projects


def save_project(projects_dir: Path, req: dict) -> dict:
    project_id = req.get("projectId") or uuid.uuid4().hex
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    files_dir = projects_dir / "files"
    files_dir.mkdir(exist_ok=True)
    clips = []
    for cl in req.get("clips", []):
        fid = cl["fileId"]
        with state.LOCK:
            f = state.FILES.get(fid)
        if not f:
            continue
        src = Path(f["path"])
        ext = src.suffix
        dst = files_dir / f"{fid}{ext}"
        if not dst.exists():
            shutil.copy2(src, dst)
        clips.append({
            "fileId": fid,
            "name": cl.get("name", f["name"]),
            "dur": cl.get("dur", f["duration"]),
            "hasAudio": cl.get("hasAudio", f.get("has_audio", True)),
            "width": cl.get("width", f.get("width", 0)),
            "height": cl.get("height", f.get("height", 0)),
            "size": cl.get("size", f.get("size", 0)),
            "segs": cl.get("segs", []),
            "ext": ext,
        })
    existing_path = projects_dir / f"{project_id}.json"
    created = now
    if existing_path.exists():
        try:
            created = json.loads(existing_path.read_text()).get("created", now)
        except Exception:
            pass
    project = {
        "id": project_id,
        "name": req.get("name", "Untitled"),
        "created": created,
        "updated": now,
        "clips": clips,
        "settings": req.get("settings", {})
    }
    existing_path.write_text(json.dumps(project, indent=2))
    return {"projectId": project_id, "name": project["name"],
            "created": created, "updated": now}


def load_project(projects_dir: Path, project_id: str, work_dir: Path) -> dict:
    """`work_dir` is where source clips get re-copied to on load, so /preview
    and /process can reach them again the way freshly-uploaded files would -
    same scratch dir the server keeps for the whole process lifetime."""
    path = projects_dir / f"{project_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Project {project_id} not found")
    data = json.loads(path.read_text())
    files_dir = projects_dir / "files"
    restored = []
    for cl in data.get("clips", []):
        fid = cl["fileId"]
        ext = cl.get("ext", ".mp4")
        src = files_dir / f"{fid}{ext}"
        if not src.exists():
            continue
        with state.LOCK:
            if fid not in state.FILES:
                dst = work_dir / f"{fid}{ext}"
                if not dst.exists():
                    shutil.copy2(src, dst)
                state.FILES[fid] = {
                    "path": str(dst),
                    "name": cl["name"],
                    "duration": cl["dur"],
                    "size": cl.get("size", src.stat().st_size),
                    "has_audio": cl.get("hasAudio", True),
                    "width": cl.get("width", 0),
                    "height": cl.get("height", 0),
                }
        restored.append({
            "fileId": fid,
            "name": cl["name"],
            "dur": cl["dur"],
            "hasAudio": cl.get("hasAudio", True),
            "width": cl.get("width", 0),
            "height": cl.get("height", 0),
            "size": cl.get("size", 0),
            "segs": cl.get("segs", [])
        })
    return {
        "projectId": data["id"],
        "name": data["name"],
        "created": data["created"],
        "updated": data["updated"],
        "clips": restored,
        "settings": data.get("settings", {})
    }


def delete_project(projects_dir: Path, project_id: str) -> None:
    path = projects_dir / f"{project_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Project {project_id} not found")
    data = json.loads(path.read_text())
    path.unlink()
    # Remove files only if no other project still references them
    files_dir = projects_dir / "files"
    referenced: set = set()
    for pf in projects_dir.glob("*.json"):
        try:
            for cl in json.loads(pf.read_text()).get("clips", []):
                referenced.add(cl["fileId"] + cl.get("ext", ".mp4"))
        except Exception:
            pass
    for cl in data.get("clips", []):
        fname = cl["fileId"] + cl.get("ext", ".mp4")
        if fname not in referenced:
            fp = files_dir / fname
            if fp.exists():
                fp.unlink(missing_ok=True)
