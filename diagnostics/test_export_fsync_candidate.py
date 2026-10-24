"""Isolated candidate validation; does not certify Windows host acceptance."""
import importlib.util
from pathlib import Path
import tempfile
from unittest import TestCase, main, mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("export_candidate", HERE/"export_fsync_candidate.py")
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

class CandidateTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        source=self.root/"frozen"/tool.RELATIVE
        source.parent.mkdir(parents=True)
        source.write_text("import os\nfrom pathlib import Path\n" + tool.OLD,encoding="utf-8")
        self.source=source
        self.result=tool.candidate(self.root/"frozen",self.root/"candidate")
        target=Path(self.result["candidate_path"])
        spec=importlib.util.spec_from_file_location("candidate_export",target)
        self.module=importlib.util.module_from_spec(spec)
        # Source fixture tests contextual replacement without executing top-level fragment.
        self.content=target.read_text(encoding="utf-8")

    def test_frozen_unmodified_and_candidate_uses_readwrite_descriptor(self):
        self.assertIn('path.open("rb")', self.source.read_text())
        self.assertIn('path.open("r+b")',self.content)
        self.assertIn('os.fsync(file.fileno())',self.content)
        self.assertTrue(self.result["frozen_unchanged"])

    def test_rejects_overwrite(self):
        with self.assertRaises(FileExistsError):
            tool.candidate(self.root/"frozen",self.root/"candidate")

    def test_rejects_inplace_mutation(self):
        with self.assertRaises(RuntimeError):
            tool.candidate(self.root/"frozen",self.root/"frozen")

if __name__=="__main__":
    main()
