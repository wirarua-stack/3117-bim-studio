# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only native model snapshots and SI quantity rows.

The FreeCAD document remains the only editable model. A content revision is a
SHA-256 of supported authored inputs and the coverage inventory, not a history
counter: Undo to identical content returns the same revision. Display settings,
file paths, timestamps and floating-point geometry caches are not revision inputs.
"""
from datetime import datetime, timezone
import hashlib
import json
import math

import FreeCAD as App
import Part

from . import __version__
from . import services
from .building import _box, door_parameters, opening_solid, wall_parameters
from .model import DOCUMENTATION_KINDS, FoundationError, grid_elevation, kind, mm

SNAPSHOT_SCHEMA = 1
WALL_RULE = "3117.uniform-wall.one-side.openings.no-joins.v1"
DOOR_RULE = "3117.overall-opening.generic-three-bar-frame.v1"
WINDOW_RULE = "3117.overall-opening.generic-four-bar-frame.v1"
SLAB_RULE = "3117.horizontal-polygon-slab.top-level.uniform.v1"
COLUMN_RULE = "3117.vertical-rectangular-column.slab-priority-cuts.v1"
BEAM_RULE = "3117.horizontal-rectangular-beam.slab-priority-cuts.v1"
REVISION_RULE = "3117.native-authored-and-coverage.sha256.v1"
NEW_CATEGORIES = ("Slab", "Column", "Beam", "Window")


def _openings(wall):
    from .building import hosted_openings
    return hosted_openings(wall)


def _finite(value, label):
    value = float(value)
    if not math.isfinite(value):
        raise FoundationError(f"{label}: cannot export a non-finite value")
    return 0.0 if value == 0 else value


def _m(obj, name):
    return _finite(mm(obj, name) / 1000.0, name)


def _identity(obj):
    return {"id": str(obj.BIM3117Id), "label": str(obj.Label),
            "object_name": str(obj.Name), "schema": int(obj.BIM3117Schema),
            "creation_version": str(obj.BIM3117Version)}


def _ready(project, recompute=True):
    if project is None or kind(project) != "Project" or project.Document is None:
        raise FoundationError("Select a 3117 project in an open document")
    doc = project.Document
    if (doc.HasPendingTransaction or App.getActiveTransaction() is not None
            or doc.Transacting or getattr(doc, "Restoring", False)):
        raise FoundationError("Finish or cancel the current edit before reading quantities or exporting")
    if services.get_project(doc) != project:
        raise FoundationError("The selected project is not the document's active 3117 project")
    services.validate_document(doc)
    if recompute:
        # Refresh host-derived geometry only. No property definition or native
        # transaction is created, and no source model is duplicated.
        doc.recompute()
    services.validate_document(doc, check_shapes=True)
    for obj in doc.Objects:
        if (kind(obj) and kind(obj) not in DOCUMENTATION_KINDS
                and any(state in str(obj.State) for state in ("Invalid", "Error", "Touched"))):
            raise FoundationError(f"{obj.Label}: finish recomputing the model before exporting")
    return doc


def _coverage(doc):
    mapping = {"Project": "IfcProject", "Level": "IfcBuildingStorey",
               "WallType": "IfcWallType", "Wall": "IfcWall", "Door": "IfcDoor",
               "Slab": "IfcSlab", "Column": "IfcColumn", "Beam": "IfcBeam", "Window": "IfcWindow"}
    extended = any(kind(obj) in NEW_CATEGORIES for obj in doc.Objects)
    items = []
    for obj in doc.Objects:
        category = kind(obj)
        role = category.lower() if category in ("Wall", "Door") + NEW_CATEGORIES else "none"
        if category == "Material":
            status, ifc_class = "mapped", "IfcMaterial"
            reason = "Native material definition; mapped to IfcMaterial with source identity, not an IFC product or an additional building quantity."
        elif category == "ElementType":
            status, ifc_class = "mapped", "Ifc" + str(obj.Category) + "Type"
            reason = "Native shared type definition; mapped to its category type and instance relations, not an additional IFC product."
        elif category in mapping:
            status, ifc_class = "mapped", mapping[category]
            # Preserve the v0.2.1 coverage inventory/hash for unchanged old models.
            reason = ("Mapped to IFC4; one quantity row per supported authored building element." if extended else
                      "Mapped to IFC4; quantity rows are limited to authored Walls and Doors.")
        elif category == "WallBody":
            status, ifc_class = "derived", ""
            reason = "Calculated shape of its authored Wall; never a second wall or quantity row."
        elif category == "Grid":
            status, ifc_class = "reference", ""
            reason = "Native datum retained in FCStd; IFC grid export is outside this release."
        elif category in ("ScheduleSet", "Schedule"):
            status, ifc_class = "reference", ""
            reason = "Native schedule definition retained in FCStd; separate schedule revision, no building quantity or IFC product."
        elif category in DOCUMENTATION_KINDS:
            status, ifc_class = "reference", ""
            reason = "Native drawing definition retained in FCStd; separate drawing revision, no building quantity or IFC product."
        else:
            status, ifc_class = "unsupported", ""
            reason = "Outside the declared 3117 mapping; omitted from quantity rows and IFC."
        items.append({"object_name": str(obj.Name),
                      "object_id": str(getattr(obj, "BIM3117Id", "")),
                      "label": str(obj.Label), "kind": str(category or obj.TypeId),
                      "status": status, "ifc_class": ifc_class,
                      "reason": reason, "quantity_role": role})
    items.sort(key=lambda item: (item["object_id"], item["object_name"]))
    counts = {status: sum(item["status"] == status for item in items)
              for status in ("mapped", "derived", "reference", "unsupported")}
    warnings = [
        "Wall quantities sum individual straight uniform walls; no wall-join overlap or material-layer deductions.",
        "Door Width/Height describe the overall wall opening, not leaf size or clear passage; geometry is a generic three-bar frame.",
    ]
    if extended:
        warnings.extend([
            "Slabs keep their full volume; explicit Slab priorities deduct intersections only from joined Columns/Beams. Other intersections are not deducted.",
            "Window Width/Height describe the overall opening; the four-bar frame has no pane, leaf or operation.",
        ])
    datum_count = sum(item["kind"] == "Grid" for item in items)
    drawing_count = sum(item["kind"] in DOCUMENTATION_KINDS and item["kind"] not in ("ScheduleSet", "Schedule") for item in items)
    schedule_count = sum(item["kind"] in ("ScheduleSet", "Schedule") for item in items)
    if datum_count:
        warnings.append(f"{datum_count} native datum object(s) are listed as reference and omitted from IFC.")
    if drawing_count:
        warnings.append(f"{drawing_count} native drawing definition(s) are references with a separate drawing revision and omitted from IFC.")
    if schedule_count:
        warnings.append(f"{schedule_count} native schedule definition(s) are references with a separate schedule revision and omitted from IFC.")
    if counts["unsupported"]:
        warnings.append(f"{counts['unsupported']} unsupported document object(s) are explicitly omitted.")
    return {"items": items, "counts": counts, "warnings": warnings,
            "complete": counts["reference"] == 0 and counts["unsupported"] == 0,
            "scope": ("3117 Project, Levels, Wall Types, Walls, Doors, polygon Slabs, rectangular Columns/Beams and hosted Windows"
                      if extended else "3117 Project, Levels, Wall Types, straight Walls and hosted rectangular Doors")}


def _authored(project):
    """Collect primitive, serializable inputs without copying host objects."""
    from . import material_quantities
    data = {"project": dict(_identity(project), number=str(project.ProjectNumber),
                            author=str(project.Author)),
            "levels": [], "grids": [], "wall_types": [], "walls": [], "doors": []}
    for obj in sorted(project.Group, key=lambda item: item.BIM3117Id):
        category = kind(obj)
        if category == "WallBody":
            continue
        item = _identity(obj)
        if category == "Level":
            item.update(elevation_m=_m(obj, "Elevation"), span_x_m=_m(obj, "SpanX"),
                        span_y_m=_m(obj, "SpanY"))
            data["levels"].append(item)
        elif category == "Grid":
            item.update(axis=str(obj.Axis), position_m=_m(obj, "Position"), length_m=_m(obj, "Length"),
                        bubble_label=str(obj.BubbleLabel), bubble_radius_m=_m(obj, "BubbleRadius"),
                        level_id=str(obj.ReferenceLevelId), offset_m=_m(obj, "ElevationOffset"),
                        elevation_m=_finite(grid_elevation(obj) / 1000.0, "Grid elevation"))
            data["grids"].append(item)
        elif category == "WallType":
            item.update(thickness_m=_m(obj, "Thickness"), material=str(obj.Material))
            item.update(material_quantities.type_fields(obj))
            data["wall_types"].append(item)
        elif category == "Material":
            item["code"] = str(obj.Code)
            data.setdefault("materials", []).append(item)
        elif category == "ElementType":
            item.update(material_quantities.type_fields(obj))
            data.setdefault("element_types", []).append(item)
        elif category == "Wall":
            values = wall_parameters(obj)
            item.update(type_id=str(obj.WallTypeId), base_level_id=str(obj.BaseLevelId),
                        top_level_id=str(obj.TopLevelId),
                        start_m=[_m(obj, "StartX"), _m(obj, "StartY")],
                        end_m=[_m(obj, "EndX"), _m(obj, "EndY")],
                        base_offset_m=_m(obj, "BaseOffset"), top_offset_m=_m(obj, "TopOffset"),
                        base_z_m=_finite(values["base_z"] / 1000.0, "Wall base"),
                        height_m=_finite(values["height"] / 1000.0, "Wall height"),
                        length_m=_finite(values["length"] / 1000.0, "Wall length"),
                        thickness_m=_finite(values["thickness"] / 1000.0, "Wall thickness"))
            data["walls"].append(item)
        elif category in ("Door", "Window"):
            if getattr(obj, "ElementTypeId", ""):
                item["type_id"] = str(obj.ElementTypeId)
            if getattr(obj, "Material", ""):
                item["material"] = str(obj.Material)
            values = door_parameters(obj)
            item.update(host_id=str(obj.HostId), **{name + "_m": _finite(value / 1000.0, name)
                                                  for name, value in values.items()})
            data.setdefault("doors" if category == "Door" else "windows", []).append(item)
        elif category in ("Slab", "Column", "Beam"):
            from . import elements
            if getattr(obj, "ElementTypeId", ""):
                item["type_id"] = str(obj.ElementTypeId)
            item["material"] = str(obj.Material)
            if category == "Slab":
                values = elements.slab_parameters(obj)
                item.update(level_id=str(obj.LevelId), offset_m=_m(obj, "Offset"),
                            thickness_m=_m(obj, "Thickness"),
                            top_z_m=_finite(values["top_z"] / 1000.0, "Slab top"),
                            base_z_m=_finite(values["bottom_z"] / 1000.0, "Slab bottom"),
                            boundary_m=[[_finite(x / 1000.0, "Boundary X"), _finite(y / 1000.0, "Boundary Y")]
                                        for x, y in values["boundary"]])
                data.setdefault("slabs", []).append(item)
            elif category == "Column":
                values = elements.column_parameters(obj)
                item.update(base_level_id=str(obj.BaseLevelId), top_level_id=str(obj.TopLevelId),
                            base_offset_m=_m(obj, "BaseOffset"), top_offset_m=_m(obj, "TopOffset"),
                            x_m=_m(obj, "X"), y_m=_m(obj, "Y"),
                            width_m=_m(obj, "Width"), depth_m=_m(obj, "Depth"),
                            rotation_deg=_finite(mm(obj, "Rotation"), "Column rotation"),
                            base_z_m=_finite(values["base_z"] / 1000.0, "Column base"),
                            height_m=_finite(values["height"] / 1000.0, "Column height"),
                            join_slab_ids=sorted(str(slab.BIM3117Id) for slab in elements.join_slabs(obj)))
                data.setdefault("columns", []).append(item)
            else:
                values = elements.beam_parameters(obj)
                item.update(level_id=str(obj.LevelId), offset_m=_m(obj, "Offset"),
                            start_m=[_m(obj, "StartX"), _m(obj, "StartY")],
                            end_m=[_m(obj, "EndX"), _m(obj, "EndY")],
                            width_m=_m(obj, "Width"), depth_m=_m(obj, "Depth"),
                            length_m=_finite(values["length"] / 1000.0, "Beam length"),
                            top_z_m=_finite(values["top_z"] / 1000.0, "Beam top"),
                            base_z_m=_finite(values["base_z"] / 1000.0, "Beam bottom"),
                            join_slab_ids=sorted(str(slab.BIM3117Id) for slab in elements.join_slabs(obj)))
                data.setdefault("beams", []).append(item)
    return data


def _revision(authored, coverage):
    rules = [WALL_RULE, DOOR_RULE]
    rules.extend(rule for key, rule in (("slabs", SLAB_RULE), ("columns", COLUMN_RULE),
                                       ("beams", BEAM_RULE), ("windows", WINDOW_RULE)) if authored.get(key))
    if authored.get("materials") or authored.get("element_types") or any(
            any(item.get(key) for key in ("code", "material_id", "layers")) for item in authored["wall_types"]):
        from .material_quantities import MATERIAL_RULE, TYPE_RULE
        rules.extend((TYPE_RULE, MATERIAL_RULE))
    value = {"revision_rule": REVISION_RULE, "quantity_rules": rules,
             "authored": authored, "coverage_inventory": [item for item in coverage["items"]
                                                          if item["kind"] not in DOCUMENTATION_KINDS]}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _close(actual, expected, label):
    if not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-9):
        raise FoundationError(f"{label}: native solid and authored dimensions disagree; recompute and repair before export")


def _same_solid(actual, expected, label):
    """Compare spatial material, including equal-volume but misplaced cuts.

    These transient OCCT solids are validation results, not new model objects or
    an editable master. A volume-only cache check cannot detect a moved opening.
    """
    for name in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"):
        if not math.isclose(getattr(actual.BoundBox, name), getattr(expected.BoundBox, name),
                            rel_tol=0.0, abs_tol=1e-6):
            raise FoundationError(f"{label}: native geometry is displaced from its authored definition")
    try:
        difference = abs(actual.cut(expected).Volume) + abs(expected.cut(actual).Volume)
    except Exception as error:
        raise FoundationError(f"{label}: cannot verify native geometry against its authored definition") from error
    if difference > max(0.001, expected.Volume * 1e-8):
        raise FoundationError(f"{label}: native geometry differs from its authored definition; recompute and repair before export")


def capture(project):
    """Return a detached SI snapshot of the current, committed, validated model.

    No export is made from a caller-supplied snapshot. Export commands recapture
    the live document and optionally compare an expected content revision.
    """
    doc = _ready(project)
    authored = _authored(project)
    coverage = _coverage(doc)
    revision = _revision(authored, coverage)
    levels = {item["id"]: item for item in authored["levels"]}
    types = {item["id"]: item for item in authored["wall_types"]}
    walls = {item["id"]: item for item in authored["walls"]}
    native = {obj.BIM3117Id: obj for obj in project.Group}
    wall_rows, door_rows, window_rows = [], [], []
    for wall in authored["walls"]:
        obj = native[wall["id"]]
        body = services.wall_body(obj)
        values_mm = wall_parameters(obj)
        expected_shape = _box(values_mm, 0, 0, 0, values_mm["length"],
                              values_mm["thickness"], values_mm["height"])
        for opening in _openings(obj):
            expected_shape = expected_shape.cut(opening_solid(opening, padded=True))
        _same_solid(body.Shape, expected_shape, obj.Label)
        gross_area = wall["length_m"] * wall["height_m"]
        opening_area = math.fsum(_m(opening, "Width") * _m(opening, "Height") for opening in _openings(obj))
        gross_volume = gross_area * wall["thickness_m"]
        net_volume = _finite(float(body.Shape.Volume) / 1e9, f"{obj.Label} Shape.Volume")
        _close(net_volume, (gross_area - opening_area) * wall["thickness_m"], obj.Label)
        net_area = net_volume / wall["thickness_m"]
        values = {"gross_side_area_m2": gross_area, "opening_side_area_m2": opening_area,
                  "net_side_area_m2": net_area, "gross_volume_m3": gross_volume,
                  "opening_volume_m3": gross_volume - net_volume, "net_volume_m3": net_volume}
        # Detect inconsistent output properties as well as inconsistent shapes;
        # never export a stale readonly quantity cache silently.
        for prop, key, scale in (("GrossVolume", "gross_volume_m3", 1e9),
                                 ("NetVolume", "net_volume_m3", 1e9),
                                 ("OpeningVolume", "opening_volume_m3", 1e9),
                                 ("GrossSideArea", "gross_side_area_m2", 1e6),
                                 ("NetSideArea", "net_side_area_m2", 1e6)):
            _close(mm(body, prop) / scale, values[key], f"{obj.Label}.{prop}")
        wall["quantities"] = values
        wall_rows.append({"element_id": wall["id"], "object_name": wall["object_name"],
                          "name": wall["label"], "type_id": wall["type_id"],
                          "type_name": types[wall["type_id"]]["label"],
                          "base_level_id": wall["base_level_id"], "base_level": levels[wall["base_level_id"]]["label"],
                          "top_level_id": wall["top_level_id"], "top_level": levels[wall["top_level_id"]]["label"],
                          "length_m": wall["length_m"], "height_m": wall["height_m"],
                          "thickness_m": wall["thickness_m"], **values,
                          "quantity_rule": WALL_RULE, "content_revision": revision})
    for door in authored["doors"] + authored.get("windows", []):
        obj = native[door["id"]]
        is_window = kind(obj) == "Window"
        host = walls[door["host_id"]]
        width, height = door["width_m"], door["height_m"]
        strip = min(0.05, width / 4.0, height / 4.0)
        values_mm = wall_parameters(obj.Host)
        door_mm = door_parameters(obj)
        strip_mm = strip * 1000.0
        if is_window:
            from .building import window_frame_solid
            expected_frame = window_frame_solid(obj)
            frame_area = 2 * strip * (height - 2 * strip) + 2 * width * strip
        else:
            parts = [
                _box(values_mm, door_mm["offset"], 0, door_mm["sill"], strip_mm,
                     values_mm["thickness"], door_mm["height"] - strip_mm),
                _box(values_mm, door_mm["offset"] + door_mm["width"] - strip_mm, 0,
                     door_mm["sill"], strip_mm, values_mm["thickness"], door_mm["height"] - strip_mm),
                _box(values_mm, door_mm["offset"], 0, door_mm["sill"] + door_mm["height"] - strip_mm,
                     door_mm["width"], values_mm["thickness"], strip_mm),
            ]
            expected_frame = Part.makeCompound(parts)
            frame_area = 2 * strip * (height - strip) + width * strip
        _same_solid(obj.Shape, expected_frame, obj.Label)
        volume = _finite(float(obj.Shape.Volume) / 1e9, f"{obj.Label} Shape.Volume")
        _close(volume, frame_area * host["thickness_m"], obj.Label)
        door["frame_volume_m3"] = volume
        rows = window_rows if is_window else door_rows
        rows.append({"element_id": door["id"], "object_name": door["object_name"],
                          "name": door["label"], "host_id": door["host_id"], "host_name": host["label"],
                          "base_level_id": host["base_level_id"], "base_level": levels[host["base_level_id"]]["label"],
                          **{name: door[name] for name in ("offset_m", "width_m", "height_m", "sill_m")},
                          "opening_area_m2": width * height,
                          "opening_volume_m3": width * height * host["thickness_m"],
                          "frame_volume_m3": volume, "count": 1,
                          "quantity_rule": WINDOW_RULE if is_window else DOOR_RULE, "content_revision": revision})
    structural_rows = {"slab_rows": [], "column_rows": [], "beam_rows": []}
    for key, rule in (("slabs", SLAB_RULE), ("columns", COLUMN_RULE), ("beams", BEAM_RULE)):
        for item in authored.get(key, []):
            from . import elements
            obj = native[item["id"]]
            gross_shape, expected_shape = elements.gross_solid(obj), elements.expected_solid(obj)
            _same_solid(obj.Shape, expected_shape, obj.Label)
            gross = _finite(gross_shape.Volume / 1e9, "Gross volume")
            net = _finite(obj.Shape.Volume / 1e9, "Net volume")
            if net > gross and not math.isclose(net, gross, rel_tol=1e-8, abs_tol=1e-9):
                raise FoundationError(f"{obj.Label}: joined volume exceeds gross volume")
            deduction = max(0.0, gross - net)
            values = {"gross_volume_m3": gross, "net_volume_m3": net, "join_deduction_m3": deduction}
            for prop, value in (("GrossVolume", gross), ("NetVolume", net)):
                _close(mm(obj, prop) / 1e9, value, f"{obj.Label}.{prop}")
            common = {"element_id": item["id"], "object_name": item["object_name"], "name": item["label"],
                      "material": item["material"], "count": 1, "quantity_rule": rule,
                      "content_revision": revision}
            if key == "slabs":
                slab = elements.slab_parameters(obj)
                area = _finite(slab["area"] / 1e6, "Slab plan area")
                perimeter = _finite(slab["perimeter"] / 1000.0, "Slab perimeter")
                _close(mm(obj, "PlanArea") / 1e6, area, f"{obj.Label}.PlanArea")
                _close(mm(obj, "Perimeter") / 1000.0, perimeter, f"{obj.Label}.Perimeter")
                values.update(gross_area_m2=area, net_area_m2=net/item["thickness_m"], perimeter_m=perimeter)
                row = dict(common, level_id=item["level_id"], level=levels[item["level_id"]]["label"],
                           **{name: item[name] for name in ("offset_m", "top_z_m", "thickness_m")}, **values)
                structural_rows["slab_rows"].append(row)
            else:
                _close(mm(obj, "JoinVolume") / 1e9, deduction, f"{obj.Label}.JoinVolume")
                section = item["width_m"] * item["depth_m"]
                _close(mm(obj, "SectionArea") / 1e6, section, f"{obj.Label}.SectionArea")
                values["section_area_m2"] = section
                row = dict(common, **values, join_slab_ids="|".join(item["join_slab_ids"]),
                           join_count=len(item["join_slab_ids"]), width_m=item["width_m"], depth_m=item["depth_m"])
                if key == "columns":
                    _close(_m(obj, "Height"), item["height_m"], f"{obj.Label}.Height")
                    row.update(base_level_id=item["base_level_id"], base_level=levels[item["base_level_id"]]["label"],
                               top_level_id=item["top_level_id"], top_level=levels[item["top_level_id"]]["label"],
                               **{name: item[name] for name in ("x_m", "y_m", "rotation_deg", "height_m",
                                                              "base_offset_m", "top_offset_m")})
                    structural_rows["column_rows"].append(row)
                else:
                    _close(_m(obj, "Length"), item["length_m"], f"{obj.Label}.Length")
                    row.update(level_id=item["level_id"], level=levels[item["level_id"]]["label"],
                               start_x_m=item["start_m"][0], start_y_m=item["start_m"][1],
                               end_x_m=item["end_m"][0], end_y_m=item["end_m"][1],
                               **{name: item[name] for name in ("length_m", "offset_m", "top_z_m")})
                    structural_rows["beam_rows"].append(row)
            item["quantities"] = values
            box = obj.Shape.BoundBox
            item["native_bounds_m"] = [[_finite(getattr(box, name) / 1000.0, name) for name in names]
                                       for names in (("XMin", "YMin", "ZMin"), ("XMax", "YMax", "ZMax"))]
    from . import material_quantities
    catalogue = {}
    if material_quantities.active(project):
        for rows in [wall_rows, door_rows, window_rows] + list(structural_rows.values()):
            for row in rows:
                row.update(material_quantities.row_type_fields(native[row["element_id"]]))
        material_rows, material_totals = material_quantities.capture(project, revision)
        catalogue.update(type_rows=material_quantities.type_rows(project, revision),
                         material_rows=material_rows, material_totals=material_totals)
        coverage["warnings"].append("Native material rows partition assigned product solids only; legacy text materials remain unassigned. Consult material_totals for assignment coverage; do not add material rows again to product quantities.")
    # Reading quantities must not accept a model that changed during a callback.
    if _revision(_authored(project), _coverage(doc)) != revision:
        raise FoundationError("The model changed while quantities were being read; refresh and retry")
    return {"snapshot_schema": SNAPSHOT_SCHEMA, "workbench_version": __version__,
            "content_revision": revision, "revision_rule": REVISION_RULE,
            "revision_scope": "3117 authored properties and coverage inventory; excludes display settings and unsupported object geometry",
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_document": {"name": doc.Name, "label": doc.Label, "file": doc.FileName},
            "units": {"length": "m", "area": "m2", "volume": "m3"},
            "coordinates": {"origin_m": [0.0, 0.0, 0.0], "axes": "right-handed X/Y, Z up",
                            "wall": "X follows start to end; material is on local +Y"},
            **authored, "wall_rows": wall_rows, "door_rows": door_rows, "window_rows": window_rows,
            **structural_rows, **catalogue,
            "coverage": coverage,
            "totals": {"walls_count": len(wall_rows), "doors_count": len(door_rows),
                       "windows_count": len(window_rows),
                       "slabs_count": len(structural_rows["slab_rows"]),
                       "columns_count": len(structural_rows["column_rows"]),
                       "beams_count": len(structural_rows["beam_rows"]),
                       **{name + "_net_volume_m3": math.fsum(row["net_volume_m3"] for row in structural_rows[name + "_rows"])
                          for name in ("slab", "column", "beam")},
                       "structural_net_volume_m3": math.fsum(row["net_volume_m3"] for rows in structural_rows.values() for row in rows),
                       "join_deduction_m3": math.fsum(row["join_deduction_m3"] for rows in structural_rows.values() for row in rows),
                       "gross_side_area_m2": math.fsum(row["gross_side_area_m2"] for row in wall_rows),
                       "net_side_area_m2": math.fsum(row["net_side_area_m2"] for row in wall_rows),
                       "gross_volume_m3": math.fsum(row["gross_volume_m3"] for row in wall_rows),
                       "net_volume_m3": math.fsum(row["net_volume_m3"] for row in wall_rows),
                       "rule": "Sum of individual walls; no wall-join overlap deductions"}}


def is_current(project, snapshot_or_revision):
    """True only if a valid committed model has the same content revision."""
    expected = (snapshot_or_revision.get("content_revision")
                if isinstance(snapshot_or_revision, dict) else snapshot_or_revision)
    try:
        return bool(expected) and capture(project)["content_revision"] == expected
    except (FoundationError, AttributeError, RuntimeError, ReferenceError):
        return False
