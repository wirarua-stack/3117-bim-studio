"""Test isolated fsync repair against the actual frozen module, never edit it."""
import importlib.util
from pathlib import Path
import tempfile
from unittest import TestCase, main, mock

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
SPEC = importlib.util.spec_from_file_location("export_candidate", HERE / "export_fsync_candidate.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)
FROZEN = KIT / "inputs/3117-bim-studio"

class CandidateTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = (FROZEN / tool.RELATIVE).read_bytes()
        self.result = tool.candidate(FROZEN, self.root / "candidate")
        module_spec = importlib.util.spec_from_file_location("candidate_export", self.result["candidate_path"])
        self.module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(self.module)
        self.folder = self.root / "outputs"
        self.folder.mkdir()
        self.paths = [self.folder / "one.csv", self.folder / "metadata.json"]

    def tearDown(self):
        self.assertEqual((FROZEN / tool.RELATIVE).read_bytes(), self.original)

    def writer(self, staged):
        for index, path in enumerate(staged):
            path.write_text(f"new-{index}", encoding="utf-8")

    def test_candidate_retains_fsync_and_frozen_module(self):
        candidate = Path(self.result["candidate_path"]).read_text(encoding="utf-8")
        self.assertIn('path.open("r+b")', candidate)
        self.assertIn('os.fsync(file.fileno())', candidate)
        self.assertTrue(self.result["frozen_unchanged"])

    def test_successful_publication_keeps_metadata_last_and_cleans_locks(self):
        self.module.publish_bundle(self.paths, self.writer)
        self.assertEqual([p.read_text() for p in self.paths], ["new-0", "new-1"])
        self.assertFalse(list(self.folder.glob("*.3117-export.lock")))
        self.assertFalse(list(self.folder.glob(".3117-export-*")))

    def test_fsync_failure_aborts_without_publishing_any_file(self):
        for path in self.paths:
            path.write_text("old", encoding="utf-8")
        with mock.patch.object(self.module.os, "fsync", side_effect=OSError("simulated sync failure")):
            with self.assertRaisesRegex(OSError, "simulated sync failure"):
                self.module.publish_bundle(self.paths, self.writer, overwrite=True)
        self.assertEqual([p.read_text() for p in self.paths], ["old", "old"])
        self.assertFalse(list(self.folder.glob("*.3117-export.lock")))
        self.assertFalse(list(self.folder.glob(".3117-export-*")))

    def test_candidate_refuses_existing_output_and_frozen_overwrite(self):
        with self.assertRaises(FileExistsError):
            tool.candidate(FROZEN, self.root / "candidate")
        with self.assertRaises(RuntimeError):
            tool.candidate(FROZEN, FROZEN)

if __name__ == "__main__":
    main()
