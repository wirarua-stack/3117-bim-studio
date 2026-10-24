# SPDX-License-Identifier: GPL-3.0-or-later
import json
import math
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from bim3117 import BuildingDocument, ModelError
from bim3117.demo import create_demo


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.doc = create_demo()
        self.wall = next(iter(self.doc.walls))
        self.typ = next(iter(self.doc.wall_types))
        self.door = next(iter(self.doc.doors))

    def test_quantities_deduct_once(self):
        rows = self.doc.quantities()
        self.assertAlmostEqual(sum(x["gross_volume_m3"] for x in rows), 12.0)
        self.assertAlmostEqual(sum(x["net_volume_m3"] for x in rows), 11.622)

    def test_shared_type_update_undo_redo(self):
        with self.doc.transaction("Change all walls"):
            self.doc.update(self.typ, thickness=0.3)
        self.assertTrue(all(x["thickness_m"] == 0.3 for x in self.doc.quantities()))
        self.assertAlmostEqual(sum(x["net_volume_m3"] for x in self.doc.quantities()), 17.433)
        self.doc.undo()
        self.assertEqual(self.doc.wall_types[self.typ].thickness, 0.2)
        self.doc.redo()
        self.assertEqual(self.doc.wall_types[self.typ].thickness, 0.3)

    def test_failed_transaction_rolls_back_every_edit(self):
        before = self.doc.to_dict()
        revision = self.doc.revision
        with self.assertRaises(ModelError):
            with self.doc.transaction("Invalid edit"):
                self.doc.update(self.typ, thickness=0.5)
                self.doc.update(self.door, width=100)
        self.assertEqual(before, self.doc.to_dict())
        self.assertEqual(revision, self.doc.revision)

    def test_bad_numbers_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ModelError):
                with self.doc.transaction("Bad thickness"):
                    self.doc.update(self.typ, thickness=value)

    def test_door_rejects_missing_host_and_outside_dimensions(self):
        for changes in ({"host_id": "missing"}, {"offset": -1}, {"sill": 2}, {"width": 9}):
            with self.subTest(changes=changes), self.assertRaises(ModelError):
                with self.doc.transaction("Bad door"):
                    self.doc.update(self.door, **changes)

    def test_overlap_rejected(self):
        with self.assertRaises(ModelError):
            with self.doc.transaction("Overlapping opening"):
                self.doc.add_door("Overlap", self.wall, 1.5, 1, 2)
        self.assertEqual(len(self.doc.doors), 1)

    def test_host_deletion_has_no_orphan(self):
        with self.assertRaises(ModelError):
            with self.doc.transaction("Delete host"):
                self.doc.remove(self.wall)
        with self.doc.transaction("Explicit deletion"):
            self.doc.remove(self.door)
            self.doc.remove(self.wall)
        self.assertEqual(len(self.doc.walls), 3)
        self.assertFalse(self.doc.doors)
        self.doc.undo()
        self.assertIn(self.wall, self.doc.walls)
        self.assertIn(self.door, self.doc.doors)

    def test_level_height_constraint_updates_quantities(self):
        upper = self.doc.walls[self.wall].top_level_id
        with self.doc.transaction("Raise storey"):
            self.doc.update(upper, elevation=4)
        self.assertTrue(all(x["height_m"] == 4 for x in self.doc.quantities()))
        self.assertAlmostEqual(sum(x["gross_volume_m3"] for x in self.doc.quantities()), 16)

    def test_wrong_level_causes_atomic_rollback(self):
        upper = self.doc.walls[self.wall].top_level_id
        with self.assertRaises(ModelError):
            with self.doc.transaction("Lower below door"):
                self.doc.update(upper, elevation=1)
        self.assertEqual(self.doc.levels[upper].elevation, 3)

    def test_immutable_records_and_transaction_requirement(self):
        with self.assertRaises(ModelError):
            self.doc.update(self.typ, thickness=0.4)
        with self.assertRaises(TypeError):
            self.doc.walls[self.wall] = None
        with self.assertRaises(AttributeError):
            self.doc.walls[self.wall].height = 5
        with self.assertRaises(AttributeError):
            self.doc.id = "new-identity"
        with self.assertRaises(AttributeError):
            self.doc.name = "outside-transaction"

    def test_new_edit_clears_redo(self):
        with self.doc.transaction("One"):
            self.doc.update(self.typ, thickness=0.3)
        self.doc.undo()
        with self.doc.transaction("Two"):
            self.doc.update(self.typ, thickness=0.4)
        self.assertFalse(self.doc.redo())

    def test_json_roundtrip_preserves_identity_and_rejects_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            self.doc.save(path)
            restored = BuildingDocument.load(path)
            self.assertEqual(self.doc.to_dict(), restored.to_dict())
            self.assertEqual(self.doc.quantities(), restored.quantities())
            self.assertFalse(restored.undo())
            data = json.loads(path.read_text())
            data["schema_version"] = 99
            path.write_text(json.dumps(data))
            with self.assertRaises(ModelError):
                BuildingDocument.load(path)

    def test_duplicate_uuid_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            data = self.doc.to_dict()
            data["walls"].append(dict(data["walls"][0]))
            path.write_text(json.dumps(data))
            with self.assertRaises(ModelError):
                BuildingDocument.load(path)

    def test_json_types_cannot_regenerate_identity_or_accept_boolean_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            for key, value in (("schema_version", True), ("schema_version", 1.0),
                               ("document_id", None), ("document_id", ""), ("walls", {})):
                with self.subTest(key=key, value=value):
                    data = self.doc.to_dict()
                    data[key] = value
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ModelError):
                        BuildingDocument.load(path)

    def test_json_bad_shape_and_unknown_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            invalid = [[], {**self.doc.to_dict(), "unknown_metadata": 1}]
            data = self.doc.to_dict()
            data["walls"][0]["start"] = None
            invalid.append(data)
            for value in invalid:
                with self.subTest(value=type(value).__name__):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ModelError):
                        BuildingDocument.load(path)

    def test_derived_overflow_rolls_back(self):
        before = self.doc.to_dict()
        with self.assertRaises(ModelError):
            with self.doc.transaction("Finite inputs causing derived overflow"):
                self.doc.update(self.wall, end=(1e308, 0))
        self.assertEqual(self.doc.to_dict(), before)

    def test_failed_save_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            self.doc.save(path)
            original = path.read_bytes()
            with self.doc.transaction("Unsaved change"):
                self.doc.update(self.typ, thickness=0.3)
            with patch("bim3117.io.os.replace", side_effect=OSError("Replacement denied")):
                with self.assertRaises(OSError):
                    self.doc.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            restored = BuildingDocument.load(path)
            self.assertEqual(restored.wall_types[self.typ].thickness, 0.2)


if __name__ == "__main__":
    unittest.main()
