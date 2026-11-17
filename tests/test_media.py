"""Ce que media doit encore savoir faire : sonder une source, juger un fichier produit, s'arrêter net."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio import media


def run(*args: object) -> None:
    subprocess.run([str(arg) for arg in args], check=True, capture_output=True, timeout=180)


class ProxySizeTests(unittest.TestCase):
    """Le proxy garde le format d'origine : aucune bande noire, aucun agrandissement."""

    def size(self, width: int, height: int) -> tuple[int, int]:
        return media._proxy_size({"width": width, "height": height})

    def test_a_landscape_rush_lands_on_1280_by_720(self):
        self.assertEqual(self.size(1920, 1080), (1280, 720))
        self.assertEqual(self.size(3840, 2160), (1280, 720))

    def test_a_vertical_rush_lands_on_720_by_1280(self):
        self.assertEqual(self.size(1080, 1920), (720, 1280))

    def test_an_unusual_shape_keeps_both_edges_under_the_limits(self):
        for source in ((2048, 1080), (1600, 1200), (2400, 1080), (1440, 1440)):
            width, height = self.size(*source)
            self.assertLessEqual(max(width, height), media.PROXY_LONG_EDGE, source)
            self.assertLessEqual(min(width, height), media.PROXY_SHORT_EDGE, source)
            self.assertEqual((width % 2, height % 2), (0, 0), source)
            self.assertAlmostEqual(width / height, source[0] / source[1], delta=0.01, msg=str(source))

    def test_a_small_rush_is_left_alone(self):
        self.assertEqual(self.size(640, 360), (640, 360))
        self.assertEqual(self.size(720, 1280), (720, 1280))


class RateTests(unittest.TestCase):
    def test_a_frame_rate_is_read_as_a_number_and_never_divides_by_zero(self):
        self.assertAlmostEqual(media._parse_rate("30000/1001"), 29.97, delta=0.01)
        self.assertEqual(media._parse_rate("25/1"), 25.0)
        self.assertEqual(media._parse_rate("25"), 25.0)
        for empty in (None, "", "0/0", "30/0"):
            self.assertEqual(media._parse_rate(empty), 0.0, repr(empty))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe absents")
class MediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source with spaces.mp4"
        run(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2.4",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2.4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(self.source),
        )

    def test_probe_reports_normalized_metadata(self) -> None:
        result = media.probe(self.source)
        self.assertEqual(result["path"], str(self.source.resolve()))
        self.assertEqual(result["name"], self.source.name)
        self.assertEqual((result["width"], result["height"]), (320, 240))
        self.assertAlmostEqual(result["duration"], 2.4, delta=0.08)
        self.assertAlmostEqual(result["fps"], 25)
        self.assertTrue(result["has_audio"])

    def test_probe_rejects_non_video(self) -> None:
        bad = self.root / "bad.mp4"
        bad.write_text("not media", encoding="utf-8")
        with self.assertRaises(media.MediaError):
            media.probe(bad)

    def test_probe_names_the_file_it_cannot_find(self) -> None:
        with self.assertRaisesRegex(media.MediaError, "introuvable"):
            media.probe(self.root / "absent.mp4")

    def test_probe_rejects_an_audio_only_file(self) -> None:
        sound = self.root / "son.m4a"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1", "-c:a", "aac", str(sound))
        with self.assertRaisesRegex(media.MediaError, "Aucune piste video"):
            media.probe(sound)

    def test_a_silent_rush_is_accepted_and_declared_silent(self) -> None:
        mute = self.root / "muet.mp4"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc2=size=160x120:rate=25:duration=1", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", str(mute))
        self.assertFalse(media.probe(mute)["has_audio"])

    def test_a_fingerprint_changes_when_the_file_or_the_offset_changes(self) -> None:
        source = {"path": str(self.source), "offset": 0}
        first = media._source_fingerprint(source)
        self.assertEqual(first, media._source_fingerprint(dict(source)))
        self.assertNotEqual(first, media._source_fingerprint(dict(source, offset=0.5)))
        copy = self.root / "copie.mp4"
        shutil.copy2(self.source, copy)
        same_bytes = media._source_fingerprint({"path": str(copy), "offset": 0})
        self.assertNotEqual(first["path"], same_bytes["path"])

    def test_a_produced_file_is_refused_when_it_does_not_match_the_order(self) -> None:
        with self.assertRaisesRegex(media.MediaError, "Dimensions"):
            media._verify_video(self.source, dimensions=(1280, 720))
        with self.assertRaisesRegex(media.MediaError, "Duree"):
            media._verify_video(self.source, expected_duration=10.0)
        info = media._verify_video(self.source, expected_duration=2.4, dimensions=(320, 240))
        self.assertEqual((info["width"], info["height"]), (320, 240))

    def test_a_produced_file_without_sound_is_refused_when_sound_was_expected(self) -> None:
        mute = self.root / "sans-son.mp4"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc2=size=160x120:rate=25:duration=1", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", str(mute))
        with self.assertRaisesRegex(media.MediaError, "piste audio"):
            media._verify_video(mute, require_audio=True)
        media._verify_video(mute, require_audio=False)

    def export(self, segments: list[dict[str, float]], stem: str = "Mon short") -> dict[str, object]:
        return media.export_montage(self.source, segments, self.root / "Montages validés" / f"{stem}.mp4",
                                    lambda *_: None, lambda: None)

    def test_a_whole_montage_is_copied_without_re_encoding(self) -> None:
        whole = [{"start": 0.0, "end": media.probe(self.source)["duration"]}]
        made = self.export(whole)
        self.assertTrue(made["remux"])
        self.assertEqual(made["pieces"], 1)
        self.assertTrue(Path(str(made["path"])).is_file())
        self.assertGreater(made["bytes"], 0)
        self.assertAlmostEqual(media.probe(made["path"])["duration"], 2.4, delta=0.15)
        # Un deuxième export ne marche pas sur le premier : il prend le nom libre d'à côté.
        again = self.export(whole)
        self.assertNotEqual(again["path"], made["path"])
        self.assertTrue(Path(str(made["path"])).is_file())

    def test_a_montage_with_blanks_cut_is_re_encoded_and_lasts_what_it_keeps(self) -> None:
        made = self.export([{"start": 0.2, "end": 0.8}, {"start": 1.4, "end": 2.0}], stem="Recoupé")
        self.assertFalse(made["remux"])
        self.assertEqual(made["pieces"], 2)
        self.assertAlmostEqual(float(made["expected"]), 1.2, places=3)
        self.assertAlmostEqual(media.probe(made["path"])["duration"], 1.2, delta=0.2)

    def test_an_export_refuses_what_it_cannot_cut(self) -> None:
        with self.assertRaisesRegex(media.MediaError, "aucun morceau"):
            self.export([])
        with self.assertRaisesRegex(media.MediaError, "aucun morceau"):
            self.export([{"start": 1.0, "end": 1.0}])
        with self.assertRaisesRegex(media.MediaError, "introuvable"):
            media.export_montage(self.root / "absent.mp4", [{"start": 0.0, "end": 1.0}],
                                 self.root / "sortie.mp4", lambda *_: None, lambda: None)

    def rouge(self, path: Path, seconds: float) -> bool:
        """Vrai si l'image prise à cet instant est rouge : c'est l'encadré posé par-dessus."""
        raw = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=120).stdout
        self.assertTrue(raw, f"aucune image à {seconds} s")
        rouges, verts = raw[0::3], raw[1::3]
        return sum(rouges) / len(rouges) > 200 and sum(verts) / len(verts) < 60

    def overlay(self, seconds: float = 4.0) -> dict[str, object]:
        """Un faux encadré : un rectangle rouge plein écran, qu'on reconnaît image par image."""
        card = self.root / "encadre.png"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "color=c=red:s=320x240", "-frames:v", "1", str(card))
        return dict(path=str(card), seconds=seconds, fade_start=seconds - 0.3, fade_seconds=0.3)

    def test_the_hook_card_sits_on_the_first_frame_and_leaves_after_four_seconds(self) -> None:
        long = self.root / "long.mp4"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc2=size=320x240:rate=25:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(long))
        made = media.export_montage(long, [{"start": 0.0, "end": 6.0}], self.root / "Montages validés" / "Avec encadré.mp4",
                                    lambda *_: None, lambda: None, overlay=self.overlay())
        self.assertTrue(made["encadre"])
        # L'encadré interdit la copie telle quelle : les images changent, il faut réencoder.
        self.assertFalse(made["remux"])
        self.assertTrue(self.rouge(made["path"], 0.0), "l’encadré doit être là dès la première image")
        self.assertTrue(self.rouge(made["path"], 3.5))
        self.assertFalse(self.rouge(made["path"], 4.5), "l’encadré doit avoir disparu après 4 s")

    def test_an_export_without_a_card_says_so(self) -> None:
        made = self.export([{"start": 0.0, "end": 1.0}], stem="Sans encadré")
        self.assertFalse(made["encadre"])

    def test_the_exported_name_stays_readable(self) -> None:
        self.assertEqual(media.export_name("Short 1 · plateau"), "Short 1 plateau")
        self.assertEqual(media.export_name("P1/02: brut?"), "P1 02 brut")
        self.assertEqual(media.export_name(""), "Montage")

    def test_diagnostics_only_reports_the_tools_the_studio_still_needs(self) -> None:
        report = media.diagnostics()
        names = [tool["name"] for tool in report["tools"]]
        self.assertEqual(names, ["ffmpeg", "ffprobe", "whisper-cli", "modèle Whisper"])
        # Les étapes Cadrage et Finition sont parties avec ImageMagick et DeepFilterNet.
        for gone in ("magick", "deep-filter", "node", "ffplay"):
            self.assertNotIn(gone, names)
        by_name = {tool["name"]: tool for tool in report["tools"]}
        self.assertTrue(by_name["ffmpeg"]["available"])
        self.assertIn("ffmpeg version", by_name["ffmpeg"]["detail"])
        self.assertIsInstance(report["fonts"], list)

    def test_a_missing_tool_is_reported_as_missing_not_invented(self) -> None:
        with mock.patch.object(media, "_tool", return_value=None):
            report = media.diagnostics()
        for tool in report["tools"]:
            if tool["name"] != "modèle Whisper":
                self.assertFalse(tool["available"], tool["name"])
                self.assertIsNone(tool["path"], tool["name"])

    def test_a_required_tool_that_is_absent_stops_the_work(self) -> None:
        with mock.patch.object(media, "_tool", return_value=None):
            with self.assertRaisesRegex(media.MediaError, "ffmpeg"):
                media._required_tool("ffmpeg")

    def test_cancellation_is_checked_while_process_runs(self) -> None:
        checks = 0

        def cancel() -> None:
            nonlocal checks
            checks += 1
            if checks >= 2:
                raise RuntimeError("cancelled")

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            media._run(["python3", "-c", "import time; time.sleep(2)"], check=cancel)
        self.assertGreaterEqual(checks, 2)


if __name__ == "__main__":
    unittest.main()
