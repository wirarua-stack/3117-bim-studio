"""Offline failure-mode checks for the runner, not Windows/FreeCAD results."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
sys.dont_write_bytecode = True
import windows_common as common
import run_native
import run_regression


def identity_fixture(gui=True):
    """Synthetic data only; never written to the acceptance evidence directory."""
    libraries = {name: {"path": "C:\\host\\" + name, "sha256": str(index) * 64}
                 for index, name in enumerate(common.CORE, 1)}
    expected = {"executable": {"path": "C:\\host\\FreeCAD.exe", "sha256": "0" * 64}, "libraries": libraries}
    identity = {"system": "Windows", "native_windows": True, "freecad": ["1", "1", "4"],
                "gui_up": gui, "entry_completed": False, "pid": 42, "stage": "minimal-native",
                "executable": copy.deepcopy(expected["executable"]), "user_data": "C:\\case\\profile\\data",
                "desktop": {"qt_platform": "windows", "screens": [{"width": 1920, "height": 1080}],
                            "window_station_visible": True, "session_id": 1},
                "loaded_library_sha256": {item["path"]: item["sha256"] for item in libraries.values()},
                "module_files": {name: libraries[name + ".pyd"] for name in ("Part", "TechDraw")},
                "addon_modules_at_entry": [], "addon_directories": []}
    return expected, identity


class EvidenceGates(unittest.TestCase):
    def test_loaded_host_identity_rejects_foreign_dll_and_wrong_pid(self):
        expected, identity = identity_fixture()
        ok, errors = common.validate_identity(identity, expected, "C:\\case\\profile", gui=True, expected_pid=42)
        self.assertTrue(ok, errors)
        identity["loaded_library_sha256"]["C:\\another\\FreeCADGui.dll"] = "3" * 64
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True, expected_pid=42)[0])
        identity["loaded_library_sha256"].pop("C:\\another\\FreeCADGui.dll")
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True, expected_pid=43)[0])

    def test_service_and_offscreen_gui_are_not_desktop_acceptance(self):
        expected, identity = identity_fixture()
        identity["desktop"]["qt_platform"] = "offscreen"
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True)[0])
        identity["desktop"]["qt_platform"] = "windows"
        identity["desktop"]["session_id"] = 0
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True)[0])

    def test_foreign_qt_path_and_wrong_version_cannot_use_matching_host_dlls(self):
        expected, identity = identity_fixture()
        expected.update(host_root="C:\\host", expected_qt_version="6.8.3", expected_python_version=[3, 12, 10])
        runtime = {"C:\\host\\" + name: "f" * 64 for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "python312.dll")}
        expected["runtime_libraries"] = [{"path": path, "sha256": digest} for path, digest in runtime.items()]
        identity.update(qt="6.8.3", python_version=[3, 12, 10])
        identity["loaded_library_sha256"].update(runtime)
        self.assertTrue(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True)[0])
        identity["qt"] = "6.8.2"
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True)[0])
        identity["qt"] = "6.8.3"
        identity["loaded_library_sha256"]["C:\\foreign\\Qt6Core.dll"] = "f" * 64
        self.assertFalse(common.validate_identity(identity, expected, "C:\\case\\profile", gui=True)[0])

    def test_success_exit_does_not_replace_completed_checks(self):
        report = {"status": "passed", "checks_passed": 1, "checks": [{"status": "passed"}]}
        self.assertTrue(common.validate_checks(report, 1))
        for mutation in ({"checks_passed": True}, {"checks": []}, {"checks": [{"status": "skipped"}]}, {"status": "running"}):
            candidate = dict(report, **mutation)
            self.assertFalse(common.validate_checks(candidate, 1), candidate)
        self.assertEqual(sum(run_native.EXPECTED_CHECKS.values()), 651)
        self.assertEqual(len(run_native.REPORTS), 19)

    def test_native_crash_is_baseline_observation_not_a_pass(self):
        expected, before = identity_fixture()
        process = {"pid": 42, "returncode": 0xc0000005, "timed_out": False, "launch_error": None}
        result = run_regression.classify_outcome("minimal-native", process, {"status": "running"}, before, {},
                                                 expected, "C:\\case\\profile")
        self.assertEqual(result["status"], "native_crash_observed")
        self.assertTrue(result["baseline_observation_complete"])
        self.assertFalse(result["gate_passed"])
        result = run_regression.classify_outcome("minimal-native", dict(process, timed_out=True), {}, before, {},
                                                 expected, "C:\\case\\profile")
        self.assertEqual(result["status"], "timed_out")
        self.assertFalse(result["baseline_observation_complete"])

    def test_incomplete_original_steps_and_wrong_counts_are_rejected(self):
        report = {"status": "passed", "addon_imported": False, "steps": ["all passed"]}
        self.assertFalse(run_regression.validate_case_report("minimal-native", report))
        report = {"status": "passed", "checks_passed": 126, "checks": [{"status": "passed"}] * 126}
        self.assertFalse(run_regression.validate_case_report("history-invariants", report))
        report["checks"].append({"status": "passed"})
        report["checks_passed"] = 127
        self.assertTrue(run_regression.validate_case_report("history-invariants", report))
        self.assertFalse(run_regression.validate_case_report("history-reopen", report))

    def test_ifc_origin_must_match_both_import_and_loaded_extension(self):
        expected = {"version": "0.8.4", "package": {"path": "C:\\isolated\\ifcopenshell\\__init__.py", "sha256": "a" * 64},
                    "wrapper": {"path": "C:\\isolated\\ifcopenshell\\_ifcopenshell_wrapper.pyd", "sha256": "b" * 64}}
        identity = {"ifcopenshell_version": "0.8.4", "module_files": {"ifcopenshell": expected["package"],
                    "ifcopenshell._ifcopenshell_wrapper": expected["wrapper"]},
                    "loaded_library_sha256": {expected["wrapper"]["path"]: "b" * 64}}
        self.assertTrue(common.validate_ifc(identity, expected))
        identity["loaded_library_sha256"] = {}
        self.assertFalse(common.validate_ifc(identity, expected))
        identity["loaded_library_sha256"] = {expected["wrapper"]["path"]: "b" * 64}
        identity["ifcopenshell_version"] = "0.8.1.post1"
        self.assertFalse(common.validate_ifc(identity, expected))

    def test_raw_summary_verifiers_fail_closed_for_missing_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "summary.json"
            common.write_json(path, {"status": "passed", "platform": "windows", "stages": [], "checks_passed": 651})
            self.assertFalse(run_native.verify_summary(path)["valid"])
            common.write_json(path, {"status": "passed", "platform": "windows", "cases": {}})
            self.assertFalse(run_regression.verify_summary(path)["valid"])


class PortablePreparation(unittest.TestCase):
    def test_profile_directories_exist_and_inherited_qt_python_paths_are_removed(self):
        with tempfile.TemporaryDirectory() as name:
            env = common.profile_env(Path(name) / "โปรไฟล์", gui=True)
            self.assertTrue(all(Path(env[key]).is_dir() for key in ("FREECAD_USER_HOME", "FREECAD_USER_DATA", "FREECAD_USER_TEMP")))
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("PYTHONHOME", env)
            self.assertNotIn("QT_QPA_PLATFORM", env)
            self.assertNotIn("QT_PLUGIN_PATH", env)

    def test_windows_macro_body_is_byte_equal_to_archived_body(self):
        before = common.verify_inputs()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for case in (*run_regression.CASES, "history-reopen", "original-3117-ui-install"):
                install = case.endswith("-install")
                case_name = case.removesuffix("-install")
                output = root / case
                output.mkdir()
                profile = root / "โปรไฟล์"
                expected = run_regression.archived_harness()
                marker = "# BODY BOUNDARY\n"
                expected.macro_header = lambda p, o: marker
                path = expected.write_macro(case_name, profile, output, run_regression.REPOSITORY,
                                             install=install, source_output=root / "source")
                body = path.read_text(encoding="utf-8").removeprefix(marker)
                path = run_regression.make_macro(case_name, profile, output, install=install, source_output=root / "source")
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.endswith(body), case)
                compile(text, str(path), "exec")
                self.assertNotIn("/proc/self", text)
                self.assertNotIn("clearUndos", text)
            entry = run_native.make_entry(root / "scripts", root / "โปรไฟล์", root / "output", root / "test.py", root / "ifc")
            compile(entry, "native-entry.py", "exec")
        self.assertEqual(before, common.verify_inputs())

    @unittest.skipIf(os.name == "nt", "This check specifically exercises the non-Windows refusal")
    def test_linux_execution_records_not_executed_without_starting_host(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for script, extra in (("run_native.py", ["--ifc-python-path", "not-a-runtime"]),
                                   ("run_regression.py", ["--tag", "patched"])):
                output = root / script
                process = subprocess.run([sys.executable, str(KIT / "scripts" / script), "--host", "not-an-executable",
                                          "--output", str(output), *extra], capture_output=True, timeout=20, check=False)
                self.assertEqual(process.returncode, 2, process.stderr.decode())
                report = json.loads((output / "summary.json").read_text())
                self.assertEqual(report["status"], "not_executed")
                self.assertIn("Native Windows", report["error"])
                self.assertFalse(report.get("cases") or report.get("stages"))


if __name__ == "__main__":
    unittest.main()
