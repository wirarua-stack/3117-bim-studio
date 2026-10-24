# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import tempfile
import unittest
from pathlib import Path
from bim3117.demo import create_demo


@unittest.skipUnless(importlib.util.find_spec("ifcopenshell"), "Install the ifc extra for IFC integration tests")
class IfcTests(unittest.TestCase):
    def setUp(self):
        import ifcopenshell
        from bim3117.ifc_export import export_ifc
        self.document = create_demo()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.ifc"
        export_ifc(self.document, self.path)
        self.model = ifcopenshell.open(str(self.path))

    def test_semantics_units_and_host_relations(self):
        import ifcopenshell.util.unit
        import ifcopenshell.util.element
        self.assertEqual(self.model.schema, "IFC4")
        for name, count in (("IfcWall", 4), ("IfcWallType", 1), ("IfcDoor", 1),
                            ("IfcOpeningElement", 1), ("IfcRelVoidsElement", 1),
                            ("IfcRelFillsElement", 1), ("IfcBuildingStorey", 2)):
            self.assertEqual(len(self.model.by_type(name)), count)
        self.assertEqual(ifcopenshell.util.unit.calculate_unit_scale(self.model), 1)
        for wall in self.model.by_type("IfcWall"):
            self.assertEqual(ifcopenshell.util.element.get_type(wall).Name, "W200")
            self.assertEqual(ifcopenshell.util.element.get_container(wall).Name, "L00")
        door = self.model.by_type("IfcDoor")[0]
        self.assertEqual(door.OverallWidth, 0.9)
        self.assertEqual(door.OverallHeight, 2.1)
        opening = door.FillsVoids[0].RelatingOpeningElement
        self.assertEqual(opening.VoidsElements[0].RelatingBuildingElement.Name, "Wall 1")

    def test_reexport_keeps_element_global_ids(self):
        from bim3117 import BuildingDocument
        from bim3117.ifc_export import export_ifc
        reference = Path(self.temp.name) / "reload.reference.json"
        self.document.save(reference)
        restored = BuildingDocument.load(reference)
        other = export_ifc(restored, Path(self.temp.name) / "again.ifc")
        for name in ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcWallType",
                     "IfcWall", "IfcDoor", "IfcOpeningElement"):
            self.assertEqual(sorted(x.GlobalId for x in self.model.by_type(name)),
                             sorted(x.GlobalId for x in other.by_type(name)))

    @unittest.skipUnless(importlib.util.find_spec("pytest"), "Install the test extra for full EXPRESS validation")
    def test_schema_validation(self):
        import ifcopenshell.validate
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.model, logger, express_rules=True)
        self.assertEqual(logger.statements, [])

    def test_opening_boolean_geometry_matches_schedule(self):
        import ifcopenshell.geom
        import ifcopenshell.util.shape
        import ifcopenshell.util.element
        settings = ifcopenshell.geom.settings()
        by_name = {row["name"]: row for row in self.document.quantities()}
        for wall in self.model.by_type("IfcWall"):
            shape = ifcopenshell.geom.create_shape(settings, wall)
            volume = ifcopenshell.util.shape.get_volume(shape.geometry)
            expected = by_name[wall.Name]["net_volume_m3"]
            self.assertAlmostEqual(volume, expected, places=6)
            qto = ifcopenshell.util.element.get_psets(wall, qtos_only=True)["Qto_WallBaseQuantities"]
            self.assertAlmostEqual(qto["NetVolume"], expected)


if __name__ == "__main__":
    unittest.main()
