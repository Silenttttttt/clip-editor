"""Smoke test for the /health endpoint added for real orchestrator probes
(not present in the original script) - starts the real Server/Handler on
an ephemeral port and hits it over a real socket."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_editor.backends import VpsBackend
from video_editor.server import Handler, Server


class HealthEndpointTest(unittest.TestCase):
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

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_health_returns_ok(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read())
            self.assertEqual(body, {"status": "ok"})

    def test_root_serves_editor_page(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            body = resp.read()
            self.assertIn(b"Video Editor", body)

    def test_unknown_route_is_404(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/nope")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
