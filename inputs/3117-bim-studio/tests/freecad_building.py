# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed-host Building Authoring acceptance with independent numeric fixtures.

Creates disposable documents. The final two-storey sample is synthetic, not a
structural design or a claim of whole-building, intersection-free quantities.
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
import Part

from bim3117_freecad import exchange, services, snapshot
from bim3117_freecad.model import FoundationError, kind


def near(actual, expected, relative=1e-8):
    return abs(float(actual) - float(expected)) <= max(1e-8, abs(float(expected)) * relative)


def row(data, category, obj):
    return next(item for item in data[category + "_rows"] if item["element_id"] == obj.BIM3117Id)


def volume(obj):
    return obj.Shape.Volume / 1e9


def observation(doc):
    """Read identity, references, authored values and native solid bounds."""
    observed = []
    for obj in doc.Objects:
        value = [obj.Name, obj.Label, kind(obj), getattr(obj, "BIM3117Id", "")]
        for name in ("Project", "Level", "BaseLevel", "TopLevel", "WallType", "Host", "Wall", "Body"):
            value.append(getattr(getattr(obj, name, None), "Name", None))
        value.append([item.Name for item in getattr(obj, "JoinSlabs", [])])
        for name in ("Elevation", "Thickness", "Offset", "X", "Y", "Width", "Depth", "Rotation",
                     "BaseOffset", "TopOffset", "StartX", "StartY", "EndX", "EndY", "Sill", "Height"):
            item = getattr(obj, name, None)
            value.append(float(item.Value) if hasattr(item, "Value") else item)
        value.append([(point.x, point.y, point.z) for point in getattr(obj, "Boundary", [])])
        if "Shape" in obj.PropertiesList:
            shape = obj.Shape
            value.append(shape.isNull())
            if not shape.isNull():
                box = shape.BoundBox
                value.extend(round(item, 7) for item in
                             (shape.Volume, box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax))
        observed.append(value)
    return observed


def make_example():
    """Build the coherent, two-storey release fixture with independent expectations."""
    project = services.create_project("3117 อาคารสองชั้น", "BLD-030", "3117 BIM")
    lower, first = services.list_levels(project)
    second = services.add_level(project, "L02", 6000)
    levels = [lower, first, second]
    boundary = [(-250, -250), (6250, -250), (6250, 4250), (-250, 4250)]
    slabs = [services.create_slab(project, f"S{index:02d}", level, boundary,
                                 thickness_mm=150, material="Concrete")
             for index, level in enumerate(levels)]
    points = [(0, 0), (6000, 0), (6000, 4000), (0, 4000)]
    columns, beams, walls, doors, windows = [], [], [], [], []
    wall_type = services.create_wall_type(project, "Block 200", 200, "Blockwork")
    wall_axes = [((150, 150), (5850, 150)), ((5850, 150), (5850, 3850)),
                 ((5850, 3850), (150, 3850)), ((150, 3850), (150, 150))]
    expected = {"Slab": {}, "Column": {}, "Beam": {}, "Wall": {}, "Door": {}, "Window": {}}
    for slab in slabs:
        expected["Slab"][slab.BIM3117Id] = 4.3875
    for storey in range(2):
        base, top, cutter = levels[storey], levels[storey + 1], slabs[storey + 1]
        for index, (x, y) in enumerate(points):
            column = services.create_column(project, f"C{storey + 1}{index + 1}", base, top,
                                            x_mm=x, y_mm=y, width_mm=300, depth_mm=300,
                                            material="Concrete")
            services.join_slab(column, cutter)
            columns.append(column)
            expected["Column"][column.BIM3117Id] = .2565
            end = points[(index + 1) % 4]
            beam = services.create_beam(project, f"B{storey + 1}{index + 1}", top,
                                        start_mm=(x, y), end_mm=end,
                                        width_mm=300, depth_mm=450, material="Concrete")
            services.join_slab(beam, cutter)
            beams.append(beam)
            expected["Beam"][beam.BIM3117Id] = .54 if index % 2 == 0 else .36
        for index, (start, end) in enumerate(wall_axes):
            wall = services.create_wall(project, f"Wall {storey + 1}-{index + 1}", wall_type, base, top,
                                        start_x_mm=start[0], start_y_mm=start[1],
                                        end_x_mm=end[0], end_y_mm=end[1], top_offset_mm=-450)
            walls.append(wall)
            expected["Wall"][wall.BIM3117Id] = [2.241, 1.599, 2.907, 1.887][index]
            if index == 0:
                door = services.create_door(project, f"D{storey + 1:02d}", wall,
                                            offset_mm=800, width_mm=900, height_mm=2100)
                doors.append(door)
                expected["Door"][door.BIM3117Id] = .05
            if index in (0, 1):
                window = services.create_window(project, f"WIN{storey + 1}{index + 1}", wall,
                                                offset_mm=3000 if index == 0 else 1200,
                                                width_mm=1200, height_mm=1200, sill_mm=900)
                windows.append(window)
                expected["Window"][window.BIM3117Id] = .046
    for label, axis, position, length in [("A", "X", 0, 6500), ("B", "X", 4000, 6500),
                                         ("1", "Y", 0, 4500), ("2", "Y", 6000, 4500)]:
        services.create_grid(project, label, axis=axis, position_mm=position, length_mm=length, level=lower)
    return project, expected


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Native Slab/Column/Beam/Window, directed slab cuts, SI quantities and IFC4"}
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
            raise AssertionError(name + ": operation was accepted")

    def undo(doc):
        doc.undo()
        doc.recompute()

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        from bim3117_freecad import elements
        check("new native model and exchange code load from the installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed)
                  for module in (elements, services, snapshot, exchange)))
        project = services.create_project("Building acceptance", "QA-030", "3117 BIM")
        doc = project.Document
        documents.append(doc.Name)
        base, top = services.list_levels(project)
        footprint = [(-250, -250), (6250, -250), (6250, 4250), (-250, 4250)]
        slab = services.create_slab(project, "Slab 150", top, footprint, thickness_mm=150, material="Concrete")
        check("slab top follows its Level and thickness extends downward",
              near(slab.Shape.BoundBox.ZMax, 3000) and near(slab.Shape.BoundBox.ZMin, 2850)
              and near(volume(slab), 4.3875) and len(slab.Shape.Solids) == 1)
        data = snapshot.capture(project)
        check("slab row has independent SI plan area perimeter thickness and volume",
              near(row(data, "slab", slab)["gross_area_m2"], 29.25)
              and near(row(data, "slab", slab)["perimeter_m"], 22)
              and near(row(data, "slab", slab)["thickness_m"], .15)
              and near(row(data, "slab", slab)["net_volume_m3"], 4.3875))
        initial = data["content_revision"]
        services.edit_slab(slab, thickness_mm=200)
        check("slab thickness edit preserves the top datum and changes native quantity",
              near(slab.Shape.BoundBox.ZMax, 3000) and near(slab.Shape.BoundBox.ZMin, 2800)
              and near(volume(slab), 5.85))
        undo(doc)
        check("slab Undo restores geometry and the original content revision",
              snapshot.capture(project)["content_revision"] == initial and near(volume(slab), 4.3875))
        services.edit_level(top, elevation_mm=3300)
        check("Level edit moves the complete slab without changing its thickness or volume",
              near(slab.Shape.BoundBox.ZMax, 3300) and near(slab.Shape.BoundBox.ZMin, 3150)
              and near(volume(slab), 4.3875))
        undo(doc)
        check("Level Undo restores slab revision", snapshot.capture(project)["content_revision"] == initial)
        before = observation(doc)
        rejects("self-intersecting slab boundary is rejected",
                lambda: services.edit_slab(slab, boundary_mm=[(0, 0), (4000, 4000), (0, 4000), (4000, 0)]))
        rejects("non-planar slab boundary is rejected",
                lambda: services.edit_slab(slab, boundary_mm=[(0, 0, 0), (4000, 0, 1), (4000, 4000, 0), (0, 4000, 0)]))
        rejects("zero thickness is rejected", lambda: services.edit_slab(slab, thickness_mm=0))
        rejects("non-finite slab coordinate is rejected",
                lambda: services.edit_slab(slab, boundary_mm=[(0, 0), (float("nan"), 0), (0, 4000)]))
        check("invalid slab operations preserve the complete prior model", observation(doc) == before)
        concave = services.create_slab(project, "Concave L", base,
                                      [(8000, 0), (12000, 0), (12000, 2000),
                                       (10000, 2000), (10000, 4000), (8000, 4000)], thickness_mm=200)
        check("concave footprint measures actual polygon area rather than its bounding rectangle",
              near(volume(concave), 2.4)
              and near(row(snapshot.capture(project), "slab", concave)["gross_area_m2"], 12))
        notch = Part.makeBox(500, 500, 50, App.Vector(10500, 2500, -100))
        check("concave footprint notch is genuinely empty", concave.Shape.common(notch).Volume < 1e-5)
        services.edit_slab(concave, boundary_mm=list(reversed([(8000, 0), (12000, 0), (12000, 2000),
                                                               (10000, 2000), (10000, 4000), (8000, 4000)])))
        check("reversed polygon winding preserves the positive solid", near(volume(concave), 2.4))
        services.delete_slab(concave)

        column = services.create_column(project, "Column rotated", base, top,
                                        x_mm=1500, y_mm=1000, width_mm=300, depth_mm=400, rotation_deg=30)
        beam = services.create_beam(project, "Beam 6m", top, start_mm=(0, 2000), end_mm=(6000, 2000),
                                    width_mm=300, depth_mm=450)
        column_id, beam_id = column.BIM3117Id, beam.BIM3117Id
        half_x = (300 * math.cos(math.pi / 6) + 400 * math.sin(math.pi / 6)) / 2
        half_y = (300 * math.sin(math.pi / 6) + 400 * math.cos(math.pi / 6)) / 2
        check("rotated column uses its centre section and Base/Top Levels",
              near(volume(column), .36) and near(column.Shape.BoundBox.ZMin, 0)
              and near(column.Shape.BoundBox.ZMax, 3000)
              and near(column.Shape.BoundBox.XMin, 1500 - half_x)
              and near(column.Shape.BoundBox.YMax, 1000 + half_y))
        check("beam is centred about its XY axis and extends below its top datum",
              near(volume(beam), .81) and near(beam.Shape.BoundBox.YMin, 1850)
              and near(beam.Shape.BoundBox.YMax, 2150)
              and near(beam.Shape.BoundBox.ZMin, 2550) and near(beam.Shape.BoundBox.ZMax, 3000))
        doc.clearUndos()
        services.join_slab(beam, slab)
        joined_beam_revision = snapshot.capture(project)["content_revision"]
        check("one slab join creates one native transaction and preserves the beam identity",
              doc.UndoCount == 1 and beam.BIM3117Id == beam_id and slab in beam.JoinSlabs)
        check("beam-slab cut removes actual intersection and preserves authored depth",
              near(volume(beam), .54) and near(beam.Depth.Value, 450)
              and near(beam.Shape.BoundBox.ZMax, 2850)
              and beam.Shape.common(slab.Shape).Volume < 1e-4)
        undo(doc)
        check("join Undo heals the beam and removes the reference", near(volume(beam), .81) and not beam.JoinSlabs)
        doc.redo(); doc.recompute()
        check("join Redo restores shape references and revision",
              near(volume(beam), .54) and snapshot.capture(project)["content_revision"] == joined_beam_revision)
        services.join_slab(column, slab)
        check("slab priority cuts a rotated column top without splitting it",
              near(volume(column), .342) and len(column.Shape.Solids) == 1 and column.BIM3117Id == column_id)
        data = snapshot.capture(project)
        check("structural rows distinguish gross join deduction and actual net volume",
              all(near(row(data, category, obj)[key], value)
                  for category, obj, values in [
                      ("beam", beam, {"gross_volume_m3": .81, "join_deduction_m3": .27, "net_volume_m3": .54}),
                      ("column", column, {"gross_volume_m3": .36, "join_deduction_m3": .018, "net_volume_m3": .342})]
                  for key, value in values.items()))
        before = observation(doc)
        rejects("a joined slab cannot be deleted", lambda: services.delete_slab(slab))
        rejects("a referenced Level cannot be deleted", lambda: services.delete_level(top))
        rejects("slab change that fully cuts a beam rolls back", lambda: services.edit_slab(slab, thickness_mm=500))
        rejects("invalid shared Level edit rolls back new dependent elements",
                lambda: services.edit_level(top, elevation_mm=-100))
        check("all rejected dependency edits preserve solids and authored values", observation(doc) == before)
        services.edit_slab(slab, thickness_mm=160)
        undo(doc)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        rejects("invalid slab proposal after Undo is rejected before changing history",
                lambda: services.edit_slab(slab, thickness_mm=500))
        check("rejected slab cut preserves the existing native Redo branch",
              history[1] > 0 and history == (doc.UndoCount, doc.RedoCount) and observation(doc) == before)
        doc.redo(); doc.recompute()
        check("preserved Slab Redo still applies its valid thickness and member cuts",
              near(slab.Thickness.Value, 160) and near(volume(beam), .522))
        undo(doc)
        splitter = services.create_slab(project, "Interior split rejected", top, footprint,
                                        thickness_mm=150, offset_mm=-1000)
        services.edit_column(column, name="Column valid rename")
        undo(doc)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        rejects("join that splits a column into disconnected solids is rejected",
                lambda: services.join_slab(column, splitter))
        check("failed split join leaves no half-applied reference or solid", observation(doc) == before)
        check("rejected split join preserves the existing native Redo branch",
              history[1] > 0 and history == (doc.UndoCount, doc.RedoCount))
        services.delete_slab(splitter)
        services.edit_slab(slab, offset_mm=150)
        check("moving a referenced slab away preserves join intent with zero deduction",
              slab in beam.JoinSlabs and near(volume(beam), .81) and near(volume(column), .36)
              and near(row(snapshot.capture(project), "beam", beam)["join_deduction_m3"], 0))
        undo(doc)
        services.unjoin_slab(column, slab)
        check("Unjoin heals a member without altering the cutter or other joined members",
              near(volume(column), .36) and not column.JoinSlabs and near(volume(beam), .54)
              and near(volume(slab), 4.3875))
        undo(doc)
        check("Unjoin Undo restores the column cut", near(volume(column), .342) and slab in column.JoinSlabs)
        before = observation(doc)
        rejects("zero-length beam is rejected", lambda: services.edit_beam(beam, end_mm=(0, 2000)))
        rejects("negative column section is rejected", lambda: services.edit_column(column, width_mm=-1))
        rejects("unsupported member-to-member cutter is rejected", lambda: services.join_slab(beam, column))
        check("invalid member operations preserve the entire model", observation(doc) == before)
        services.edit_beam(beam, width_mm=350)
        undo(doc)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        rejects("joined beam section that would be fully removed is rejected before history changes",
                lambda: services.edit_beam(beam, depth_mm=100))
        check("rejected joined Beam section preserves the native Redo branch",
              history[1] > 0 and history == (doc.UndoCount, doc.RedoCount) and observation(doc) == before)
        doc.redo(); doc.recompute()
        check("preserved Beam Redo still applies its valid section", near(beam.Width.Value, 350) and near(volume(beam), .63))
        undo(doc)
        services.edit_column(column, rotation_deg=45)
        undo(doc)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        rejects("joined column height that creates a disconnected cap is rejected before history changes",
                lambda: services.edit_column(column, top_offset_mm=100))
        check("rejected joined Column proposal preserves the native Redo branch",
              history[1] > 0 and history == (doc.UndoCount, doc.RedoCount) and observation(doc) == before)
        doc.redo(); doc.recompute()
        check("preserved Column Redo still applies its valid rotation",
              near(column.Rotation.Value, 45) and near(volume(column), .342))
        undo(doc)

        wall_type = services.create_wall_type(project, "W200", 200)
        wall = services.create_wall(project, "Host Wall", wall_type, base, top, end_x_mm=6000)
        door = services.create_door(project, "Door", wall, offset_mm=700, width_mm=900, height_mm=2100)
        window = services.create_window(project, "Window", wall, offset_mm=3000,
                                        width_mm=1200, height_mm=1200, sill_mm=900)
        body = services.wall_body(wall)
        check("Door and Window jointly cut their host wall", near(volume(body), 2.934))
        probe = Part.makeBox(600, 100, 600, App.Vector(3300, 50, 1200))
        check("window opening is empty through the native wall and its frame centre",
              body.Shape.common(probe).Volume < 1e-4 and window.Shape.common(probe).Volume < 1e-4)
        sill_probe = Part.makeBox(300, 100, 20, App.Vector(3400, 50, 910))
        check("window has a real lower frame bar in contrast to the existing three-bar door",
              window.Shape.common(sill_probe).Volume > 1 and near(volume(window), .046))
        data = snapshot.capture(project)
        check("window row carries source host and actual cut/frame quantities",
              row(data, "window", window)["host_id"] == wall.BIM3117Id
              and near(row(data, "window", window)["opening_area_m2"], 1.44)
              and near(row(data, "window", window)["frame_volume_m3"], .046))
        services.edit_window(window, offset_mm=3500)
        undo(doc)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        rejects("window overlapping an existing door is rejected",
                lambda: services.edit_window(window, offset_mm=1000))
        rejects("door overlapping an existing window is rejected",
                lambda: services.edit_door(door, offset_mm=3100))
        rejects("window exceeding host height is rejected", lambda: services.edit_window(window, sill_mm=2500))
        check("failed mixed openings preserve host and both frames", observation(doc) == before)
        check("rejected mixed opening proposals preserve the native Redo branch",
              history[1] > 0 and history == (doc.UndoCount, doc.RedoCount))
        doc.redo(); doc.recompute()
        check("preserved Window Redo still applies its valid opening relocation",
              near(window.Offset.Value, 3500) and near(volume(body), 2.934))
        undo(doc)
        second_host = services.create_wall(project, "Rehost target", wall_type, base, top,
                                           start_x_mm=8000, start_y_mm=0, end_x_mm=8000, end_y_mm=6000)
        services.edit_window(window, host=second_host)
        check("window rehost heals the old wall and cuts the rotated destination",
              near(volume(body), 3.222) and near(volume(services.wall_body(second_host)), 3.312)
              and near(window.Shape.BoundBox.XMin, 7800)
              and window.Host == second_host)
        undo(doc)
        check("rehost Undo restores original identity host and both wall solids",
              window.Host == wall and near(volume(body), 2.934)
              and near(volume(services.wall_body(second_host)), 3.6))
        window_id = window.BIM3117Id
        services.delete_window(window)
        check("deleting a window heals its host while preserving the door", near(volume(body), 3.222))
        undo(doc)
        window = next(item for item in services.list_windows(project) if item.BIM3117Id == window_id)
        check("window deletion Undo restores persistent identity and opening", near(volume(body), 2.934) and window.Host == wall)
        baseline = snapshot.capture(project)
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        snapshot.capture(project)
        check("expanded snapshot is read-only for authored content and native history",
              observation(doc) == before and history == (doc.UndoCount, doc.RedoCount))
        doc.openTransaction("QA direct slab property edit")
        slab.Thickness = 100
        rejects("expanded snapshot rejects a pending native edit", lambda: snapshot.capture(project))
        doc.recompute();doc.commitTransaction()
        check("direct native thickness edit propagates to joined members",
              near(volume(beam), .63) and near(volume(column), .348))
        undo(doc)
        check("direct-property Undo restores revision and all join quantities",
              snapshot.capture(project)["content_revision"] == baseline["content_revision"])
        original_shape = slab.Shape.copy()
        shift = App.Matrix()
        shift.move(App.Vector(100, 0, 0))
        try:
            # Bake the offset into BRep geometry and clear Touched, keeping
            # Placement identity so automatic repair cannot conceal the probe.
            slab.Shape = original_shape.transformGeometry(shift)
            slab.purgeTouched()
            check("raw slab probe preserves volume while shifting actual geometry",
                  near(slab.Shape.Volume, original_shape.Volume)
                  and near(slab.Shape.BoundBox.XMin, original_shape.BoundBox.XMin + 100))
            rejects("same-volume displaced Slab is rejected by spatial export validation",
                    lambda: snapshot.capture(project))
        finally:
            slab.Shape = original_shape
            slab.purgeTouched()
            doc.recompute()

        # Backward restore: old file bytes are never overwritten.
        legacy = Path(__file__).resolve().parents[1] / "examples" / "exchange" / "Quantity_Exchange_Workbench.FCStd"
        legacy_snapshot = legacy.with_name("exchange-snapshot.json")
        old_hash = hashlib.sha256(legacy.read_bytes()).hexdigest()
        old_doc = App.openDocument(str(legacy));documents.append(old_doc.Name)
        legacy_data = snapshot.capture(services.get_project(old_doc))
        check("v0.2.1 sample retains its authored revision with empty new categories",
              legacy_data["content_revision"] == json.loads(legacy_snapshot.read_text(encoding="utf-8"))["content_revision"]
              and all(not legacy_data[k + "_rows"] for k in ("slab", "column", "beam", "window")))
        legacy_name = old_doc.Name
        App.closeDocument(legacy_name)
        documents.remove(legacy_name)
        check("legacy sample remains byte-identical", hashlib.sha256(legacy.read_bytes()).hexdigest() == old_hash)

        project, expected = make_example()
        doc = project.Document;documents.append(doc.Name)
        data = snapshot.capture(project)
        check("two-storey fixture has every authored category with no derived duplicate rows",
              {name:len(data[name + "_rows"]) for name in ("slab", "column", "beam", "wall", "door", "window")}
              == {"slab":3,"column":8,"beam":8,"wall":8,"door":2,"window":4})
        for category, values in expected.items():
            for identifier, expected_volume in values.items():
                obj = next(item for item in doc.Objects if getattr(item, "BIM3117Id", None) == identifier)
                shape_obj = services.wall_body(obj) if category == "Wall" else obj
                check(f"independent native fixture volume: {obj.Label}", near(volume(shape_obj), expected_volume))
        totals = {name:sum(item["net_volume_m3"] for item in data[name + "_rows"])
                  for name in ("slab", "column", "beam", "wall")}
        check("category totals follow the declared per-element join rules",
              all(near(totals[name], expected_value) for name, expected_value in
                  {"slab":13.1625,"column":2.052,"beam":3.6,"wall":17.268}.items()))
        before, history = observation(doc), (doc.UndoCount, doc.RedoCount)
        # These explicitly named QA outputs are disposable and repeatable.
        csv_result = exchange.export_csv(project, output / "Building_Authoring_Workbench.csv", overwrite=True)
        try:
            ifc_result = exchange.export_ifc(project, output / "Building_Authoring_Workbench.ifc", overwrite=True)
        except FoundationError:
            # Retain a diagnostic for a failed fixture without publishing it as
            # a successful export or weakening the production readback gate.
            from bim3117_freecad import ifc_native
            diagnostic = ifc_native.validate_ifc(ifc_native.build_ifc(data), data)
            (output / "building-ifc-failure.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        check("expanded export writes six CSV categories plus one completion metadata file",
              len(csv_result["files"]) == 7 and len([p for p in csv_result["files"] if p.endswith('.csv')]) == 6)
        check("CSV and IFC exports preserve native authored state and Undo history",
              observation(doc) == before and history == (doc.UndoCount, doc.RedoCount))
        for category, count in [("slabs",3),("columns",8),("beams",8),("windows",4)]:
            path = output / ("Building_Authoring_Workbench_" + category + ".csv")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            check(f"{category} CSV identities and revision match the model",
                  len(rows) == count and len({value['element_id'] for value in rows}) == count
                  and all(value['content_revision'] == data['content_revision'] for value in rows))
        import ifcopenshell
        model = ifcopenshell.open(str(output / "Building_Authoring_Workbench.ifc"))
        check("native IFC includes exact counts of the new classes and shared hosted openings",
              all(len(model.by_type(name)) == count for name,count in
                  {"IfcSlab":3,"IfcColumn":8,"IfcBeam":8,"IfcWall":8,"IfcDoor":2,"IfcWindow":4,
                   "IfcOpeningElement":6,"IfcRelVoidsElement":6,"IfcRelFillsElement":6}.items()))
        check("written IFC passes expanded schema placement relationship and solid validation",
              ifc_result["validation"]["status"] == "passed")
        report["ifcopenshell"] = ifcopenshell.version
        sample_dir = output / "ตัวอย่าง_อาคาร";sample_dir.mkdir(exist_ok=True)
        sample = sample_dir / "Building_Authoring_Workbench.FCStd"
        doc.recompute();doc.saveAs(str(sample))
        (output / "building-snapshot.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        report.update(status="passed",checks_passed=len(report["checks"]),sample=str(sample),
                      sample_sha256=hashlib.sha256(sample.read_bytes()).hexdigest(),
                      content_revision=data["content_revision"],expected_net_volumes_m3=expected,
                      category_net_totals_m3=totals,
                      element_ids={obj.Name:obj.BIM3117Id for obj in doc.Objects},
                      csv_result=csv_result,ifc_result=ifc_result)
        return report
    except BaseException as error:
        report.update(status="failed",error=str(error),traceback=traceback.format_exc(),checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "building-test-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        for name in reversed(documents):
            if App.getDocument(name) is not None:
                App.closeDocument(name)
