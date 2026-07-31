"""In-memory registries shared across modules for the lifetime of one
server process.

This is a single-process, single-instance server (no multi-replica
coordination, no external cache) - matching the design of the original
script this project is based on. A module-level dict + one lock is enough:

- FILES: every media file the process currently knows about - both
  temp-uploaded source clips and ffmpeg-processed outputs - keyed by a
  random file id. Read/written by ffmpeg_ops.py (registers job outputs),
  projects.py (restores clips referenced by a saved project) and
  server.py (registers uploads, serves previews).
- JOBS: currently running/finished ffmpeg export jobs, keyed by job id.
  Written by ffmpeg_ops.run_job, read by server.py's SSE progress stream.
"""

from __future__ import annotations

import threading

LOCK = threading.Lock()

FILES: dict[str, dict] = {}
JOBS: dict[str, dict] = {}
