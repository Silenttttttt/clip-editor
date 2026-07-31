"""Tests for ffmpeg_ops.probe() error reporting - requires a real ffprobe
binary on PATH (skipped otherwise, same convention as the rest of the
suite avoiding new dependencies)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_editor import ffmpeg_ops


@unittest.skipUnless(shutil.which("ffprobe"), "ffprobe not installed")
class ProbeErrorMessagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_garbage_input_raises_informative_error(self):
        # Previously ffprobe ran with `-v quiet`, which suppresses its own
        # diagnostic stderr entirely - a corrupt/invalid file's error
        # message came back completely blank (confirmed live: `{"error":
        # ""}`). It must now contain a real reason.
        junk = self.tmp / "junk.mp4"
        junk.write_bytes(b"not a real video file, just random bytes 12345")
        with self.assertRaises(RuntimeError) as ctx:
            ffmpeg_ops.probe(junk)
        self.assertTrue(str(ctx.exception).strip(), "error message must not be blank")

    def test_empty_file_raises_informative_error(self):
        empty = self.tmp / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaises(RuntimeError) as ctx:
            ffmpeg_ops.probe(empty)
        self.assertTrue(str(ctx.exception).strip())

    def test_audio_only_file_rejected_as_no_video_stream(self):
        # A file with no video stream (e.g. audio-only) is a valid media
        # file to ffprobe but useless to this editor - must fail clearly
        # rather than silently returning width=0/height=0.
        import subprocess
        audio_only = self.tmp / "audio.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             str(audio_only)],
            capture_output=True, timeout=30, check=True,
        )
        with self.assertRaises(RuntimeError) as ctx:
            ffmpeg_ops.probe(audio_only)
        self.assertIn("video", str(ctx.exception).lower())

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_real_video_probes_successfully(self):
        import subprocess
        real = self.tmp / "real.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
             "-c:v", "libx264", "-preset", "veryfast", str(real)],
            capture_output=True, timeout=30, check=True,
        )
        meta = ffmpeg_ops.probe(real)
        self.assertEqual(meta["width"], 64)
        self.assertEqual(meta["height"], 64)
        self.assertAlmostEqual(meta["duration"], 1.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
