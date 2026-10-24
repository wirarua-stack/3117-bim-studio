# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual Bonsai import of the v0.5.0 typed two-storey fixture.

Run in Blender with an already enabled Bonsai add-on and a disposable profile.
The scene is cleared. Baseline native numeric expectations come from the frozen
v0.3.0 fixture; the new catalogue may not alter any of its 33 product solids.
This is application/mesh evidence using IfcOpenShell, not a second-kernel or
Windows claim. Background mode performs no visual review.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ifc", "snapshot", "native-report", "baseline-snapshot", "baseline-native-report", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--gui-hold-seconds", type=float, default=15.0)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not math.isfinite(args.gui_hold_seconds) or args.gui_hold_seconds < 0:
        parser.error("--gui-hold-seconds must be finite and nonnegative")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "bonsai-types-report.json").exists():
        parser.error("Choose a fresh evidence directory")
    return args


ARGS = arguments()
import bpy
import bonsai
import bonsai.tool as tool
import ifcopenshell
import ifcopenshell.util.element as element
import ifcopenshell.validate
from mathutils import Vector

SNAPSHOT = json.loads(ARGS.snapshot.read_text(encoding="utf-8"))
SOURCE = json.loads(ARGS.native_report.read_text(encoding="utf-8"))
BASELINE = json.loads(ARGS.baseline_snapshot.read_text(encoding="utf-8"))
BASELINE_REPORT = json.loads(ARGS.baseline_native_report.read_text(encoding="utf-8"))
CATEGORIES = (("walls", "Wall", 8), ("slabs", "Slab", 3), ("columns", "Column", 8),
              ("beams", "Beam", 8), ("doors", "Door", 2), ("windows", "Window", 4))
report = {"status": "running", "blender": bpy.app.version_string,
          "blender_build_hash": bpy.app.build_hash.decode(), "bonsai": bonsai.bbim_semver["version"],
          "ifcopenshell": ifcopenshell.version, "python": sys.version, "platform": platform.platform(),
          "background": bpy.app.background, "visual_review": {"status": "not_run"},
          "content_revision": SNAPSHOT["content_revision"], "checks": [], "observations": [],
          "sources": {name: {"path": str(getattr(ARGS, name)), "sha256": hashlib.sha256(getattr(ARGS, name).read_bytes()).hexdigest()}
                      for name in ("ifc", "snapshot", "native_report", "baseline_snapshot", "baseline_native_report")},
          "scope": "Actual Bonsai import and Blender meshes; six typed product categories, native materials and layer usages, conserved quantities, unchanged legacy fixture geometry. Uses IfcOpenShell, not another IFC kernel. GUI review is separate from numeric checks; no Windows claim."}


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    report["checks"].append({"name": name, "status": "passed"})


def near(actual, expected):
    return math.isclose(float(actual), float(expected), rel_tol=2e-6, abs_tol=2e-6)


def guid(identifier):
    return ifcopenshell.guid.compress(identifier.replace("-", ""))


def world_vertices(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def mesh_volume(obj):
    vertices = world_vertices(obj)
    obj.data.calc_loop_triangles()
    origin = vertices[0]
    points = [tuple(float(vertex[i]) - float(origin[i]) for i in range(3)) for vertex in vertices]
    terms = []
    for triangle in obj.data.loop_triangles:
        a, b, c = (points[index] for index in triangle.vertices)
        terms.append(a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0]))
    return abs(math.fsum(terms) / 6.0)


def mesh_bounds(obj):
    vertices = world_vertices(obj)
    return [[min(vertex[axis] for vertex in vertices) for axis in range(3)],
            [max(vertex[axis] for vertex in vertices) for axis in range(3)]]


def wall_point(wall, along, across, elevation):
    sx, sy = wall["start_m"]
    ex, ey = wall["end_m"]
    ux, uy = (ex-sx)/wall["length_m"], (ey-sy)/wall["length_m"]
    return (sx+ux*along-uy*across, sy+uy*along+ux*across, wall["base_z_m"]+elevation)


def wall_bounds(wall, opening=None):
    along, z, length, height = 0.0, 0.0, wall["length_m"], wall["height_m"]
    if opening is not None:
        along, z, length, height = (opening[name] for name in ("offset_m", "sill_m", "width_m", "height_m"))
    points = [wall_point(wall, along+x, y, z+h) for x in (0.0, length)
              for y in (0.0, wall["thickness_m"]) for h in (0.0, height)]
    return [[min(point[axis] for point in points) for axis in range(3)],
            [max(point[axis] for point in points) for axis in range(3)]]


def segment_hits(obj, start, end):
    inverse = obj.matrix_world.inverted()
    start, end = inverse @ Vector(start), inverse @ Vector(end)
    delta = end-start
    return obj.ray_cast(start, delta.normalized(), distance=delta.length)[0]


def wall_ray(obj, wall, along, elevation):
    return segment_hits(obj, wall_point(wall, along, -.2, elevation),
                        wall_point(wall, along, wall["thickness_m"]+.2, elevation))


def member_segment(member, category, z):
    if category == "Column":
        angle = math.radians(member["rotation_deg"])
        ux, uy = math.cos(angle), math.sin(angle)
        x, y, half = member["x_m"], member["y_m"], member["width_m"]/2+.1
        return (x-ux*half, y-uy*half, z), (x+ux*half, y+uy*half, z)
    sx, sy = member["start_m"]
    ex, ey = member["end_m"]
    ux, uy, half = (ex-sx)/member["length_m"], (ey-sy)/member["length_m"], member["width_m"]/2+.1
    x, y = (sx+ex)/2, (sy+ey)/2
    return (x+uy*half, y-ux*half, z), (x-uy*half, y+ux*half, z)


def prepare_gui(objects):
    """Presentation only: preserve imported mesh data and source IFC bytes."""
    colors = {"Slab": (.64, .70, .77, 1), "Column": (.34, .45, .58, 1),
              "Beam": (.40, .52, .65, 1), "Wall": (.80, .77, .69, 1),
              "Door": (.83, .37, .10, 1), "Window": (.07, .48, .58, 1)}
    bpy.ops.object.select_all(action="DESELECT")
    for key, category, _ in CATEGORIES:
        for item in SNAPSHOT[key]:
            objects[item["id"]].color = colors[category]
    active = objects[SNAPSHOT["windows"][0]["id"]]
    active.select_set(True)
    bpy.context.view_layer.objects.active = active
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
    report["display"] = {"changes": "Viewport object colors, camera, overlays and selected window only",
                         "geometry_modified": False, "view": "Two-storey southeast axonometric"}


def quit_app():
    bpy.ops.wm.quit_blender()


def ready_for_capture():
    try:
        # Bonsai may finish switching workspaces after Load IFC returns. Apply
        # presentation to the final active workspace immediately before capture.
        prepare_gui(objects)
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
        report["checks_passed"] = len(report["checks"])
        (ARGS.output / "bonsai-types-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (ARGS.output / "capture.ready").write_text("ready", encoding="utf-8")
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        (ARGS.output / "bonsai-types-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if ARGS.gui_hold_seconds:
        bpy.app.timers.register(quit_app, first_interval=ARGS.gui_hold_seconds)


try:
    check("typed native fixture and baseline independent expectations passed",
          SOURCE["status"] == BASELINE_REPORT["status"] == "passed"
          and SOURCE["content_revision"] == SNAPSHOT["content_revision"]
          and BASELINE_REPORT["content_revision"] == BASELINE["content_revision"])
    metadata = json.loads(ARGS.ifc.with_name(ARGS.ifc.stem + "_ifc_metadata.json").read_text(encoding="utf-8"))
    check("IFC completion metadata binds exact payload to the current native revision",
          metadata["content_revision"] == SNAPSHOT["content_revision"] and metadata["validation"]["status"] == "passed"
          and any(item["name"] == ARGS.ifc.name and item["sha256"] == report["sources"]["ifc"]["sha256"] for item in metadata["files"]))
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    result = bpy.ops.bim.load_project(filepath=str(ARGS.ifc.resolve()), should_start_fresh_session=False,
                                      skip_recent=True, skip_autosave_recovery=True)
    check("public Bonsai Load IFC Project completes", result == {"FINISHED"})
    model = tool.Ifc.get()
    check("active Bonsai IFC4 retains all 33 authored products and six shared types",
          model.schema == "IFC4" and all(len(model.by_type("Ifc"+category)) == count and
          len(model.by_type("Ifc"+category+"Type")) == 1 for _, category, count in CATEGORIES))
    check("Bonsai imports metre units without rescaling", near(bpy.context.scene.unit_settings.scale_length, 1.0))
    native_materials = {}
    for material in model.by_type("IfcMaterial"):
        pset = next((pset for pset in material.HasProperties if pset.Name == "BIM3117_Source"), None)
        if pset:
            props = {prop.Name: prop.NominalValue.wrappedValue for prop in pset.Properties}
            check("native material " + material.Name + " source identity and revision",
                  props["SourceUUID"] not in native_materials and props["ContentRevision"] == SNAPSHOT["content_revision"])
            native_materials[props["SourceUUID"]] = material
    check("all seven native materials survive without fabricated frame components",
          len(model.by_type("IfcMaterial")) == len(native_materials) == len(SNAPSHOT["materials"]) == 7
          and set(native_materials) == {item["id"] for item in SNAPSHOT["materials"]})
    types = {item["id"]: item for item in SNAPSHOT["wall_types"] + SNAPSHOT["element_types"]}
    walls = {item["id"]: item for item in SNAPSHOT["walls"]}
    slabs = {item["id"]: item for item in SNAPSHOT["slabs"]}
    objects, totals = {}, {}
    for key, category, count in CATEGORIES:
        baseline = {item["id"]: item for item in BASELINE[key]}
        check(category + " UUIDs and counts match the frozen native geometry fixture",
              len(SNAPSHOT[key]) == count and set(baseline) == {item["id"] for item in SNAPSHOT[key]})
        measurements = []
        for item in SNAPSHOT[key]:
            entity = model.by_guid(guid(item["id"]))
            obj = tool.Ifc.get_object(entity)
            label = category + " " + item["label"]
            check(label + ": actual Blender product mesh maps back to the native UUID",
                  obj is not None and obj.type == "MESH" and len(obj.data.vertices) > 0 and tool.Ifc.get_entity(obj) == entity)
            objects[item["id"]] = obj
            source = element.get_psets(entity)["BIM3117_Source"]
            typ = element.get_type(entity)
            check(label + ": native type relationship and source revision survive import",
                  typ is not None and typ.GlobalId == guid(item["type_id"]) and source["SourceUUID"] == item["id"]
                  and source["ContentRevision"] == SNAPSHOT["content_revision"])
            data = types[item["type_id"]]
            material = element.get_material(entity)
            if data.get("layers"):
                expected_axis, sense, offset = ("AXIS2", "POSITIVE", 0.0) if category == "Wall" else ("AXIS3", "NEGATIVE", item["thickness_m"])
                check(label + ": ordered layers and usage orientation survive Bonsai import",
                      material is not None and material.is_a("IfcMaterialLayerSetUsage")
                      and material.ForLayerSet == element.get_material(typ)
                      and material.LayerSetDirection == expected_axis and material.DirectionSense == sense
                      and near(material.OffsetFromReferenceLine, offset)
                      and len(material.ForLayerSet.MaterialLayers) == len(data["layers"])
                      and all(layer.Material == native_materials[expected["material_id"]]
                              and near(layer.LayerThickness, expected["thickness_m"])
                              and (layer.Category or "") == expected["role"]
                              for layer, expected in zip(material.ForLayerSet.MaterialLayers, data["layers"])))
            else:
                check(label + ": homogeneous material is inherited from its real type",
                      material == element.get_material(typ) == native_materials[data["material_id"]])
            expected_volume = BASELINE_REPORT["expected_net_volumes_m3"][category][item["id"]]
            volume, bounds = mesh_volume(obj), mesh_bounds(obj)
            measurements.append(volume)
            old = baseline[item["id"]]
            expected_bounds = wall_bounds(old) if category == "Wall" else wall_bounds(walls[item["host_id"]], old) if category in ("Door", "Window") else old["native_bounds_m"]
            check(label + ": actual Blender net volume and bounds preserve the frozen native solid",
                  near(volume, expected_volume) and all(near(bounds[side][axis], expected_bounds[side][axis]) for side in range(2) for axis in range(3)))
            rows = [row for row in SNAPSHOT["material_rows"] if row["element_id"] == item["id"]]
            qto = element.get_psets(entity, qtos_only=True)["BIM3117_MaterialQuantities"]
            check(label + ": material rows conserve the imported native product volume",
                  near(math.fsum(row["net_volume_m3"] for row in rows), volume)
                  and all(near(qto[("Layer" + str(row["layer_index"]) if row["layer_index"] else "Homogeneous") + "NetVolume"], row["net_volume_m3"]) for row in rows))
            report["observations"].append({"category": category, "source_uuid": item["id"], "ifc_guid": entity.GlobalId,
                "type_guid": typ.GlobalId, "blender_object": obj.name, "mesh_volume_m3": volume,
                "expected_volume_m3": expected_volume, "world_bounds_m": bounds, "material_row_count": len(rows)})
        totals[category] = math.fsum(measurements)
    for key, category in (("columns", "Column"), ("beams", "Beam")):
        for member in SNAPSHOT[key]:
            obj = objects[member["id"]]
            for slab_id in member["join_slab_ids"]:
                slab = slabs[slab_id]
                cut_z = (slab["base_z_m"]+slab["top_z_m"])/2
                remaining_z = (member["native_bounds_m"][0][2]+member["native_bounds_m"][1][2])/2
                check(category + " " + member["label"] + ": imported member retains its real slab-priority cut",
                      not segment_hits(obj, *member_segment(member, category, cut_z))
                      and segment_hits(obj, *member_segment(member, category, remaining_z)))
    for key, category in (("doors", "Door"), ("windows", "Window")):
        for item in SNAPSHOT[key]:
            wall, obj = walls[item["host_id"]], objects[item["id"]]
            centre, z = item["offset_m"]+item["width_m"]/2, item["sill_m"]+item["height_m"]/2
            strip = min(.05, item["width_m"]/4, item["height_m"]/4)
            check(category + " " + item["label"] + ": imported wall void and generic frame centre remain empty",
                  not wall_ray(objects[wall["id"]], wall, centre, z) and not wall_ray(obj, wall, centre, z))
            check(category + " " + item["label"] + ": original frame bars survive type/material assignment",
                  wall_ray(obj, wall, item["offset_m"]+strip/2, z)
                  and wall_ray(obj, wall, centre, item["sill_m"]+item["height_m"]-strip/2)
                  and wall_ray(obj, wall, centre, item["sill_m"]+strip/2) == (category == "Window"))
    check("Bonsai has exactly 33 authored mesh products and no material-layer product duplication",
          len([obj for obj in bpy.data.objects if obj.type == "MESH" and tool.Ifc.get_entity(obj) is not None]) == 33)
    check("material assignment coverage is complete and partitions conserve the whole declared product set",
          SNAPSHOT["material_totals"]["assigned_product_count"] == SNAPSHOT["material_totals"]["product_count"] == 33
          and len(SNAPSHOT["material_rows"]) == 55 and SNAPSHOT["material_totals"]["complete"]
          and near(SNAPSHOT["material_totals"]["net_volume_m3"], math.fsum(totals.values())))
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    report["express_validation"] = {"statements": logger.statements, "count": len(logger.statements)}
    check("Bonsai IFC schema and full EXPRESS validation have no findings", not logger.statements)
    check("actual Bonsai import leaves source IFC bytes unchanged",
          hashlib.sha256(ARGS.ifc.read_bytes()).hexdigest() == report["sources"]["ifc"]["sha256"])
    report.update(status="passed", category_mesh_totals_m3=totals, material_rows=len(SNAPSHOT["material_rows"]),
                  native_material_count=len(native_materials), type_count=len(types),
                  layer_set_count=len(model.by_type("IfcMaterialLayerSet")), layer_usage_count=len(model.by_type("IfcMaterialLayerSetUsage")))
    if not bpy.app.background:
        prepare_gui(objects)
        report.update(status="geometry_passed_capture_pending", visual_review={"status": "capture_pending"},
                      screenshot=str(ARGS.output / "Bonsai_Types_Quantities.png"))
        bpy.app.timers.register(ready_for_capture, first_interval=2.0)
except BaseException as error:
    report.update(status="failed", error=str(error), traceback=traceback.format_exc())
    if not bpy.app.background:
        bpy.app.timers.register(quit_app, first_interval=.2)
    raise
finally:
    report["checks_passed"] = len(report["checks"])
    (ARGS.output / "bonsai-types-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
