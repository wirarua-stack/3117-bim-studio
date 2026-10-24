# SPDX-License-Identifier: GPL-3.0-or-later
"""Paper-space SVG from a detached, validated native drawing capture.

All geometry is supplied in native millimetres by drawing_geometry. This module
only places it on paper: X right / Y up is converted to SVG X right / Y down
exactly once. Numeric scales are preserved; a view that cannot fit is rejected.
No FreeCAD object, transaction, view property or external font installation is
created by rendering.
"""
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import unicodedata

from .model import FoundationError

PAPER_MM = (420.0, 297.0)
FONT_FAMILY = "Sarabun"
RENDER_RULE = "3117-a3-landscape-two-view-vector-v1"
NAVY = "#173247"
ORANGE = "#D36D24"
INK = "#263A46"
MUTED = "#566B78"
LIGHT = "#DCE4EA"
FONT_ROOT = Path(__file__).resolve().parent / "fonts"
_FONT_IDS = None
_FONT_CACHE = None


def _finite(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise FoundationError(f"{label} must be a finite number") from error
    if not math.isfinite(value):
        raise FoundationError(f"{label} must be a finite number")
    return value


def _number(value):
    value = _finite(value, "Drawing coordinate")
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _label(value):
    value = " ".join(str(value).split())
    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise FoundationError("Drawing text contains unsupported control characters")
    return value


def _escape(value):
    return html.escape(str(value), quote=True)


def _font_assets():
    global _FONT_CACHE
    if _FONT_CACHE is None:
        try:
            manifest = json.loads((FONT_ROOT / "SOURCE.json").read_text(encoding="utf-8"))
            files = {item["name"]: item for item in manifest["files"]}
            regular = (FONT_ROOT / "Sarabun-Regular.ttf").read_bytes()
            bold = (FONT_ROOT / "Sarabun-Bold.ttf").read_bytes()
            license_text = (FONT_ROOT / "OFL.txt").read_text(encoding="utf-8")
            for name, data in (("Sarabun-Regular.ttf", regular), ("Sarabun-Bold.ttf", bold),
                               ("OFL.txt", license_text.encode("utf-8"))):
                if hashlib.sha256(data).hexdigest() != files[name]["sha256"]:
                    raise ValueError("Font asset hash does not match its source record")
        except (OSError, KeyError, ValueError) as error:
            raise FoundationError("The bundled drawing fonts are missing or changed; reinstall this workbench package") from error
        _FONT_CACHE = (regular, bold, license_text, manifest)
    return _FONT_CACHE


def ensure_fonts(required=False):
    """Register the bundled fonts in the host GUI process, never the OS.

    SVG creation also works in FreeCADCmd. PDF and GUI preview use the running
    host QGuiApplication; a second Qt application/runtime is never created here.
    """
    global _FONT_IDS
    try:
        from PySide import QtGui
        application = QtGui.QGuiApplication.instance()
        if application is None or not isinstance(application, QtGui.QGuiApplication):
            if required:
                raise FoundationError("PDF export needs the FreeCAD GUI; open the document in normal FreeCAD and export again")
            return False
        if _FONT_IDS is None:
            _font_assets()
            identifiers = [QtGui.QFontDatabase.addApplicationFont(str(FONT_ROOT / name))
                           for name in ("Sarabun-Regular.ttf", "Sarabun-Bold.ttf")]
            if any(identifier < 0 for identifier in identifiers):
                raise FoundationError("FreeCAD could not load the bundled Sarabun drawing fonts")
            _FONT_IDS = identifiers
        return True
    except ImportError as error:
        if required:
            raise FoundationError("PDF export needs the Qt runtime supplied by FreeCAD") from error
        return False


def _width(text, size):
    """Deterministic conservative label estimate, independent of GUI DPI."""
    result = 0.0
    for char in _label(text):
        if unicodedata.combining(char) or 0x0E31 == ord(char) or 0x0E34 <= ord(char) <= 0x0E3A or 0x0E47 <= ord(char) <= 0x0E4E:
            continue
        if char in "MW@%":
            result += .96
        elif char in "ilI.,:;!'| ":
            result += .32
        elif 0x0E00 <= ord(char) <= 0x0E7F:
            result += .83
        elif ord(char) > 0x2E80:
            result += 1.0
        else:
            result += .64
    return result * size


def _fit(text, size, max_width, minimum=None):
    text = _label(text)
    if minimum is not None:
        while size > minimum and _width(text, size) > max_width:
            size = max(minimum, size - .1)
    if _width(text, size) <= max_width:
        return text, size, False
    short = text
    while short and _width(short + "...", size) > max_width:
        short = short[:-1]
    return short.rstrip() + "...", size, True


def _text(x, y, value, size=2.6, fill=INK, weight=400, anchor="start", rotation=None,
          max_width=None, minimum=None, source_id=None):
    original = _label(value)
    value = original
    if max_width is not None:
        value, size, _ = _fit(value, size, max_width, minimum)
    attributes = [f'x="{_number(x)}"', f'y="{_number(y)}"', f'font-size="{_number(size)}"',
                  f'fill="{fill}"', f'font-weight="{weight}"', f'text-anchor="{anchor}"']
    if rotation is not None:
        attributes.append(f'transform="rotate({_number(rotation)} {_number(x)} {_number(y)})"')
    if source_id:
        attributes.append(f'data-source-id="{_escape(source_id)}"')
    return "<text " + " ".join(attributes) + "><title>" + _escape(original) + "</title>" + _escape(value) + "</text>"


def _line(x1, y1, x2, y2, width=.18, color=INK, dash=None):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="M{_number(x1)} {_number(y1)} L{_number(x2)} {_number(y2)}" '
            f'fill="none" stroke="{color}" stroke-width="{_number(width)}"{extra}/>')


def _path(points, transform, close=False):
    if not isinstance(points, (tuple, list)) or len(points) < 2:
        raise FoundationError("Drawing path must contain at least two points")
    result = []
    for index, point in enumerate(points):
        if len(point) != 2:
            raise FoundationError("Drawing path points must be two-dimensional")
        x, y = transform(point)
        result.append(("M" if index == 0 else "L") + _number(x) + " " + _number(y))
    return " ".join(result) + (" Z" if close else "")


def _bounds(geometry):
    values = geometry.get("bounds_mm")
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise FoundationError("Drawing geometry has no usable two-dimensional bounds")
    x0, y0, x1, y1 = [_finite(value, "Drawing extent") for value in values]
    if x1 - x0 <= 1e-7 or y1 - y0 <= 1e-7:
        raise FoundationError("The drawing view has no positive width and height; adjust its range")
    return x0, y0, x1, y1


def _project(frame, point):
    origin, right, up = frame["origin_mm"], frame["right"], frame["up"]
    relative = [_finite(point[i], "Datum coordinate") - _finite(origin[i], "View origin") for i in range(3)]
    return [sum(relative[i] * right[i] for i in range(3)),
            sum(relative[i] * up[i] for i in range(3))]


def _clip_line(start, end, bounds):
    """Liang-Barsky clipping, retaining the authored finite datum extent."""
    x0, y0 = start
    dx, dy = end[0] - x0, end[1] - y0
    lower, upper = 0.0, 1.0
    for p, q in ((-dx, x0 - bounds[0]), (dx, bounds[2] - x0),
                 (-dy, y0 - bounds[1]), (dy, bounds[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
        else:
            value = q / p
            if p < 0:
                lower = max(lower, value)
            else:
                upper = min(upper, value)
            if lower > upper:
                return None
    return [[x0 + lower * dx, y0 + lower * dy], [x0 + upper * dx, y0 + upper * dy]]


def _dimension_label(value):
    return f"{value:,.0f}" if math.isclose(value, round(value), abs_tol=1e-6) else f"{value:,.2f}".rstrip("0").rstrip(".")


def _dimensions(parts, bounds, transform, left_offset):
    x0, y0, x1, y1 = bounds
    left, bottom = transform((x0, y0))
    right, top = transform((x1, y1))
    horizontal_y, vertical_x = bottom + 10.0, left - left_offset
    for x in (left, right):
        parts.append(_line(x, bottom + 1.4, x, horizontal_y + 2, .13, MUTED))
        parts.append(_line(x - .9, horizontal_y + .9, x + .9, horizontal_y - .9, .25))
    parts.append(_line(left, horizontal_y, right, horizontal_y, .16))
    parts.append(_text((left + right) / 2, horizontal_y - 1.5, _dimension_label(x1 - x0), 2.6, anchor="middle"))
    for y in (top, bottom):
        parts.append(_line(vertical_x - 2, y, left - 1.4, y, .13, MUTED))
        parts.append(_line(vertical_x - .9, y + .9, vertical_x + .9, y - .9, .25))
    parts.append(_line(vertical_x, top, vertical_x, bottom, .16))
    parts.append(_text(vertical_x - 1.5, (top + bottom) / 2, _dimension_label(y1 - y0), 2.6,
                       anchor="middle", rotation=-90))
    return [{"axis": "view_x", "value_mm": x1 - x0, "definition": "projected geometry bounding-box extent",
             "paper_endpoints_mm": [[left, horizontal_y], [right, horizontal_y]]},
            {"axis": "view_y", "value_mm": y1 - y0, "definition": "projected geometry bounding-box extent",
             "paper_endpoints_mm": [[vertical_x, top], [vertical_x, bottom]]}]


def _grid_datums(parts, view, bounds, transform, scale):
    annotations = []
    frame = view["geometry"].get("frame")
    if not frame:
        return annotations
    clip = [bounds[0] - 3 * scale, bounds[1] - 3 * scale,
            bounds[2] + 3 * scale, bounds[3] + 3 * scale]
    for grid in sorted(view.get("grids", []), key=lambda item: (str(item.get("label", "")), str(item.get("id", "")))):
        half = _finite(grid["length_mm"], "Grid length") / 2
        position, elevation = _finite(grid["position_mm"], "Grid position"), _finite(grid["elevation_mm"], "Grid elevation")
        if grid["axis"] == "X":
            a, b = [-half, position, elevation], [half, position, elevation]
        else:
            a, b = [position, -half, elevation], [position, half, elevation]
        clipped = _clip_line(_project(frame, a), _project(frame, b), clip)
        if clipped is None:
            continue
        first, last = transform(clipped[0]), transform(clipped[1])
        parts.append(_line(*first, *last, .13, "#738692", "4 1.2 .7 1.2"))
        # A single bubble at the top/left clipped end keeps tag columns clear.
        center = min((first, last), key=lambda point: (point[1], point[0]))
        label = _label(grid.get("label") or grid.get("name") or "?")
        parts.append(f'<circle cx="{_number(center[0])}" cy="{_number(center[1])}" r="2.5" fill="white" stroke="{MUTED}" stroke-width=".18"/>')
        parts.append(_text(center[0], center[1] + .8, label, 2.3, anchor="middle", max_width=4.1,
                           minimum=2.2, source_id=grid.get("id")))
        annotations.append({"kind": "grid", "source_id": grid.get("id"), "text": label,
                            "paper_line_mm": [list(first), list(last)], "clipped_to_view": True})
    return annotations


def _level_datums(parts, view, bounds, transform, scale):
    annotations = []
    frame = view["geometry"].get("frame")
    if not frame:
        return annotations
    x_left = transform((bounds[0], bounds[1]))[0]
    for level in sorted(view.get("levels", []), key=lambda item: (item["elevation_mm"], str(item.get("id", "")))):
        elevation = _finite(level["elevation_mm"], "Level elevation")
        projected = _project(frame, [frame["origin_mm"][0], frame["origin_mm"][1], elevation])
        if projected[1] < bounds[1] - 1e-6 or projected[1] > bounds[3] + 1e-6:
            continue
        y = transform((bounds[0], projected[1]))[1]
        x = x_left - 3.5
        parts.append(_line(x - 16, y, x_left + 2, y, .13, MUTED, "2 1"))
        parts.append(f'<path d="M{_number(x)} {_number(y)} l-2 -2 h4 Z" fill="{NAVY}"/>')
        text = f"{_label(level.get('name', 'Level'))} {elevation / 1000:+.3f}"
        parts.append(_text(x - 1, y - 2.8, text, 2.3, anchor="end", max_width=18.0,
                           minimum=2.2, source_id=level.get("id")))
        annotations.append({"kind": "level", "source_id": level.get("id"), "name": level.get("name"),
                            "elevation_mm": elevation, "text": text, "paper_anchor_mm": [x, y]})
    return annotations


def _tags(parts, view, transform, plot, cell):
    sources = [item for item in view["geometry"].get("sources", []) if item.get("taggable")]
    tags = []
    if not sources:
        return tags
    sources.sort(key=lambda item: (transform(item["anchor_mm"])[1], str(item["id"])))
    top, bottom = plot[1], plot[1] + plot[3]
    spacing = 4.1
    if (len(sources) - 1) * spacing > bottom - top:
        raise FoundationError(f"View '{view['name']}' has too many visible tags for this sheet. Hide tags or split the view across sheets.")
    desired = [transform(item["anchor_mm"])[1] for item in sources]
    positions = []
    for i, y in enumerate(desired):
        positions.append(max(top, y, positions[-1] + spacing if i else top))
    if positions[-1] > bottom:
        # Compress only the crowded lower rows. Shifting every tag upward
        # would push an otherwise valid tag at the top outside the plot.
        positions[-1] = bottom
        for i in range(len(positions) - 2, -1, -1):
            positions[i] = min(positions[i], positions[i + 1] - spacing)
    x_text = plot[0] + plot[2] + 5.0
    width = cell[0] + cell[2] - x_text - 1.5
    for source, y in zip(sources, positions):
        anchor = transform(source["anchor_mm"])
        elbow = [x_text - 2.0, y]
        parts.append(_line(*anchor, *elbow, .10, "#82939F"))
        parts.append(_line(*elbow, x_text - .8, y, .10, "#82939F"))
        parts.append(f'<circle cx="{_number(anchor[0])}" cy="{_number(anchor[1])}" r=".45" fill="{MUTED}"/>')
        original = _label(source.get("name") or source.get("category") or "Element")
        display, size, truncated = _fit(original, 2.5, width, 2.25)
        parts.append(_text(x_text, y + .7, display, size, source_id=source["id"]))
        tags.append({"source_id": source["id"], "category": source.get("category"),
                     "source_name": original, "display_text": display, "truncated": truncated,
                     "model_anchor_mm": list(source["anchor_mm"]),
                     "paper_anchor_mm": list(anchor), "paper_text_mm": [x_text, y + .7]})
    return tags


def _scale_bar(parts, x, y, scale):
    target = 40.0 * scale
    magnitude = 10 ** math.floor(math.log10(target))
    length = max(value * magnitude for value in (0.1, 0.2, 0.5, 1, 2, 5) if value * magnitude <= target + 1e-9)
    paper = length / scale
    for index in range(4):
        parts.append(f'<rect x="{_number(x + index * paper / 4)}" y="{_number(y)}" width="{_number(paper / 4)}" height="1.4" fill="{NAVY if index % 2 == 0 else "white"}" stroke="{NAVY}" stroke-width=".12"/>')
    for index, value in ((0, 0.0), (2, length / 2000), (4, length / 1000)):
        text = f"{value:g}" + (" m" if index == 4 else "")
        parts.append(_text(x + index * paper / 4, y + 4.5, text, 2.2, anchor="middle"))
    return {"model_length_mm": length, "paper_length_mm": paper, "scale_denominator": scale}


def _render_view(parts, view, cell, index):
    geometry = view["geometry"]
    bounds = _bounds(geometry)
    scale = _finite(view.get("scale_denominator"), "View scale denominator")
    if not 1 <= scale <= 10000:
        raise FoundationError("Drawing scale denominator must be between 1 and 10000")
    name = _label(view.get("name", "View"))
    kind = str(view.get("view_type", ""))
    plan = kind.lower() == "plan"
    show_levels = bool(view.get("show_levels")) and not plan
    show_tags = bool(view.get("show_tags"))
    show_dimensions = bool(view.get("show_dimensions"))
    left_margin = 28.0 if show_levels else (16.0 if show_dimensions else 8.0)
    right_margin = 36.0 if show_tags else 8.0
    plot = [cell[0] + left_margin, 52.0, cell[2] - left_margin - right_margin, 170.0]
    width, height = (bounds[2] - bounds[0]) / scale, (bounds[3] - bounds[1]) / scale
    if width > plot[2] + 1e-6 or height > plot[3] + 1e-6:
        needed = max((bounds[2] - bounds[0]) / plot[2], (bounds[3] - bounds[1]) / plot[3])
        raise FoundationError(f"View '{name}' does not fit A3 at 1:{scale:g}. Use a single-view sheet or a smaller drawing scale (denominator at least {math.ceil(needed)}). The scale was not changed.")
    origin = [plot[0] + (plot[2] - width) / 2, plot[1] + (plot[3] - height) / 2]
    def transform(point):
        x, y = _finite(point[0], "Projected X"), _finite(point[1], "Projected Y")
        return [origin[0] + (x - bounds[0]) / scale,
                origin[1] + (bounds[3] - y) / scale]
    parts.append(f'<g id="view-{_escape(view["id"])}" data-view-type="{_escape(kind)}" data-scale-denominator="{_number(scale)}">')
    parts.append(_text(cell[0] + 2, 35, f"{index + 1:02d}  {name}", 3.65, NAVY, 700,
                       max_width=cell[2] - 28, minimum=3.0))
    parts.append(_text(cell[0] + cell[2] - 2, 35, f"1:{scale:g}", 3.2, NAVY, 700, anchor="end"))
    types = {"plan": "PLAN / แปลน", "section": "SECTION / รูปตัด", "elevation": "ELEVATION / รูปด้าน"}
    parts.append(_text(cell[0] + 2, 40, types.get(kind.lower(), kind), 2.2, MUTED))
    parts.append(_line(cell[0] + 2, 43, cell[0] + cell[2] - 2, 43, .18, LIGHT))
    # Datums are behind model edges; their display extents are clipped to the view.
    datums = []
    if plan and view.get("show_grid"):
        datums.extend(_grid_datums(parts, view, bounds, transform, scale))
    if show_levels:
        datums.extend(_level_datums(parts, view, bounds, transform, scale))
    # Even-odd fill preserves holes in actual section faces.
    cut_paths = []
    for face in geometry.get("cut_faces", []):
        loops = face.get("loops", [])
        if not loops:
            continue
        data = " ".join(_path(loop, transform, close=True) for loop in loops)
        cut_paths.append((data, face))
        parts.append(f'<path d="{data}" fill="{LIGHT}" fill-rule="evenodd" stroke="none" data-source-id="{_escape(face.get("source_id", ""))}"/>')
    for points in geometry.get("visible_paths", []):
        parts.append(f'<path d="{_path(points, transform)}" fill="none" stroke="{INK}" stroke-width=".18" stroke-linecap="round" stroke-linejoin="round"/>')
    for points in geometry.get("hidden_paths", []):
        parts.append(f'<path d="{_path(points, transform)}" fill="none" stroke="{MUTED}" stroke-width=".12" stroke-dasharray="2 1"/>')
    for points in geometry.get("overhead_paths", []):
        parts.append(f'<path d="{_path(points, transform)}" fill="none" stroke="{MUTED}" stroke-width=".15" stroke-dasharray="3 1.2"/>')
    for data, face in cut_paths:
        parts.append(f'<path d="{data}" fill="none" stroke="{NAVY}" stroke-width=".45" stroke-linejoin="round" data-source-id="{_escape(face.get("source_id", ""))}"/>')
    dimensions = _dimensions(parts, bounds, transform, 24 if show_levels else 9) if show_dimensions else []
    for dimension in dimensions:
        dimension.update(view_id=view["id"], source_ids=[source["id"] for source in geometry.get("sources", [])],
                         measured_bounds_mm=list(bounds))
    tags = _tags(parts, view, transform, plot, cell) if show_tags else []
    bar = _scale_bar(parts, cell[0] + 5, 237, scale)
    parts.append(_text(cell[0] + cell[2] - 3, 240, "Dimensions: mm", 2.2, MUTED, anchor="end"))
    if plan:
        x = cell[0] + cell[2] - 6
        parts.append(_line(x, 48, x, 54, .25, NAVY))
        parts.append(f'<path d="M{_number(x)} 47 l-1.2 2.4 h2.4 Z" fill="{NAVY}"/>')
        parts.append(_text(x - 3, 50, "+Y", 2.2, MUTED, anchor="end"))
    parts.append("</g>")
    return {"view_id": view["id"], "name": name, "view_type": kind,
            "scale_denominator": scale, "cell_mm": cell, "plot_mm": plot,
            "geometry_bounds_mm": list(bounds), "geometry_paper_bounds_mm": [origin[0], origin[1], origin[0] + width, origin[1] + height],
            "dimensions": dimensions, "tags": tags, "datums": datums, "scale_bar": bar,
            "visible_paths": len(geometry.get("visible_paths", [])),
            "cut_faces": len(cut_paths), "overhead_paths": len(geometry.get("overhead_paths", [])),
            "exclusions": geometry.get("exclusions", [])}


def render_sheet(captured):
    """Return a complete SVG, exact paper layout and annotation provenance."""
    if not isinstance(captured, dict) or captured.get("schema") != 1:
        raise FoundationError("Unsupported drawing capture schema")
    sheet = captured.get("sheet", {})
    if sheet.get("paper", "A3") != "A3" or sheet.get("orientation", "Landscape") != "Landscape":
        raise FoundationError("This drawing release supports A3 landscape sheets")
    views = captured.get("views", [])
    if not 1 <= len(views) <= 2:
        raise FoundationError("Place one or two views on each A3 sheet")
    for key in ("model_revision", "drawing_revision"):
        value = captured.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise FoundationError("Drawing capture has no valid model/drawing content revision")
    regular, bold, license_text, font_record = _font_assets()
    ensure_fonts()
    metadata = {"schema": 1, "render_rule": RENDER_RULE, "model_revision": captured["model_revision"],
                "drawing_revision": captured["drawing_revision"], "sheet_id": sheet.get("id"),
                "units": "native model mm; paper mm", "font_license": license_text,
                "font_sources": font_record}
    # Embedded web fonts keep standalone SVGs readable outside FreeCAD. The
    # host Qt renderer uses the same fonts registered with QFontDatabase.
    style = ("@font-face{font-family:Sarabun;font-style:normal;font-weight:400;src:url(data:font/ttf;base64," + base64.b64encode(regular).decode("ascii") + ")}"
             "@font-face{font-family:Sarabun;font-style:normal;font-weight:700;src:url(data:font/ttf;base64," + base64.b64encode(bold).decode("ascii") + ")}"
             "text{font-family:Sarabun,sans-serif}")
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297" font-family="Sarabun" font-size="2.6">',
             '<title>' + _escape(sheet.get("number", "") + " " + sheet.get("name", "Drawing sheet")) + '</title>',
             '<desc>Native FreeCAD model-derived vector drawing. Print at 100 percent on A3 for the stated scales.</desc>',
             '<metadata id="3117-provenance">' + _escape(json.dumps(metadata, ensure_ascii=False, sort_keys=True)) + '</metadata>',
             '<defs><style type="text/css">' + style + '</style></defs>',
             '<rect x="0" y="0" width="420" height="297" fill="white"/>',
             f'<rect x="10" y="10" width="400" height="277" fill="none" stroke="{NAVY}" stroke-width=".35"/>',
             f'<rect x="10" y="10" width="2" height="12" fill="{ORANGE}"/>',
             _text(16, 19, "3117  BIM STUDIO", 4.2, NAVY, 700),
             _text(406, 18.5, "DRAWINGS / แบบจากโมเดล", 3.2, NAVY, 700, anchor="end"),
             _line(10, 25, 410, 25, .3, NAVY)]
    cells = [[12, 28, 396, 220]] if len(views) == 1 else [[12, 28, 196, 220], [212, 28, 196, 220]]
    if len(views) == 2:
        parts.append(_line(210, 30, 210, 246, .15, LIGHT))
    layout_views = [_render_view(parts, view, cell, index) for index, (view, cell) in enumerate(zip(views, cells))]
    parts.extend([_line(10, 252, 410, 252, .35, NAVY),
                  _line(210, 252, 210, 287, .25, NAVY),
                  _line(320, 252, 320, 287, .25, NAVY)])
    project = captured.get("project", {})
    parts.append(_text(14, 258.5, "PROJECT / โครงการ", 2.0, MUTED, 700))
    parts.append(_text(14, 266, project.get("name", "Project"), 4.0, NAVY, 700, max_width=192, minimum=3.0))
    parts.append(_text(14, 273, sheet.get("name", "Drawing sheet"), 3.4, NAVY, max_width=192, minimum=2.7))
    parts.append(_text(14, 280, "Author / ผู้จัดทำ: " + _label(sheet.get("author") or project.get("author") or "-"), 2.3, max_width=192))
    parts.append(_text(14, 284.5, "A3 landscape | Print 100% | Model-derived snapshot", 2.0, MUTED))
    parts.append(_text(214, 258.5, "SOURCE / ที่มา", 2.0, MUTED, 700))
    parts.append(_text(214, 265, "Model  " + captured["model_revision"][:16], 2.5, NAVY))
    parts.append(_text(214, 271, "Drawing  " + captured["drawing_revision"][:16], 2.5, NAVY))
    parts.append(_text(214, 278, "Issue / ฉบับ: " + _label(sheet.get("issue") or "-"), 2.5, max_width=101))
    parts.append(_text(214, 284.5, "Full source IDs and hashes in export metadata", 2.0, MUTED, max_width=101))
    parts.append(_text(324, 258.5, "SHEET / เลขที่แบบ", 2.0, MUTED, 700))
    parts.append(_text(324, 270, sheet.get("number", "-"), 7.0, NAVY, 700, max_width=82, minimum=4.0))
    scales = " / ".join("1:" + _number(view["scale_denominator"]) for view in views)
    parts.append(_text(324, 278, "Scale  " + scales + " @ A3", 2.8, max_width=82))
    parts.append(_text(324, 284.5, "Units: mm unless explicitly marked m", 2.0, MUTED, max_width=82))
    parts.append('</svg>')
    layout = {"paper_mm": list(PAPER_MM), "orientation": "Landscape", "views": layout_views,
              "render_rule": RENDER_RULE, "font_family": FONT_FAMILY,
              "annotation_policy": "Overall dimensions follow projected geometry bounds; tags follow visible source labels/UUIDs; datum extents are view-clipped."}
    validation = {"status": "passed", "paper": "A3", "orientation": "Landscape", "units": "mm",
                  "view_count": len(views), "explicit_scales_preserved": True, "no_fit_rescaling": True,
                  "model_revision": captured["model_revision"], "drawing_revision": captured["drawing_revision"],
                  "visible_path_count": sum(view["visible_paths"] for view in layout_views),
                  "cut_face_count": sum(view["cut_faces"] for view in layout_views),
                  "dimension_count": sum(len(view["dimensions"]) for view in layout_views),
                  "tag_count": sum(len(view["tags"]) for view in layout_views),
                  "datum_count": sum(len(view["datums"]) for view in layout_views),
                  "truncated_tag_count": sum(tag["truncated"] for view in layout_views for tag in view["tags"]),
                  "full_source_names_retained_in_metadata": True}
    return {"svg": "\n".join(parts) + "\n", "validation": validation, "layout": layout}
