# SPDX-License-Identifier: GPL-3.0-or-later
"""Review the v0.3.0 two-storey native fixture in an actual Bonsai application.

Run with Blender --python, putting this harness's arguments after --. Bonsai
must already be enabled in a disposable profile. This harness clears the scene;
never run it in an unsaved authoring session. No software is installed here.

This is fixture acceptance, not a general IFC validator. Expected volumes come
from the passing native fixture's independent numeric assertions. Measurements
and ray casts use the real imported Blender meshes. Bonsai uses IfcOpenShell,
so this is cross-application evidence, not proof of another IFC geometry kernel.
A GUI run remains capture_pending until its screenshot is visually reviewed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for option, variable in (("ifc", "BIM3117_REVIEW_IFC"),
                             ("snapshot", "BIM3117_REVIEW_SNAPSHOT"),
                             ("native-report", "BIM3117_REVIEW_NATIVE_REPORT"),
                             ("output", "BIM3117_REVIEW_OUTPUT")):
        parser.add_argument("--" + option, default=os.environ.get(variable))
    parser.add_argument("--gui-hold-seconds", type=float, default=15.0,
                        help="Keep GUI open after capture.ready; zero keeps it open")
    extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(extra)
    for name in ("ifc", "snapshot", "native_report", "output"):
        if not getattr(args, name):
            parser.error("Missing --" + name.replace("_", "-"))
        setattr(args, name, Path(getattr(args, name)).expanduser().resolve())
    for name in ("ifc", "snapshot", "native_report"):
        if not getattr(args, name).is_file():
            parser.error("Input does not exist: " + str(getattr(args, name)))
    if not math.isfinite(args.gui_hold_seconds) or args.gui_hold_seconds < 0:
        parser.error("--gui-hold-seconds must be finite and nonnegative")
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("bonsai-building-report.json", "capture.ready", "Bonsai_Building_Authoring.png"):
        if (args.output / name).exists():
            parser.error("Use a fresh output directory: evidence already exists")
    return args


ARGS = arguments()
import bpy
import bonsai
import bonsai.tool as tool
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.validate
from mathutils import Vector

OUT = ARGS.output
IFC = ARGS.ifc
SNAPSHOT = json.loads(ARGS.snapshot.read_text(encoding="utf-8"))
SOURCE_REPORT = json.loads(ARGS.native_report.read_text(encoding="utf-8"))
CATEGORIES = (("slabs", "Slab", 3), ("columns", "Column", 8), ("beams", "Beam", 8),
              ("walls", "Wall", 8), ("doors", "Door", 2), ("windows", "Window", 4))
report = {
    "status": "running", "blender": bpy.app.version_string,
    "blender_build_hash": bpy.app.build_hash.decode(), "bonsai": bonsai.bbim_semver["version"],
    "ifcopenshell": ifcopenshell.version, "python": sys.version, "platform": platform.platform(),
    "background": bpy.app.background,
    "review_mode": "background_application" if bpy.app.background else "gui_application",
    "visual_review": {"status": "not_run" if bpy.app.background else "capture_pending"},
    "source_ifc": str(IFC), "source_snapshot": str(ARGS.snapshot),
    "source_native_report": str(ARGS.native_report),
    "source_sha256": hashlib.sha256(IFC.read_bytes()).hexdigest(),
    "source_snapshot_sha256": hashlib.sha256(ARGS.snapshot.read_bytes()).hexdigest(),
    "source_native_report_sha256": hashlib.sha256(ARGS.native_report.read_bytes()).hexdigest(),
    "content_revision": SNAPSHOT["content_revision"], "checks": [], "observations": [],
    "mesh_tolerance": "max(2e-6, abs(expected) * 2e-6)",
    "scope": "Actual Bonsai import, Blender meshes and rays, IFC quantities/relations and full EXPRESS. Uses IfcOpenShell; no other-kernel or Windows claim.",
}


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    report["checks"].append({"name": name, "status": "passed"})


def near(actual, expected):
    return abs(float(actual) - float(expected)) <= max(2e-6, abs(float(expected)) * 2e-6)


def guid(identifier):
    return ifcopenshell.guid.compress(identifier.replace("-", ""))


def world_vertices(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def mesh_volume(obj):
    """Stable closed-mesh volume from the imported Blender triangulation."""
    vertices = world_vertices(obj)
    obj.data.calc_loop_triangles()
    origin = tuple(vertices[0])
    points = [tuple(float(vertex[axis]) - origin[axis] for axis in range(3)) for vertex in vertices]
    terms = []
    for triangle in obj.data.loop_triangles:
        a, b, c = (points[index] for index in triangle.vertices)
        terms.append(a[0] * (b[1]*c[2] - b[2]*c[1])
                     - a[1] * (b[0]*c[2] - b[2]*c[0])
                     + a[2] * (b[0]*c[1] - b[1]*c[0]))
    return abs(math.fsum(terms) / 6.0)


def mesh_bounds(obj):
    vertices = world_vertices(obj)
    return [[min(vertex[axis] for vertex in vertices) for axis in range(3)],
            [max(vertex[axis] for vertex in vertices) for axis in range(3)]]


def bounds_match(actual, expected):
    return all(near(actual[side][axis], expected[side][axis])
               for side in range(2) for axis in range(3))


def wall_point(wall, along, across, elevation):
    start = Vector((*wall["start_m"], wall["base_z_m"]))
    ux = (wall["end_m"][0] - wall["start_m"][0]) / wall["length_m"]
    uy = (wall["end_m"][1] - wall["start_m"][1]) / wall["length_m"]
    return start + Vector((ux*along - uy*across, uy*along + ux*across, elevation))


def wall_bounds(wall, opening=None):
    along, z, length, height = 0.0, 0.0, wall["length_m"], wall["height_m"]
    if opening is not None:
        along, z, length, height = (opening[name] for name in
                                   ("offset_m", "sill_m", "width_m", "height_m"))
    points = [wall_point(wall, along+x, y, z+h)
              for x in (0.0, length) for y in (0.0, wall["thickness_m"]) for h in (0.0, height)]
    return [[min(point[axis] for point in points) for axis in range(3)],
            [max(point[axis] for point in points) for axis in range(3)]]


def segment_hits(obj, start, finish):
    inverse = obj.matrix_world.inverted()
    start, finish = inverse @ Vector(start), inverse @ Vector(finish)
    delta = finish - start
    return obj.ray_cast(start, delta.normalized(), distance=delta.length)[0]


def wall_ray(obj, wall, along, elevation):
    return segment_hits(obj, wall_point(wall, along, -0.2, elevation),
                        wall_point(wall, along, wall["thickness_m"]+0.2, elevation))


def member_segment(member, category, z):
    """A transverse fixture probe, independent of exported boolean operands."""
    if category == "Column":
        angle = math.radians(member["rotation_deg"])
        ux, uy = math.cos(angle), math.sin(angle)
        x, y = member["x_m"], member["y_m"]
        half = member["width_m"] / 2 + 0.1
        return ((x-ux*half, y-uy*half, z), (x+ux*half, y+uy*half, z))
    sx, sy = member["start_m"]
    ex, ey = member["end_m"]
    ux, uy = (ex-sx)/member["length_m"], (ey-sy)/member["length_m"]
    x, y = (sx+ex)/2, (sy+ey)/2
    half = member["width_m"] / 2 + 0.1
    return ((x+uy*half, y-ux*half, z), (x-uy*half, y+ux*half, z))


def write_report():
    report["checks_passed"] = len(report["checks"])
    (OUT / "bonsai-building-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def inspect():
    try:
        check("source installed-native building suite passed with matching revision",
              SOURCE_REPORT["status"] == "passed"
              and SOURCE_REPORT["content_revision"] == SNAPSHOT["content_revision"])
        metadata_path = IFC.with_name(IFC.stem + "_ifc_metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        check("IFC completion metadata binds these payload bytes to the native snapshot",
              metadata["content_revision"] == SNAPSHOT["content_revision"]
              and metadata["validation"]["status"] == "passed"
              and any(item["name"] == IFC.name and item["sha256"] == report["source_sha256"]
                      for item in metadata["files"]))
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        status = bpy.ops.bim.load_project(filepath=str(IFC), should_start_fresh_session=False,
                                         skip_recent=True, skip_autosave_recovery=True)
        check("public Bonsai Load IFC Project operator finishes", status == {"FINISHED"})
        model = tool.Ifc.get()
        check("active Bonsai file is IFC4 with all six expected category counts",
              model.schema == "IFC4" and all(len(model.by_type("Ifc"+category)) == count
                                             and len(SNAPSHOT[key]) == count
                                             for key, category, count in CATEGORIES))
        check("storeys types and opening relationships have the expected fixture counts",
              all(len(model.by_type(name)) == count for name, count in
                  (("IfcBuildingStorey", 3), ("IfcWallType", 1), ("IfcOpeningElement", 6),
                   ("IfcRelVoidsElement", 6), ("IfcRelFillsElement", 6))))
        check("Bonsai scene uses metre scale", near(bpy.context.scene.unit_settings.scale_length, 1.0))
        check("all IfcRoot GlobalIds are unique",
              len({entity.GlobalId for entity in model.by_type("IfcRoot")}) == len(model.by_type("IfcRoot")))
        walls = {item["id"]: item for item in SNAPSHOT["walls"]}
        slabs = {item["id"]: item for item in SNAPSHOT["slabs"]}
        objects = {}
        category_totals = {}
        for key, category, count in CATEGORIES:
            measured = []
            for item in SNAPSHOT[key]:
                entity = model.by_guid(guid(item["id"]))
                obj = tool.Ifc.get_object(entity)
                label = category + " " + item["label"]
                check(label + ": maps to a real Blender mesh and expected IFC identity",
                      entity.is_a("Ifc"+category) and obj is not None and obj.type == "MESH"
                      and tool.Ifc.get_entity(obj) == entity and len(obj.data.vertices) > 0)
                objects[item["id"]] = obj
                props = ifcopenshell.util.element.get_psets(entity)
                source = props["BIM3117_Source"]
                level_id = item.get("base_level_id", item.get("level_id"))
                if category in ("Door", "Window"):
                    level_id = walls[item["host_id"]]["base_level_id"]
                container = ifcopenshell.util.element.get_container(entity)
                check(label + ": source UUID revision and storey survive import",
                      source["SourceUUID"] == item["id"]
                      and source["ContentRevision"] == SNAPSHOT["content_revision"]
                      and container.GlobalId == guid(level_id))
                expected = SOURCE_REPORT["expected_net_volumes_m3"][category][item["id"]]
                volume = mesh_volume(obj)
                measured.append(volume)
                bounds = mesh_bounds(obj)
                expected_bounds = (wall_bounds(item) if category == "Wall" else
                                   wall_bounds(walls[item["host_id"]], item) if category in ("Door", "Window")
                                   else item["native_bounds_m"])
                observation = {"category": category, "name": item["label"], "source_uuid": item["id"],
                               "ifc_guid": entity.GlobalId, "blender_object": obj.name,
                               "mesh_volume_m3": volume, "expected_volume_m3": expected,
                               "absolute_error_m3": abs(volume-expected), "world_bounds_m": bounds,
                               "expected_bounds_m": expected_bounds,
                               "vertices": len(obj.data.vertices), "polygons": len(obj.data.polygons)}
                report["observations"].append(observation)
                check(label + ": imported triangle volume matches independent numeric expectation", near(volume, expected))
                check(label + ": actual world bounds match the native geometry", bounds_match(bounds, expected_bounds))
                if category in ("Slab", "Column", "Beam", "Wall"):
                    qto = props["Qto_"+category+"BaseQuantities"]
                    check(label + ": quantity net volume agrees with the imported Blender solid",
                          near(qto["NetVolume"], volume)
                          and near(qto["GrossVolume"], item["quantities"]["gross_volume_m3"]))
                else:
                    check(label + ": frame quantity and dimension meaning survive import",
                          near(source["FrameVolumeM3"], volume)
                          and "Overall wall-cut opening" in source["DimensionMeaning"])
                if category == "Wall":
                    check(label + ": shared WallType and Base/Top Level semantics survive",
                          ifcopenshell.util.element.get_type(entity).GlobalId == guid(item["type_id"])
                          and source["BaseLevelUUID"] == item["base_level_id"]
                          and source["TopLevelUUID"] == item["top_level_id"])
                elif category in ("Slab", "Column", "Beam"):
                    check(label + ": material and declared join identities/deduction survive",
                          source["MaterialDescription"] == item["material"]
                          and source["JoinSlabUUIDs"] == "|".join(item.get("join_slab_ids", []))
                          and near(source["JoinDeductionM3"], item["quantities"]["join_deduction_m3"]))
            category_totals[category] = math.fsum(measured)
        report["category_mesh_totals_m3"] = category_totals
        check("all category totals match the independently tested two-storey fixture",
              all(near(category_totals[category], math.fsum(SOURCE_REPORT["expected_net_volumes_m3"][category].values()))
                  for _, category, _ in CATEGORIES))
        for key, category in (("columns", "Column"), ("beams", "Beam")):
            for member in SNAPSHOT[key]:
                obj = objects[member["id"]]
                for slab_id in member["join_slab_ids"]:
                    slab = slabs[slab_id]
                    cut_z = (slab["base_z_m"] + slab["top_z_m"]) / 2
                    segment = member_segment(member, category, cut_z)
                    # The ray segment is inside the slab footprint, so test slab
                    # occupancy with a vertical ray crossing the slab's surfaces.
                    a, b = segment
                    x, y = (a[0]+b[0])/2, (a[1]+b[1])/2
                    slab_hit = segment_hits(objects[slab_id], (x, y, slab["base_z_m"]-0.1),
                                            (x, y, slab["top_z_m"]+0.1))
                    remaining_z = (member["native_bounds_m"][0][2] + member["native_bounds_m"][1][2]) / 2
                    check(category + " " + member["label"] + ": imported slab occupies the removed member zone",
                          slab_hit and not segment_hits(obj, *segment))
                    check(category + " " + member["label"] + ": positive member material remains below the join",
                          segment_hits(obj, *member_segment(member, category, remaining_z)))
        for key, category in (("doors", "Door"), ("windows", "Window")):
            for item in SNAPSHOT[key]:
                wall = walls[item["host_id"]]
                host = model.by_guid(guid(wall["id"]))
                host_obj = objects[wall["id"]]
                entity = model.by_guid(guid(item["id"]))
                obj = objects[item["id"]]
                label = category + " " + item["label"]
                opening = entity.FillsVoids[0].RelatingOpeningElement
                source = ifcopenshell.util.element.get_psets(entity)["BIM3117_Source"]
                check(label + ": fill and void relationships identify its native Wall host",
                      len(entity.FillsVoids) == 1 and len(opening.VoidsElements) == 1
                      and opening.VoidsElements[0].RelatingBuildingElement == host
                      and source["HostWallUUID"] == wall["id"])
                centre = item["offset_m"] + item["width_m"]/2
                middle_z = item["sill_m"] + item["height_m"]/2
                strip = min(.05, item["width_m"]/4, item["height_m"]/4)
                check(label + ": real wall opening and frame centre are empty",
                      not wall_ray(host_obj, wall, centre, middle_z)
                      and not wall_ray(obj, wall, centre, middle_z))
                check(label + ": wall beside the opening and above its head remains solid",
                      wall_ray(host_obj, wall, item["offset_m"]-.1, middle_z)
                      and wall_ray(host_obj, wall, centre, item["sill_m"]+item["height_m"]+.05))
                check(label + ": imported generic frame contains both jamb and head material",
                      wall_ray(obj, wall, item["offset_m"]+strip/2, middle_z)
                      and wall_ray(obj, wall, centre, item["sill_m"]+item["height_m"]-strip/2))
                lower_hit = wall_ray(obj, wall, centre, item["sill_m"]+strip/2)
                check(label + (": window bottom frame bar is solid" if category == "Window" else ": door has no bottom bar"),
                      lower_hit if category == "Window" else not lower_hit)
        check("Bonsai contains exactly 33 authored mesh products with no derived WallBody duplication",
              len([obj for obj in bpy.data.objects if obj.type == "MESH" and tool.Ifc.get_entity(obj) is not None]) == 33)
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(model, logger, express_rules=True)
        report["express_validation"] = {"statements": logger.statements, "count": len(logger.statements)}
        check("full schema and EXPRESS validation in the Bonsai runtime reports zero findings", not logger.statements)
        check("Bonsai import leaves the exact IFC payload bytes unchanged",
              hashlib.sha256(IFC.read_bytes()).hexdigest() == report["source_sha256"])
        report["status"] = "passed"
        if bpy.app.background:
            write_report()
        else:
            style_review(objects)
            bpy.app.timers.register(finish_gui, first_interval=2.0)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        write_report()
        if bpy.app.background:
            raise
        bpy.app.timers.register(quit_app, first_interval=.2)
    return None


def style_review(objects):
    """Display colors/camera only; source bytes and imported mesh data unchanged."""
    colors = {"Slab": (.64, .70, .77, 1), "Column": (.34, .45, .58, 1),
              "Beam": (.40, .52, .65, 1), "Wall": (.80, .77, .69, 1),
              "Door": (.83, .37, .10, 1), "Window": (.07, .48, .58, 1)}
    bpy.ops.object.select_all(action="DESELECT")
    for key, category, _ in CATEGORIES:
        for item in SNAPSHOT[key]:
            objects[item["id"]].color = colors[category]
    # Selecting a window exposes an authored product in Bonsai's properties.
    target = objects[SNAPSHOT["windows"][0]["id"]]
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "SOLID"
            space.shading.color_type = "OBJECT"
            space.shading.show_shadows = True
            space.shading.show_cavity = True
            space.overlay.show_floor = False
            space.overlay.show_axis_x = False
            space.overlay.show_axis_y = False
            space.region_3d.view_perspective = "ORTHO"
            space.region_3d.view_location = Vector((3.0, 2.0, 2.7))
            space.region_3d.view_distance = 16.8
            space.region_3d.view_rotation = Vector((12, -18, 12)).to_track_quat("Z", "Y")
            space.show_region_ui = False
        elif area.type == "PROPERTIES":
            area.spaces.active.context = "SCENE"
        area.tag_redraw()
    report["display"] = {"changes": "Object viewport colors, camera, overlays and selected window only",
                         "geometry_modified": False, "view": "Two-storey southeast axonometric"}


def quit_app():
    bpy.ops.wm.quit_blender()
    return None


def finish_gui():
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
        report["status"] = "geometry_passed_capture_pending"
        report["screenshot"] = str(OUT / "Bonsai_Building_Authoring.png")
        write_report()
        (OUT / "capture.ready").write_text("ready", encoding="utf-8")
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        write_report()
    if ARGS.gui_hold_seconds:
        bpy.app.timers.register(quit_app, first_interval=ARGS.gui_hold_seconds)
    return None


if bpy.app.background:
    inspect()
else:
    bpy.app.timers.register(inspect, first_interval=1.0)
