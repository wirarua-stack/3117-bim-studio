# SPDX-License-Identifier: GPL-3.0-or-later
"""Material data-loss cases for multi-file snapshot publication."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "workbench" / "bim3117_freecad" / "export_files.py"
SPEC = importlib.util.spec_from_file_location("bim3117_export_files_test", MODULE_PATH)
files = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(files)


class ExportPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.paths = [self.folder / name for name in ("walls.csv", "walls_doors.csv", "walls_csv_metadata.json")]

    def writer(self, staged):
        for index, path in enumerate(staged):
            path.write_text(f"new-{index}", encoding="utf-8")
        return "validated"

    def originals(self):
        for index, path in enumerate(self.paths):
            path.write_text(f"old-{index}", encoding="utf-8")

    def assert_clean(self):
        self.assertFalse(list(self.folder.glob(".3117-export-*")))
        self.assertFalse(list(self.folder.glob("*.3117-export.lock")))

    def test_metadata_is_published_last_after_source_revision_gate(self):
        original = files.os.replace
        calls = []

        def replace(source, target):
            calls.append(Path(target).name)
            return original(source, target)

        def before_commit():
            self.assertFalse(any(path.exists() for path in self.paths))
            calls.append("revision-checked")

        with mock.patch.object(files.os, "replace", replace):
            result = files.publish_bundle(self.paths, self.writer, before_commit=before_commit)
        self.assertEqual(result, "validated")
        self.assertEqual(calls, ["revision-checked"] + [path.name for path in self.paths])
        self.assertEqual([path.read_text() for path in self.paths], ["new-0", "new-1", "new-2"])
        self.assert_clean()

    def test_overwrite_requires_explicit_opt_in_for_any_sidecar(self):
        self.paths[1].write_text("keep sidecar")
        with self.assertRaises(files.ExportFileError):
            files.publish_bundle(self.paths, self.writer)
        self.assertEqual(self.paths[1].read_text(), "keep sidecar")
        self.assertFalse(self.paths[0].exists())
        self.assert_clean()

    def test_writer_failure_does_not_replace_existing_files(self):
        self.originals()

        def failed_writer(staged):
            staged[0].write_text("incomplete")
            raise RuntimeError("IFC readback validation failed")

        with self.assertRaises(RuntimeError):
            files.publish_bundle(self.paths, failed_writer, overwrite=True)
        self.assertEqual([path.read_text() for path in self.paths], ["old-0", "old-1", "old-2"])
        self.assert_clean()

    def test_source_changed_before_commit_leaves_existing_files_intact(self):
        self.originals()

        def changed():
            raise ValueError("source changed")

        with self.assertRaisesRegex(ValueError, "source changed"):
            files.publish_bundle(self.paths, self.writer, overwrite=True, before_commit=changed)
        self.assertEqual([path.read_text() for path in self.paths], ["old-0", "old-1", "old-2"])
        self.assert_clean()

    def test_second_replace_failure_restores_existing_bundle(self):
        self.originals()
        original = files.os.replace
        count = 0

        def replace(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated disk failure")
            return original(source, target)

        with mock.patch.object(files.os, "replace", replace), self.assertRaises(OSError):
            files.publish_bundle(self.paths, self.writer, overwrite=True)
        self.assertEqual([path.read_text() for path in self.paths], ["old-0", "old-1", "old-2"])
        self.assert_clean()

    def test_metadata_replace_failure_removes_new_payloads(self):
        original = files.os.replace

        def replace(source, target):
            if Path(target) == self.paths[-1]:
                raise OSError("metadata publication failed")
            return original(source, target)

        with mock.patch.object(files.os, "replace", replace), self.assertRaises(OSError):
            files.publish_bundle(self.paths, self.writer)
        self.assertFalse(any(path.exists() for path in self.paths))
        self.assert_clean()

    def test_existing_lock_is_not_removed_by_another_exporter(self):
        lock = self.paths[0].with_name(self.paths[0].name + ".3117-export.lock")
        lock.write_text("another process owns this")
        with self.assertRaises(files.ExportFileError):
            files.publish_bundle(self.paths, self.writer)
        self.assertEqual(lock.read_text(), "another process owns this")
        self.assertFalse(any(path.exists() for path in self.paths))

    def test_overlapping_sidecar_is_locked_even_with_different_main_file(self):
        # Another exporter chose our doors sidecar as its principal output.
        locked = self.paths[1].with_name(self.paths[1].name + ".3117-export.lock")
        locked.write_text("owned by the overlapping exporter")
        with self.assertRaises(files.ExportFileError):
            files.publish_bundle(self.paths, self.writer)
        self.assertFalse(any(path.exists() for path in self.paths))
        self.assertEqual(list(self.folder.glob("*.3117-export.lock")), [locked])
        self.assertEqual(locked.read_text(), "owned by the overlapping exporter")

    def test_symlink_destination_does_not_replace_unrelated_target(self):
        target = self.folder / "unrelated.txt"
        target.write_text("preserve")
        try:
            self.paths[0].symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("This environment cannot create symlinks")
        with self.assertRaises(files.ExportFileError):
            files.publish_bundle(self.paths, self.writer, overwrite=True)
        self.assertEqual(target.read_text(), "preserve")
        self.assertTrue(self.paths[0].is_symlink())
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
