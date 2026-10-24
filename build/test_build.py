"""Offline checks for build guards; none execute Windows or FreeCAD."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import build_freecad as build


class BuildGuardTests(unittest.TestCase):
    def test_reviewed_patch_and_asset_pins_are_complete(self):
        lock = json.loads(build.LOCK_PATH.read_text())
        self.assertEqual(build.verify_locks(lock)["status"], "locks_verified_only")
        self.assertEqual(lock["source_commit"], "4fd3bf320d9566a27e60069fc8387448aaa3a094")

    def test_download_cache_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "artifact.zip"
            p.write_bytes(b"good")
            item = {"filename": p.name, "sha256": build.sha(p), "bytes": 4,
                    "url": "https://invalid.example/not-used"}
            p.write_bytes(b"evil")
            with self.assertRaisesRegex(RuntimeError, "Pinned file check failed"):
                build.download(item, Path(directory))

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escaped.txt", "invalid")
            with self.assertRaisesRegex(RuntimeError, "Unsafe ZIP path"):
                build.extract_zip(archive, root / "unpack")
            self.assertFalse((root / "escaped.txt").exists())

    def test_release_bindings_cannot_be_satisfied_by_debug_defines(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "FreeCADGui.vcxproj"
            p.write_text('''<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
              <PropertyGroup><WindowsTargetPlatformVersion>10.0.26100.0</WindowsTargetPlatformVersion></PropertyGroup>
              <ItemDefinitionGroup Condition="Debug|x64"><ClCompile><PreprocessorDefinitions>HAVE_PYSIDE6;HAVE_SHIBOKEN6</PreprocessorDefinitions></ClCompile></ItemDefinitionGroup>
              <ItemDefinitionGroup Condition="Release|x64"><ClCompile><PreprocessorDefinitions>NDEBUG</PreprocessorDefinitions></ClCompile></ItemDefinitionGroup>
            </Project>''')
            with self.assertRaisesRegex(RuntimeError, "lacks compiled"):
                build.binding_definitions(p)
            p.write_text(p.read_text().replace("<PreprocessorDefinitions>NDEBUG", "<PreprocessorDefinitions>HAVE_PYSIDE6;HAVE_SHIBOKEN6;NDEBUG"))
            result = build.binding_definitions(p)
            self.assertEqual(result["windows_sdk_version"], "10.0.26100.0")

    def test_non_pe_cannot_be_attested_as_windows_host(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "FreeCAD.exe"
            p.write_bytes(b"\x7fELF" + b"\0" * 128)
            with self.assertRaisesRegex(RuntimeError, "Not a Windows PE"):
                build.check_pe_x64(p)

    def test_timeout_still_kills_owned_process_if_tree_cleanup_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            process = mock.Mock(pid=42)
            process.wait.side_effect = [subprocess.TimeoutExpired(["cmake.exe"], 1), 1]
            process.poll.return_value = None
            with mock.patch.object(build.subprocess, "Popen", return_value=process), \
                 mock.patch.object(build.subprocess, "run", side_effect=subprocess.TimeoutExpired(["taskkill.exe"], 30)):
                with self.assertRaisesRegex(RuntimeError, "bounded owned-process cleanup"):
                    build.run(["cmake.exe"], log, timeout=1)
            process.kill.assert_called_once_with()
            evidence = json.loads(log.with_suffix(".cleanup.json").read_text())
            self.assertFalse(evidence["tree_termination_confirmed"])
            self.assertEqual(evidence["owned_process_exit_code"], 1)

    @unittest.skipIf(sys.platform == "win32", "The Linux platform guard is exercised only on Linux")
    def test_linux_attempt_refuses_before_creating_workroot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            result = subprocess.run([sys.executable, str(Path(build.__file__)), "--work-root", str(output),
                                     "--variant", "patched"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Native Windows AMD64 execution is required", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
