import json
import unittest
from unittest import mock
from studio import setup

REPO = {"url": "https://github.com/exemple/atelier.git", "branch": "feat/test"}


class SetupTests(unittest.TestCase):
    def test_every_requirement_has_an_install_command(self):
        items = setup.requirements()
        self.assertEqual(len({item["id"] for item in items}), len(items))
        for item in items:
            self.assertTrue(item["install"].strip(), item["id"])
            self.assertIsInstance(item["available"], bool, item["id"])
            self.assertTrue(item["why"].strip(), item["id"])

    def test_the_checklist_covers_the_two_steps_and_nothing_more(self):
        with mock.patch.object(setup.platform, "system", return_value="Linux"):
            ids = [item["id"] for item in setup.requirements()]
        self.assertEqual(ids, ["python", "ffmpeg", "whisper", "whisper-model", "fonts", "chrome"])
        # Les étapes Cadrage et Finition sont parties : plus de Node, d'HyperFrames ni d'ImageMagick.
        for gone in ("node", "hyperframes", "imagemagick", "deep-filter", "claude"):
            self.assertNotIn(gone, ids)

    def test_homebrew_is_asked_for_on_a_mac_only(self):
        with mock.patch.object(setup.platform, "system", return_value="Darwin"):
            self.assertEqual(setup.requirements()[0]["id"], "homebrew")
        with mock.patch.object(setup.platform, "system", return_value="Linux"):
            self.assertNotIn("homebrew", [item["id"] for item in setup.requirements()])

    def test_missing_tools_are_reported_not_hidden(self):
        from studio import encadre
        with mock.patch.object(setup.media, "_tool", return_value=None), \
             mock.patch.object(setup.media, "_installed_fonts", return_value=[]), \
             mock.patch.object(encadre, "chrome_binary", side_effect=setup.media.MediaError("absent")), \
             mock.patch.object(setup.Path, "is_dir", return_value=False), \
             mock.patch.object(setup.Path, "is_file", return_value=False):
            report = setup.report()
        by_id = {item["id"]: item for item in report["requirements"]}
        for key in ("ffmpeg", "whisper", "whisper-model", "fonts", "chrome"):
            self.assertFalse(by_id[key]["available"], key)
        self.assertLess(report["ready"], report["required"])

    def test_script_and_prompt_share_the_same_sources(self):
        script, prompt = setup.install_script(REPO), setup.install_prompt(REPO)
        for text in (script, prompt):
            self.assertIn("brew install python ffmpeg whisper-cpp", text)
            self.assertIn(setup.WHISPER_MODEL_URL, text)
            self.assertIn(REPO["url"], text)
            self.assertIn("feat/test", text)
            self.assertIn("ZTNature", text)
            self.assertIn("google-chrome", text)
            for gone in ("npm ci", "hyperframes", "imagemagick", "deep-filter", "LUT"):
                self.assertNotIn(gone, text)
        self.assertIn(str(setup.WHISPER_MODEL_BYTES), prompt)
        self.assertIn("set -e", script)
        self.assertIn("studio doctor", script)

    def test_the_whisper_model_is_only_trusted_when_it_is_whole(self):
        items = {item["id"]: item for item in setup.requirements()}
        model = items["whisper-model"]
        self.assertIn("curl -L --fail", model["install"])
        with mock.patch.object(setup.Path, "is_file", return_value=False):
            self.assertFalse({i["id"]: i for i in setup.requirements()}["whisper-model"]["available"])


class DoctorCommandTests(unittest.TestCase):
    def test_doctor_reports_the_full_checklist_and_fails_when_a_required_tool_is_missing(self):
        import io, contextlib, sys as _sys
        from studio import __main__ as cli
        items = [
            {"id": "ffmpeg", "label": "FFmpeg", "group": "Médias", "required": True, "available": True,
             "detail": "", "install": "brew install ffmpeg"},
            {"id": "whisper", "label": "whisper.cpp", "group": "Transcription", "required": True,
             "available": False, "detail": "absent", "install": "brew install whisper-cpp"},
            {"id": "fonts", "label": "Polices ZT Nature", "group": "Marque", "required": False,
             "available": False, "detail": "", "install": ""},
        ]
        out = io.StringIO()
        with mock.patch.object(setup, "requirements", return_value=items), \
             mock.patch.object(_sys, "argv", ["studio", "doctor"]), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as stop:
                cli.main()
        self.assertEqual(stop.exception.code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["missing"], ["whisper.cpp"])
        self.assertEqual([r["label"] for r in report["requirements"]],
                         ["FFmpeg", "whisper.cpp", "Polices ZT Nature"])


if __name__ == "__main__":
    unittest.main()
