"""Controller/gate failure cases. These tests do not execute Windows/FreeCAD."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
sys.dont_write_bytecode = True
import collect_acceptance
import run_acceptance


class ControllerTests(unittest.TestCase):
    def test_empty_run_cannot_become_windows_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = collect_acceptance.collect(Path(temporary))
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["windows_automated_acceptance_passed"])
        self.assertFalse(result["release_ready"])
        self.assertEqual(result["windows_desktop_acceptance"], "pending")
        self.assertEqual(result["gates"]["native_3117"]["status"], "failed")
        self.assertEqual(result["gates"]["public_zip_gui"]["status"], "failed")

    def test_preflight_never_claims_windows_execution(self):
        result = run_acceptance.preflight()
        self.assertEqual(result["frozen_inputs"]["status"], "passed")
        self.assertEqual(result["windows_execution"], "not_executed")
        self.assertFalse(result["release_ready"])

    def test_build_claim_does_not_replace_native_platform_and_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps({"status": "built_not_acceptance_tested", "variant": "patched",
                                        "platform": {"system": "Linux", "machine": "x86_64"}}))
            result = collect_acceptance.validate_build(path, "patched", collect_acceptance.read(KIT / "build/windows-build.lock.json"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("Build did not run on native Windows x64", result["errors"])
        self.assertIn("Host binary inventory is incomplete", result["errors"])

    def test_bad_summary_is_a_failed_gate_not_an_uncaught_success(self):
        def invalid():
            raise KeyError("missing raw report")
        result = collect_acceptance.gate(invalid)
        self.assertEqual(result["status"], "failed")
        self.assertIn("missing raw report", result["errors"][0])

    def test_timeout_still_stops_owned_process_when_tree_cleanup_times_out(self):
        owned = Mock()
        owned.pid = 123
        owned.wait.side_effect = [subprocess.TimeoutExpired(["owned"], 1), 0]
        owned.poll.return_value = None
        journal = {"steps": []}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(run_acceptance.subprocess, "Popen", return_value=owned), \
                 patch.object(run_acceptance.subprocess, "run", side_effect=subprocess.TimeoutExpired(["taskkill"], 30)), \
                 patch.dict(os.environ, {"SystemRoot": "C:\\Windows"}):
                result = run_acceptance.run_step(journal, Path(temporary), "synthetic-timeout", ["owned"], 1)
        self.assertEqual(result, 124)
        owned.kill.assert_called_once()
        self.assertTrue(journal["steps"][0]["timed_out"])
        self.assertFalse(journal["steps"][0]["tree_cleanup_confirmed"])

    @unittest.skipIf(os.name == "nt", "Specifically verifies the non-Windows controller refusal")
    def test_non_windows_controller_retains_blocked_status_and_starts_no_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new-run"
            process = subprocess.run([sys.executable, str(KIT / "scripts/run_acceptance.py"),
                                      "--work-root", str(output)], capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 2, process.stderr.decode(errors="replace"))
            result = collect_acceptance.read(output / "WINDOWS_ACCEPTANCE.json")
            journal = collect_acceptance.read(output / "run.json")
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["windows_automated_acceptance_passed"])
            self.assertEqual(journal["steps"], [])
            self.assertEqual(journal["frozen_inputs_after"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
