# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only OCCT cuts and TechDraw projections of the committed native model.

Coordinates in this module are model millimetres.  A view's local X points
right, local Y points up, and local Z points towards the viewer.  The returned
plain-data geometry is a derived result, never an editable model or mesh.

The caller must first run the committed-document/snapshot validation gate.
This layer creates no document objects, properties, or transactions.  Current
3117 building solids are polyhedral; encountering a curved edge is an explicit
unsupported-geometry error rather than an undocumented tessellation.
"""
import math

import FreeCAD as App
import Part
import TechDraw

from .model import FoundationError, kind, number

GEOMETRY_RULE = "3117.occt-cut-techdraw-hlr.polyhedral-orthographic.v1"
PRODUCT_KINDS = ("Wall", "Door", "Window", "Slab", "Column", "Beam")
TOLERANCE_MM = 1e-6


def _vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise FoundationError(label + " must contain three millimetre coordinates")
    return App.Vector(*(number(v, label) for v in value))


def _coordinates(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def _clean(value):
    value = round(float(value), 6)
    return 0.0 if abs(value) < TOLERANCE_MM else value


def _point(vector):
    return [_clean(vector.x), _clean(vector.y)]


def frame_for_definition(definition):
    """Return the right/up frame; direction points from viewer into model."""
    view_type = definition.get("view_type")
    if view_type not in ("Plan", "Section", "Elevation"):
        raise FoundationError("Drawing view must be Plan, Section or Elevation")
    origin = _vector(definition.get("origin_mm", [0.0, 0.0, 0.0]), "View origin")
    if view_type == "Plan":
        elevation = number(definition.get("level_elevation_mm"), "Plan level elevation")
        bottom = number(definition.get("bottom_offset_mm"), "Plan bottom offset")
        cut = number(definition.get("cut_offset_mm"), "Plan cut offset")
        top = number(definition.get("top_offset_mm"), "Plan top offset")
        if not bottom < cut < top:
            raise FoundationError("Plan view range must satisfy Bottom < Cut < Top")
        number(cut - bottom, "Plan depth below cut", positive=True)
        number(top - cut, "Plan depth above cut", positive=True)
        origin = App.Vector(origin.x, origin.y, elevation + cut)
        right, up, direction = App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, -1)
    else:
        direction = _vector(definition.get("direction"), "View direction")
        cardinal = ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0))
        matches = [v for v in cardinal if (direction - App.Vector(*v)).Length < 1e-9]
        if len(matches) != 1:
            raise FoundationError("Section/elevation direction must be +X, -X, +Y or -Y")
        direction = App.Vector(*matches[0])
        up = App.Vector(0, 0, 1)
        right = up.cross(-direction)
        number(definition.get("depth_mm"), "View depth", positive=True)
    return {"origin_mm": _coordinates(origin), "right": _coordinates(right),
            "up": _coordinates(up), "direction": _coordinates(direction)}


def project_point(definition, xyz):
    """Project a world point to the same X-right/Y-up mm frame as the paths."""
    frame = frame_for_definition(definition)
    relative = _vector(xyz, "World point") - App.Vector(*frame["origin_mm"])
    return [_clean(relative.dot(App.Vector(*frame["right"]))),
            _clean(relative.dot(App.Vector(*frame["up"])))]


def _matrix(frame):
    origin = App.Vector(*frame["origin_mm"])
    axes = (App.Vector(*frame["right"]), App.Vector(*frame["up"]),
            -App.Vector(*frame["direction"]))
    matrix = App.Matrix()
    for index, axis in enumerate(axes, 1):
        for column, value in enumerate(_coordinates(axis), 1):
            setattr(matrix, "A%d%d" % (index, column), value)
        setattr(matrix, "A%d4" % index, -axis.dot(origin))
    return matrix


def _bounds(shape):
    box = shape.BoundBox
    return [_clean(box.XMin), _clean(box.YMin), _clean(box.XMax), _clean(box.YMax)]


def _line(edge):
    if type(edge.Curve).__name__ not in ("Line", "LineSegment"):
        raise FoundationError("Drawing projection currently supports straight native edges only")
    start = edge.valueAt(edge.FirstParameter)
    end = edge.valueAt(edge.LastParameter)
    if math.hypot(start.x - end.x, start.y - end.y) <= TOLERANCE_MM:
        return None
    return start, end


def _paths(shapes):
    paths, seen = [], set()
    for shape in shapes:
        for edge in shape.Edges:
            line = _line(edge)
            if line is None:
                continue
            start, end = map(_point, line)
            key = tuple(sorted((tuple(start), tuple(end))))
            if key not in seen:
                seen.add(key)
                paths.append([list(key[0]), list(key[1])])
    return sorted(paths)


def _project(shapes):
    if not shapes:
        return [], []
    compound = Part.makeCompound(shapes)
    # A global HLR projection is essential: projecting each product separately
    # would display back walls and members through foreground opaque solids.
    projected = TechDraw.projectEx(compound, App.Vector(0, 0, 1))
    visible = projected[:5]
    return _paths(visible), [edge for shape in visible for edge in shape.Edges]


def _cut_faces(source, plane):
    shape = source["shape"]
    box = shape.BoundBox
    # Tangency at an outer boundary is an elevation outline, not cut material.
    if box.ZMin >= -TOLERANCE_MM or box.ZMax <= TOLERANCE_MM:
        return []
    intersection = shape.common(plane)
    result = []
    for face in intersection.Faces:
        if face.Area <= TOLERANCE_MM:
            continue
        loops = []
        for wire in face.Wires:
            if not wire.isClosed():
                raise FoundationError("OCCT returned an open cut-face boundary")
            for edge in wire.Edges:
                _line(edge)
            points = [_point(vertex.Point) for vertex in wire.OrderedVertexes]
            if len(points) < 3:
                raise FoundationError("OCCT returned a degenerate cut-face boundary")
            # Canonical start/winding keeps JSON stable after native reopen.
            variants = []
            for direction in (points, list(reversed(points))):
                first = min(range(len(direction)), key=lambda i: tuple(direction[i]))
                variants.append(direction[first:] + direction[:first])
            points = min(variants)
            loops.append(points + [points[0]])
        loops.sort()
        result.append({"source_id": source["id"], "category": source["category"],
                       "loops": loops, "area_mm2": _clean(face.Area)})
    return sorted(result, key=lambda item: item["loops"])


def _frontmost_sources(edges, sources):
    """Find visible edge ownership using actual OCCT ray/solid intersections.

    A shared projected outline is not sufficient proof that a back object is
    visible.  Each global HLR segment's midpoint is intersected with all local
    native shapes, and only the first surface towards the viewer owns it.
    Coincident native surfaces may legitimately have multiple owners.  An
    unresolved tangent is left untaggable rather than assigning a guessed ID.
    """
    owners = {source["id"]: [] for source in sources}
    if not edges or not sources:
        return owners
    front = max(source["shape"].BoundBox.ZMax for source in sources) + 1.0
    back = min(source["shape"].BoundBox.ZMin for source in sources) - 1.0
    seen = set()
    for edge in edges:
        line = _line(edge)
        if line is None:
            continue
        midpoint = (line[0] + line[1]) * 0.5
        key = tuple(_point(midpoint))
        if key in seen:
            continue
        seen.add(key)
        ray = Part.makeLine(App.Vector(midpoint.x, midpoint.y, front),
                            App.Vector(midpoint.x, midpoint.y, back))
        hits = []
        for source in sources:
            shape = source["shape"]
            box = shape.BoundBox
            if (midpoint.x < box.XMin - TOLERANCE_MM or midpoint.x > box.XMax + TOLERANCE_MM
                    or midpoint.y < box.YMin - TOLERANCE_MM or midpoint.y > box.YMax + TOLERANCE_MM):
                continue
            intersection = shape.common(ray)
            if intersection.Vertexes:
                hits.append((max(v.Point.z for v in intersection.Vertexes), source["id"]))
        if hits:
            nearest = max(hit[0] for hit in hits)
            for distance, identifier in hits:
                if abs(distance - nearest) <= TOLERANCE_MM:
                    owners[identifier].append(_point(midpoint))
    return owners


def _collect_sources(project, matrix):
    sources = []
    for obj in project.Group:
        category = kind(obj)
        if category not in PRODUCT_KINDS:
            continue
        geometry = obj.Body if category == "Wall" else obj
        shape = geometry.Shape
        if shape.isNull() or not shape.isValid() or not shape.Solids:
            raise FoundationError(obj.Label + ": native solid is missing or invalid for drawing")
        local = shape.copy()
        local.transformShape(matrix, True)
        sources.append({"id": str(obj.BIM3117Id), "name": str(obj.Label),
                        "category": category, "shape": local})
    return sorted(sources, key=lambda item: item["id"])


def build_view_geometry(project, definition):
    """Cut/project native building solids without modifying their document.

    Plans use the exact Bottom/Cut interval and show overhead-only products
    intersecting Cut/Top as a separate dashed projection.  A product crossing
    the cut plane is not repeated in the overhead layer.  Section and elevation
    directions point into the model and retain the positive depth interval.
    Sections add true plane-intersection loops; elevations do not mark cuts.
    """
    frame = frame_for_definition(definition)
    sources = _collect_sources(project, _matrix(frame))
    if not sources:
        raise FoundationError("The selected project has no supported building solids to draw")
    xmin = min(source["shape"].BoundBox.XMin for source in sources) - 1.0
    ymin = min(source["shape"].BoundBox.YMin for source in sources) - 1.0
    xmax = max(source["shape"].BoundBox.XMax for source in sources) + 1.0
    ymax = max(source["shape"].BoundBox.YMax for source in sources) + 1.0
    view_type = definition["view_type"]
    if view_type == "Plan":
        depth = definition["cut_offset_mm"] - definition["bottom_offset_mm"]
        overhead_depth = definition["top_offset_mm"] - definition["cut_offset_mm"]
        overhead_box = Part.makeBox(xmax - xmin, ymax - ymin, overhead_depth,
                                   App.Vector(xmin, ymin, 0))
    else:
        depth = number(definition["depth_mm"], "View depth", positive=True)
        overhead_box = None
    below_box = Part.makeBox(xmax - xmin, ymax - ymin, depth,
                            App.Vector(xmin, ymin, -depth))
    plane = Part.makePlane(xmax - xmin, ymax - ymin, App.Vector(xmin, ymin, 0))
    main, overhead, cut_faces, excluded = [], [], [], []
    for source in sources:
        shape = source["shape"]
        if (overhead_box is not None and shape.BoundBox.ZMin > TOLERANCE_MM):
            clipped = shape.common(overhead_box)
            layer = "overhead"
        else:
            clipped = shape.common(below_box)
            layer = "projection"
        if (clipped.isNull() or not clipped.Faces
                or (layer == "overhead" and clipped.Volume <= TOLERANCE_MM)):
            excluded.append({"id": source["id"], "name": source["name"],
                             "category": source["category"],
                             "reason": "Outside the exact view range or depth"})
            continue
        item = {**source, "shape": clipped, "layer": layer}
        if layer == "overhead":
            overhead.append(item)
        else:
            main.append(item)
            if view_type != "Elevation":
                cut_faces.extend(_cut_faces(source, plane))
    visible_paths, visible_edges = _project([source["shape"] for source in main])
    overhead_paths, overhead_edges = _project([source["shape"] for source in overhead])
    main_owners = _frontmost_sources(visible_edges, main)
    overhead_owners = _frontmost_sources(overhead_edges, overhead)
    cut_ids = {face["source_id"] for face in cut_faces}
    output_sources = []
    for source in main + overhead:
        bounds = _bounds(source["shape"])
        center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
        owned = (overhead_owners if source["layer"] == "overhead" else main_owners)[source["id"]]
        is_cut = source["id"] in cut_ids
        visible = bool(owned) or is_cut
        anchor = min(owned, key=lambda point: (math.dist(point, center), point)) if owned else center
        output_sources.append({"id": source["id"], "name": source["name"],
                               "category": source["category"], "bounds_mm": bounds,
                               "anchor_mm": [_clean(value) for value in anchor],
                               "visible": visible, "taggable": bool(owned), "cut": is_cut,
                               "overhead": source["layer"] == "overhead",
                               "visibility_reason": ("Native first-hit ownership of global visible HLR edge"
                                                     if owned else "No unambiguous visible edge anchor; tag omitted")})
    all_points = [p for path in visible_paths + overhead_paths for p in path]
    all_points.extend(p for face in cut_faces for loop in face["loops"] for p in loop)
    if not all_points:
        raise FoundationError("No building geometry intersects this drawing view range or depth")
    bounds = [_clean(min(p[0] for p in all_points)), _clean(min(p[1] for p in all_points)),
              _clean(max(p[0] for p in all_points)), _clean(max(p[1] for p in all_points))]
    return {"rule": GEOMETRY_RULE, "units": "mm", "coordinate_convention": "X right, Y up",
            "frame": frame, "bounds_mm": bounds, "visible_paths": visible_paths,
            "hidden_paths": [], "overhead_paths": overhead_paths, "cut_faces": cut_faces,
            "sources": sorted(output_sources, key=lambda item: item["id"]),
            "exclusions": excluded,
            "notes": ["Global OCCT/TechDraw hidden-line removal; no display-mesh projection.",
                      "Overhead layer contains only whole products above the plan cut and inside its top range.",
                      "Unsupported native edge curves are rejected; current authored products are polyhedral."]}
