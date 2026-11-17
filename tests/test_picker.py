from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from studio import picker


class PickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        for name in ("Downloads", "Desktop/Rushs"):
            (self.home / name).mkdir(parents=True)
        self.root = Path(self.tmp.name) / "data"; self.root.mkdir()
        patcher = mock.patch.object(picker.Path, "home", return_value=self.home); patcher.start(); self.addCleanup(patcher.stop)

    def test_first_opening_is_downloads_then_the_last_folder(self):
        self.assertEqual(picker.default_directory(self.root, "video"), self.home / "Downloads")
        rush = self.home / "Desktop/Rushs/camera.mp4"; rush.write_bytes(b"x")
        picker.remember(self.root, "video", rush)
        self.assertEqual(picker.default_directory(self.root, "video"), self.home / "Desktop/Rushs")
        self.assertEqual(picker.default_directory(self.root, "autre"), self.home / "Downloads")

    def test_an_unreadable_memory_file_is_ignored(self):
        picker.memory_path(self.root).write_text("{ cassé", encoding="utf-8")
        self.assertEqual(picker.default_directory(self.root, "video"), self.home / "Downloads")

    def test_deleted_folder_falls_back_to_downloads(self):
        gone = self.home / "Desktop/Ancien"; gone.mkdir(); (gone / "a.mov").write_bytes(b"x")
        picker.remember(self.root, "video", gone / "a.mov"); (gone / "a.mov").unlink(); gone.rmdir()
        self.assertEqual(picker.default_directory(self.root, "video"), self.home / "Downloads")

    def test_labels_are_human(self):
        self.assertEqual(picker.folder_label(self.home / "Downloads"), "Téléchargements")
        self.assertEqual(picker.folder_label(self.home / "Desktop/Rushs"), "Bureau › Rushs")
        self.assertEqual(picker.folder_label(self.home), "Dossier personnel")

    def test_script_filters_type_and_escapes_path(self):
        script = picker.build_script("video", Path('/Users/x/Mes "rushs"'))
        self.assertIn("activate", script)
        self.assertIn('of type {"public.movie"}', script[-1])
        self.assertIn('POSIX file "/Users/x/Mes \\"rushs\\"" as alias', script[-1])

    def test_pick_remembers_choice_and_handles_cancel(self):
        rush = self.home / "Desktop/Rushs/interview.mov"; rush.write_bytes(b"x")
        ok = subprocess.CompletedProcess([], 0, stdout=f"{rush}\n", stderr="")
        cancel = subprocess.CompletedProcess([], 1, stdout="", stderr="execution error: User canceled. (-128)")
        with mock.patch.object(picker.platform, "system", return_value="Darwin"), mock.patch.object(picker.subprocess, "run", return_value=ok) as run:
            result = picker.pick(self.root, "video")
        self.assertIn(str(self.home / "Downloads"), run.call_args.args[0][-1])
        self.assertEqual((result["name"], result["label"]), ("interview.mov", "Bureau › Rushs"))
        with mock.patch.object(picker.platform, "system", return_value="Darwin"), mock.patch.object(picker.subprocess, "run", return_value=cancel):
            self.assertTrue(picker.pick(self.root, "video")["cancelled"])
        self.assertEqual(picker.default_directory(self.root, "video").resolve(), (self.home / "Desktop/Rushs").resolve())

    def test_unknown_kind_and_other_systems_refused(self):
        with self.assertRaises(ValueError): picker.describe(self.root, "pdf")
        with mock.patch.object(picker.platform, "system", return_value="Linux"):
            with self.assertRaises(picker.PickerUnavailable): picker.pick(self.root, "video")


if __name__ == "__main__":
    unittest.main()
