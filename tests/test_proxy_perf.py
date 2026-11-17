"""Contrat du proxy : 720p au format d'origine, une image-clé toutes les dix images, et rien qui traîne."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from studio import media


def source_video(path: Path, size: str, duration: float = 2.0, rate: int = 25, audio: bool = True) -> Path:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={duration}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}", "-c:a", "aac"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True, timeout=180)
    return path


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe absents")
class ProxyPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = source_video(self.root / "paysage.mp4", "1920x1080")
        self.item = {"id": "cam", "path": str(self.source), "offset": 0}

    def test_proxy_is_720p_and_has_a_keyframe_every_ten_frames(self):
        events = []
        result = media.make_proxy(self.item, self.root / "out", lambda *event: events.append(event), lambda: None)
        self.assertEqual((result["width"], result["height"]), (1280, 720))
        self.assertEqual(events[0][1], "Préparation du proxy")
        self.assertEqual(events[-1], (100, "Proxy terminé"))
        self.assertEqual(media.PROXY_FORMAT, "h264-720p-natif-gop10")
        media._verify_proxy_gop(Path(result["path"]), 25, lambda: None)
        self.assertEqual(list((self.root / "out").glob(".proxy-*")), [])

    def test_a_vertical_rush_keeps_its_own_shape(self):
        # Le reel est tourné en 9:16 : le proxy ne doit pas y ajouter de bandes noires.
        portrait = source_video(self.root / "portrait.mp4", "1080x1920", audio=False)
        result = media.make_proxy({"id": "cam", "path": str(portrait), "offset": 0},
                                  self.root / "vertical", lambda *_: None, lambda: None)
        self.assertEqual((result["width"], result["height"]), (720, 1280))
        self.assertFalse(result["has_audio"])

    def test_a_small_rush_is_never_blown_up(self):
        small = source_video(self.root / "petit.mp4", "640x360", audio=False)
        result = media.make_proxy({"id": "cam", "path": str(small), "offset": 0},
                                  self.root / "petit-out", lambda *_: None, lambda: None)
        self.assertEqual((result["width"], result["height"]), (640, 360))

    def test_keyframes_follow_the_source_rate_at_30_fps(self):
        source = source_video(self.root / "thirty.mp4", "1920x1080", duration=4, rate=30, audio=False)
        result = media.make_proxy({"id": "cam", "path": str(source), "offset": 0},
                                  self.root / "thirty-out", lambda *_: None, lambda: None)
        frames = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=key_frame",
                                 "-of", "csv=p=0", result["path"]], capture_output=True, text=True, check=True).stdout.split()
        keys = [index for index, flag in enumerate(frames) if flag.strip(",") == "1"]
        self.assertGreater(len(keys), 2)
        self.assertLessEqual(max(b - a for a, b in zip(keys, keys[1:])), 10)

    def test_an_existing_proxy_is_reused_instead_of_re_encoded(self):
        first = media.make_proxy(self.item, self.root / "cache", lambda *_: None, lambda: None)
        events = []
        again = media.make_proxy(self.item, self.root / "cache", lambda *event: events.append(event), lambda: None)
        self.assertEqual(first["path"], again["path"])
        # Un proxy repris ne réencode rien : pas même une étape de préparation.
        self.assertEqual(events, [])

    def test_an_older_proxy_format_is_never_reused(self):
        with mock.patch.object(media, "PROXY_FORMAT", "h264-360p-ancien"):
            older = media.make_proxy(self.item, self.root / "same", lambda *_: None, lambda: None)
        current = media.make_proxy(self.item, self.root / "same", lambda *_: None, lambda: None)
        self.assertNotEqual(Path(older["path"]).name, Path(current["path"]).name)

    def test_cancelling_leaves_nothing_behind(self):
        long_source = source_video(self.root / "cancel.mp4", "1920x1080", duration=60, audio=False)
        started = time.time()

        class Cancelled(Exception):
            pass

        def check():
            if time.time() - started > 1.5:
                raise Cancelled()
        with self.assertRaises(Cancelled):
            media.make_proxy({"id": "cam", "path": str(long_source), "offset": 0},
                             self.root / "cancel", lambda *_: None, check)
        self.assertEqual([p.name for p in (self.root / "cancel").iterdir()], [])
        leftover = subprocess.run(["pgrep", "-f", str(long_source)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(leftover, "")

    def test_a_source_that_lasts_nothing_is_refused(self):
        empty = self.root / "vide.mp4"
        empty.write_bytes(b"pas une video")
        with self.assertRaises(media.MediaError):
            media.make_proxy({"id": "cam", "path": str(empty), "offset": 0},
                             self.root / "vide-out", lambda *_: None, lambda: None)


if __name__ == "__main__":
    unittest.main()
