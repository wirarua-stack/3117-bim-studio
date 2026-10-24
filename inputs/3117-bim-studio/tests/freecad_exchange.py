# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-host checks for native quantity snapshots and CSV / IFC exchange.

Run against the installed workbench, with its host's IfcOpenShell available.
This is a Linux/Windows-capable harness, not a claim that both hosts were run.
The exported IFC is a candidate for separate Bonsai application inspection.
"""
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App
import Part

from bim3117_freecad import exchange, services, snapshot
from bim3117_freecad.model import FoundationError


def _near(actual, expected):
    return abs(float(actual) - float(expected)) <= max(1e-8, abs(float(expected)) * 1e-8)


def _row(data, category, identifier):
    return next(row for row in data[category + "_rows"] if row["element_id"] == identifier)


def _csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _file_hashes(paths):
    return {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}


def _document_observation(doc):
    """Observe authored identity/references and native solids independently."""
    rows = []
    for obj in doc.Objects:
        item = [obj.Name, obj.Label, services.kind(obj), getattr(obj, "BIM3117Id", "")]
        for name in ("Project", "WallType", "BaseLevel", "TopLevel", "Host", "Wall", "Body"):
            reference = getattr(obj, name, None)
            item.append(getattr(reference, "Name", None))
        for name in ("Elevation", "Thickness", "StartX", "StartY", "EndX", "EndY", "BaseOffset",
                     "TopOffset", "Offset", "Width", "Height", "Sill"):
            value = getattr(obj, name, None)
            item.append(float(value.Value) if hasattr(value, "Value") else value)
        if "Shape" in obj.PropertiesList:
            shape = obj.Shape
            item.append(shape.isNull())
            if not shape.isNull():
                box = shape.BoundBox
                item.extend(round(value, 7) for value in
                            (shape.Volume, box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax))
        rows.append(item)
    return rows


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Installed native quantity / CSV / IFC4 exchange; separate-app review is independent"}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    def rejects(name, operation, errors=(FoundationError, ValueError, FileExistsError)):
        try:
            operation()
        except errors:
            check(name, True)
        else:
            raise AssertionError(name + ": operation was incorrectly accepted")

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("snapshot and exchange are loaded from the installed addon",
              Path(snapshot.__file__).resolve().is_relative_to(installed)
              and Path(exchange.__file__).resolve().is_relative_to(installed))
        project = services.create_project("3117 ปริมาณและ IFC", "QTY-003", "3117 BIM")
        doc = project.Document
        lower, upper = services.list_levels(project)
        wall_type = services.create_wall_type(project, "W200", thickness_mm=200, material="Concrete")
        wall = services.create_wall(project, "W200", wall_type, lower, upper,
                                    end_x_mm=6000, end_y_mm=0)
        original_wall_label = wall.Label
        door = services.create_door(project, "ประตู D01", wall, offset_mm=1200,
                                    width_mm=900, height_mm=2100, sill_mm=0)
        body = services.wall_body(wall)
        baseline = snapshot.capture(project)
        revision = baseline["content_revision"]
        check("content revision is a full deterministic SHA-256 digest",
              len(revision) == 64 and all(char in "0123456789abcdef" for char in revision)
              and snapshot.capture(project)["content_revision"] == revision)
        check("quantity rows count authored wall and door exactly once",
              len(baseline["wall_rows"]) == 1 and len(baseline["door_rows"]) == 1
              and baseline["wall_rows"][0]["element_id"] == wall.BIM3117Id
              and baseline["door_rows"][0]["element_id"] == door.BIM3117Id
              and body.BIM3117Id not in {r["element_id"] for r in baseline["wall_rows"]})
        row = _row(baseline, "wall", wall.BIM3117Id)
        check("independent SI length area and volume fixture is correct",
              all(_near(row[key], expected) for key, expected in {
                  "length_m": 6, "height_m": 3, "thickness_m": .2,
                  "gross_side_area_m2": 18, "opening_side_area_m2": 1.89,
                  "net_side_area_m2": 16.11, "gross_volume_m3": 3.6,
                  "opening_volume_m3": .378, "net_volume_m3": 3.222}.items())
              and _near(row["net_volume_m3"], body.Shape.Volume / 1e9))
        door_row = _row(baseline, "door", door.BIM3117Id)
        check("door row identifies its host and overall cut independently of the frame",
              door_row["host_id"] == wall.BIM3117Id and door_row["count"] == 1
              and _near(door_row["width_m"], .9) and _near(door_row["height_m"], 2.1)
              and _near(door_row["opening_area_m2"], 1.89)
              and _near(door_row["opening_volume_m3"], .378)
              and _near(door_row["frame_volume_m3"], door.Shape.Volume / 1e9)
              and door_row["frame_volume_m3"] < door_row["opening_volume_m3"])
        check("rows carry explicit rules, references and the snapshot revision",
              all(r["quantity_rule"] and r["content_revision"] == revision
                  for r in baseline["wall_rows"] + baseline["door_rows"])
              and row["type_id"] == wall_type.BIM3117Id
              and row["base_level_id"] == lower.BIM3117Id and row["top_level_id"] == upper.BIM3117Id)
        check("quantity identity uses source UUIDs even when the host disambiguates requested labels",
              row["element_id"] != row["type_id"]
              and row["name"] == wall.Label and row["type_name"] == wall_type.Label)
        observation, undo, redo = _document_observation(doc), doc.UndoCount, doc.RedoCount
        snapshot.capture(project)
        snapshot.is_current(project, baseline)
        check("capture and current checks preserve model geometry and native history",
              _document_observation(doc) == observation and doc.UndoCount == undo and doc.RedoCount == redo
              and not doc.HasPendingTransaction and App.getActiveTransaction() is None)

        services.edit_level(upper, elevation_mm=3300)
        changed = snapshot.capture(project)
        check("top-level edit changes revision and recalculates net quantity to 3.582 m3",
              changed["content_revision"] != revision
              and _near(_row(changed, "wall", wall.BIM3117Id)["net_volume_m3"], 3.582)
              and not snapshot.is_current(project, baseline) and snapshot.is_current(project, changed))
        stale_path = output / "stale_should_not_exist.csv"
        rejects("stale expected revision rejects export before writing",
                lambda: exchange.export_csv(project, stale_path, expected_revision=revision))
        check("stale export leaves no output file", not stale_path.exists())
        doc.undo()
        doc.recompute()
        check("Undo restores prior content revision and exact quantity",
              snapshot.is_current(project, revision)
              and _near(_row(snapshot.capture(project), "wall", wall.BIM3117Id)["net_volume_m3"], 3.222))
        doc.redo()
        doc.recompute()
        check("Redo restores changed revision rather than a fresh artificial counter",
              snapshot.capture(project)["content_revision"] == changed["content_revision"])
        doc.undo()
        doc.recompute()
        services.edit_wall_type(wall_type, thickness_mm=250)
        thick = snapshot.capture(project)
        check("shared type edit updates native solid and exported quantities",
              _near(_row(thick, "wall", wall.BIM3117Id)["thickness_m"], .25)
              and _near(_row(thick, "wall", wall.BIM3117Id)["net_volume_m3"], 4.0275))
        doc.undo()
        doc.recompute()
        check("type Undo restores the original snapshot identity", snapshot.is_current(project, revision))

        doc.openTransaction("Native quantity input edit")
        try:
            wall.EndX = 6500
            rejects("capture refuses an uncommitted native transaction", lambda: snapshot.capture(project))
            doc.recompute()
            doc.commitTransaction()
        except BaseException:
            doc.abortTransaction()
            raise
        check("committed Property Editor edit updates revision and measured quantity",
              snapshot.capture(project)["content_revision"] != revision
              and _near(_row(snapshot.capture(project), "wall", wall.BIM3117Id)["net_volume_m3"], 3.522))
        doc.undo()
        doc.recompute()
        check("native property Undo restores original content revision", snapshot.is_current(project, baseline))
        doc.openTransaction("Empty transaction capture guard")
        try:
            rejects("capture also refuses an empty active native transaction", lambda: snapshot.capture(project))
        finally:
            doc.abortTransaction()
            if App.getActiveTransaction() is not None:
                App.closeActiveTransaction()

        # Raw cached geometry can have a valid solid and correct volume while
        # occupying the wrong place. Bake the transform into the BRep, retain
        # identity Placement and clear Touched to prevent an automatic repair
        # from concealing the stale-solid defect we intend to detect.
        for candidate, category in ((body, "wall body"), (door, "door frame")):
            original_shape = candidate.Shape.copy()
            shift = App.Matrix()
            shift.move(App.Vector(10000, 0, 0))
            try:
                candidate.Shape = original_shape.transformGeometry(shift)
                candidate.purgeTouched()
                check("raw " + category + " probe retains volume but changes spatial geometry",
                      _near(candidate.Shape.Volume, original_shape.Volume)
                      and candidate.Shape.BoundBox.XMin > original_shape.BoundBox.XMin + 9999)
                rejects("snapshot rejects equal-volume displaced " + category,
                        lambda: snapshot.capture(project))
            finally:
                candidate.Shape = original_shape
                candidate.purgeTouched()
                doc.recompute()
        check("restoring cached geometry restores the original valid snapshot",
              snapshot.is_current(project, revision))

        csv_path = output / "ส่งออก_ภาษาไทย" / "ปริมาณ.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        doors_path = csv_path.with_name(csv_path.stem + "_doors.csv")
        csv_meta = csv_path.with_name(csv_path.stem + "_csv_metadata.json")
        observation, undo, redo = _document_observation(doc), doc.UndoCount, doc.RedoCount
        csv_result = exchange.export_csv(project, csv_path, expected_revision=revision)
        check("CSV bundle writes separate wall door and metadata files in Thai paths",
              all(path.is_file() for path in (csv_path, doors_path, csv_meta))
              and Path(csv_result["metadata_path"]) == csv_meta)
        wall_csv, door_csv = _csv_rows(csv_path), _csv_rows(doors_path)
        check("CSV contains native UUIDs SI values and explicit revision",
              len(wall_csv) == len(door_csv) == 1
              and wall_csv[0]["element_id"] == wall.BIM3117Id
              and door_csv[0]["host_id"] == wall.BIM3117Id
              and _near(wall_csv[0]["net_volume_m3"], 3.222)
              and wall_csv[0]["content_revision"] == revision
              and csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
        metadata = json.loads(csv_meta.read_text(encoding="utf-8"))
        check("CSV metadata identifies source revision and coverage",
              metadata["content_revision"] == revision and "coverage" in metadata)
        check("CSV export is a read-only operation with no Undo item",
              _document_observation(doc) == observation and (doc.UndoCount, doc.RedoCount) == (undo, redo))
        original_files = _file_hashes((csv_path, doors_path, csv_meta))
        rejects("existing output is preserved unless overwrite is explicit",
                lambda: exchange.export_csv(project, csv_path))
        check("refused overwrite preserves every previous file byte",
              _file_hashes((csv_path, doors_path, csv_meta)) == original_files)

        services.edit_wall(wall, name="=2+3")
        services.edit_door(door, name="@door")
        safe_path = csv_path.parent / "spreadsheet_text.csv"
        exchange.export_csv(project, safe_path)
        safe_wall = _csv_rows(safe_path)[0]
        safe_door = _csv_rows(safe_path.with_name(safe_path.stem + "_doors.csv"))[0]
        safe_meta = json.loads(safe_path.with_name(safe_path.stem + "_csv_metadata.json").read_text(encoding="utf-8"))
        check("spreadsheet formula text is neutralized without altering numeric columns",
              safe_wall["name"] == "'=2+3" and safe_door["name"] == "'@door"
              and _near(safe_wall["net_volume_m3"], 3.222)
              and "=2+3" in json.dumps(safe_meta, ensure_ascii=False))
        doc.undo()
        doc.recompute()
        doc.undo()
        doc.recompute()
        check("renaming and Undo preserve row UUIDs and restore original revision",
              snapshot.is_current(project, revision)
              and _row(snapshot.capture(project), "wall", wall.BIM3117Id)["name"] == original_wall_label)

        grid = services.create_grid(project, "Grid A", level=lower)
        unsupported = doc.addObject("Part::Feature", "UnsupportedSolid")
        unsupported.Label = "Unmapped reference block"
        unsupported.Shape = Part.makeBox(500, 500, 500)
        doc.recompute()
        mixed = snapshot.capture(project)
        coverage = {item["object_name"]: item for item in mixed["coverage"]["items"]}
        check("coverage explicitly distinguishes mapped derived reference and unsupported objects",
              coverage[wall.Name]["status"] == "mapped"
              and coverage[body.Name]["status"] == "derived"
              and coverage[grid.Name]["status"] == "reference"
              and coverage[unsupported.Name]["status"] == "unsupported"
              and not mixed["coverage"]["complete"])
        check("unsupported solid and derived wall body do not create duplicate quantity rows",
              len(mixed["wall_rows"]) == len(mixed["door_rows"]) == 1
              and mixed["content_revision"] != revision)
        coverage_path = output / "coverage.csv"
        coverage_result = exchange.export_csv(project, coverage_path)
        check("export returns the same explicit omission inventory as the captured model",
              coverage_result["coverage"] == mixed["coverage"])
        doc.openTransaction("Remove disposable coverage fixtures")
        doc.removeObject(unsupported.Name)
        project.removeObject(grid)
        doc.removeObject(grid.Name)
        doc.recompute()
        doc.commitTransaction()
        check("removing temporary coverage fixtures restores original content identity",
              snapshot.is_current(project, revision))

        # Invalidate one native graph using an unsupported raw deletion, then
        # restore it with host Undo. Export must fail before publishing bytes.
        type_name = wall_type.Name
        doc.openTransaction("Unsupported raw type removal")
        doc.removeObject(type_name)
        doc.recompute()
        doc.commitTransaction()
        invalid_path = output / "invalid_should_not_exist.csv"
        rejects("invalid native reference graph cannot be captured", lambda: snapshot.capture(project))
        rejects("invalid native reference graph cannot publish CSV", lambda: exchange.export_csv(project, invalid_path))
        check("invalid export leaves no published file", not invalid_path.exists())
        doc.undo()
        doc.recompute()
        wall_type = doc.getObject(type_name)
        check("Undo restores model validity and revision after invalid raw deletion",
              services.validate_document(doc, check_shapes=True) and snapshot.is_current(project, revision))

        import ifcopenshell
        import ifcopenshell.util.element
        report["ifcopenshell"] = ifcopenshell.version
        ifc_path = csv_path.with_suffix(".ifc")
        observation, undo, redo = _document_observation(doc), doc.UndoCount, doc.RedoCount
        ifc_result = exchange.export_ifc(project, ifc_path, expected_revision=revision)
        ifc_meta = ifc_path.with_name(ifc_path.stem + "_ifc_metadata.json")
        model = ifcopenshell.open(str(ifc_path))
        check("native IFC4 exports one wall door opening and type without derived duplicates",
              model.schema == "IFC4" and len(model.by_type("IfcWall")) == 1
              and len(model.by_type("IfcDoor")) == 1 and len(model.by_type("IfcOpeningElement")) == 1
              and len(model.by_type("IfcWallType")) == 1 and len(model.by_type("IfcBuildingStorey")) == 2)
        ifc_wall, ifc_door = model.by_type("IfcWall")[0], model.by_type("IfcDoor")[0]
        opening = model.by_type("IfcOpeningElement")[0]
        check("native IFC preserves UUID-derived GUIDs and real host void fill relationships",
              ifc_wall.GlobalId == ifcopenshell.guid.compress(wall.BIM3117Id.replace("-", ""))
              and ifc_door.GlobalId == ifcopenshell.guid.compress(door.BIM3117Id.replace("-", ""))
              and opening.VoidsElements[0].RelatingBuildingElement == ifc_wall
              and ifc_door.FillsVoids[0].RelatingOpeningElement == opening)
        check("CSV and IFC sharing a stem keep independent metadata files",
              csv_meta.is_file() and ifc_meta.is_file()
              and _file_hashes((csv_path, doors_path, csv_meta)) == original_files
              and json.loads(ifc_meta.read_text(encoding="utf-8"))["content_revision"] == revision)
        check("IFC export validates and preserves native geometry and Undo Redo state",
              ifc_result["validation"] and _document_observation(doc) == observation
              and (doc.UndoCount, doc.RedoCount) == (undo, redo))
        repeat_path = output / "repeat.ifc"
        exchange.export_ifc(project, repeat_path)
        repeat = ifcopenshell.open(str(repeat_path))
        check("repeat native IFC export preserves every rooted GlobalId",
              {item.GlobalId for item in model.by_type("IfcRoot")}
              == {item.GlobalId for item in repeat.by_type("IfcRoot")})

        # Produce a useful independent-app fixture covering rotated/reversed
        # axes, a signed basement level, offsets and nonzero door sill.
        basement = services.add_level(project, "B01", -3000)
        diagonal = services.create_wall(project, "Diagonal basement", wall_type, basement, lower,
                                         start_x_mm=0, start_y_mm=6000, end_x_mm=3000, end_y_mm=10000,
                                         base_offset_mm=100, top_offset_mm=-200)
        diagonal_door = services.create_door(project, "Basement door", diagonal, offset_mm=500,
                                             width_mm=800, height_mm=2000, sill_mm=100)
        reversed_wall = services.create_wall(project, "Reversed wall", wall_type, lower, upper,
                                              start_x_mm=6000, start_y_mm=4000, end_x_mm=2000, end_y_mm=4000)
        reversed_door = services.create_door(project, "Reversed door", reversed_wall, offset_mm=700,
                                              width_mm=800, height_mm=2100, sill_mm=0)
        grid = services.create_grid(project, "Grid A", level=lower)
        final = snapshot.capture(project)
        expected_net = {wall.BIM3117Id: 3.222, diagonal.BIM3117Id: 2.38, reversed_wall.BIM3117Id: 2.064}
        check("multiwall sample quantities use native axes elevations and offsets",
              len(final["wall_rows"]) == len(final["door_rows"]) == 3
              and all(_near(_row(final, "wall", key)["net_volume_m3"], value)
                      for key, value in expected_net.items()))
        sample = output / "save_ภาษาไทย" / "Quantity_Exchange_Workbench.FCStd"
        sample.parent.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(sample))
        check("saving FCStd does not change model content revision",
              snapshot.capture(project)["content_revision"] == final["content_revision"])
        final_ifc = output / "Quantity_Exchange_Workbench.ifc"
        final_ifc_result = exchange.export_ifc(project, final_ifc, expected_revision=final["content_revision"])
        final_csv_result = exchange.export_csv(project, output / "Quantity_Exchange_Workbench.csv",
                                                expected_revision=final["content_revision"])
        (output / "exchange-snapshot.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects if services.kind(obj)}
        names = {"project": project.Name, "wall": wall.Name, "body": body.Name,
                 "door": door.Name, "type": wall_type.Name, "base": lower.Name, "top": upper.Name,
                 "basement": basement.Name, "diagonal": diagonal.Name,
                 "diagonal_door": diagonal_door.Name, "reversed_wall": reversed_wall.Name,
                 "reversed_door": reversed_door.Name}
        report.update(status="passed", checks_passed=len(report["checks"]), sample=str(sample),
                      baseline_revision=revision, content_revision=final["content_revision"],
                      element_ids=identifiers, element_names=names, expected_net_volumes_m3=expected_net,
                      ifc=str(final_ifc), ifc_result=final_ifc_result, csv_result=final_csv_result)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(),
                      checks_passed=len(report["checks"]))
        with (output / "exchange-attempt-errors.jsonl").open("a", encoding="utf-8") as failed:
            failed.write(json.dumps(report, ensure_ascii=False) + "\n")
        raise
    finally:
        (output / "exchange-test-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
    return report


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/bim3117-exchange-tests"), indent=2))
