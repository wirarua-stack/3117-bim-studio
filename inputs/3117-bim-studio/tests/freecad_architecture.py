# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall / hosted-door integration checks inside an installed FreeCAD addon.

Run ``main(output_dir)`` using the host Python. Assertions inspect OCCT solids,
native properties and document transactions. They do not certify Windows,
construction quantities, wall joins, drawings or IFC interoperability.
"""
import json
import math
from pathlib import Path
import platform
import sys
import traceback
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import FreeCAD as App
import Part

from bim3117_freecad import services
from bim3117_freecad.model import FoundationError


def _near(actual, expected):
    return abs(float(actual) - float(expected)) <= max(1e-6, abs(float(expected)) * 1e-9)


def _quantity(obj, name):
    value = getattr(obj, name)
    return float(value.Value if hasattr(value, "Value") else value)


def _ids(doc):
    return {obj.Name: obj.BIM3117Id for obj in doc.Objects if services.kind(obj)}


def _state(doc):
    """Capture semantic inputs and geometric observations, not proxy internals."""
    properties = (
        "BIM3117Id", "BIM3117Kind", "Label", "Project", "Group", "Elevation",
        "Thickness", "Material", "WallType", "WallTypeId", "BaseLevel",
        "BaseLevelId", "TopLevel", "TopLevelId", "StartX", "StartY", "EndX",
        "EndY", "BaseOffset", "TopOffset", "Body", "BodyId", "Host", "HostId",
        "Offset", "Width", "Height", "Sill", "Wall", "WallId", "Openings",
        "OpeningIds", "GrossVolume", "NetVolume", "OpeningVolume",
        "GrossSideArea", "NetSideArea", "ValidationMessage",
    )

    def plain(value):
        if hasattr(value, "Value"):
            return round(float(value.Value), 6)
        if hasattr(value, "Name") and hasattr(value, "Document"):
            return value.Name
        if isinstance(value, (list, tuple)):
            return tuple(plain(item) for item in value)
        return value

    result = {}
    for obj in doc.Objects:
        if not services.kind(obj):
            continue
        item = {prop: plain(getattr(obj, prop)) for prop in properties if prop in obj.PropertiesList}
        if "Shape" in obj.PropertiesList:
            shape = obj.Shape
            item["shape_null"] = shape.isNull()
            if not shape.isNull():
                box = shape.BoundBox
                item["shape"] = tuple(round(number, 5) for number in (
                    shape.Volume, box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax))
        result[obj.Name] = item
    return result


def _probe(start, end, along, across, height, size=100.0):
    """Independent oriented cube, in the documented +X/+Y wall convention."""
    cube = Part.makeBox(size, size, size, App.Vector(along, across, height))
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    cube.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), angle)
    cube.translate(App.Vector(start[0], start[1], 0))
    return cube


def _xml_ids(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("Document.xml"))
    identifiers = {}
    for obj in root.findall("./ObjectData/Object"):
        value = obj.find("./Properties/Property[@name='BIM3117Id']/String")
        if value is not None:
            identifiers[obj.get("name")] = value.get("value")
    return identifiers


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": checks,
              "scope": "Installed native WallType / Wall / Door / boolean WallBody integration"}
    doc = legacy = other_doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def rejects(name, operation):
        before, undo = _state(doc), doc.UndoCount
        try:
            operation()
        except FoundationError:
            pass
        else:
            raise AssertionError(name + ": invalid command was accepted")
        check(name, _state(doc) == before and doc.UndoCount == undo
              and not doc.HasPendingTransaction and App.getActiveTransaction() is None)

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("services loaded from installed addon",
              Path(services.__file__).resolve().is_relative_to(installed))
        project = services.create_project("3117 Parametric Test", "WALL-002", "3117 BIM")
        doc = project.Document
        lower, upper = services.list_levels(project)
        wall_type = services.create_wall_type(project, "Concrete 200", thickness_mm=200,
                                               material="Concrete")
        before = doc.UndoCount
        wall = services.create_wall(project, "Wall A", wall_type, lower, upper)
        body = services.wall_body(wall)
        check("wall and derived solid created in one native undo item",
              doc.UndoCount == before + 1 and wall.TypeId == "App::FeaturePython"
              and body.TypeId == "Part::FeaturePython" and body.Wall == wall
              and wall.Body == body and wall in project.Group and body in project.Group)
        check("uncut wall is a valid 6 by 3 by 0.2 metre solid",
              body.Shape.isValid() and len(body.Shape.Solids) == 1
              and _near(body.Shape.Volume, 3_600_000_000)
              and _near(body.Shape.BoundBox.XLength, 6000)
              and _near(body.Shape.BoundBox.YLength, 200)
              and _near(body.Shape.BoundBox.ZLength, 3000))
        check("type level and body identities are explicit native references",
              wall.WallTypeId == wall_type.BIM3117Id and wall.BaseLevelId == lower.BIM3117Id
              and wall.TopLevelId == upper.BIM3117Id and wall.BodyId == body.BIM3117Id
              and body.WallId == wall.BIM3117Id
              and wall.getTypeIdOfProperty("BaseOffset") == "App::PropertyDistance"
              and services.resolve_authoring_object(body) == wall)
        wall_b = services.create_wall(project, "Wall B", wall_type, lower, upper,
                                      start_y_mm=4000, end_x_mm=4000, end_y_mm=4000)
        body_b = services.wall_body(wall_b)
        before = doc.UndoCount
        door = services.create_door(project, "D01", wall, offset_mm=1000,
                                    width_mm=900, height_mm=2100)
        names = {"wall": wall.Name, "body": body.Name, "wall_b": wall_b.Name,
                 "body_b": body_b.Name, "door": door.Name, "type": wall_type.Name,
                 "base": lower.Name, "top": upper.Name, "project": project.Name}
        original_ids = _ids(doc)
        check("door creation atomically records host and boolean dependency",
              doc.UndoCount == before + 1 and door.Host == wall
              and door.HostId == wall.BIM3117Id and list(body.Openings) == [door]
              and list(body.OpeningIds) == [door.BIM3117Id])
        check("door removes 0.378 cubic metres from actual wall solid",
              body.Shape.isValid() and len(body.Shape.Solids) == 1
              and _near(body.Shape.Volume, 3_222_000_000)
              and not door.Shape.isNull() and door.Shape.isValid())
        hole = _probe((0, 0), (6000, 0), 1100, 50, 1000)
        material = _probe((0, 0), (6000, 0), 500, 50, 1000)
        head = _probe((0, 0), (6000, 0), 1100, 50, 2500)
        check("opening is a void through thickness with jamb and head material retained",
              _near(body.Shape.common(hole).Volume, 0)
              and _near(body.Shape.common(material).Volume, 1_000_000)
              and _near(body.Shape.common(head).Volume, 1_000_000))
        check("derived diagnostic quantities match independent gross and net fixture",
              _near(_quantity(body, "GrossVolume"), 3_600_000_000)
              and _near(_quantity(body, "OpeningVolume"), 378_000_000)
              and _near(_quantity(body, "NetVolume"), body.Shape.Volume)
              and _near(_quantity(body, "GrossSideArea"), 18_000_000)
              and _near(_quantity(body, "NetSideArea"), 16_110_000))

        services.edit_wall_type(wall_type, thickness_mm=250)
        check("type thickness propagates to two instances and their cut solids",
              _near(body.Shape.Volume, 4_027_500_000)
              and _near(body_b.Shape.Volume, 3_000_000_000)
              and _near(body.Shape.BoundBox.YLength, 250)
              and _near(body_b.Shape.BoundBox.YLength, 250)
              and _near(door.Shape.BoundBox.YLength, 250)
              and _ids(doc) == original_ids)
        doc.undo()
        doc.recompute()
        check("native undo restores type and both dependent solids",
              _near(wall_type.Thickness.Value, 200) and _near(body.Shape.Volume, 3_222_000_000)
              and _near(body_b.Shape.Volume, 2_400_000_000))
        doc.redo()
        doc.recompute()
        check("native redo restores propagated type geometry",
              _near(body.Shape.Volume, 4_027_500_000) and _near(body_b.Shape.Volume, 3_000_000_000))
        services.edit_wall_type(wall_type, thickness_mm=200)
        alternate = services.create_wall_type(project, "Block 150", thickness_mm=150)
        services.edit_wall(wall_b, wall_type=alternate)
        check("changing one instance type preserves identities and leaves the other wall unchanged",
              wall_b.WallType == alternate and wall_b.WallTypeId == alternate.BIM3117Id
              and _near(body_b.Shape.Volume, 1_800_000_000)
              and _near(body.Shape.Volume, 3_222_000_000)
              and wall_b.BIM3117Id == original_ids[wall_b.Name])
        services.edit_wall_type(alternate, thickness_mm=180)
        check("editing alternate type affects only its assigned wall instance",
              _near(body_b.Shape.Volume, 2_160_000_000)
              and _near(body.Shape.Volume, 3_222_000_000))
        services.edit_wall(wall_b, wall_type=wall_type)
        services.delete_wall_type(alternate)
        services.edit_level(upper, elevation_mm=3300)
        check("top level updates all linked walls while retaining door dimensions",
              _near(body.Shape.Volume, 3_582_000_000) and _near(body_b.Shape.Volume, 2_640_000_000)
              and _near(wall.Height.Value, 3300) and _near(door.Height.Value, 2100))
        doc.undo()
        doc.recompute()
        check("level undo restores the cut solid", _near(body.Shape.Volume, 3_222_000_000))
        doc.redo()
        doc.recompute()
        check("level redo restores the cut solid", _near(body.Shape.Volume, 3_582_000_000))
        services.edit_level(upper, elevation_mm=3000)
        rejects("lowering top below hosted door rolls back level and every solid",
                lambda: services.edit_level(upper, elevation_mm=1800))
        rejects("nonpositive effective wall height rolls back the level command",
                lambda: services.edit_level(upper, elevation_mm=-100))
        rejects("shortening host below its opening rolls back wall and door",
                lambda: services.edit_wall(wall, end_x_mm=1500))

        # Axis transforms are checked with independent OCCT probes and lengths.
        # The first pose is not parallel to a global axis; the second reverses it.
        for label, start, end in (
            ("diagonal", (1000, 2000), (4600, 6800)),
            ("reversed", (4600, 6800), (1000, 2000)),
        ):
            services.edit_wall(wall, start_x_mm=start[0], start_y_mm=start[1],
                               end_x_mm=end[0], end_y_mm=end[1])
            cut_probe = _probe(start, end, 1100, 50, 1000)
            solid_probe = _probe(start, end, 500, 50, 1000)
            frame_box = door.Shape.BoundBox
            ux, uy = (end[0] - start[0]) / 6000, (end[1] - start[1]) / 6000
            corners = [(start[0] + ux * u - uy * v, start[1] + uy * u + ux * v)
                       for u in (1000, 1900) for v in (0, 200)]
            check(label + " host axis moves its real opening and hosted frame",
                  _near(body.Shape.Volume, 3_222_000_000)
                  and _near(body.Shape.common(cut_probe).Volume, 0)
                  and _near(body.Shape.common(solid_probe).Volume, 1_000_000)
                  and _near(frame_box.XMin, min(point[0] for point in corners))
                  and _near(frame_box.XMax, max(point[0] for point in corners))
                  and _near(frame_box.YMin, min(point[1] for point in corners))
                  and _near(frame_box.YMax, max(point[1] for point in corners))
                  and _near(frame_box.ZMin, 0) and _near(frame_box.ZMax, 2100)
                  and _ids(doc) == original_ids)
        services.edit_wall(wall, start_x_mm=0, start_y_mm=0, end_x_mm=6000, end_y_mm=0)

        services.edit_door(door, offset_mm=3000, width_mm=1000, height_mm=2200)
        check("door edit heals old hole and cuts its new width height and position",
              _near(body.Shape.Volume, 3_160_000_000)
              and _near(body.Shape.common(hole).Volume, 1_000_000)
              and _near(body.Shape.common(_probe((0, 0), (6000, 0), 3100, 50, 1000)).Volume, 0))
        doc.undo()
        doc.recompute()
        check("door edit undo restores opening and stable identity",
              _near(body.Shape.Volume, 3_222_000_000)
              and _near(body.Shape.common(hole).Volume, 0) and _ids(doc) == original_ids)
        doc.redo()
        doc.recompute()
        check("door edit redo restores new cut geometry", _near(body.Shape.Volume, 3_160_000_000))
        services.edit_door(door, offset_mm=1000, width_mm=900, height_mm=2100)

        before = doc.UndoCount
        services.edit_door(door, host=wall_b, offset_mm=500)
        check("rehost updates both wall solids and dependency lists in one transaction",
              doc.UndoCount == before + 1 and door.Host == wall_b
              and door.HostId == wall_b.BIM3117Id and list(body.Openings) == []
              and list(body_b.Openings) == [door] and _near(body.Shape.Volume, 3_600_000_000)
              and _near(body_b.Shape.Volume, 2_022_000_000))
        doc.undo()
        doc.recompute()
        check("rehost undo restores both hosts and original opening",
              door.Host == wall and list(body.Openings) == [door] and list(body_b.Openings) == []
              and _near(body.Shape.Volume, 3_222_000_000) and _near(body_b.Shape.Volume, 2_400_000_000)
              and _ids(doc) == original_ids)

        before = doc.UndoCount
        doc.openTransaction("Native architecture property edit")
        wall.EndX = 6500
        wall.EndX = 500  # Would leave the hosted opening outside its wall.
        door.Width = 7000
        wall_type.Thickness = 0
        upper.Elevation = 1800
        doc.recompute()
        doc.commitTransaction()
        check("native property edit preserves valid change and rejects downstream invalid dimensions",
              doc.UndoCount == before + 1 and _near(wall.EndX.Value, 6500)
              and _near(door.Width.Value, 900) and _near(wall_type.Thickness.Value, 200)
              and _near(upper.Elevation.Value, 3000) and _near(body.Shape.Volume, 3_522_000_000))
        doc.undo()
        doc.recompute()
        check("native property undo restores the complete graph",
              _near(wall.EndX.Value, 6000) and _near(body.Shape.Volume, 3_222_000_000)
              and services.validate_document(doc, check_shapes=True))

        second = services.create_door(project, "D02", wall, offset_mm=3000,
                                      width_mm=800, height_mm=2000, sill_mm=100)
        check("multiple nonoverlapping openings cut exact volume and retain sill material",
              _near(body.Shape.Volume, 2_902_000_000)
              and _near(body.Shape.common(_probe((0, 0), (6000, 0), 3100, 50, 0, size=50)).Volume, 125000)
              and _near(body.Shape.common(_probe((0, 0), (6000, 0), 3100, 50, 500)).Volume, 0))
        rejects("overlapping openings are rejected without partial edits",
                lambda: services.edit_door(second, offset_mm=1500))
        rejects("opening past host end is rejected without partial edits",
                lambda: services.create_door(project, "Outside", wall, offset_mm=5800))
        rejects("opening above host is rejected without partial edits",
                lambda: services.edit_door(door, height_mm=3100))
        rejects("negative sill is rejected without partial edits",
                lambda: services.edit_door(door, sill_mm=-1))
        for label, operation in (
            ("NaN thickness", lambda: services.edit_wall_type(wall_type, thickness_mm=float("nan"))),
            ("infinite door width", lambda: services.edit_door(door, width_mm=float("inf"))),
            ("boolean door width", lambda: services.edit_door(door, width_mm=True)),
            ("zero length wall", lambda: services.edit_wall(wall, end_x_mm=0)),
        ):
            rejects(label + " is rejected with unchanged document and history", operation)

        rejects("referenced wall type deletion is blocked", lambda: services.delete_wall_type(wall_type))
        rejects("referenced level deletion includes wall dependencies", lambda: services.delete_level(lower))
        rejects("wall deletion is blocked while it hosts doors", lambda: services.delete_wall(wall))
        # Begin an independent deletion/history scenario. FreeCAD's default
        # undo stack is capped at 20 entries; the preceding geometry scenarios
        # already exercise that many transactions. Clear only this disposable
        # test document's history, without changing any user preferences, so
        # the strict +1 checks below measure command atomicity rather than cap.
        report["deletion_scenario_prior_undo_count"] = doc.UndoCount
        doc.clearUndos()
        second_name, second_id = second.Name, second.BIM3117Id
        before = doc.UndoCount
        services.delete_door(second)
        check("deleting door heals its host in one undo item",
              doc.UndoCount == before + 1 and doc.getObject(second_name) is None
              and list(body.Openings) == [door] and _near(body.Shape.Volume, 3_222_000_000))
        doc.undo()
        doc.recompute()
        second = doc.getObject(second_name)
        check("undo door deletion restores identity host membership and solid cut",
              second.BIM3117Id == second_id and second.Host == wall
              and second in project.Group and second in body.Openings
              and _near(body.Shape.Volume, 2_902_000_000))
        doc.redo()
        doc.recompute()
        check("redo door deletion heals the solid again",
              doc.getObject(second_name) is None and _near(body.Shape.Volume, 3_222_000_000))

        # A post-mutation failure must roll back a new door and the host's lists.
        validator = services.validate_document
        snapshot, undo = _state(doc), doc.UndoCount
        def fail_gate(*args, **kwargs):
            raise RuntimeError("Injected architecture validation gate failure")
        services.validate_document = fail_gate
        try:
            try:
                services.create_door(project, "Must roll back", wall, offset_mm=3000)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Injected post-mutation failure was ignored")
        finally:
            services.validate_document = validator
        check("post-mutation failure restores object set links geometry and undo count",
              _state(doc) == snapshot and doc.UndoCount == undo
              and App.getActiveTransaction() is None and not doc.HasPendingTransaction)

        before = doc.UndoCount
        b_id, b_body_id = wall_b.BIM3117Id, body_b.BIM3117Id
        services.delete_wall(wall_b)
        check("unhosted wall deletion removes authored wall and derived body atomically",
              doc.UndoCount == before + 1 and doc.getObject(names["wall_b"]) is None
              and doc.getObject(names["body_b"]) is None)
        doc.undo()
        doc.recompute()
        wall_b, body_b = doc.getObject(names["wall_b"]), doc.getObject(names["body_b"])
        check("undo wall deletion restores both IDs and the type level graph",
              wall_b.BIM3117Id == b_id and body_b.BIM3117Id == b_body_id
              and wall_b.Body == body_b and body_b.Wall == wall_b and wall_b.WallType == wall_type
              and _near(body_b.Shape.Volume, 2_400_000_000))

        basement = services.add_level(project, "B01", -3000)
        cellar = services.create_wall(project, "Basement wall", wall_type, basement, lower,
                                      start_y_mm=8000, end_x_mm=3000, end_y_mm=8000,
                                      base_offset_mm=100, top_offset_mm=-200)
        cellar_door = services.create_door(project, "DB01", cellar, offset_mm=500,
                                           width_mm=700, height_mm=2000, sill_mm=100)
        cellar_body = services.wall_body(cellar)
        check("basement wall respects signed base top offsets and hosted sill",
              _near(cellar_body.Shape.BoundBox.ZMin, -2900)
              and _near(cellar_body.Shape.BoundBox.ZMax, -200)
              and _near(cellar.Height.Value, 2700)
              and _near(cellar_body.Shape.Volume, 1_340_000_000))
        services.edit_level(basement, elevation_mm=-3300)
        check("base level movement updates host bottom door elevation and net solid",
              _near(cellar_body.Shape.BoundBox.ZMin, -3200)
              and _near(cellar_door.Shape.BoundBox.ZMin, -3100)
              and _near(cellar_body.Shape.Volume, 1_520_000_000))
        services.delete_door(cellar_door)
        services.delete_wall(cellar)
        services.delete_level(basement)

        other = services.create_project("Other project")
        other_doc = other.Document
        other_type = services.create_wall_type(other, "Other type")
        foreign_lower, foreign_upper = services.list_levels(other)
        foreign_wall = services.create_wall(other, "Other wall", other_type, foreign_lower, foreign_upper)
        rejects("cross-document wall type assignment is rejected", lambda: services.edit_wall(wall, wall_type=other_type))
        rejects("cross-document level assignment is rejected", lambda: services.edit_wall(wall, top_level=foreign_upper))
        rejects("cross-document door host assignment is rejected", lambda: services.edit_door(door, host=foreign_wall))
        App.closeDocument(other_doc.Name)
        other_doc = None
        App.setActiveDocument(doc.Name)

        # Unsupported raw removals must fail closed, retaining the missing UUID.
        # Each probe is aborted so the sample remains valid and editable.
        for removed_kind in ("type", "top", "wall", "door"):
            wall, wall_b = doc.getObject(names["wall"]), doc.getObject(names["wall_b"])
            body, body_b = doc.getObject(names["body"]), doc.getObject(names["body_b"])
            door, wall_type = doc.getObject(names["door"]), doc.getObject(names["type"])
            upper = doc.getObject(names["top"])
            snapshot = _state(doc)
            removed_name = names[removed_kind]
            removed_id = doc.getObject(removed_name).BIM3117Id
            doc.openTransaction("Unsupported raw removal " + removed_kind)
            try:
                doc.removeObject(removed_name)
                doc.recompute()
                try:
                    services.validate_document(doc, check_shapes=True)
                except FoundationError:
                    invalid = True
                else:
                    invalid = False
                if removed_kind == "type":
                    missing = wall.WallType is None and wall.WallTypeId == removed_id
                elif removed_kind == "top":
                    missing = wall.TopLevel is None and wall.TopLevelId == removed_id
                elif removed_kind == "wall":
                    missing = door.Host is None and door.HostId == removed_id and body.WallId == removed_id
                else:
                    missing = removed_id in body.OpeningIds
                shape_failed_closed = body.Shape.isNull()
                if removed_kind != "door":
                    shape_failed_closed = shape_failed_closed and door.Shape.isNull()
                check("raw " + removed_kind + " deletion preserves missing identity and clears dependent geometry",
                      invalid and missing and shape_failed_closed)
            finally:
                doc.abortTransaction()
                if App.getActiveTransaction() is not None:
                    App.closeActiveTransaction()
                doc.recompute()
            check("abort raw " + removed_kind + " deletion restores graph and solids", _state(doc) == snapshot)
        wall, wall_b = doc.getObject(names["wall"]), doc.getObject(names["wall_b"])
        body, body_b = doc.getObject(names["body"]), doc.getObject(names["body_b"])
        door, wall_type = doc.getObject(names["door"]), doc.getObject(names["type"])
        lower, upper = doc.getObject(names["base"]), doc.getObject(names["top"])

        check("complete authoring graph validates after dependency and transaction probes",
              services.validate_document(doc, check_shapes=True)
              and not any("Error" in obj.State for obj in doc.Objects)
              and _ids(doc) == original_ids)
        saved = output / "save_ภาษาไทย" / "Architecture_Workbench.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(saved))
        saved_ids = _ids(doc)
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(saved))
        doc.recompute()
        check("same-process FCStd restore retains every native UUID and valid solid",
              _ids(doc) == saved_ids and services.validate_document(doc, check_shapes=True)
              and _near(doc.getObject(names["body"]).Shape.Volume, 3_222_000_000))

        legacy_path = Path(__file__).resolve().parents[1] / "examples" / "freecad" / "Foundation_Workbench.FCStd"
        legacy_ids = _xml_ids(legacy_path)
        legacy = App.openDocument(str(legacy_path))
        legacy.recompute()
        legacy_project = services.get_project(legacy)
        check("v0.1 Foundation sample opens under v0.2 with unchanged persisted UUIDs",
              bool(legacy_ids) and _ids(legacy) == legacy_ids
              and all(obj.BIM3117Version == "0.1.0" for obj in legacy.Objects if services.kind(obj))
              and services.validate_document(legacy, check_shapes=True))
        grid = next(item for item in services.list_grids(legacy_project) if item.ReferenceLevel is not None)
        reference = grid.ReferenceLevel
        before_z = grid.Shape.BoundBox.ZMin
        services.edit_level(reference, elevation_mm=reference.Elevation.Value + 250)
        changed_z = grid.Shape.BoundBox.ZMin
        legacy.undo()
        legacy.recompute()
        check("v0.1 restored proxies remain editable with native dependency undo",
              _near(changed_z, before_z + 250) and _near(grid.Shape.BoundBox.ZMin, before_z)
              and _ids(legacy) == legacy_ids and services.validate_document(legacy, check_shapes=True))
        App.closeDocument(legacy.Name)
        legacy = None
        report.update(status="passed", sample=str(saved), element_ids=saved_ids,
                      element_names=names, elements=len(doc.Objects), checks_passed=len(checks),
                      numeric_fixture={"length_mm": 6000, "height_mm": 3000, "thickness_mm": 200,
                                       "opening_width_mm": 900, "opening_height_mm": 2100,
                                       "gross_volume_m3": 3.6, "opening_volume_m3": 0.378,
                                       "net_volume_m3": 3.222},
                      legacy_sample=str(legacy_path), legacy_sample_ids=legacy_ids)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(checks))
        raise
    finally:
        (output / "architecture-test-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        for opened in (legacy, other_doc, doc):
            if opened is not None and opened.Name in App.listDocuments():
                App.closeDocument(opened.Name)
    return report


if __name__ == "__main__":
    destination = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bim3117-architecture-tests"
    print(json.dumps(main(destination), indent=2, ensure_ascii=False))
