"""CLI entry point: `python -m clip_editor [flags]`.

Preserves the original script's defaults exactly - `--upload-backend`
defaults to `vps`, which still requires `--server`/`--api-key` (or the
matching env vars) as a hard error, exactly as before. Nothing changes for
an existing deployment unless it explicitly opts into
`--upload-backend local-storage`.
"""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

from .backends import build_backend
from .server import Handler, Server


def _require(name: str) -> None:
    if not shutil.which(name):
        print(f"Error: '{name}' not found in PATH.", file=sys.stderr)
        print("Install: brew install ffmpeg  /  sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video editor + production relay")
    parser.add_argument("--upload-backend", choices=["vps", "local-storage"],
                         default=os.environ.get("UPLOAD_BACKEND", "vps"),
                         help="Where 'Export & Upload' pushes the finished video. Default: vps "
                              "(unchanged original behavior).")
    parser.add_argument("--server", default=os.environ.get("UPLOAD_SERVER_URL", ""), metavar="URL",
                         help="[vps backend] Base URL of the receiving server.")
    parser.add_argument("--api-key", default=os.environ.get("UPLOAD_API_KEY", ""), metavar="KEY",
                         help="[vps backend] X-Api-Key header value.")
    parser.add_argument("--local-storage-url", default=os.environ.get("LOCAL_STORAGE_URL", ""), metavar="URL",
                         help="[local-storage backend] Base URL of the local-storage CDN instance.")
    parser.add_argument("--local-storage-bucket",
                         default=os.environ.get("LOCAL_STORAGE_BUCKET", "clip-editor"), metavar="BUCKET",
                         help="[local-storage backend] Bucket to upload processed videos into.")
    parser.add_argument("--local-storage-write-token",
                         default=os.environ.get("LOCAL_STORAGE_WRITE_TOKEN", ""), metavar="TOKEN",
                         help="[local-storage backend] X-Activator-Write-Token, required only if the "
                              "target instance is write-protected while scaled to zero.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("UPLOAD_PORT", "7777")))
    parser.add_argument("--projects-dir",
                         default=os.environ.get("PROJECTS_DIR", str(Path.home() / ".clip-editor-projects")),
                         metavar="DIR")
    return parser


def main() -> None:
    _require("ffmpeg")
    _require("ffprobe")
    parser = _build_parser()
    args = parser.parse_args()

    if args.upload_backend == "vps":
        if not args.server:
            parser.error("--server required for --upload-backend vps (or UPLOAD_SERVER_URL)")
        if not args.api_key:
            parser.error("--api-key required for --upload-backend vps (or UPLOAD_API_KEY)")
    elif args.upload_backend == "local-storage":
        if not args.local_storage_url:
            parser.error("--local-storage-url required for --upload-backend local-storage "
                          "(or LOCAL_STORAGE_URL)")

    Handler.backend = build_backend(
        args.upload_backend,
        server_url=args.server,
        api_key=args.api_key,
        local_storage_url=args.local_storage_url,
        local_storage_bucket=args.local_storage_bucket,
        local_storage_write_token=args.local_storage_write_token,
    )

    projects_dir = Path(args.projects_dir).expanduser().resolve()
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "files").mkdir(exist_ok=True)
    Handler.projects_dir = projects_dir

    work_dir = Path(tempfile.mkdtemp(prefix="clip-editor-"))
    atexit.register(lambda: shutil.rmtree(work_dir, ignore_errors=True))
    Handler.work_dir = work_dir

    ip = _local_ip()
    srv = Server(("0.0.0.0", args.port), Handler)
    print(f"Video editor  ->  backend={args.upload_backend}")
    print(f"  http://{ip}:{args.port}")
    print(f"  http://localhost:{args.port}  (this machine)")
    print(f"  Projects: {projects_dir}")
    print(f"  Scratch:  {work_dir}\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
