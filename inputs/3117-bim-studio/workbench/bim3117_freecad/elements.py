# SPDX-License-Identifier: GPL-3.0-or-later
"""Level-bound slabs, rectangular columns/beams and directed slab cuts.

All geometry is built from native authored properties in millimetres, in world
coordinates. Slab/Beam Level + Offset is the TOP elevation. A joined Column or
Beam depends on Slab cutters; Slabs never depend on those members. This limited
join graph is acyclic by construction and never alters the authored dimensions.
"""
import math

import FreeCAD as App
import Part

from .model import (FoundationError, _BaseProxy, _common, _link_project,
                    _property, kind, mm, number, text)
from .building import _add_reference, _reference, _output, _identity_placement, _box

ELEMENT_KINDS = ("Slab", "Column", "Beam")
TOLERANCE_MM = 1e-7


def boundary_points(value):
    """Validate one simple XY polygon, returning an unclosed list of pairs.

    A repeated closing point is accepted and removed. Holes, zero edges,
    repeated vertices, crossings and self-touching boundaries are rejected.
    """
    if isinstance(value, (str, bytes)):
        raise FoundationError("Slab boundary must be a sequence of XY points")
    try:
        supplied = list(value)
    except TypeError as error:
        raise FoundationError("Slab boundary must be a sequence of XY points") from error
    points = []
    for vertex in supplied:
        if all(hasattr(vertex, name) for name in ("x", "y", "z")):
            coords = (vertex.x, vertex.y, vertex.z)
        else:
            try:
                coords = tuple(vertex)
            except TypeError as error:
                raise FoundationError("Each slab boundary point must contain X and Y") from error
        if len(coords) not in (2, 3):
            raise FoundationError("Each slab boundary point must contain X/Y or X/Y/Z=0")
        x, y = number(coords[0], "Boundary X"), number(coords[1], "Boundary Y")
        if len(coords) == 3 and abs(number(coords[2], "Boundary Z")) > TOLERANCE_MM:
            raise FoundationError("Slab boundary must lie in the XY plane (Z=0); Level controls elevation")
        points.append((x, y))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise FoundationError("Slab boundary needs at least three distinct vertices")
    for index, point in enumerate(points):
        for other in points[:index]:
            if math.hypot(point[0] - other[0], point[1] - other[1]) <= TOLERANCE_MM:
                raise FoundationError("Slab boundary contains repeated vertices")
    count = len(points)
    for index in range(count):
        a, b, c = points[index - 1], points[index], points[(index + 1) % count]
        number(math.hypot(b[0] - c[0], b[1] - c[1]), "Slab edge length", positive=True)
        if (_orientation(a, b, c) == 0
                and (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0):
            raise FoundationError("Slab boundary doubles back along an edge")
    for first in range(count):
        a, b = points[first], points[(first + 1) % count]
        for second in range(first + 1, count):
            if second == first + 1 or (first == 0 and second == count - 1):
                continue
            c, d = points[second], points[(second + 1) % count]
            if _segments_touch(a, b, c, d):
                raise FoundationError("Slab boundary crosses or touches itself")
    origin_x, origin_y = points[0]
    try:
        signed = math.fsum((a[0] - origin_x) * (b[1] - origin_y)
                           - (b[0] - origin_x) * (a[1] - origin_y)
                           for a, b in zip(points, points[1:] + points[:1])) / 2.0
    except (ValueError, OverflowError) as error:
        raise FoundationError("Slab boundary area is outside the supported numeric range") from error
    if not math.isfinite(signed) or abs(signed) < 1e-6:
        raise FoundationError("Slab boundary must enclose a positive area")
    return points


def _orientation(a, b, c):
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    tolerance = TOLERANCE_MM * max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))
    return 1 if cross > tolerance else -1 if cross < -tolerance else 0


def _on_segment(a, b, p):
    return (min(a[0], b[0]) - TOLERANCE_MM <= p[0] <= max(a[0], b[0]) + TOLERANCE_MM
            and min(a[1], b[1]) - TOLERANCE_MM <= p[1] <= max(a[1], b[1]) + TOLERANCE_MM)


def _segments_touch(a, b, c, d):
    o1, o2, o3, o4 = (_orientation(a, b, c), _orientation(a, b, d),
                       _orientation(c, d, a), _orientation(c, d, b))
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return ((o1 == 0 and _on_segment(a, b, c)) or (o2 == 0 and _on_segment(a, b, d))
            or (o3 == 0 and _on_segment(c, d, a)) or (o4 == 0 and _on_segment(c, d, b)))


def slab_parameters(slab):
    from .catalog import effective_dimension, effective_material
    level = _reference(slab, "Level", "Level")
    top_z = number(mm(level, "Elevation"), "Slab level elevation") + number(mm(slab, "Offset"), "Slab top offset")
    return _slab_values(slab.Boundary, effective_dimension(slab, "Thickness"), top_z, effective_material(slab))


def _slab_values(boundary, thickness, top_z, material):
    """Validate saved or proposed values without writing native properties."""
    points = boundary_points(boundary)
    thickness = number(thickness, "Slab thickness", positive=True)
    ox, oy = points[0]
    area = abs(math.fsum((a[0] - ox) * (b[1] - oy) - (b[0] - ox) * (a[1] - oy)
                        for a, b in zip(points, points[1:] + points[:1]))) / 2.0
    perimeter = math.fsum(math.hypot(b[0] - a[0], b[1] - a[1])
                          for a, b in zip(points, points[1:] + points[:1]))
    number(top_z, "Slab top elevation")
    number(top_z - thickness, "Slab bottom elevation")
    text(material, "Material")
    return {"boundary": points, "top_z": top_z, "bottom_z": top_z - thickness,
            "thickness": thickness, "area": area, "perimeter": perimeter}


def _proposed_number(obj, prop, updates):
    from .catalog import effective_dimension
    return updates[prop] if updates is not None and prop in updates else effective_dimension(obj, prop)


def _proposed_level(obj, prop, references):
    if references is None or prop not in references:
        return _reference(obj, prop, "Level")
    level = references[prop]
    if kind(level) != "Level" or level.Project != obj.Project or level.Document != obj.Document:
        raise FoundationError(f"{obj.Label}: {prop} must be a Level in the same project")
    return level


def column_parameters(column, updates=None, references=None):
    base = _proposed_level(column, "BaseLevel", references)
    top = _proposed_level(column, "TopLevel", references)
    base_z = number(mm(base, "Elevation"), "Column base elevation") + number(_proposed_number(column, "BaseOffset", updates), "Column base offset")
    top_z = number(mm(top, "Elevation"), "Column top elevation") + number(_proposed_number(column, "TopOffset", updates), "Column top offset")
    values = {"center_x": number(_proposed_number(column, "X", updates), "Column X"),
              "center_y": number(_proposed_number(column, "Y", updates), "Column Y"),
              "width": number(_proposed_number(column, "Width", updates), "Column width", positive=True),
              "depth": number(_proposed_number(column, "Depth", updates), "Column depth", positive=True),
              "rotation_deg": number(_proposed_number(column, "Rotation", updates), "Column rotation"),
              "base_z": number(base_z, "Column base elevation"),
              "top_z": number(top_z, "Column top elevation"),
              "height": number(top_z - base_z, "Effective column height", positive=True)}
    text(updates.get("Material", column.Material) if updates is not None else column.Material, "Material")
    return values


def beam_parameters(beam, updates=None, references=None):
    level = _proposed_level(beam, "Level", references)
    sx, sy = number(_proposed_number(beam, "StartX", updates), "Beam start X"), number(_proposed_number(beam, "StartY", updates), "Beam start Y")
    ex, ey = number(_proposed_number(beam, "EndX", updates), "Beam end X"), number(_proposed_number(beam, "EndY", updates), "Beam end Y")
    length = number(math.hypot(ex - sx, ey - sy), "Beam axis length", positive=True)
    width = number(_proposed_number(beam, "Width", updates), "Beam width", positive=True)
    depth = number(_proposed_number(beam, "Depth", updates), "Beam depth", positive=True)
    top_z = number(mm(level, "Elevation"), "Beam level elevation") + number(_proposed_number(beam, "Offset", updates), "Beam top offset")
    number(top_z, "Beam top elevation")
    number(top_z - depth, "Beam bottom elevation")
    text(updates.get("Material", beam.Material) if updates is not None else beam.Material, "Material")
    return {"start_x": sx, "start_y": sy, "ux": (ex - sx) / length,
            "uy": (ey - sy) / length, "length": length, "width": width, "depth": depth,
            "top_z": top_z, "base_z": top_z - depth}


def _single_solid(shape, label):
    if (shape.isNull() or not shape.isValid() or len(shape.Solids) != 1
            or not math.isfinite(shape.Volume) or shape.Volume <= 0):
        raise FoundationError(f"{label}: geometry must remain one connected positive-volume solid; split/full-removal joins are unsupported")
    return shape


def slab_solid(slab):
    """Build the uncut slab from authored inputs; never read Shape or outputs."""
    return _slab_solid_from_values(slab_parameters(slab), slab.Label)


def _slab_solid_from_values(values, label):
    points = [App.Vector(x, y, values["top_z"]) for x, y in values["boundary"]]
    face = Part.Face(Part.makePolygon(points + [points[0]]))
    return _single_solid(face.extrude(App.Vector(0, 0, -values["thickness"])), label)


def slab_edit_solid(slab, values, level=None):
    """Transient proposed slab for a command preflight, never a stored model.

    ``values`` contains only validated native-property updates from the service.
    The service validates a supplied replacement Level before calling this.
    """
    from .catalog import effective_dimension, effective_material
    level = _reference(slab, "Level", "Level") if level is None else level
    top_z = number(mm(level, "Elevation"), "Slab level elevation") + number(
        values.get("Offset", mm(slab, "Offset")), "Slab top offset")
    proposed = _slab_values(values.get("Boundary", slab.Boundary),
                            values["Thickness"] if "Thickness" in values else effective_dimension(slab, "Thickness"),
                            top_z, values["Material"] if "Material" in values else effective_material(slab))
    try:
        return _slab_solid_from_values(proposed, values.get("Label", slab.Label))
    except FoundationError:
        raise
    except Exception as error:
        raise FoundationError(f"{slab.Label}: OCCT could not build the proposed slab ({error})") from error


def gross_solid(obj, updates=None, references=None):
    expected = kind(obj)
    if expected == "Slab":
        return slab_solid(obj)
    if expected == "Column":
        p = column_parameters(obj, updates, references)
        theta = math.radians(p["rotation_deg"])
        ux, uy = math.cos(theta), math.sin(theta)
        inputs = {"start_x": p["center_x"], "start_y": p["center_y"],
                  "ux": ux, "uy": uy, "base_z": p["base_z"]}
        return _single_solid(_box(inputs, -p["width"] / 2, -p["depth"] / 2, 0,
                                  p["width"], p["depth"], p["height"]), obj.Label)
    if expected == "Beam":
        p = beam_parameters(obj, updates, references)
        return _single_solid(_box(p, 0, -p["width"] / 2, 0,
                                  p["length"], p["width"], p["depth"]), obj.Label)
    raise FoundationError("Only Slab, Column and Beam have building-member solid definitions")


def join_slabs(member):
    """Validate saved cutter identities, including dangling raw-delete links."""
    if kind(member) not in ("Column", "Beam"):
        raise FoundationError("Only a Column or Beam can be cut by Slabs")
    slabs = list(member.JoinSlabs)
    ids = list(member.JoinSlabIds)
    if (len(slabs) != len(ids) or len(ids) != len(set(ids))
            or any(slab is None for slab in slabs)):
        raise FoundationError(f"{member.Label}: slab join references are missing or duplicated; use Unjoin Slab to repair")
    for slab, identifier in zip(slabs, ids):
        if (kind(slab) != "Slab" or slab.Project != member.Project
                or slab.Document != member.Document or identifier != slab.BIM3117Id):
            raise FoundationError(f"{member.Label}: join cutter must be a Slab in the same project with a matching identity")
    return slabs


def _cut_member(shape, slabs, slab_overrides=None):
    # Stable UUID order avoids differences from selection order while cuts
    # deduct the union of overlapping cutters, never double-counting volume.
    for slab in sorted(slabs, key=lambda item: item.BIM3117Id):
        cutter = slab_overrides.get(slab.BIM3117Id) if slab_overrides is not None else None
        shape = shape.cut(slab_solid(slab) if cutter is None else cutter)
    return shape.removeSplitter()


def member_edit_solid(member, updates, references):
    """Build a proposed Column/Beam with its existing native slab cutters."""
    try:
        gross = gross_solid(member, updates, references)
        return _single_solid(_cut_member(gross, join_slabs(member)), member.Label)
    except FoundationError:
        raise
    except Exception as error:
        raise FoundationError(f"{member.Label}: OCCT could not build the proposed member ({error})") from error


def expected_solid(obj, joined=True, extra_slabs=(), slab_overrides=None):
    """Transient expected geometry, including directed slab-priority cuts.

    Extra cutters or transient replacement cutter solids are used only for
    command preflight; the normal execution/export path reads native properties.
    """
    try:
        shape = gross_solid(obj)
        if joined and kind(obj) in ("Column", "Beam"):
            shape = _cut_member(shape, join_slabs(obj) + list(extra_slabs), slab_overrides)
        return _single_solid(shape, obj.Label)
    except FoundationError:
        raise
    except Exception as error:
        # The Property Editor guard catches FoundationError to restore its prior
        # value. Kernel failures must follow the same atomic validation path.
        raise FoundationError(f"{obj.Label}: OCCT could not build the authored solid ({error})") from error


def validate_element_object(obj):
    _identity_placement(obj)
    expected = kind(obj)
    if expected == "Slab":
        slab_parameters(obj)
    elif expected == "Column":
        column_parameters(obj)
        join_slabs(obj)
    elif expected == "Beam":
        beam_parameters(obj)
        join_slabs(obj)
    else:
        raise FoundationError("Unsupported building element")


def affected_elements(obj):
    """Include geometric dependants without following cached shapes."""
    objects = list(obj.Document.Objects)
    expected = kind(obj)
    affected = [obj] if expected in ELEMENT_KINDS else []
    if expected == "Level":
        affected.extend(item for item in objects
                        if ((kind(item) in ("Slab", "Beam") and item.LevelId == obj.BIM3117Id)
                            or (kind(item) == "Column" and obj.BIM3117Id in (item.BaseLevelId, item.TopLevelId))))
    slabs = {item.BIM3117Id for item in affected if kind(item) == "Slab"}
    if slabs:
        affected.extend(item for item in objects if kind(item) in ("Column", "Beam")
                        and slabs.intersection(item.JoinSlabIds) and item not in affected)
    return affected


def validate_affected_elements(obj):
    for item in affected_elements(obj):
        validate_element_object(item)
        expected_solid(item)


def invalidate_element_dependents(obj, reason):
    from .building import clear_calculated_shape
    for item in affected_elements(obj):
        if item != obj:
            clear_calculated_shape(item, reason)


class SlabProxy(_BaseProxy):
    editable = ("Label", "Level", "Boundary", "Thickness", "Offset", "Material", "Placement", "ElementType")
    reference_properties = {"Level": "Level", "ElementType": "ElementType"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Slab")
        _link_project(obj, project)
        _add_reference(obj, "Level", "Level")
        _property(obj, "App::PropertyVectorList", "Boundary", "Slab Instance", "One simple XY polygon in mm; Z must be zero", [])
        _property(obj, "App::PropertyLength", "Thickness", "Slab Instance", "Thickness downwards from the top elevation", 150.0)
        _property(obj, "App::PropertyDistance", "Offset", "Slab Instance", "Top elevation offset above Level", 0.0)
        _property(obj, "App::PropertyString", "Material", "Slab Instance", "Instance material description; no layered assembly", "")
        from .catalog import initialize_instance
        initialize_instance(obj)
        for prop, type_name in (("PlanArea", "App::PropertyArea"), ("Perimeter", "App::PropertyLength"),
                                ("GrossVolume", "App::PropertyVolume"), ("NetVolume", "App::PropertyVolume")):
            _output(obj, type_name, prop, "Calculated from the slab definition in native mm units")
        obj.setEditorMode("Placement", 1)
        self._finish(obj)

    def build(self, obj):
        values = slab_parameters(obj)
        shape = expected_solid(obj)
        obj.Shape = shape
        obj.PlanArea, obj.Perimeter = values["area"], values["perimeter"]
        obj.GrossVolume, obj.NetVolume = shape.Volume, shape.Volume


class _MemberProxy(_BaseProxy):
    list_reference_properties = ("JoinSlabs",)

    def _join_properties(self, obj):
        _property(obj, "App::PropertyLinkList", "JoinSlabs", "3117 References", "Slab-priority cuts; change only with Join/Unjoin Slab commands", [], True)
        _property(obj, "App::PropertyStringList", "JoinSlabIds", "3117 Identity", "Expected cutter UUIDs; retained when native links are lost", [], True)
        for prop in ("GrossVolume", "NetVolume", "JoinVolume"):
            _output(obj, "App::PropertyVolume", prop, "Actual solid volume before/after union of slab cuts; native mm^3")
        _output(obj, "App::PropertyArea", "SectionArea", "Authored rectangular gross section area; native mm^2")
        obj.setEditorMode("Placement", 1)

    def _build_member(self, obj, section_area):
        gross, net = gross_solid(obj), expected_solid(obj)
        obj.Shape = net
        obj.SectionArea = section_area
        obj.GrossVolume, obj.NetVolume = gross.Volume, net.Volume
        obj.JoinVolume = max(0.0, gross.Volume - net.Volume)


class ColumnProxy(_MemberProxy):
    editable = ("Label", "BaseLevel", "TopLevel", "X", "Y", "Width", "Depth", "Rotation",
                "BaseOffset", "TopOffset", "Material", "JoinSlabs", "Placement", "ElementType")
    reference_properties = {"BaseLevel": "Level", "TopLevel": "Level", "ElementType": "ElementType"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Column")
        _link_project(obj, project)
        for prop in ("BaseLevel", "TopLevel"):
            _add_reference(obj, prop, "Level")
        for prop in ("X", "Y", "BaseOffset", "TopOffset"):
            _property(obj, "App::PropertyDistance", prop, "Column Instance", "Column center or level offset in millimetres", 0.0)
        for prop in ("Width", "Depth"):
            _property(obj, "App::PropertyLength", prop, "Column Instance", "Rectangular section dimension", 300.0)
        _property(obj, "App::PropertyAngle", "Rotation", "Column Instance", "Section rotation about project Z in degrees", 0.0)
        _property(obj, "App::PropertyString", "Material", "Column Instance", "Instance material description", "")
        from .catalog import initialize_instance
        initialize_instance(obj)
        _output(obj, "App::PropertyLength", "Height", "Authored effective height before joins")
        self._join_properties(obj)
        self._finish(obj)

    def build(self, obj):
        values = column_parameters(obj)
        self._build_member(obj, values["width"] * values["depth"])
        obj.Height = values["height"]


class BeamProxy(_MemberProxy):
    editable = ("Label", "Level", "StartX", "StartY", "EndX", "EndY", "Width", "Depth",
                "Offset", "Material", "JoinSlabs", "Placement", "ElementType")
    reference_properties = {"Level": "Level", "ElementType": "ElementType"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Beam")
        _link_project(obj, project)
        _add_reference(obj, "Level", "Level")
        for prop, value in (("StartX", 0.0), ("StartY", 0.0), ("EndX", 6000.0), ("EndY", 0.0), ("Offset", 0.0)):
            _property(obj, "App::PropertyDistance", prop, "Beam Instance", "Horizontal centerline coordinate or top elevation offset", value)
        _property(obj, "App::PropertyLength", "Width", "Beam Instance", "Section width centered about the XY axis", 300.0)
        _property(obj, "App::PropertyLength", "Depth", "Beam Instance", "Section depth downwards from the top elevation", 450.0)
        _property(obj, "App::PropertyString", "Material", "Beam Instance", "Instance material description", "")
        from .catalog import initialize_instance
        initialize_instance(obj)
        _output(obj, "App::PropertyLength", "Length", "Authored horizontal axis length before joins")
        self._join_properties(obj)
        self._finish(obj)

    def build(self, obj):
        values = beam_parameters(obj)
        self._build_member(obj, values["width"] * values["depth"])
        obj.Length = values["length"]
