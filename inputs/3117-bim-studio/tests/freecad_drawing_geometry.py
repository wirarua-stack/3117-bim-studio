# SPDX-License-Identifier: GPL-3.0-or-later
"""Native OCCT/TechDraw projection checks with independent numeric fixtures.

These transient Part solids exercise drawing geometry only; they do not create
an alternate editable model or mutate a user's FreeCAD document.
"""
import json
import math
from pathlib import Path
import platform
import sys
import traceback
from types import SimpleNamespace

import FreeCAD as App
import Part

from bim3117_freecad import drawing_geometry as geometry
from bim3117_freecad.model import FoundationError


def _source(name, category, shape):
    values = dict(BIM3117Id=name, Label=name, BIM3117Kind=category)
    if category == "Wall":
        values["Body"] = SimpleNamespace(Shape=shape)
    else:
        values["Shape"] = shape
    return SimpleNamespace(**values)


def _project(*sources):
    return SimpleNamespace(Group=list(sources))


def _plan(cut=1200, bottom=-150, top=2800):
    return {"view_type": "Plan", "origin_mm": [0, 0, 0], "level_elevation_mm": 0,
            "bottom_offset_mm": bottom, "cut_offset_mm": cut, "top_offset_mm": top}


def _vertical(view_type="Section", y=100, depth=1000):
    return {"view_type": view_type, "origin_mm": [0, y, 0],
            "direction": [0, 1, 0], "depth_mm": depth}


def _inside(point, loop):
    x, y = point
    inside = False
    for a, b in zip(loop, loop[1:]):
        if ((a[1] > y) != (b[1] > y)
                and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]):
            inside = not inside
    return inside


def _filled(point, faces):
    return any(sum(_inside(point, loop) for loop in face["loops"]) % 2 == 1 for face in faces)


def _loop_area(loop):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:]))) / 2


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Transient native OCCT cuts, global TechDraw HLR and source visibility"}

    def check(name, condition, **observations):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed", **observations})

    def rejected(name, callback):
        try:
            callback()
        except FoundationError:
            check(name, True)
            return
        raise AssertionError(name)

    def near(a, b):
        return math.isclose(a, b, rel_tol=1e-8, abs_tol=0.002)

    try:
        documents_before = tuple(App.listDocuments())
        check("Plan frame is world XY without double inversion",
              geometry.project_point(_plan(), [6000, 4000, 9000]) == [6000, 4000])
        check("Front frame is world X right and Z up",
              geometry.project_point(_vertical(), [1500, 900, 2400]) == [1500, 2400])
        reverse = {**_vertical(), "direction": [0, -1, 0]}
        check("Rear cardinal view reverses horizontal direction explicitly",
              geometry.project_point(reverse, [1500, 900, 2400]) == [-1500, 2400])
        rejected("Diagonal vertical directions are explicitly unsupported", lambda:
                 geometry.frame_for_definition({**_vertical(), "direction": [1, 1, 0]}))
        rejected("Invalid plan range rejected before OCCT", lambda:
                 geometry.frame_for_definition(_plan(cut=1200, bottom=1300)))
        rejected("Sub-tolerance plan range rejected before OCCT", lambda:
                 geometry.frame_for_definition(_plan(cut=1200, top=1200.00000001)))

        wall = Part.makeBox(6000, 200, 3000).cut(
            Part.makeBox(1200, 400, 1200, App.Vector(2000, -100, 900)))
        native_before = wall.exportBrepToString()
        project = _project(_source("wall-with-window", "Wall", wall))
        section = geometry.build_view_geometry(project, _vertical())
        check("Section preserves a native window hole as two evenodd loops",
              len(section["cut_faces"]) == 1 and len(section["cut_faces"][0]["loops"]) == 2)
        face = section["cut_faces"][0]
        areas = sorted(_loop_area(loop) for loop in face["loops"])
        check("Independent section area equals gross wall minus real opening",
              near(face["area_mm2"], 6000 * 3000 - 1200 * 1200)
              and near(areas[-1] - areas[0], 6000 * 3000 - 1200 * 1200))
        check("Cut fill leaves the actual window interior empty",
              not _filled((2600, 1500), section["cut_faces"]))
        check("Positive cut material is present beside the window",
              _filled((1000, 1500), section["cut_faces"]))
        plan = geometry.build_view_geometry(project, _plan())
        check("Plan cut through window gives two wall pieces",
              len(plan["cut_faces"]) == 2
              and near(sum(f["area_mm2"] for f in plan["cut_faces"]), (6000 - 1200) * 200))
        above = geometry.build_view_geometry(project, _plan(cut=2500, top=2800))
        check("Raising plan cut above window restores continuous wall material",
              len(above["cut_faces"]) == 1 and near(above["cut_faces"][0]["area_mm2"], 6000 * 200))

        beam = Part.makeBox(4000, 300, 450, App.Vector(-2000, -150, 550))
        beam.rotate(App.Vector(), App.Vector(0, 0, 1), 30)
        rotated = geometry.build_view_geometry(_project(_source("rotated-beam", "Beam", beam)),
                                               _plan(cut=900))
        check("Rotated rectangular member keeps exact native cut area",
              near(sum(f["area_mm2"] for f in rotated["cut_faces"]), 4000 * 300))
        expected_x = 4000 * math.cos(math.pi / 6) + 300 * math.sin(math.pi / 6)
        check("Rotated projection width agrees with independent trigonometry",
              near(rotated["bounds_mm"][2] - rotated["bounds_mm"][0], expected_x))

        # The drawing layer must use the joined native remainder, not rebuild
        # a gross member from its dimensions. This side notch leaves one solid.
        joined_column = Part.makeBox(300, 300, 3000).cut(
            Part.makeBox(150, 500, 200, App.Vector(0, -100, 2500)))
        joined = geometry.build_view_geometry(
            _project(_source("joined-column", "Column", joined_column)), _vertical(y=150))
        check("Joined member section area retains the native slab deduction",
              len(joined_column.Solids) == 1 and len(joined["cut_faces"]) == 1
              and near(joined["cut_faces"][0]["area_mm2"], 300 * 3000 - 150 * 200))
        check("Joined member cut fill leaves deducted material empty",
              not _filled((75, 2600), joined["cut_faces"])
              and _filled((225, 2600), joined["cut_faces"]))

        overhead = _source("overhead-beam", "Beam", Part.makeBox(6000, 300, 300, App.Vector(0, -500, 2500)))
        too_high = _source("above-top", "Beam", Part.makeBox(6000, 300, 300, App.Vector(0, -900, 2700)))
        touching_top = _source("touch-top", "Beam", Part.makeBox(6000, 300, 300, App.Vector(0, -1300, 2600)))
        below = _source("below-bottom", "Slab", Part.makeBox(6000, 300, 100, App.Vector(0, -1700, -400)))
        ranged = geometry.build_view_geometry(_project(project.Group[0], overhead, too_high, touching_top, below),
                                              _plan(top=2600))
        check("Overhead beam inside Top range produces dashed-layer lines", bool(ranged["overhead_paths"]))
        check("A wall crossing Cut is not duplicated in the overhead layer",
              not next(s for s in ranged["sources"] if s["id"] == "wall-with-window")["overhead"])
        check("Top and Bottom range omit wholly outside native products",
              {s["id"] for s in ranged["exclusions"]} == {"above-top", "touch-top", "below-bottom"})
        check("Clipped overhead source preserves its projected native bounds",
              next(s for s in ranged["sources"] if s["id"] == "overhead-beam")["bounds_mm"] == [0, -500, 6000, -200])

        front = _source("front", "Column", Part.makeBox(100, 100, 200))
        back = _source("back", "Column", Part.makeBox(100, 100, 200, App.Vector(0, 400, 0)))
        elevation = geometry.build_view_geometry(_project(front, back), _vertical("Elevation", y=-100))
        flags = {s["id"]: s for s in elevation["sources"]}
        check("Global HLR suppresses duplicate coincident front/back outlines",
              len(elevation["visible_paths"]) == 4)
        check("Native first-hit source is taggable", flags["front"]["visible"] and flags["front"]["taggable"])
        check("Fully occluded source with identical projected bounds is not tagged",
              not flags["back"]["visible"] and not flags["back"]["taggable"])
        check("Elevation does not invent section hatching", not elevation["cut_faces"])
        shallow = geometry.build_view_geometry(_project(front, back), _vertical("Elevation", y=-100, depth=150))
        check("Finite elevation depth excludes a farther object",
              {s["id"] for s in shallow["exclusions"]} == {"back"})
        through = geometry.build_view_geometry(_project(front), _vertical("Section", y=50))
        check("Section plane adds the genuine first-face cut", len(through["cut_faces"]) == 1
              and near(through["cut_faces"][0]["area_mm2"], 100 * 200))
        rejected("An empty positive-depth view reports no intersecting geometry", lambda:
                 geometry.build_view_geometry(_project(front), _vertical("Elevation", y=300)))
        rejected("Unsupported native curved edges are not silently tessellated", lambda:
                 geometry.build_view_geometry(_project(_source("curve", "Column", Part.makeCylinder(100, 3000))), _plan()))

        check("Repeat projection has deterministic detached values",
              geometry.build_view_geometry(project, _vertical()) == section)
        check("Transient cuts leave the original native BRep byte-identical",
              wall.exportBrepToString() == native_before)
        check("Geometry projection creates no FreeCAD documents", tuple(App.listDocuments()) == documents_before)
        report.update(status="passed", checks_passed=len(report["checks"]), geometry_module=geometry.__file__)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(),
                      checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "drawing-geometry-test-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
