"""Functional tests for the upload backends against a local mock HTTP
server - no real network calls, no real credentials. This is the "mock it
locally" functional test for VpsBackend the project README promises,
since hitting the real AdvogadosX production API from a test is out of
bounds.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_editor.backends import BackendError, LocalStorageBackend, VpsBackend, build_backend


class _MockVpsHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        assert self.path == "/api/admin/videos/upload"
        assert self.headers.get("X-Api-Key") == "test-key-123"
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        assert b"filename=\"clip.mp4\"" in body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"url": "/videos/clip-abc123.mp4"}).encode())


class _MockLocalStorageHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        assert self.path == "/buckets/clip-editor/files"
        assert self.headers.get("X-Activator-Write-Token") == "secret-token"
        assert self.headers.get("Content-Disposition") == 'attachment; filename="clip.mp4"'
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        assert body == b"fake-video-bytes"
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": "11111111-1111-1111-1111-111111111111",
            "bucket": "clip-editor",
            "key": "clip.mp4",
            "filename": "clip.mp4",
            "file_size": len(b"fake-video-bytes"),
        }).encode())


class _MockErrorHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "write-protected: missing token"}).encode())


def _serve(handler_cls) -> tuple[HTTPServer, threading.Thread, str]:
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    return srv, t, f"http://127.0.0.1:{port}"


class VpsBackendTest(unittest.TestCase):
    def test_push_prefixes_relative_url(self):
        srv, _t, base = _serve(_MockVpsHandler)
        try:
            backend = VpsBackend(base, "test-key-123")
            result = backend.push(b"fake-video-bytes", "clip.mp4", "video/mp4")
            self.assertEqual(result["url"], base + "/videos/clip-abc123.mp4")
        finally:
            srv.shutdown()

    def test_requires_server_and_key(self):
        with self.assertRaises(ValueError):
            VpsBackend("", "key")
        with self.assertRaises(ValueError):
            VpsBackend("http://x", "")


class LocalStorageBackendTest(unittest.TestCase):
    def test_push_builds_download_url_from_key(self):
        srv, _t, base = _serve(_MockLocalStorageHandler)
        try:
            backend = LocalStorageBackend(base, bucket="clip-editor", write_token="secret-token")
            result = backend.push(b"fake-video-bytes", "clip.mp4", "video/mp4")
            self.assertEqual(result["url"], f"{base}/buckets/clip-editor/files/clip.mp4")
            self.assertEqual(result["key"], "clip.mp4")
        finally:
            srv.shutdown()

    def test_error_response_raises_backend_error_with_status(self):
        srv, _t, base = _serve(_MockErrorHandler)
        try:
            backend = LocalStorageBackend(base, write_token="wrong-token")
            with self.assertRaises(BackendError) as ctx:
                backend.push(b"x", "clip.mp4", "video/mp4")
            self.assertEqual(ctx.exception.status, 403)
        finally:
            srv.shutdown()

    def test_requires_base_url(self):
        with self.assertRaises(ValueError):
            LocalStorageBackend("")


class BuildBackendTest(unittest.TestCase):
    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            build_backend("s3")

    def test_vps_default_matches_original_behavior(self):
        backend = build_backend("vps", server_url="https://example.com", api_key="k")
        self.assertIsInstance(backend, VpsBackend)

    def test_local_storage_selectable(self):
        backend = build_backend("local-storage", local_storage_url="http://storage.internal")
        self.assertIsInstance(backend, LocalStorageBackend)


if __name__ == "__main__":
    unittest.main()
