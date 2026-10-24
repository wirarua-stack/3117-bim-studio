# SPDX-License-Identifier: GPL-3.0-or-later
"""Exchange tests for the native snapshot adapter, without mocking IFC.

Run with a Python runtime containing IfcOpenShell, e.g. the pinned FreeCAD
runtime. The host integration suite separately captures these snapshots from
real native objects. Synthetic dictionaries here test the adapter contract.
"""
import copy
import importlib.util
import math
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench"))


def identifier(name):
    return str(uuid5(NAMESPACE_URL, "3117-native-ifc-test:" + name))


def fixture():
    """Independent 6 x 3 x 0.2 m wall, with a 0.9 x 2.1 m overall opening."""
    return {
        "snapshot_schema": 1, "workbench_version": "0.2.1", "content_revision": "a"*64,
        "project": {"id": identifier("project"), "label": "โครงการทดสอบ", "number": "3117-QA", "author": "3117 QA"},
        "levels": [{"id": identifier("base"), "label": "L00", "elevation_m": 0.0},
                   {"id": identifier("top"), "label": "L01", "elevation_m": 3.0}],
        "wall_types": [{"id": identifier("type"), "label": "W200", "thickness_m": 0.2, "material": "Masonry"}],
        "walls": [{"id": identifier("wall"), "label": "Wall 01", "type_id": identifier("type"),
                   "base_level_id": identifier("base"), "top_level_id": identifier("top"),
                   "start_m": [0.0, 0.0], "end_m": [6.0, 0.0], "base_z_m": 0.0,
                   "length_m": 6.0, "height_m": 3.0, "thickness_m": 0.2,
                   "base_offset_m": 0.0, "top_offset_m": 0.0,
                   "quantities": {"gross_side_area_m2": 18.0, "net_side_area_m2": 16.11,
                                  "opening_side_area_m2": 1.89, "gross_volume_m3": 3.6,
                                  "net_volume_m3": 3.222, "opening_volume_m3": 0.378}}],
        "doors": [{"id": identifier("door"), "label": "ประตู 01", "host_id": identifier("wall"),
                   "offset_m": 1.2, "width_m": 0.9, "height_m": 2.1, "sill_m": 0.0,
                   "frame_volume_m3": 0.05}],
        "grids": [], "coverage": {"complete": True, "items": [], "counts": {}, "warnings": []},
    }


def building_fixture():
    """Authored millimetre-independent dimensions with analytically known cuts."""
    source = fixture()
    source["workbench_version"] = "0.3.0"
    source["windows"] = [{"id": identifier("window"), "label": "Window 01", "host_id": identifier("wall"),
                          "offset_m": 3.0, "width_m": 1.2, "height_m": 1.0, "sill_m": 1.0,
                          "frame_volume_m3": 0.042}]
    source["walls"][0]["quantities"].update(net_side_area_m2=14.91, opening_side_area_m2=3.09,
                                             net_volume_m3=2.982, opening_volume_m3=0.618)
    source["slabs"] = [{"id": identifier("slab"), "label": "Slab 01", "level_id": identifier("top"),
                        "offset_m": 0.0, "thickness_m": 0.15, "top_z_m": 3.0, "base_z_m": 2.85,
                        "boundary_m": [[-0.5, -0.5], [6.5, -0.5], [6.5, 3.5], [-0.5, 3.5]],
                        "material": "Concrete", "native_bounds_m": [[-0.5, -0.5, 2.85], [6.5, 3.5, 3.0]],
                        "quantities": {"gross_area_m2": 28.0, "net_area_m2": 28.0, "perimeter_m": 22.0,
                                       "gross_volume_m3": 4.2, "net_volume_m3": 4.2, "join_deduction_m3": 0.0}}]
    half_x = 0.15*math.cos(math.pi/6)+0.2*math.sin(math.pi/6)
    half_y = 0.15*math.sin(math.pi/6)+0.2*math.cos(math.pi/6)
    source["columns"] = [{"id": identifier("column"), "label": "Column 01", "base_level_id": identifier("base"),
                          "top_level_id": identifier("top"), "base_offset_m": 0.0, "top_offset_m": 0.0,
                          "x_m": 1.0, "y_m": 2.0, "width_m": 0.3, "depth_m": 0.4, "rotation_deg": 30.0,
                          "base_z_m": 0.0, "height_m": 3.0, "join_slab_ids": [identifier("slab")],
                          "material": "Concrete", "native_bounds_m": [[1-half_x, 2-half_y, 0.0], [1+half_x, 2+half_y, 2.85]],
                          "quantities": {"section_area_m2": 0.12, "gross_volume_m3": 0.36,
                                         "net_volume_m3": 0.342, "join_deduction_m3": 0.018}}]
    source["beams"] = [{"id": identifier("beam"), "label": "Beam 01", "level_id": identifier("top"),
                        "offset_m": 0.0, "start_m": [0.0, 2.0], "end_m": [6.0, 2.0],
                        "width_m": 0.3, "depth_m": 0.45, "length_m": 6.0, "top_z_m": 3.0, "base_z_m": 2.55,
                        "join_slab_ids": [identifier("slab")], "material": "Concrete",
                        "native_bounds_m": [[0.0, 1.85, 2.55], [6.0, 2.15, 2.85]],
                        "quantities": {"section_area_m2": 0.135, "gross_volume_m3": 0.81,
                                       "net_volume_m3": 0.54, "join_deduction_m3": 0.27}}]
    return source


def typed_fixture():
    """The same six native solids, with material partitions and real shared types."""
    source = building_fixture()
    source["workbench_version"] = "0.5.0"
    source["materials"] = [{"id": identifier("material-" + name), "label": name, "code": code}
                           for name, code in (("Masonry", "M01"), ("Finish", "F01"), ("Concrete", "C01"), ("Frame", "FR01"))]
    materials = {item["label"]: item for item in source["materials"]}
    source["wall_types"][0].update(code="W200", layers=[
        {"material_id": materials["Finish"]["id"], "thickness_m": 0.02, "role": "Finish"},
        {"material_id": materials["Masonry"]["id"], "thickness_m": 0.18, "role": "Core"}])
    source["element_types"] = []
    for key, category, dims in (("slabs", "Slab", ("thickness_m",)),
                                ("columns", "Column", ("width_m", "depth_m")),
                                ("beams", "Beam", ("width_m", "depth_m")),
                                ("doors", "Door", ("width_m", "height_m")),
                                ("windows", "Window", ("width_m", "height_m"))):
        data = source[key][0]
        typ = {"id": identifier("type-" + category), "label": category + " Type", "category": category,
               "code": category.upper(), **{name: data[name] for name in dims}}
        if category == "Slab":
            typ["layers"] = [{"material_id": materials["Finish"]["id"], "thickness_m": 0.05, "role": "Finish"},
                             {"material_id": materials["Concrete"]["id"], "thickness_m": 0.1, "role": "Core"}]
        else:
            typ["material_id"] = materials["Frame" if category in ("Door", "Window") else "Concrete"]["id"]
        source["element_types"].append(typ)
        data["type_id"] = typ["id"]
    types = {item["id"]: item for item in source["wall_types"] + source["element_types"]}
    materials = {item["id"]: item for item in source["materials"]}
    levels = {item["id"]: item for item in source["levels"]}
    source["material_rows"] = []
    for key, category in (("walls", "Wall"), ("slabs", "Slab"), ("columns", "Column"),
                           ("beams", "Beam"), ("doors", "Door"), ("windows", "Window")):
        data = source[key][0]
        typ = types[data["type_id"]]
        level_id = data.get("level_id", data.get("base_level_id", source["walls"][0]["base_level_id"]))
        gross = data["frame_volume_m3"] if category in ("Door", "Window") else data["quantities"]["gross_volume_m3"]
        net = data["frame_volume_m3"] if category in ("Door", "Window") else data["quantities"]["net_volume_m3"]
        layers = typ.get("layers") or [{"material_id": typ["material_id"], "role": "homogeneous", "thickness_m": ""}]
        for index, layer in enumerate(layers):
            factor = layer["thickness_m"] / typ["thickness_m"] if typ.get("layers") else 1.0
            material = materials[layer["material_id"]]
            source["material_rows"].append({"element_id": data["id"], "name": data["label"], "category": category,
                "level_id": level_id, "level": levels[level_id]["label"], "type_id": typ["id"], "type_name": typ["label"],
                "material_id": material["id"], "material_name": material["label"], "material_code": material["code"],
                "layer_index": index + 1 if typ.get("layers") else 0, "layer_role": layer["role"],
                "thickness_m": layer["thickness_m"], "gross_volume_m3": gross * factor,
                "net_volume_m3": net * factor, "deduction_volume_m3": (gross - net) * factor,
                "quantity_rule": "3117.material.native-solid-partition.v1", "content_revision": source["content_revision"]})
    source["material_totals"] = {"row_count": 8, "assigned_product_count": 6, "product_count": 6,
        "unassigned_product_count": 0, "complete": True,
        **{name: math.fsum(row[name] for row in source["material_rows"])
           for name in ("gross_volume_m3", "net_volume_m3", "deduction_volume_m3")}}
    return source


def multistorey_opening_fixture():
    """Two orthogonal walls per storey, with square apertures and mixed fills."""
    source = fixture()
    source["workbench_version"] = "0.3.0"
    source["levels"].append({"id": identifier("roof"), "label": "L02", "elevation_m": 6.0})
    template = source["walls"][0]
    source["walls"], source["doors"], source["windows"] = [], [], []
    for storey in range(2):
        for index, (start, end, length) in enumerate((([0.15, 0.15], [5.85, 0.15], 5.7),
                                                      ([5.85, 0.15], [5.85, 3.85], 3.7))):
            name = f"{storey}-{index}"
            wall = copy.deepcopy(template)
            wall.update(id=identifier("multi-wall-"+name), label="Wall "+name,
                        base_level_id=source["levels"][storey]["id"], top_level_id=source["levels"][storey+1]["id"],
                        start_m=start, end_m=end, length_m=length, height_m=2.55, base_z_m=storey*3.0, top_offset_m=-0.45)
            opening_area = 1.44 + (1.89 if index == 0 else 0.0)
            wall["quantities"] = {"gross_side_area_m2": length*2.55, "opening_side_area_m2": opening_area,
                                  "net_side_area_m2": length*2.55-opening_area, "gross_volume_m3": length*2.55*0.2,
                                  "opening_volume_m3": opening_area*0.2, "net_volume_m3": (length*2.55-opening_area)*0.2}
            source["walls"].append(wall)
            source["windows"].append({"id": identifier("multi-window-"+name), "label": "Window "+name,
                                       "host_id": wall["id"], "offset_m": 3.0 if index == 0 else 1.2,
                                       "width_m": 1.2, "height_m": 1.2, "sill_m": 0.9, "frame_volume_m3": 0.046})
            if index == 0:
                source["doors"].append({"id": identifier("multi-door-"+name), "label": "Door "+name,
                                         "host_id": wall["id"], "offset_m": 0.8, "width_m": 0.9,
                                         "height_m": 2.1, "sill_m": 0.0, "frame_volume_m3": 0.05})
    return source


@unittest.skipUnless(importlib.util.find_spec("ifcopenshell"), "IfcOpenShell is an optional host dependency")
class NativeIfcTests(unittest.TestCase):
    def setUp(self):
        import ifcopenshell
        from bim3117_freecad import ifc_native
        self.ifc = ifcopenshell
        self.adapter = ifc_native
        self.snapshot = fixture()

    def assert_valid(self, model, snapshot=None):
        report = self.adapter.validate_ifc(model, snapshot or self.snapshot)
        self.assertEqual(report["status"], "passed", [c for c in report["checks"] if c["status"] != "passed"])
        return report

    def test_roundtrip_schema_geometry_relationships_and_quantities(self):
        model = self.adapter.build_ifc(self.snapshot)
        with tempfile.TemporaryDirectory(prefix="3117_native_ifc_") as directory:
            path = Path(directory) / "โครงการ.ifc"
            model.write(str(path))
            restored = self.ifc.open(str(path))
            report = self.assert_valid(restored)
        self.assertEqual(report["ifcopenshell_version"], self.ifc.version)
        self.assertAlmostEqual(report["geometry"][0]["volume_m3"], 3.222, places=8)
        self.assertAlmostEqual(report["geometry"][1]["volume_m3"], 0.05, places=8)
        self.assertEqual(model.by_type("IfcProject")[0].Name, "โครงการทดสอบ")
        self.assertEqual(len(model.by_type("IfcWall")), 1)
        self.assertEqual(len(model.by_type("IfcRelVoidsElement")), 1)
        self.assertEqual(len(model.by_type("IfcRelFillsElement")), 1)

    def test_all_root_ids_stable_after_rename_and_new_revision(self):
        before = self.adapter.build_ifc(self.snapshot)
        changed = copy.deepcopy(self.snapshot)
        changed["content_revision"] = "b"*64
        changed["project"]["label"] = "Renamed project"
        changed["walls"][0]["label"] = "Renamed wall"
        changed["doors"][0]["label"] = "Renamed door"
        after = self.adapter.build_ifc(changed)
        self.assertEqual({e.GlobalId for e in before.by_type("IfcRoot")},
                         {e.GlobalId for e in after.by_type("IfcRoot")})
        self.assert_valid(after, changed)

    def test_diagonal_reversed_axis_signed_elevation_and_offsets(self):
        self.snapshot["levels"][0]["elevation_m"] = -1.2
        self.snapshot["levels"][1]["elevation_m"] = 2.4
        wall = self.snapshot["walls"][0]
        wall.update(start_m=[2.0, -3.0], end_m=[-1.0, 1.0], length_m=5.0,
                    base_offset_m=0.15, top_offset_m=-0.05, base_z_m=-1.05, height_m=3.4)
        wall["quantities"].update(gross_side_area_m2=17.0, net_side_area_m2=15.11,
                                  gross_volume_m3=3.4, net_volume_m3=3.022)
        self.snapshot["doors"][0].update(offset_m=1.5, sill_m=0.2)
        report = self.assert_valid(self.adapter.build_ifc(self.snapshot))
        from ifcopenshell.util.placement import get_local_placement
        model = self.adapter.build_ifc(self.snapshot)
        placement = get_local_placement(model.by_type("IfcDoor")[0].ObjectPlacement)
        self.assertAlmostEqual(placement[0, 3], 1.1)
        self.assertAlmostEqual(placement[1, 3], -1.8)
        self.assertAlmostEqual(placement[2, 3], -0.85)
        self.assertAlmostEqual(report["geometry"][0]["volume_m3"], 3.022, places=8)

    def test_multiple_openings_and_shared_type_have_single_wall_row(self):
        door = copy.deepcopy(self.snapshot["doors"][0])
        door.update(id=identifier("door2"), label="Door 02", offset_m=4.0, sill_m=0.3)
        self.snapshot["doors"].append(door)
        wall = self.snapshot["walls"][0]
        wall["quantities"].update(net_side_area_m2=14.22, net_volume_m3=2.844,
                                  opening_side_area_m2=3.78, opening_volume_m3=0.756)
        other = copy.deepcopy(wall)
        other.update(id=identifier("wall2"), label="Wall 02", start_m=[6.0, 1.0], end_m=[0.0, 1.0])
        other["quantities"].update(net_side_area_m2=18.0, net_volume_m3=3.6,
                                   opening_side_area_m2=0.0, opening_volume_m3=0.0)
        self.snapshot["walls"].append(other)
        model = self.adapter.build_ifc(self.snapshot)
        self.assert_valid(model)
        self.assertEqual(len(model.by_type("IfcWall")), 2)
        self.assertEqual(len(model.by_type("IfcWallType")), 1)
        self.assertEqual(len(model.by_type("IfcRelDefinesByType")[0].RelatedObjects), 2)
        self.assertEqual(len(model.by_type("IfcElementQuantity")), 2)

    def test_validator_rejects_equal_volume_opening_in_wrong_location(self):
        model = self.adapter.build_ifc(self.snapshot)
        opening = model.by_type("IfcOpeningElement")[0]
        location = opening.ObjectPlacement.RelativePlacement.Location
        coords = location.Coordinates
        location.Coordinates = (coords[0]+1.0, coords[1], coords[2])
        report = self.adapter.validate_ifc(model, self.snapshot)
        self.assertEqual(report["status"], "failed")
        failures = {c["name"].split(":")[0] for c in report["checks"] if c["status"] == "failed"}
        self.assertIn("door-placement", failures)
        self.assertIn("opening-empty", failures)

    def test_validator_rejects_stale_native_solid_volume(self):
        self.snapshot["walls"][0]["quantities"]["net_volume_m3"] = 3.6
        model = self.adapter.build_ifc(self.snapshot)
        report = self.adapter.validate_ifc(model, self.snapshot)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(c["name"] == "geometry:"+identifier("wall") and c["status"] == "failed"
                            for c in report["checks"]))

    def test_invalid_reference_duplicate_id_nonfinite_and_overlap_rejected(self):
        cases = []
        missing = copy.deepcopy(self.snapshot)
        missing["doors"][0]["host_id"] = identifier("absent")
        cases.append(missing)
        duplicate = copy.deepcopy(self.snapshot)
        duplicate["doors"][0]["id"] = duplicate["walls"][0]["id"]
        cases.append(duplicate)
        nonfinite = copy.deepcopy(self.snapshot)
        nonfinite["walls"][0]["height_m"] = math.nan
        cases.append(nonfinite)
        overlapping = copy.deepcopy(self.snapshot)
        second = copy.deepcopy(overlapping["doors"][0])
        second["id"] = identifier("overlap")
        overlapping["doors"].append(second)
        cases.append(overlapping)
        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                with self.assertRaises((self.adapter.IfcExportError, ValueError)):
                    self.adapter.build_ifc(snapshot)

    def test_empty_building_remains_valid_and_readonly(self):
        self.snapshot["walls"] = []
        self.snapshot["doors"] = []
        original = copy.deepcopy(self.snapshot)
        self.assert_valid(self.adapter.build_ifc(self.snapshot))
        self.assertEqual(self.snapshot, original)

    def test_building_roundtrip_join_quantities_and_four_bar_window(self):
        source = building_fixture()
        original = copy.deepcopy(source)
        model = self.adapter.build_ifc(source)
        with tempfile.TemporaryDirectory(prefix="3117_building_ifc_") as directory:
            path = Path(directory) / "building.ifc"
            model.write(str(path))
            report = self.assert_valid(self.ifc.open(str(path)), source)
        self.assertEqual(source, original)
        geometry = {item["id"]: item for item in report["geometry"]}
        for name, volume in (("wall", 2.982), ("slab", 4.2), ("column", 0.342), ("beam", 0.54), ("window", 0.042)):
            self.assertAlmostEqual(geometry[identifier(name)]["volume_m3"], volume, places=8)
        for category in ("Slab", "Column", "Beam", "Window"):
            self.assertEqual(len(model.by_type("Ifc"+category)), 1)
            self.assertEqual(len(model.by_type("Ifc"+category+"Type")), 0)
        self.assertEqual(len(model.by_type("IfcWindow")[0].Representation.Representations[0].Items), 4)
        self.assertEqual(len(model.by_type("IfcRelVoidsElement")), 2)
        self.assertEqual(len(model.by_type("IfcRelFillsElement")), 2)
        self.assertEqual(len(model.by_type("IfcBooleanResult")), 2)

    def test_native_types_materials_roundtrip_preserves_products_and_geometry(self):
        source = typed_fixture()
        original = copy.deepcopy(source)
        baseline = self.assert_valid(self.adapter.build_ifc(building_fixture()), building_fixture())
        model = self.adapter.build_ifc(source)
        with tempfile.TemporaryDirectory(prefix="3117_types_ifc_") as directory:
            path = Path(directory) / "types.ifc"
            model.write(str(path))
            report = self.assert_valid(self.ifc.open(str(path)), source)
        self.assertEqual(source, original)
        expected = {item["id"]: item["volume_m3"] for item in baseline["geometry"]}
        actual = {item["id"]: item["volume_m3"] for item in report["geometry"]}
        self.assertEqual(set(actual), set(expected))
        for identifier, value in expected.items():
            self.assertAlmostEqual(actual[identifier], value, places=8)
        self.assertEqual(len(model.by_type("IfcMaterial")), 4)
        self.assertEqual(len(model.by_type("IfcMaterialLayerSet")), 2)
        self.assertEqual(len(model.by_type("IfcMaterialLayerSetUsage")), 2)
        self.assertEqual(len(model.by_type("IfcRelDefinesByType")), 6)
        usages = {item.LayerSetDirection: item for item in model.by_type("IfcMaterialLayerSetUsage")}
        self.assertEqual((usages["AXIS2"].DirectionSense, usages["AXIS2"].OffsetFromReferenceLine), ("POSITIVE", 0.0))
        self.assertEqual((usages["AXIS3"].DirectionSense, usages["AXIS3"].OffsetFromReferenceLine), ("NEGATIVE", 0.15))
        for category in ("Wall", "Slab", "Column", "Beam", "Door", "Window"):
            self.assertEqual(len(model.by_type("Ifc" + category + "Type")), 1)

    def test_native_types_materials_full_express_validation(self):
        if not importlib.util.find_spec("pytest"):
            self.skipTest("IfcOpenShell EXPRESS executor requires pytest")
        source = typed_fixture()
        report = self.adapter.validate_ifc(self.adapter.build_ifc(source), source, express_rules=True)
        self.assertEqual(report["status"], "passed", [item for item in report["checks"] if item["status"] == "failed"])

    def test_native_type_material_contract_rejects_inconsistency(self):
        cases = []
        missing = typed_fixture()
        missing["materials"].pop(0)
        cases.append(missing)
        wrong_category = typed_fixture()
        wrong_category["doors"][0]["type_id"] = wrong_category["windows"][0]["type_id"]
        cases.append(wrong_category)
        dimensions = typed_fixture()
        dimensions["element_types"][3]["width_m"] += 0.1
        cases.append(dimensions)
        layers = typed_fixture()
        layers["wall_types"][0]["layers"][0]["thickness_m"] += 0.01
        cases.append(layers)
        assignment = typed_fixture()
        assignment["wall_types"][0]["material_id"] = assignment["materials"][0]["id"]
        cases.append(assignment)
        omitted = typed_fixture()
        omitted["material_rows"].pop()
        cases.append(omitted)
        duplicate = typed_fixture()
        duplicate["material_rows"].append(copy.deepcopy(duplicate["material_rows"][0]))
        cases.append(duplicate)
        for name, value in (("level_id", identifier("absent")), ("layer_index", 2),
                             ("material_code", "Wrong"), ("net_volume_m3", 0.0),
                             ("content_revision", "b" * 64)):
            source = typed_fixture()
            source["material_rows"][0][name] = value
            cases.append(source)
        for index, source in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(self.adapter.IfcExportError):
                    self.adapter.build_ifc(source)

    def test_serialized_layer_direction_order_material_and_quantities_are_checked(self):
        source = typed_fixture()
        for mutation in ("orientation", "offset", "order", "material", "quantity", "type_relation"):
            with self.subTest(mutation=mutation):
                model = self.adapter.build_ifc(source)
                if mutation == "orientation":
                    model.by_type("IfcMaterialLayerSetUsage")[0].DirectionSense = "NEGATIVE"
                elif mutation == "offset":
                    model.by_type("IfcMaterialLayerSetUsage")[1].OffsetFromReferenceLine = 0.0
                elif mutation == "order":
                    layers = model.by_type("IfcMaterialLayerSet")[0]
                    layers.MaterialLayers = tuple(reversed(layers.MaterialLayers))
                elif mutation == "material":
                    model.by_type("IfcMaterial")[0].Name = "Wrong material"
                elif mutation == "quantity":
                    qto = next(item for item in model.by_type("IfcElementQuantity") if item.Name == "BIM3117_MaterialQuantities")
                    qto.Quantities[0].VolumeValue += 0.1
                else:
                    relation = next(item for item in model.by_type("IfcRelDefinesByType") if item.RelatingType.is_a("IfcDoorType"))
                    model.remove(relation)
                self.assertEqual(self.adapter.validate_ifc(model, source)["status"], "failed")

    def test_diagonal_reversed_member_axes_and_signed_level_offsets(self):
        source = building_fixture()
        # Rotate the entire building 126.87 degrees and translate it. The beam
        # then runs along (-0.6, 0.8); bounds below are calculated independently.
        ux, uy, tx, ty, dz = -0.6, 0.8, -5.0, -2.0, -1.25
        def point(p):
            return [tx+ux*p[0]-uy*p[1], ty+uy*p[0]+ux*p[1]]
        for level in source["levels"]:
            level["elevation_m"] += dz
        for wall in source["walls"]:
            wall["start_m"], wall["end_m"] = point(wall["start_m"]), point(wall["end_m"])
            wall["base_z_m"] += dz
        slab = source["slabs"][0]
        slab["boundary_m"] = [point(p) for p in slab["boundary_m"]]
        slab["base_z_m"] += dz
        slab["top_z_m"] += dz
        slab["native_bounds_m"] = [[min(p[i] for p in slab["boundary_m"]) for i in range(2)]+[slab["base_z_m"]],
                                    [max(p[i] for p in slab["boundary_m"]) for i in range(2)]+[slab["top_z_m"]]]
        column = source["columns"][0]
        column["x_m"], column["y_m"] = point([column["x_m"], column["y_m"]])
        column["rotation_deg"] += math.degrees(math.atan2(uy, ux))
        column["base_offset_m"] = 0.1
        column["base_z_m"] += dz+0.1
        column["height_m"] -= 0.1
        column["quantities"].update(gross_volume_m3=0.348, net_volume_m3=0.33)
        angle = math.radians(column["rotation_deg"])
        dx = abs(math.cos(angle))*0.15+abs(math.sin(angle))*0.2
        dy = abs(math.sin(angle))*0.15+abs(math.cos(angle))*0.2
        column["native_bounds_m"] = [[column["x_m"]-dx, column["y_m"]-dy, column["base_z_m"]],
                                      [column["x_m"]+dx, column["y_m"]+dy, slab["base_z_m"]]]
        beam = source["beams"][0]
        beam["start_m"], beam["end_m"] = point(beam["start_m"]), point(beam["end_m"])
        beam["base_z_m"] += dz
        beam["top_z_m"] += dz
        corners = [[p[0]-sign*uy*0.15, p[1]+sign*ux*0.15] for p in (beam["start_m"], beam["end_m"]) for sign in (-1, 1)]
        beam["native_bounds_m"] = [[min(p[i] for p in corners) for i in range(2)]+[beam["base_z_m"]],
                                    [max(p[i] for p in corners) for i in range(2)]+[slab["base_z_m"]]]
        self.assert_valid(self.adapter.build_ifc(source), source)

    def test_overlapping_slab_cutters_deduct_union_and_keep_ids_on_rename(self):
        source = building_fixture()
        lower = copy.deepcopy(source["slabs"][0])
        lower.update(id=identifier("lower-slab"), label="Lower slab", offset_m=-0.05,
                     thickness_m=0.2, base_z_m=2.75, top_z_m=2.95)
        lower["quantities"].update(gross_volume_m3=5.6, net_volume_m3=5.6)
        lower["native_bounds_m"][0][2], lower["native_bounds_m"][1][2] = 2.75, 2.95
        source["slabs"].append(lower)
        for key, net, deduction in (("columns", 0.33, 0.03), ("beams", 0.36, 0.45)):
            source[key][0]["join_slab_ids"].append(lower["id"])
            source[key][0]["native_bounds_m"][1][2] = 2.75
            source[key][0]["quantities"].update(net_volume_m3=net, join_deduction_m3=deduction)
        before = self.adapter.build_ifc(source)
        self.assert_valid(before, source)
        source["content_revision"] = "d"*64
        for key in ("slabs", "columns", "beams", "windows"):
            for item in source[key]:
                item["label"] += " renamed"
        after = self.adapter.build_ifc(source)
        self.assert_valid(after, source)
        self.assertEqual({item.GlobalId for item in before.by_type("IfcRoot")},
                         {item.GlobalId for item in after.by_type("IfcRoot")})

    def test_misplaced_join_cutter_rejected_even_when_volume_and_bounds_match(self):
        source = building_fixture()
        model = self.adapter.build_ifc(source)
        column = model.by_type("IfcColumn")[0]
        cutter = column.Representation.Representations[0].Items[0].SecondOperand
        # The slab is wide enough that a 0.1 m move has identical member cut
        # volume and bounds; provenance must still agree with the source slab.
        cutter.Position.Location.Coordinates = (0.1, 0.0, 2.85)
        report = self.adapter.validate_ifc(model, source)
        failures = [item["name"] for item in report["checks"] if item["status"] == "failed"]
        self.assertEqual(failures, ["join-cutters:"+identifier("column")])

    def test_missing_join_and_mixed_door_window_overlap_are_rejected(self):
        for scenario in ("join", "overlap", "stale-volume"):
            source = building_fixture()
            with self.subTest(scenario=scenario):
                if scenario == "join":
                    source["beams"][0]["join_slab_ids"] = [identifier("missing-slab")]
                    with self.assertRaises(self.adapter.IfcExportError):
                        self.adapter.build_ifc(source)
                elif scenario == "overlap":
                    source["windows"][0]["offset_m"] = 1.5
                    with self.assertRaises(self.adapter.IfcExportError):
                        self.adapter.build_ifc(source)
                else:
                    source["beams"][0]["quantities"]["net_volume_m3"] = 0.81
                    report = self.adapter.validate_ifc(self.adapter.build_ifc(source), source)
                    self.assertEqual(report["status"], "failed")
                    self.assertTrue(any(item["name"] == "geometry:"+identifier("beam") and item["status"] == "failed"
                                        for item in report["checks"]))

    def test_concave_slab_rejects_equal_volume_mirrored_profile(self):
        source = fixture()
        source["slabs"] = [{"id": identifier("concave-slab"), "label": "L-shaped slab", "level_id": identifier("base"),
                            "offset_m": -0.2, "top_z_m": -0.2, "base_z_m": -0.35, "thickness_m": 0.15,
                            "boundary_m": [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3]], "material": "Concrete",
                            "native_bounds_m": [[0.0, 0.0, -0.35], [4.0, 3.0, -0.2]],
                            "quantities": {"gross_area_m2": 6.0, "net_area_m2": 6.0, "perimeter_m": 14.0,
                                           "gross_volume_m3": 0.9, "net_volume_m3": 0.9, "join_deduction_m3": 0.0}}]
        model = self.adapter.build_ifc(source)
        self.assert_valid(model, source)
        profile = model.by_type("IfcSlab")[0].Representation.Representations[0].Items[0].SweptArea
        mirrored = [(0., 0.), (4., 0.), (4., 3.), (3., 3.), (3., 1.), (0., 1.), (0., 0.)]
        for vertex, coords in zip(profile.OuterCurve.Points, mirrored):
            vertex.Coordinates = coords
        report = self.adapter.validate_ifc(model, source)
        failures = [item["name"] for item in report["checks"] if item["status"] == "failed"]
        self.assertEqual(failures, ["join-cutters:"+identifier("concave-slab")])

    def test_multistorey_square_openings_have_empty_voids_and_solid_material(self):
        source = multistorey_opening_fixture()
        model = self.adapter.build_ifc(source)
        with tempfile.TemporaryDirectory(prefix="3117_multistorey_ifc_") as directory:
            path = Path(directory) / "two-storeys.ifc"
            model.write(str(path))
            model = self.ifc.open(str(path))
        self.assert_valid(model, source)
        settings = self.ifc.geom.settings()
        settings.set("use-world-coords", False)
        for window in source["windows"]:
            wall = model.by_guid(self.adapter.global_id(window["host_id"]))
            shape = self.ifc.geom.create_shape(settings, wall)
            flat = shape.geometry.verts
            vertices = [tuple(flat[i+j] for j in range(3)) for i in range(0, len(flat), 3)]
            faces = list(shape.geometry.faces)
            with self.subTest(window=window["label"]):
                # This strictly interior void point made the former fixed ray
                # graze the aperture edge, falsely reporting material. Exercise
                # the exact square opening on both levels and both wall axes.
                edge_tangent_probe = (window["offset_m"]+0.96, 0.02, 1.86)
                self.assertFalse(self.adapter._inside_mesh(edge_tangent_probe, vertices, faces))
                self.assertTrue(self.adapter._inside_mesh((0.1, 0.1, 0.5), vertices, faces))
        moved = source["windows"][0]
        opening = model.by_guid(self.adapter.global_id(self.adapter.opening_id(moved["id"])))
        old = opening.ObjectPlacement.RelativePlacement.Location.Coordinates
        opening.ObjectPlacement.RelativePlacement.Location.Coordinates = (old[0]+0.6, old[1], old[2])
        report = self.adapter.validate_ifc(model, source)
        self.assertTrue(any(item["name"] == "opening-empty:"+moved["id"] and item["status"] == "failed"
                            for item in report["checks"]))

    @unittest.skipUnless(importlib.util.find_spec("pytest"), "Full EXPRESS requires optional QA dependency pytest")
    def test_full_express_validation(self):
        model = self.adapter.build_ifc(self.snapshot)
        report = self.adapter.validate_ifc(model, self.snapshot, express_rules=True)
        self.assertEqual(report["status"], "passed", report["express_rules"])
        self.assertEqual(report["express_rules"]["status"], "passed")

    @unittest.skipUnless(importlib.util.find_spec("pytest"), "Full EXPRESS requires optional QA dependency pytest")
    def test_building_full_express_validation(self):
        source = building_fixture()
        report = self.adapter.validate_ifc(self.adapter.build_ifc(source), source, express_rules=True)
        self.assertEqual(report["status"], "passed", [item for item in report["checks"] if item["status"] != "passed"])
        self.assertEqual(report["express_rules"]["status"], "passed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
