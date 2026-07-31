"""Tests for real HTTP behavior of /preview (Range requests) and
/upload-temp - starts the real Server/Handler on an ephemeral port, same
convention as test_server_health.py."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_editor import state
from clip_editor.backends import VpsBackend
from clip_editor.server import Handler, Server


class _ServerTestBase(unittest.TestCase):
    def setUp(self):
        Handler.backend = VpsBackend("http://example.invalid", "test-key")
        self.tmp = Path(tempfile.mkdtemp())
        Handler.projects_dir = self.tmp / "projects"
        Handler.projects_dir.mkdir()
        Handler.work_dir = self.tmp / "work"
        Handler.work_dir.mkdir()
        self.srv = Server(("127.0.0.1", 0), Handler)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        with state.LOCK:
            state.FILES.clear()
            state.JOBS.clear()

    def _get(self, path, headers=None, method="GET"):
        req = urllib.request.Request(self.base + path, headers=headers or {}, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()


class PreviewRangeTest(_ServerTestBase):
    """Confirmed live on the real deployment: a suffix Range
    (bytes=-N, "last N bytes") was misinterpreted as bytes 0..N, and an
    out-of-bounds start produced a response with a *negative*
    Content-Length (malformed enough to break the HTTP framing - it
    surfaced as a 502 through the activator proxy in front of this
    server)."""

    def setUp(self):
        super().setUp()
        self.content = bytes(range(256)) * 40  # 10240 bytes, easy to index into
        self.file_id = "testfile"
        p = self.tmp / "clip.mp4"
        p.write_bytes(self.content)
        with state.LOCK:
            state.FILES[self.file_id] = {"path": str(p), "name": "clip.mp4"}

    def test_full_file_no_range(self):
        status, headers, body = self._get(f"/preview/{self.file_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(body), len(self.content))
        self.assertEqual(headers.get("Content-Length"), str(len(self.content)))

    def test_forward_range(self):
        status, headers, body = self._get(f"/preview/{self.file_id}", {"Range": "bytes=100-199"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.content[100:200])
        self.assertEqual(headers.get("Content-Range"), f"bytes 100-199/{len(self.content)}")

    def test_open_ended_range(self):
        status, headers, body = self._get(f"/preview/{self.file_id}", {"Range": "bytes=100-"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.content[100:])

    def test_suffix_range_returns_last_n_bytes(self):
        status, headers, body = self._get(f"/preview/{self.file_id}", {"Range": "bytes=-500"})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 500)
        self.assertEqual(body, self.content[-500:])
        size = len(self.content)
        self.assertEqual(headers.get("Content-Range"), f"bytes {size - 500}-{size - 1}/{size}")

    def test_out_of_bounds_start_is_416_not_malformed(self):
        status, headers, body = self._get(
            f"/preview/{self.file_id}", {"Range": "bytes=999999999-999999999999"}
        )
        self.assertEqual(status, 416)
        cl = headers.get("Content-Length")
        self.assertIsNotNone(cl)
        self.assertGreaterEqual(int(cl), 0)  # never negative
        self.assertEqual(headers.get("Content-Range"), f"bytes */{len(self.content)}")
        self.assertEqual(body, b"")

    def test_unknown_file_id_is_404(self):
        status, _headers, _body = self._get("/preview/does-not-exist")
        self.assertEqual(status, 404)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
class UploadTempMimeTest(_ServerTestBase):
    """Confirmed live: a genuinely valid video uploaded with a generic
    declared Content-Type (e.g. application/octet-stream - what real
    browsers send for containers with no OS-registered MIME type) used to
    get hard-rejected with a 415 before ffprobe ever got a chance to look
    at the actual bytes."""

    def _make_video(self) -> bytes:
        out = self.tmp / "src.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
             "-c:v", "libx264", "-preset", "veryfast", str(out)],
            capture_output=True, timeout=30, check=True,
        )
        return out.read_bytes()

    def _multipart(self, filename: str, content_type: str, data: bytes):
        boundary = "----testboundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        return body, headers

    def test_valid_video_with_generic_content_type_is_accepted(self):
        data = self._make_video()
        body, headers = self._multipart("clip.mp4", "application/octet-stream", data)
        req = urllib.request.Request(self.base + "/upload-temp", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)

    def test_garbage_upload_is_415_with_real_message_not_500_blank(self):
        body, headers = self._multipart("junk.mp4", "video/mp4", b"not a real video, just junk bytes")
        req = urllib.request.Request(self.base + "/upload-temp", data=body, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=15)
            self.fail("expected an HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 415)
            import json
            payload = json.loads(exc.read())
            self.assertTrue(payload.get("error", "").strip(), "error message must not be blank")


if __name__ == "__main__":
    unittest.main()
