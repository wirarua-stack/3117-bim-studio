"""Offline checks of Windows runner safeguards, not Windows host acceptance."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
import prepare_ifc
import run_public_gui as public


class PublicEvidenceGateTests(unittest.TestCase):
    def report(self, count):
        return {"status": "passed", "checks_passed": count,
                "checks": [{"name": str(i), "status": "passed"} for i in range(count)],
                "zip_sha256": public.FROZEN_ZIP_SHA256, "gui_checks_passed": 24}

    def test_clean_exit_cannot_replace_inner_assertions(self):
        good, reasons = public.validate_stage(self.report(7), {}, {"exit_code": 0, "timed_out": False}, 24, 7)
        self.assertFalse(good)
        self.assertTrue(any("Public GUI" in reason for reason in reasons))

    def test_claimed_count_does_not_hide_failed_inner_check(self):
        inner = self.report(24)
        inner["checks"][12]["status"] = "failed"
        good, _ = public.validate_stage(self.report(7), inner, {"exit_code": 0}, 24, 7)
        self.assertFalse(good)

    def test_native_process_crash_rejects_a_completed_report(self):
        good, _ = public.validate_stage(self.report(7), self.report(24), {"exit_code": 0xC0000005}, 24, 7)
        self.assertFalse(good)

    def test_timeout_and_zero_exit_are_not_accepted(self):
        good, _ = public.validate_stage(self.report(7), self.report(24), {"exit_code": 0, "timed_out": True}, 24, 7)
        self.assertFalse(good)

    def test_installer_success_does_not_count_as_gui_model_tests(self):
        good, _ = public.validate_stage(self.report(6), self.report(24), {"exit_code": 0}, 0, 6)
        self.assertFalse(good)

    def test_summary_totals_cannot_bypass_missing_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "summary.json"
            path.write_text(json.dumps({"schema": 1, "status": "passed", "platform": "windows",
                                        "stages": [], "public_gui_checks_passed": 248, "packaging_checks_passed": 48}))
            self.assertEqual(public.verify_summary(path)["status"], "failed")

    @unittest.skipIf(os.name == "nt", "This check specifically exercises non-Windows rejection")
    def test_linux_controller_cannot_create_a_windows_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new-run"
            process = subprocess.run([sys.executable, str(KIT / "scripts/run_public_gui.py"),
                                      "--host", str(Path(folder) / "FreeCAD.exe"), "--ifc-python-path", folder,
                                      "--output", str(output)], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(process.returncode, 0)
            report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "not_executed")
            self.assertFalse(report["host_executed"])
            self.assertEqual(report["stages"], [])

    def test_frozen_archive_extracts_and_revalidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = public.checked_package(KIT / "inputs/3117_BIM_Studio_v0_5_0_FreeCAD.zip", Path(folder) / "แตกไฟล์")
            macro = root / public.STAGES[1][1]
            macro.write_bytes(macro.read_bytes() + b"\n# changed\n")
            with self.assertRaisesRegex(RuntimeError, "differs"):
                public.checked_package(KIT / "inputs/3117_BIM_Studio_v0_5_0_FreeCAD.zip", Path(folder) / "แตกไฟล์")

    def test_generated_autopilot_preserves_all_assertion_predicates(self):
        original = (KIT / "inputs/package-gui/package_autopilot.FCMacro").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "autopilot.FCMacro"
            record = public.make_windows_autopilot(output, Path(folder) / "ไทย", Path(folder) / "ifc")
            generated = output.read_text(encoding="utf-8")
            def predicates(source):
                tree = ast.parse(source)
                return [ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_package_check"]
            self.assertEqual(predicates(original), predicates(generated))
            self.assertEqual(len(predicates(original)), 11)
            self.assertTrue(record["assertions_and_handlers_equal_after_utf8_io_normalization"])
            self.assertNotIn("/proc/self", generated)
            self.assertNotIn("XDG_DATA_HOME", generated)


class IsolatedWheelTests(unittest.TestCase):
    def test_downloaded_wheels_cannot_pass_runtime_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "ifc-preflight.json"
            report.write_text(json.dumps({"status": "prepared_only", "host_executed": False,
                                          "platform": "windows", "wheels": [{"sha256": "claimed"}]}))
            self.assertEqual(prepare_ifc.verify_preflight(report)["status"], "failed")

    def test_generated_probe_preserves_paths_with_marker_words(self):
        source = prepare_ifc.probe_source(Path("C:/SCRIPTS ไทย"), Path("C:/RUNTIME PROFILE"),
                                          Path("C:/profile folder"), Path("C:/REPORT.json"))
        tree = ast.parse(source)
        bindings = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body[:4]}
        self.assertEqual(bindings["RUNTIME"], "C:/RUNTIME PROFILE")
        self.assertEqual(bindings["SCRIPTS"], "C:/SCRIPTS ไทย")

    def test_lock_targets_embedded_python_and_excludes_qt_numpy(self):
        lock = prepare_ifc.load_lock()
        self.assertEqual(lock["target"]["python"], [3, 12])
        self.assertFalse({"numpy", "pyside6", "pyqt6", "shiboken6"} & {row["package"] for row in lock["packages"]})

    def test_windows_aliases_and_traversal_are_rejected(self):
        for name in ["../escape.py", "C:/escape.py", "pkg/a.py:payload", "\\server\\file", "pkg/NUL.txt", "pkg/COM1.py", "pkg/trailing. /x", "/tmp/x"]:
            with self.subTest(name=name):
                self.assertFalse(prepare_ifc.safe_member(name))

    def test_wheel_cannot_install_pth_startup_code(self):
        with tempfile.TemporaryDirectory() as folder:
            wheel = Path(folder) / "fixture.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("startup.pth", "import invented_payload")
            with self.assertRaisesRegex(RuntimeError, "outside explicit"):
                prepare_ifc.extract_wheel(wheel, Path(folder) / "runtime")

    def test_wheel_does_not_overwrite_runtime_files(self):
        with tempfile.TemporaryDirectory() as folder:
            wheel = Path(folder) / "fixture.whl"
            target = Path(folder) / "runtime"
            target.mkdir()
            (target / "module.py").write_text("existing")
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("module.py", "replacement")
            with self.assertRaisesRegex(RuntimeError, "replace"):
                prepare_ifc.extract_wheel(wheel, target)
            self.assertEqual((target / "module.py").read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
