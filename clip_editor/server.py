"""HTTP handler + server: routing, Range-request preview streaming, SSE
progress, and the multipart /upload-temp parser. Functionally identical to
the original script's Handler/Server classes - the only real behavior
change is `_push` now calling through a pluggable `backends.UploadBackend`
instead of always doing a hardcoded VPS multipart POST.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

from . import ffmpeg_ops, projects, state
from .backends import BackendError, UploadBackend
from .ui import PAGE


def _parse_multipart(body: bytes, content_type: str) -> tuple[bytes, str, str]:
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        raise ValueError("No boundary in Content-Type")
    boundary = m.group(1).strip('"').encode()
    for part in body.split(b"--" + boundary)[1:]:
        if not part.rstrip(b"\r\n-"):
            continue
        sep = part.find(b"\r\n\r\n")
        if sep == -1:
            continue
        headers_raw = part[:sep].lstrip(b"\r\n")
        data = part[sep + 4:]
        if data.endswith(b"\r\n"):
            data = data[:-2]
        if not data:
            continue
        headers = {}
        for line in headers_raw.split(b"\r\n"):
            if b":" in line:
                k, _, v = line.partition(b":")
                headers[k.strip().lower().decode(errors="replace")] = v.strip().decode(errors="replace")
        cd = headers.get("content-disposition", "")
        ct = headers.get("content-type", "video/mp4")
        fn = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', cd)
        return data, (fn.group(1).strip() if fn else "upload.mp4"), ct
    raise ValueError("No file part found")


class Handler(BaseHTTPRequestHandler):
    # Wired once by __main__.py before the server starts serving.
    backend: UploadBackend | None = None
    projects_dir: Path = Path.home() / ".clip-editor-projects"
    work_dir: Path = Path("/tmp")

    def log_message(self, fmt, *args):
        print(f"  [{self.address_string()}] {fmt % args}")

    def do_GET(self):
        if self.path == "/health":
            # Not present in the original script - added because any real
            # orchestrator (k8s liveness/readiness, a load balancer) needs
            # a cheap, dependency-free endpoint to poll. Deliberately does
            # not touch ffmpeg/disk/the upload backend - it only proves
            # this process is alive and accepting connections.
            self._json(200, {"status": "ok"})
        elif self.path in ("/", "/index.html"):
            self._raw(200, "text/html; charset=utf-8", PAGE)
        elif self.path.startswith("/preview/"):
            self._serve_video(self.path[9:])
        elif self.path.startswith("/progress/"):
            self._sse_progress(self.path[10:])
        elif self.path == "/projects":
            self._json(200, projects.list_projects(self.projects_dir))
        elif self.path.startswith("/projects/"):
            pid = self.path[10:]
            try:
                self._json(200, projects.load_project(self.projects_dir, pid, self.work_dir))
            except FileNotFoundError as exc:
                self._json(404, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
        else:
            self._raw(404, "text/plain", b"Not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        if self.path == "/upload-temp":
            self._upload_temp(body)
        elif self.path == "/process":
            self._process(body)
        elif self.path == "/push":
            self._push(body)
        elif self.path == "/projects":
            self._save_project_req(body)
        else:
            self._raw(404, "text/plain", b"Not found")

    def do_DELETE(self):
        if self.path.startswith("/projects/"):
            pid = self.path[10:]
            try:
                projects.delete_project(self.projects_dir, pid)
                self._json(200, {"ok": True})
            except FileNotFoundError as exc:
                self._json(404, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
        else:
            self._raw(404, "text/plain", b"Not found")

    def _raw(self, status, ct, body):
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status, data):
        self._raw(status, "application/json", json.dumps(data).encode())

    def _serve_video(self, file_id):
        with state.LOCK:
            f = state.FILES.get(file_id)
        if not f or not os.path.exists(f["path"]):
            self._raw(404, "text/plain", b"Not found")
            return
        path = f["path"]
        ext = Path(path).suffix.lower().lstrip(".")
        ct = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/mp4",
              "avi": "video/x-msvideo", "mkv": "video/x-matroska"}.get(ext, "video/mp4")
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        try:
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if not m:
                    self._raw(416, "text/plain", b"Range Not Satisfiable")
                    return
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as fh:
                    fh.seek(start)
                    rem = length
                    while rem > 0:
                        chunk = fh.read(min(65536, rem))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        rem -= len(chunk)
            else:
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as fh:
                    while chunk := fh.read(65536):
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser cancelled the request (normal during seeking)

    def _sse_progress(self, job_id):
        with state.LOCK:
            if job_id not in state.JOBS:
                self._raw(404, "text/plain", b"Not found")
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        while True:
            with state.LOCK:
                snap = json.dumps(state.JOBS.get(job_id, {}))
            if snap != last:
                try:
                    self.wfile.write(f"data: {snap}\n\n".encode())
                    self.wfile.flush()
                except Exception:
                    break
                last = snap
            if json.loads(snap).get("status") in ("done", "error"):
                break
            time.sleep(0.2)
        # No Content-Length/chunked framing on this streamed response - the
        # client's only way to know the body has ended is the connection
        # closing. A request sent as "HTTP/1.1" (which most clients,
        # including curl, do unconditionally) makes the stdlib default to
        # keep-alive, so without this the socket stays open after this
        # handler returns and the client hangs waiting for bytes that will
        # never come (confirmed live: curl hung indefinitely on an
        # already-"done" job, even hitting the pod directly with no proxy
        # in between).
        self.close_connection = True

    def _upload_temp(self, body):
        try:
            ct = self.headers.get("Content-Type", "")
            data, filename, mime = _parse_multipart(body, ct)
            if not mime.startswith("video/"):
                self._json(415, {"error": f"Expected video/*, got {mime}"})
                return
            file_id = uuid.uuid4().hex
            ext = Path(filename).suffix or ".mp4"
            path = self.work_dir / f"{file_id}{ext}"
            path.write_bytes(data)
            meta = ffmpeg_ops.probe(path)
            with state.LOCK:
                state.FILES[file_id] = {"path": str(path), "name": filename,
                                         "duration": meta["duration"], "size": len(data),
                                         "has_audio": meta["has_audio"],
                                         "width": meta["width"], "height": meta["height"]}
            self._json(200, {"fileId": file_id, "filename": filename,
                              "duration": meta["duration"], "width": meta["width"],
                              "height": meta["height"], "hasAudio": meta["has_audio"],
                              "size": len(data)})
        except Exception as exc:
            print(f"  upload-temp error: {exc}")
            self._json(500, {"error": str(exc)})

    def _process(self, body):
        try:
            req = json.loads(body)
            clip_list = req.get("clips", [])
            if not clip_list:
                self._json(400, {"error": "No clips provided"})
                return
            sources = []
            for cl in clip_list:
                fid = cl.get("fileId")
                with state.LOCK:
                    f = state.FILES.get(fid)
                if not f:
                    self._json(404, {"error": f"File {fid} not found"})
                    return
                sources.append({
                    "fileId": fid,
                    "path": f["path"],
                    "meta": {"duration": f["duration"], "has_audio": f["has_audio"],
                             "width": f.get("width", 0), "height": f.get("height", 0)},
                    "segments": cl.get("segments") or [],
                })
            job_id = uuid.uuid4().hex
            dst = self.work_dir / f"out_{job_id}.mp4"
            threading.Thread(
                target=ffmpeg_ops.run_job,
                args=(job_id, sources, dst, req.get("settings", {})),
                daemon=True,
            ).start()
            self._json(200, {"jobId": job_id})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _push(self, body):
        try:
            if self.backend is None:
                self._json(500, {"error": "No upload backend configured"})
                return
            req = json.loads(body)
            fid = req.get("fileId")
            with state.LOCK:
                f = state.FILES.get(fid)
            if not f:
                self._json(404, {"error": "File not found"})
                return
            video_bytes = Path(f["path"]).read_bytes()
            fname = f["name"]
            ext = Path(fname).suffix.lstrip(".") or "mp4"
            result = self.backend.push(video_bytes, fname, f"video/{ext}")
            print(f"  pushed: {result.get('url')}")
            self._json(200, result)
        except BackendError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _save_project_req(self, body):
        try:
            result = projects.save_project(self.projects_dir, json.loads(body))
            self._json(200, result)
        except Exception as exc:
            self._json(500, {"error": str(exc)})


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
