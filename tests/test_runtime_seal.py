import json
from pathlib import Path
import tempfile
import unittest

import sys
KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
import seal_accepted_runtime


class RuntimeSealTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        build = root / "hosts/patched/build"
        for family in seal_accepted_runtime.RUNTIME_FAMILIES:
            directory = build / family
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{family.lower()}.dat").write_bytes((family + "-accepted").encode())
        manifest = root / "hosts/patched/host-manifest.json"
        manifest.write_text(json.dumps({"variant": "patched", "host_root": str(build)}), encoding="utf-8")
        report = root / "WINDOWS_ACCEPTANCE.json"
        report.write_text(json.dumps({
            "status": "passed",
            "windows_automated_acceptance_passed": True,
            "release_ready": False,
        }), encoding="utf-8")
        return temporary, root, build, manifest, report

    def test_seals_only_exact_tested_runtime(self):
        temporary, root, _, _, _ = self.fixture()
        self.addCleanup(temporary.cleanup)
        output = seal_accepted_runtime.seal(root, run_id="1", run_attempt="2", source_commit="abc")
        value = json.loads(output.read_text())
        self.assertFalse(value["release_ready"])
        self.assertEqual(value["source_commit"], "abc")
        self.assertEqual(len(value["files"]), len(seal_accepted_runtime.RUNTIME_FAMILIES))
        self.assertEqual(value["runtime_root"], "hosts/patched/build")
        self.assertTrue(all("\\" not in item["path"] for item in value["files"]))

    def test_rejects_failed_or_release_ready_report(self):
        temporary, root, _, _, report = self.fixture()
        self.addCleanup(temporary.cleanup)
        value = json.loads(report.read_text())
        value["status"] = "failed"
        report.write_text(json.dumps(value))
        with self.assertRaises(RuntimeError):
            seal_accepted_runtime.seal(root)
        value["status"] = "passed"
        value["release_ready"] = True
        report.write_text(json.dumps(value))
        with self.assertRaises(RuntimeError):
            seal_accepted_runtime.seal(root)

    def test_rejects_manifest_pointing_at_another_build(self):
        temporary, root, _, manifest, _ = self.fixture()
        self.addCleanup(temporary.cleanup)
        other = root / "other-build"
        other.mkdir()
        manifest.write_text(json.dumps({"variant": "patched", "host_root": str(other)}))
        with self.assertRaises(RuntimeError):
            seal_accepted_runtime.seal(root)


if __name__ == "__main__":
    unittest.main()
