# SPDX-License-Identifier: GPL-3.0-or-later
"""Material install risks: ownership, upgrade, rollback, paths, preservation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("bim3117_install_support_tests", Path(__file__).resolve().parents[1] / "install_support.py")
install_support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_support)


class InstallSupportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "ชุดติดตั้ง 3117"
        self.source.mkdir()
        self.user = self.root / "ข้อมูล FreeCAD"
        self.user.mkdir()
        self.workbench = self.source / "workbench"
        self.workbench.mkdir()
        (self.workbench / "Init.py").write_text("# synthetic test workbench\n")
        (self.workbench / "InitGui.py").write_text("# version one\n")
        (self.workbench / "package.xml").write_text('<package><name>BIM3117</name><version>0.1.0</version></package>')
        (self.source / "LICENSE").write_text("Synthetic test fixture license")
        (self.source / "THIRD_PARTY.md").write_text("No bundled dependencies in test fixture")
        self.target = self.user / "Mod" / "BIM3117"

    def test_first_install_in_unicode_path_has_identity_and_licenses(self):
        result = install_support.install(self.source, self.user)
        self.assertEqual(Path(result["target"]), self.target)
        self.assertIsNone(result["backup"])
        receipt = install_support.installed_info(self.target)
        self.assertEqual(receipt["project_id"], install_support.PROJECT_ID)
        self.assertIn("InitGui.py", receipt["sha256"])
        self.assertTrue((self.target / "LICENSE").is_file())

    def test_unowned_existing_directory_is_not_modified(self):
        self.target.mkdir(parents=True)
        keep = self.target / "project.FCStd"
        keep.write_bytes(b"valuable project fixture")
        with self.assertRaises(install_support.InstallError):
            install_support.install(self.source, self.user)
        self.assertEqual(keep.read_bytes(), b"valuable project fixture")
        self.assertEqual(list(self.target.iterdir()), [keep])

    def test_upgrade_preserves_old_files_outside_mod(self):
        install_support.install(self.source, self.user)
        (self.target / "user_note.txt").write_text("keep this")
        (self.workbench / "InitGui.py").write_text("# version two\n")
        result = install_support.install(self.source, self.user)
        backup = Path(result["backup"])
        self.assertEqual(backup.parent, self.user / "BIM3117_Backups")
        self.assertEqual((backup / "user_note.txt").read_text(), "keep this")
        self.assertEqual((backup / "InitGui.py").read_text(), "# version one\n")
        self.assertEqual((self.target / "InitGui.py").read_text(), "# version two\n")

    def test_failed_promotion_restores_previous_installation(self):
        install_support.install(self.source, self.user)
        previous = (self.target / install_support.RECEIPT_NAME).read_bytes()
        original = Path.replace

        def fail_stage(path, target):
            if path.name.startswith("BIM3117-stage-"):
                raise OSError("simulated promotion failure")
            return original(path, target)

        with patch.object(Path, "replace", fail_stage), self.assertRaises(OSError):
            install_support.install(self.source, self.user)
        self.assertEqual((self.target / install_support.RECEIPT_NAME).read_bytes(), previous)
        self.assertEqual(list(self.user.glob("BIM3117-stage-*")), [])
        self.assertFalse((self.user / "BIM3117-install.lock").exists())

    def test_uninstall_and_restore_preserve_files(self):
        install_support.install(self.source, self.user)
        project = self.user / "example.FCStd"
        project.write_bytes(b"unrelated document")
        result = install_support.uninstall(self.user)
        self.assertFalse(self.target.exists())
        backup = Path(result["backup"])
        self.assertTrue((backup / "Init.py").is_file())
        self.assertEqual(project.read_bytes(), b"unrelated document")
        install_support.restore(self.user, backup.name)
        self.assertTrue((self.target / "Init.py").is_file())
        self.assertFalse(backup.exists())

    def test_restore_rejects_path_traversal(self):
        for value in ("../other", "..", "/absolute", "C:\\outside", "folder/file"):
            with self.subTest(value=value), self.assertRaises(install_support.InstallError):
                install_support.restore(self.user, value)

    def test_linked_payload_is_rejected_without_touching_target(self):
        outside = self.root / "outside.py"
        outside.write_text("# not part of package")
        try:
            (self.workbench / "linked.py").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links are unavailable in this test environment")
        with self.assertRaises(install_support.InstallError):
            install_support.install(self.source, self.user)
        self.assertFalse(self.target.exists())

    def test_concurrent_install_lock_blocks_changes(self):
        lock = self.user / "BIM3117-install.lock"
        lock.write_text("existing installer")
        with self.assertRaises(install_support.InstallError):
            install_support.install(self.source, self.user)
        self.assertEqual(lock.read_text(), "existing installer")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
