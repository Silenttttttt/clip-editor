"""Unit tests for ffmpeg command construction - pure string-building logic,
no real ffmpeg binary required (build_cmd never shells out)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_editor.ffmpeg_ops import build_cmd


def _source(path="clip.mp4", duration=10.0, width=1280, height=720, has_audio=True, segments=None):
    return {
        "fileId": "abc",
        "path": path,
        "meta": {"duration": duration, "width": width, "height": height, "has_audio": has_audio},
        "segments": segments or [],
    }


class BuildCmdTest(unittest.TestCase):
    def test_single_clip_fast_path_uses_ss_to(self):
        cmd = build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70})
        self.assertIn("-ss", cmd)
        self.assertIn("-to", cmd)
        self.assertIn("-c:a", cmd)
        self.assertNotIn("-filter_complex", cmd)

    def test_muted_drops_audio_encoding(self):
        cmd = build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70, "muted": True})
        self.assertIn("-an", cmd)
        self.assertNotIn("-c:a", cmd)

    def test_no_audio_source_forces_mute(self):
        cmd = build_cmd([_source(has_audio=False)], Path("/tmp/out.mp4"), {"quality": 70, "muted": False})
        self.assertIn("-an", cmd)

    def test_multi_clip_uses_concat_filter_complex(self):
        sources = [_source(path="a.mp4"), _source(path="b.mp4", width=640, height=360)]
        cmd = build_cmd(sources, Path("/tmp/out.mp4"), {"quality": 70})
        self.assertIn("-filter_complex", cmd)
        idx = cmd.index("-filter_complex")
        self.assertIn("concat=n=2", cmd[idx + 1])

    def test_target_size_uses_bitrate_encoding(self):
        cmd = build_cmd([_source(duration=20)], Path("/tmp/out.mp4"), {"quality": 70, "targetMb": 5})
        self.assertIn("-b:v", cmd)
        self.assertNotIn("-crf", cmd)

    def test_quality_without_target_uses_crf(self):
        cmd = build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70})
        self.assertIn("-crf", cmd)

    def test_output_has_faststart_and_dst_path(self):
        cmd = build_cmd([_source()], Path("/tmp/out123.mp4"), {"quality": 70})
        self.assertIn("+faststart", cmd)
        self.assertEqual(cmd[-1], "/tmp/out123.mp4")

    def test_negative_target_size_rejected(self):
        # Confirmed live: a negative targetMb used to sail through, get
        # clamped to a 50kbps bitrate floor, and produce a "successful"
        # but garbage export with no error at all.
        with self.assertRaises(ValueError):
            build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70, "targetMb": -5})

    def test_zero_target_size_is_treated_as_unset(self):
        # 0 is falsy/meaningless as a target size - should behave like no
        # target size was given at all (CRF path), not raise.
        cmd = build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70, "targetMb": 0})
        self.assertIn("-crf", cmd)

    def test_negative_volume_rejected(self):
        with self.assertRaises(ValueError):
            build_cmd([_source()], Path("/tmp/out.mp4"), {"quality": 70, "volume": -10})


if __name__ == "__main__":
    unittest.main()
