# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed FreeCAD tests for native type/material quantities and exchange.

All documents are disposable. The historical examples are opened read-only in
memory and never saved. ``reopen`` must run in a separate FreeCAD process.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def near(actual, expected):
    return math.isclose(float(actual), float(expected), rel_tol=1e-8, abs_tol=1e-8)


def main(output_dir, legacy_root=None):
    from bim3117_freecad import catalog, exchange, ifc_native, material_quantities, services, snapshot
    from bim3117_freecad.model import FoundationError, kind
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Native layered and homogeneous material quantities, catalogue CSV and IFC4 type/material readback"}
    documents = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    def rejects(name, operation):
        try:
            operation()
        except (FoundationError, ValueError):
            check(name, True)
        else:
            raise AssertionError(name + ": accepted")

    def rows(data, obj):
        return [item for item in data["material_rows"] if item["element_id"] == obj.BIM3117Id]

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("catalogue, snapshot, material quantities and exchange load from installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed)
                  for module in (catalog, snapshot, material_quantities, exchange, ifc_native)))
        root = Path(legacy_root) if legacy_root is not None else Path(__file__).resolve().parents[1] / "examples"
        historical = root / "building"
        old_path = historical / "Building_Authoring_Workbench.FCStd"
        check("historical native building fixture is present", old_path.is_file())
        old = App.openDocument(str(old_path))
        documents.append(old.Name)
        old.recompute()
        old_project = services.get_project(old)
        old_snapshot = snapshot.capture(old_project)
        expected = json.loads((historical / "building-snapshot.json").read_text(encoding="utf-8"))
        check("legacy model revision and aggregate quantities remain unchanged",
              old_snapshot["content_revision"] == expected["content_revision"] and old_snapshot["totals"] == expected["totals"])
        check("empty catalogue migration adds no authored fields or sidecars",
              all(key not in old_snapshot for key in ("materials", "element_types", "type_rows", "material_rows", "material_totals")))
        legacy_export = exchange.export_csv(old_project, output / "legacy.csv")
        legacy_csv = [Path(path) for path in legacy_export["files"] if path.endswith(".csv")]
        suffixes = ("", "_doors", "_slabs", "_columns", "_beams", "_windows")
        check("all six legacy CSV payloads stay byte-identical",
              len(legacy_csv) == 6 and all((output / ("legacy" + suffix + ".csv")).read_bytes() ==
                  (historical / ("Building_Authoring_Workbench" + suffix + ".csv")).read_bytes() for suffix in suffixes))
        report["legacy_content_revision"] = old_snapshot["content_revision"]
        old_name = old.Name
        App.closeDocument(old_name)
        documents.remove(old_name)

        project = services.create_project("3117 ชนิดและปริมาณวัสดุ", "TQ-050", "3117 BIM")
        doc = project.Document
        documents.append(doc.Name)
        base, top = services.list_levels(project)
        masonry = catalog.create_material(project, "Masonry", "M01")
        finish = catalog.create_material(project, "วัสดุผิว", "F01")
        concrete = catalog.create_material(project, "Concrete", "C01")
        frame = catalog.create_material(project, "Generic frame", "FR01")
        wall_type = catalog.create_type(project, "Wall 200 layered", "Wall", code="W200", layers=[
            {"material": finish, "thickness_mm": 20, "role": "Finish"},
            {"material": masonry, "thickness_mm": 180, "role": "Core"}])
        slab_type = catalog.create_type(project, "Slab 150 layered", "Slab", code="S150", layers=[
            {"material": finish, "thickness_mm": 50, "role": "Finish"},
            {"material": concrete, "thickness_mm": 100, "role": "Core"}])
        column_type = catalog.create_type(project, "Column 300x400", "Column", width_mm=300, depth_mm=400,
                                           material=concrete, code="C300")
        beam_type = catalog.create_type(project, "Beam 300x450", "Beam", width_mm=300, depth_mm=450,
                                         material=concrete, code="B300")
        door_type = catalog.create_type(project, "Door 900x2100", "Door", width_mm=900, height_mm=2100,
                                         material=frame, code="D090")
        window_type = catalog.create_type(project, "Window 1200x1000", "Window", width_mm=1200, height_mm=1000,
                                           material=frame, code="WIN120")
        wall = services.create_wall(project, "Layered wall", wall_type, base, top, end_x_mm=6000, end_y_mm=0)
        door = services.create_door(project, "Door frame", wall, offset_mm=1200)
        window = services.create_window(project, "Window frame", wall, offset_mm=3000, width_mm=1200, height_mm=1000, sill_mm=1000)
        slab = services.create_slab(project, "Layered slab", top, [(-500, -500), (6500, -500), (6500, 3500), (-500, 3500)])
        column = services.create_column(project, "Rotated column", base, top, x_mm=1000, y_mm=2000,
                                        width_mm=300, depth_mm=400, rotation_deg=30)
        beam = services.create_beam(project, "Beam", top, start_mm=(0, 2000), end_mm=(6000, 2000), width_mm=300, depth_mm=450)
        for obj, typ in ((door, door_type), (window, window_type), (slab, slab_type), (column, column_type), (beam, beam_type)):
            catalog.assign_type(obj, typ)
        services.join_slab(column, slab)
        services.join_slab(beam, slab)
        data = snapshot.capture(project)
        revision = data["content_revision"]
        check("six product rows, six type rows and eight material rows describe one model",
              sum(len(data[key]) for key in ("wall_rows", "door_rows", "window_rows", "slab_rows", "column_rows", "beam_rows")) == 6
              and len(data["type_rows"]) == 6 and len(data["material_rows"]) == 8)
        check("material coverage reports every assigned product once",
              data["material_totals"]["assigned_product_count"] == data["material_totals"]["product_count"] == 6
              and data["material_totals"]["unassigned_product_count"] == 0 and data["material_totals"]["complete"])
        expected = {wall.BIM3117Id: (3.6, 2.982), slab.BIM3117Id: (4.2, 4.2),
                    column.BIM3117Id: (.36, .342), beam.BIM3117Id: (.81, .54),
                    door.BIM3117Id: (.05, .05), window.BIM3117Id: (.042, .042)}
        check("native material partitions conserve independent gross and net fixture volumes",
              all(near(math.fsum(row["gross_volume_m3"] for row in data["material_rows"] if row["element_id"] == identifier), gross)
                  and near(math.fsum(row["net_volume_m3"] for row in data["material_rows"] if row["element_id"] == identifier), net)
                  for identifier, (gross, net) in expected.items()))
        check("wall layers deduct both real hosted apertures without counting WallBody",
              [row["material_id"] for row in rows(data, wall)] == [finish.BIM3117Id, masonry.BIM3117Id]
              and near(rows(data, wall)[0]["net_volume_m3"], .2982) and near(rows(data, wall)[1]["net_volume_m3"], 2.6838)
              and near(rows(data, wall)[0]["deduction_volume_m3"], .0618)
              and services.wall_body(wall).BIM3117Id not in {row["element_id"] for row in data["material_rows"]})
        check("slab top-down layers keep full volume while joined members carry cut volumes",
              near(rows(data, slab)[0]["net_volume_m3"], 1.4) and near(rows(data, slab)[1]["net_volume_m3"], 2.8)
              and near(rows(data, column)[0]["deduction_volume_m3"], .018)
              and near(rows(data, beam)[0]["deduction_volume_m3"], .27))
        check("door/window material rows measure only the generic native frames",
              len(rows(data, door)) == len(rows(data, window)) == 1
              and all(row["layer_index"] == 0 and row["layer_role"] == "homogeneous"
                      for row in rows(data, door) + rows(data, window))
              and near(rows(data, door)[0]["net_volume_m3"], door.Shape.Volume / 1e9)
              and near(rows(data, window)[0]["net_volume_m3"], window.Shape.Volume / 1e9))
        check("all material rows share native type/material/level identity and revision",
              all(row["level_id"] in (base.BIM3117Id, top.BIM3117Id) and row["level"] and row["type_id"]
                  and row["material_id"] and row["material_code"] and row["quantity_rule"]
                  and row["content_revision"] == revision for row in data["material_rows"]))
        check("type rows count authored instances and expose SI dimensions",
              all(row["instance_count"] == 1 for row in data["type_rows"])
              and next(row for row in data["type_rows"] if row["type_id"] == slab_type.BIM3117Id)["thickness_m"] == .15)
        history = (doc.UndoCount, doc.RedoCount, len(doc.Objects))
        snapshot.capture(project)
        check("material measurement creates no authored objects or history entries",
              history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)) and not doc.HasPendingTransaction)

        catalog.edit_material(finish, name="Renamed finish", code="F02")
        changed = snapshot.capture(project)
        check("material rename/code changes revision and all derived identities without altering volume",
              changed["content_revision"] != revision
              and all(row["material_name"] == "Renamed finish" and row["material_code"] == "F02"
                      for row in changed["material_rows"] if row["material_id"] == finish.BIM3117Id)
              and near(changed["material_totals"]["net_volume_m3"], data["material_totals"]["net_volume_m3"]))
        rejects("old revision cannot publish a material schedule", lambda: exchange.export_csv(project, output / "stale.csv", expected_revision=revision))
        check("stale publication creates no payload", not (output / "stale.csv").exists())
        doc.undo(); doc.recompute()
        check("Undo restores material labels, codes and the exact revision", snapshot.capture(project)["content_revision"] == revision)
        doc.redo(); doc.recompute()
        check("Redo restores the complete material revision", snapshot.capture(project)["content_revision"] == changed["content_revision"])
        doc.undo(); doc.recompute()
        catalog.edit_type(wall_type, layers=[{"material": masonry, "thickness_mm": 180, "role": "Core"},
                                            {"material": finish, "thickness_mm": 20, "role": "Finish"}])
        ordered = snapshot.capture(project)
        check("layer order is authored even when total product shape stays the same",
              ordered["content_revision"] != revision and rows(ordered, wall)[0]["material_id"] == masonry.BIM3117Id
              and near(rows(ordered, wall)[0]["net_volume_m3"], 2.6838))
        doc.undo(); doc.recompute()
        catalog.edit_type(slab_type, layers=[{"material": finish, "thickness_mm": 50, "role": "Finish"},
                                            {"material": concrete, "thickness_mm": 150, "role": "Core"}])
        thicker = snapshot.capture(project)
        check("shared slab layer thickness updates member cut and material rows in one model revision",
              near(rows(thicker, slab)[1]["net_volume_m3"], 4.2)
              and near(rows(thicker, column)[0]["net_volume_m3"], .336)
              and near(rows(thicker, beam)[0]["net_volume_m3"], .45))
        doc.undo(); doc.recompute()
        check("thickness Undo restores all material volumes and revision", snapshot.capture(project)["content_revision"] == revision)
        services.edit_wall(wall, start_x_mm=2000, start_y_mm=1000, end_x_mm=-1600, end_y_mm=5800)
        rotated = snapshot.capture(project)
        check("reversed diagonal wall retains local positive-Y layer partitions and hosted cuts",
              all(near(a["net_volume_m3"], b["net_volume_m3"]) for a, b in zip(rows(rotated, wall), rows(data, wall))))
        doc.undo(); doc.recompute()
        check("wall rotation Undo restores material source revision", snapshot.capture(project)["content_revision"] == revision)
        catalog.assign_type(door, None)
        detached = snapshot.capture(project)
        check("detached frame retains descriptive material text as authored unassigned data",
              detached["doors"][0].get("material") == frame.Label and not detached["doors"][0].get("type_id")
              and detached["material_totals"]["assigned_product_count"] == 5 and not rows(detached, door))
        doc.openTransaction("Edit detached frame description")
        door.Material = "Legacy frame description"
        doc.recompute()
        doc.commitTransaction()
        described = snapshot.capture(project)
        check("editing unassigned frame material text invalidates the authored revision without assigning a material",
              described["content_revision"] != detached["content_revision"]
              and described["doors"][0]["material"] == "Legacy frame description" and not rows(described, door))
        doc.undo(); doc.recompute()
        doc.undo(); doc.recompute()
        check("frame detach and description Undo restore material assignment and revision", snapshot.capture(project)["content_revision"] == revision)
        unassigned = services.create_column(project, "Legacy text material", base, top, x_mm=10000, material="Concrete text only")
        mixed = snapshot.capture(project)
        check("unassigned legacy text is explicitly omitted and never silently quantified",
              mixed["material_totals"]["assigned_product_count"] == 6 and mixed["material_totals"]["product_count"] == 7
              and mixed["material_totals"]["unassigned_product_count"] == 1 and not mixed["material_totals"]["complete"]
              and mixed["material_totals"]["unassigned_products"][0]["element_id"] == unassigned.BIM3117Id
              and "legacy material text" in mixed["material_totals"]["unassigned_products"][0]["reason"]
              and not rows(mixed, unassigned))
        doc.undo(); doc.recompute()
        check("removing the disposable unassigned product restores original coverage and revision",
              snapshot.capture(project)["content_revision"] == revision)

        csv_result = exchange.export_csv(project, output / "Types_Quantities.csv", expected_revision=revision)
        check("catalogue CSV exports six product tables plus types and native material partitions",
              len(csv_result["files"]) == 9 and (output / "Types_Quantities_types.csv").is_file()
              and (output / "Types_Quantities_materials.csv").is_file())
        with (output / "Types_Quantities_materials.csv").open(encoding="utf-8-sig", newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        check("material CSV retains layer order, SI volumes and all row identities",
              len(csv_rows) == 8 and all(row["content_revision"] == revision and row["level_id"] and row["material_id"] for row in csv_rows)
              and near(math.fsum(float(row["net_volume_m3"]) for row in csv_rows), data["material_totals"]["net_volume_m3"]))
        with (output / "Types_Quantities_types.csv").open(encoding="utf-8-sig", newline="") as stream:
            csv_types = list(csv.DictReader(stream))
        check("type CSV layers use parseable ordered JSON and resolved SI dimensions",
              len(csv_types) == 6 and len(json.loads(next(row for row in csv_types if row["type_id"] == slab_type.BIM3117Id)["layers"])) == 2)
        metadata = json.loads(Path(csv_result["metadata_path"]).read_text(encoding="utf-8"))
        check("catalogue bundle metadata verifies all published payload hashes",
              all(hashlib.sha256((output / item["name"]).read_bytes()).hexdigest() == item["sha256"] for item in metadata["files"])
              and metadata["snapshot"]["material_totals"]["assigned_product_count"] == 6)
        ifc_path = output / "Types_Quantities.ifc"
        ifc_result = exchange.export_ifc(project, ifc_path, expected_revision=revision)
        check("serialized IFC passes exact typed material relationship, quantity and solid validation",
              ifc_result["validation"]["status"] == "passed")
        import ifcopenshell
        model = ifcopenshell.open(str(ifc_path))
        check("IFC keeps one authored product and one actual shared type per category",
              all(len(model.by_type("Ifc" + category)) == len(model.by_type("Ifc" + category + "Type")) == 1
                  for category in ("Wall", "Slab", "Column", "Beam", "Door", "Window"))
              and len(model.by_type("IfcMaterial")) == 4 and len(model.by_type("IfcMaterialLayerSet")) == 2)
        usages = {usage.LayerSetDirection: usage for usage in model.by_type("IfcMaterialLayerSetUsage")}
        check("IFC wall/slab material orientations match unchanged native prism origins",
              usages["AXIS2"].DirectionSense == "POSITIVE" and near(usages["AXIS2"].OffsetFromReferenceLine, 0)
              and usages["AXIS3"].DirectionSense == "NEGATIVE" and near(usages["AXIS3"].OffsetFromReferenceLine, .15))
        native_file = output / "Types_Quantities_Workbench.FCStd"
        doc.saveAs(str(native_file))
        saved = snapshot.capture(project)
        check("saving FCStd does not change native content or quantity identity", saved["content_revision"] == revision)
        (output / "types-exchange-snapshot.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        report.update(status="passed", checks_passed=len(report["checks"]), content_revision=revision,
                      sample=str(native_file), ifc=str(ifc_path), ifc_validation=ifc_result["validation"],
                      element_ids={obj.Name: obj.BIM3117Id for obj in doc.Objects if kind(obj)},
                      material_totals=data["material_totals"], expected_volumes=expected,
                      wall_name=wall.Name, slab_type_name=slab_type.Name,
                      rooted_ifc_ids=sorted(item.GlobalId for item in model.by_type("IfcRoot")))
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "types-exchange-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for name in documents:
            App.closeDocument(name)
    return report


def reopen(output_dir):
    """Run after main in a fresh installed-host process."""
    output = Path(output_dir)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": []}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    try:
        prior = json.loads((output / "types-exchange-test-report.json").read_text(encoding="utf-8"))
        check("prior installed-native suite passed", prior["status"] == "passed")
        check("native catalogue proxies are not preregistered before restore", "bim3117_freecad.catalog" not in sys.modules)
        doc = App.openDocument(prior["sample"])
        doc.recompute()
        from bim3117_freecad import exchange, services, snapshot
        from bim3117_freecad.model import kind
        project = services.get_project(doc)
        captured = snapshot.capture(project)
        check("fresh FCStd restores exact authored content revision", captured["content_revision"] == prior["content_revision"])
        check("fresh FCStd restores stable material, type and product UUIDs",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects if kind(obj)} == prior["element_ids"])
        check("fresh FCStd restores material partition rows and assignment coverage",
              captured["material_totals"] == prior["material_totals"] and len(captured["material_rows"]) == 8)
        current = exchange.export_ifc(project, output / "Types_Quantities_Reopened.ifc", expected_revision=prior["content_revision"])
        import ifcopenshell
        model = ifcopenshell.open(str(output / "Types_Quantities_Reopened.ifc"))
        check("fresh IFC publication validates type, layer and native solids", current["validation"]["status"] == "passed")
        check("fresh IFC publication preserves all rooted GlobalIds", sorted(item.GlobalId for item in model.by_type("IfcRoot")) == prior["rooted_ifc_ids"])
        report.update(status="passed", checks_passed=len(report["checks"]), content_revision=captured["content_revision"],
                      ifc_validation=current["validation"])
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "types-exchange-reopen-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
