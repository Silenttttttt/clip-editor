"""Pluggable "where does the finished video go" backends.

An UploadBackend takes the raw processed video bytes and hands back a dict
with at least a "url" key pointing at where the video can now be fetched
from. `server.py`'s /push handler doesn't know or care which backend is
configured - it just calls `.push(...)` and forwards the result (or raises
BackendError, which becomes an HTTP error response with a matching status).

Two real implementations ship here:

- VpsBackend: the ORIGINAL behavior, unchanged - multipart POST straight to
  a VPS's /api/admin/videos/upload endpoint with an X-Api-Key header. This
  remains the default so existing deployments (e.g. AdvogadosX's) keep
  working with zero reconfiguration.

- LocalStorageBackend: pushes instead to a self-hosted local-storage CDN
  instance (github.com/Silenttttttt/rust-local-storage-cdn) - a simple
  S3-like file store. Useful for a homelab deployment that has no VPS to
  push to.

IMPORTANT, HONEST LIMITATION - read before using local-storage in
production: the URL LocalStorageBackend returns is a direct URL to
wherever local-storage itself is reachable from (its configured
`base_url`) - it is NOT rewritten onto any other public domain. If you
need videos processed by this tool to appear under a specific public
domain (e.g. because some other system already expects /videos/xyz.mp4
under its own domain), there are exactly two real ways to get there, and
neither is implemented by this repo:

  1. Change the receiving backend so it can accept a URL reference
     instead of raw file bytes, and have it fetch/relay from local-storage
     itself.
  2. Build a reverse-proxy/route-registration layer in front of
     local-storage that publishes it under the target domain.

Do not assume LocalStorageBackend's URL is publicly routable under any
domain other than wherever `LOCAL_STORAGE_URL` itself already resolves.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Protocol


class UploadBackend(Protocol):
    def push(self, video_bytes: bytes, filename: str, content_type: str) -> dict:
        """Uploads `video_bytes` and returns a JSON-serializable dict with at
        least a "url" key. Raises BackendError on failure."""
        ...


class BackendError(Exception):
    """Raised with an HTTP-status-like `.status` so callers can propagate a
    sane status code (e.g. the remote's own 4xx/5xx) instead of a blanket 500."""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


def _multipart_body(field_name: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f'Content-Type: {content_type}\r\n\r\n'
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, boundary


def _http_post(req: urllib.request.Request, timeout: int = 600) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            data = json.loads(raw)
        except Exception:
            data = {"error": raw or f"HTTP {exc.code}"}
        raise BackendError(data.get("error", str(data)), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"Could not reach upload backend: {exc.reason}", status=502) from exc


class VpsBackend:
    """EXACT original behavior, preserved: multipart POST to
    `{server}/api/admin/videos/upload` with an `X-Api-Key` header. Expects
    a JSON response containing a "url" key (relative "/..." urls get the
    server prefixed on)."""

    def __init__(self, server_url: str, api_key: str):
        if not server_url:
            raise ValueError("VpsBackend requires a server URL (--server / UPLOAD_SERVER_URL)")
        if not api_key:
            raise ValueError("VpsBackend requires an API key (--api-key / UPLOAD_API_KEY)")
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def push(self, video_bytes: bytes, filename: str, content_type: str) -> dict:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
        body, boundary = _multipart_body("file", filename, f"video/{ext}", video_bytes)
        target = f"{self.server_url}/api/admin/videos/upload"
        req = urllib.request.Request(
            target, data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Api-Key": self.api_key,
            },
            method="POST",
        )
        _status, result = _http_post(req)
        if isinstance(result.get("url"), str) and result["url"].startswith("/"):
            result["url"] = self.server_url + result["url"]
        return result


class LocalStorageBackend:
    """Pushes to a local-storage CDN instance's real API:

        POST /buckets/{bucket}/files
            body = raw file bytes
            Content-Disposition: attachment; filename="X"  (sets the stored key)
            Content-Type: <content_type>

    Returns 201 + a JSON FileInfo record (id/bucket/key/filename/...) on
    success. The download URL is built from that record's "key" (the
    canonical stored name - confirmed against local-storage's own source:
    `storage.store_file(bucket, key=filename, ...)`, so key == the filename
    we sent, but reading it back from the response instead of assuming it
    is more robust to any future server-side renaming).

    While local-storage is scaled to zero and write-protected, mutating
    requests need an `X-Activator-Write-Token` header matching the
    activator's own token - pass it as `write_token`.
    """

    def __init__(self, base_url: str, bucket: str = "clip-editor", write_token: str | None = None):
        if not base_url:
            raise ValueError("LocalStorageBackend requires a base URL (LOCAL_STORAGE_URL)")
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self.write_token = write_token or None

    def push(self, video_bytes: bytes, filename: str, content_type: str) -> dict:
        target = f"{self.base_url}/buckets/{self.bucket}/files"
        headers = {
            "Content-Type": content_type or "video/mp4",
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if self.write_token:
            headers["X-Activator-Write-Token"] = self.write_token
        req = urllib.request.Request(target, data=video_bytes, headers=headers, method="POST")
        _status, info = _http_post(req)
        key = info.get("key") or filename
        info["url"] = f"{self.base_url}/buckets/{self.bucket}/files/{key}"
        return info


def build_backend(
    kind: str,
    *,
    server_url: str = "",
    api_key: str = "",
    local_storage_url: str = "",
    local_storage_bucket: str = "clip-editor",
    local_storage_write_token: str = "",
) -> UploadBackend:
    if kind == "vps":
        return VpsBackend(server_url, api_key)
    if kind == "local-storage":
        return LocalStorageBackend(local_storage_url, local_storage_bucket, local_storage_write_token)
    raise ValueError(f"Unknown upload backend: {kind!r} (expected 'vps' or 'local-storage')")
