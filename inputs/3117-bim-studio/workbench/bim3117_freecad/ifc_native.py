# SPDX-License-Identifier: GPL-3.0-or-later
"""IFC4 exchange for a validated, read-only native model snapshot.

This adapter never changes the FreeCAD document and does not read the separate
reference-model JSON format. Its argument is the SI snapshot captured by the
native quantity service. IfcOpenShell is an optional host dependency, imported
only when IFC is requested. The caller owns file-level atomic replacement and
rollback of caught publication failures; a multi-file export is not crash-atomic.

Geometry is explicit IFC swept solids, with normal void/fill relationships and
explicit slab-priority boolean differences for joined columns/beams. Walls are
uniform straight prisms; doors/windows match the native generic frames, without
a leaf/pane or a claim about clear passage size.

References:
https://docs.ifcopenshell.org/ifcopenshell-python/geometry_creation.html
https://docs.ifcopenshell.org/ifcopenshell-python/validation.html
"""

import importlib
import json
import math
from uuid import UUID, uuid5


class IfcExportError(ValueError):
    """The declared native exchange contract cannot be fulfilled."""


PRODUCT_COLLECTIONS = (("walls", "Wall"), ("slabs", "Slab"), ("columns", "Column"),
                       ("beams", "Beam"), ("doors", "Door"), ("windows", "Window"))
TYPE_DIMENSIONS = {"Wall": ("thickness_m",), "Slab": ("thickness_m",),
                   "Column": ("width_m", "depth_m"), "Beam": ("width_m", "depth_m"),
                   "Door": ("width_m", "height_m"), "Window": ("width_m", "height_m")}


def _catalogue_types(snapshot):
    return {item["id"]: dict(item, category="Wall") for item in snapshot["wall_types"]} | {
        item["id"]: item for item in snapshot.get("element_types", [])}


def _native_material(typ):
    return bool(typ.get("material_id") or typ.get("layers"))


def _catalogue_contract(snapshot, levels, walls):
    """Validate native type/material identity without manufacturing assignments."""
    types = _catalogue_types(snapshot)
    materials = {item["id"]: item for item in snapshot.get("materials", [])}
    products, expected_rows = {}, {}

    def equal(actual, expected, name):
        if not math.isclose(_number(actual, name), _number(expected, name), rel_tol=1e-8, abs_tol=1e-9):
            raise IfcExportError(name + " is inconsistent in the native snapshot")

    for material in materials.values():
        if not isinstance(material.get("label"), str) or not material["label"].strip():
            raise IfcExportError("Native material requires a name")
    if any(item.get("category") not in ("Slab", "Column", "Beam", "Door", "Window") for item in snapshot.get("element_types", [])):
        raise IfcExportError("ElementType category must be Slab, Column, Beam, Door or Window")
    for typ in types.values():
        category = typ.get("category")
        if category not in TYPE_DIMENSIONS:
            raise IfcExportError("Unsupported native type category")
        for name in TYPE_DIMENSIONS[category]:
            _number(typ[name], category + " type " + name, True)
        material_id, layers = typ.get("material_id", ""), typ.get("layers", [])
        if material_id and material_id not in materials:
            raise IfcExportError("Type references an absent native material")
        if layers:
            if category not in ("Wall", "Slab") or material_id:
                raise IfcExportError("Only Wall/Slab types support layers; homogeneous and layered assignments are exclusive")
            for layer in layers:
                if layer.get("material_id") not in materials:
                    raise IfcExportError("Layer references an absent native material")
                _number(layer["thickness_m"], "Layer thickness", True)
                if not isinstance(layer.get("role"), str):
                    raise IfcExportError("Layer role must be text")
            equal(math.fsum(layer["thickness_m"] for layer in layers), typ["thickness_m"], "Layer total thickness")
    for key, category in PRODUCT_COLLECTIONS:
        for data in snapshot.get(key, []):
            products[data["id"]] = (data, category)
            type_id = data.get("type_id")
            if not type_id:
                continue
            if type_id not in types or types[type_id]["category"] != category:
                raise IfcExportError("Product references an absent or incompatible native type")
            typ = types[type_id]
            for name in TYPE_DIMENSIONS[category]:
                equal(data[name], typ[name], category + " instance/type " + name)
            if _native_material(typ):
                expected_rows[data["id"]] = typ
    rows_by_element = {}
    for row in snapshot.get("material_rows", []):
        identifier = row.get("element_id")
        if identifier not in expected_rows:
            raise IfcExportError("Material quantity row has no matching native product assignment")
        data, category = products[identifier]
        typ = expected_rows[identifier]
        level_id = (walls[data["host_id"]]["base_level_id"] if category in ("Door", "Window") else
                    data["base_level_id"] if category in ("Wall", "Column") else data["level_id"])
        if (row.get("category") != category or row.get("type_id") != typ["id"] or
                row.get("level_id") != level_id or row.get("level") != levels[level_id]["label"] or
                row.get("content_revision") != snapshot["content_revision"]):
            raise IfcExportError("Material quantity identity, level or revision is inconsistent")
        for name in ("gross_volume_m3", "deduction_volume_m3", "net_volume_m3"):
            if _number(row[name], name) < 0:
                raise IfcExportError("Material quantity volumes must be nonnegative")
        equal(row["gross_volume_m3"]-row["deduction_volume_m3"], row["net_volume_m3"], "Material gross/deduction/net")
        material_id = row.get("material_id")
        if material_id not in materials or row.get("material_name") != materials[material_id]["label"] or row.get("material_code", "") != materials[material_id].get("code", ""):
            raise IfcExportError("Material quantity name/code/identity is inconsistent")
        rows_by_element.setdefault(identifier, []).append(row)
    if set(rows_by_element) != set(expected_rows):
        raise IfcExportError("Material quantities must cover every native assigned product exactly")
    for identifier, typ in expected_rows.items():
        data, category = products[identifier]
        rows = sorted(rows_by_element[identifier], key=lambda row: row["layer_index"])
        layers = typ.get("layers", [])
        if layers:
            if len(rows) != len(layers):
                raise IfcExportError("Material quantity row count differs from native layers")
            for index, (row, layer) in enumerate(zip(rows, layers), 1):
                if row["layer_index"] != index or row["material_id"] != layer["material_id"] or row["layer_role"] != layer["role"]:
                    raise IfcExportError("Material quantity layer order or identity differs from the type")
                equal(row["thickness_m"], layer["thickness_m"], "Material quantity layer thickness")
        elif len(rows) != 1 or rows[0]["layer_index"] != 0 or rows[0]["material_id"] != typ["material_id"]:
            raise IfcExportError("Homogeneous material requires one whole-product row")
        gross = data["frame_volume_m3"] if category in ("Door", "Window") else data["quantities"]["gross_volume_m3"]
        net = data["frame_volume_m3"] if category in ("Door", "Window") else data["quantities"]["net_volume_m3"]
        equal(math.fsum(row["gross_volume_m3"] for row in rows), gross, "Material gross volume conservation")
        equal(math.fsum(row["net_volume_m3"] for row in rows), net, "Material net volume conservation")
    if "material_totals" in snapshot:
        totals = snapshot["material_totals"]
        if (totals.get("assigned_product_count") != len(expected_rows) or totals.get("product_count") != len(products) or
                totals.get("unassigned_product_count") != len(products)-len(expected_rows) or
                totals.get("row_count") != len(snapshot.get("material_rows", [])) or
                totals.get("complete") != (len(products) == len(expected_rows))):
            raise IfcExportError("Material assignment coverage is inconsistent")
        for name in ("gross_volume_m3", "deduction_volume_m3", "net_volume_m3"):
            equal(totals[name], math.fsum(row[name] for row in snapshot.get("material_rows", [])), "Material total " + name)


def dependency_info():
    """Report the actual optional dependency without installing anything."""
    try:
        module = importlib.import_module("ifcopenshell")
        importlib.import_module("ifcopenshell.geom")
        return {"available": True, "version": str(module.version), "error": "",
                "message": "IfcOpenShell " + str(module.version) + " is available in this FreeCAD runtime."}
    except (ImportError, OSError) as error:
        return {"available": False, "version": "", "error": str(error),
                "message": "IFC export requires IfcOpenShell compatible with FreeCAD's embedded Python. "
                           "Use a compatible host distribution or install the matching optional dependency. "
                           "No dependency was installed automatically. " + str(error)}


def ifc_available():
    return dependency_info()["available"]


def _ifc():
    try:
        return importlib.import_module("ifcopenshell")
    except (ImportError, OSError) as error:
        raise IfcExportError(
            "IFC export requires an IfcOpenShell build compatible with FreeCAD's "
            "embedded Python. No dependency was installed automatically. " + str(error)
        ) from error


def global_id(identifier):
    """Lossless, stable UUID -> IFC compressed GlobalId conversion."""
    module = _ifc()
    importlib.import_module("ifcopenshell.guid")
    return module.guid.compress(UUID(str(identifier)).hex)


def opening_id(door_id):
    return str(uuid5(UUID(str(door_id)), "opening"))


def _number(value, name, positive=False):
    if isinstance(value, bool):
        raise IfcExportError(name + " must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise IfcExportError(name + " must be a finite number") from error
    if not math.isfinite(result) or (positive and result <= 0):
        raise IfcExportError(name + " must be finite" + (" and positive" if positive else ""))
    return result


def _snapshot_contract(snapshot):
    """Reject missing, ambiguous or inconsistent export inputs early."""
    if snapshot.get("snapshot_schema") != 1:
        raise IfcExportError("Unsupported native snapshot schema")
    revision = snapshot.get("content_revision", "")
    if len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise IfcExportError("A SHA-256 native content revision is required")
    project = snapshot["project"]
    seen = set()
    for item in [project] + sum((list(snapshot.get(name, [])) for name in
                                ("levels", "wall_types", "materials", "element_types", "walls", "doors", "slabs", "columns", "beams", "windows")), []):
        identifier = str(item["id"])
        UUID(identifier)
        if identifier in seen:
            raise IfcExportError("Duplicate native UUID: " + identifier)
        seen.add(identifier)
    levels = {item["id"]: item for item in snapshot["levels"]}
    types = {item["id"]: item for item in snapshot["wall_types"]}
    walls = {item["id"]: item for item in snapshot["walls"]}
    for level in levels.values():
        _number(level["elevation_m"], "Level elevation")
    for typ in types.values():
        _number(typ["thickness_m"], "Wall type thickness", True)
    for wall in walls.values():
        if wall["type_id"] not in types or any(wall[key] not in levels for key in
                                              ("base_level_id", "top_level_id")):
            raise IfcExportError("Wall references an absent type or level")
        if len(wall["start_m"]) != 2 or len(wall["end_m"]) != 2:
            raise IfcExportError("Wall axis requires XY coordinate pairs")
        sx, sy = [_number(v, "Wall start") for v in wall["start_m"]]
        ex, ey = [_number(v, "Wall end") for v in wall["end_m"]]
        for key in ("length_m", "height_m", "thickness_m"):
            _number(wall[key], key, True)
        expected_base = levels[wall["base_level_id"]]["elevation_m"] + wall["base_offset_m"]
        expected_top = levels[wall["top_level_id"]]["elevation_m"] + wall["top_offset_m"]
        for actual, expected, name in (
            (wall["length_m"], math.hypot(ex-sx, ey-sy), "Wall axis length"),
            (wall["thickness_m"], types[wall["type_id"]]["thickness_m"], "Wall type thickness"),
            (wall["base_z_m"], expected_base, "Wall base level"),
            (wall["height_m"], expected_top-expected_base, "Wall top level"),
        ):
            if not math.isclose(_number(actual, name), _number(expected, name),
                                rel_tol=1e-9, abs_tol=1e-9):
                raise IfcExportError(name + " is inconsistent in the native snapshot")
        for key in ("gross_side_area_m2", "net_side_area_m2", "gross_volume_m3", "net_volume_m3"):
            _number(wall["quantities"][key], key, True)
    slabs = {item["id"]: item for item in snapshot.get("slabs", [])}

    def equal(actual, expected, name):
        if not math.isclose(_number(actual, name), _number(expected, name), rel_tol=1e-9, abs_tol=1e-9):
            raise IfcExportError(name + " is inconsistent in the native snapshot")

    for slab in slabs.values():
        if slab["level_id"] not in levels:
            raise IfcExportError("Slab references an absent level")
        _number(slab["thickness_m"], "Slab thickness", True)
        boundary = slab["boundary_m"]
        if len(boundary) < 3 or any(len(point) != 2 for point in boundary):
            raise IfcExportError("Slab needs a simple XY polygon with at least three vertices")
        for point in boundary:
            for value in point:
                _number(value, "Slab boundary")
        equal(slab["top_z_m"], levels[slab["level_id"]]["elevation_m"] + slab["offset_m"], "Slab top")
        equal(slab["base_z_m"], slab["top_z_m"] - slab["thickness_m"], "Slab bottom")
    for key in ("columns", "beams"):
        for member in snapshot.get(key, []):
            _number(member["width_m"], "Member width", True)
            _number(member["depth_m"], "Member depth", True)
            joins = member.get("join_slab_ids", [])
            if len(joins) != len(set(joins)) or any(identifier not in slabs for identifier in joins):
                raise IfcExportError("Member has missing or duplicate slab join references")
            if key == "columns":
                if any(member[name] not in levels for name in ("base_level_id", "top_level_id")):
                    raise IfcExportError("Column references an absent level")
                for name in ("x_m", "y_m", "rotation_deg"):
                    _number(member[name], name)
                _number(member["height_m"], "Column height", True)
                equal(member["base_z_m"], levels[member["base_level_id"]]["elevation_m"]+member["base_offset_m"], "Column base")
                equal(member["height_m"], levels[member["top_level_id"]]["elevation_m"]+member["top_offset_m"]-member["base_z_m"], "Column height")
            else:
                if member["level_id"] not in levels:
                    raise IfcExportError("Beam references an absent level")
                if len(member["start_m"]) != 2 or len(member["end_m"]) != 2:
                    raise IfcExportError("Beam needs start/end XY coordinates")
                for point in (member["start_m"], member["end_m"]):
                    for value in point:
                        _number(value, "Beam axis")
                _number(member["length_m"], "Beam length", True)
                equal(member["length_m"], math.dist(member["start_m"], member["end_m"]), "Beam length")
                equal(member["top_z_m"], levels[member["level_id"]]["elevation_m"]+member["offset_m"], "Beam top")
                equal(member["base_z_m"], member["top_z_m"]-member["depth_m"], "Beam bottom")
    for data in sum((list(snapshot.get(key, [])) for key in ("slabs", "columns", "beams")), []):
        for name in ("gross_volume_m3", "net_volume_m3"):
            _number(data["quantities"][name], name, True)
        bounds = data.get("native_bounds_m")
        if bounds is None or len(bounds) != 2 or any(len(point) != 3 for point in bounds):
            raise IfcExportError("Structural snapshot requires native spatial bounds")
        for point in bounds:
            for value in point:
                _number(value, "Native bounds")
    rectangles = {}
    for door in snapshot["doors"] + snapshot.get("windows", []):
        if door["host_id"] not in walls:
            raise IfcExportError("Door references an absent host")
        wall = walls[door["host_id"]]
        for key in ("width_m", "height_m", "frame_volume_m3"):
            _number(door[key], key, True)
        x, z = _number(door["offset_m"], "Door offset"), _number(door["sill_m"], "Door sill")
        w, h = door["width_m"], door["height_m"]
        if x < 0 or z < 0 or x+w > wall["length_m"]+1e-10 or z+h > wall["height_m"]+1e-10:
            raise IfcExportError("Door opening lies outside its native host")
        for px, pz, pw, ph in rectangles.setdefault(door["host_id"], []):
            if min(x+w, px+pw)-max(x, px) > 1e-10 and min(z+h, pz+ph)-max(z, pz) > 1e-10:
                raise IfcExportError("Native opening rectangles overlap")
        rectangles[door["host_id"]].append((x, z, w, h))
    _catalogue_contract(snapshot, levels, walls)
    return project, levels, types, walls


def build_ifc(snapshot):
    """Build an IFC4 file in memory; does not publish or mutate source data."""
    module = _ifc()
    project_data, level_data, type_data, wall_data = _snapshot_contract(snapshot)
    catalogue_types = _catalogue_types(snapshot)
    model = module.file(schema="IFC4")
    namespace = UUID(project_data["id"])
    revision = snapshot["content_revision"]

    def uid(key):
        return str(uuid5(namespace, key))

    def root_entity(ifc_class, key, name=None, identity=None, **kwargs):
        return model.create_entity(ifc_class, GlobalId=global_id(identity or uid(key)),
                                   Name=name, **kwargs)

    def point(coords):
        return model.create_entity("IfcCartesianPoint", Coordinates=tuple(float(x) for x in coords))

    def direction(coords):
        return model.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in coords))

    def axis(location=(0, 0, 0), x_axis=(1, 0, 0)):
        return model.create_entity("IfcAxis2Placement3D", Location=point(location),
                                   Axis=direction((0, 0, 1)), RefDirection=direction(x_axis))

    def placement(parent=None, location=(0, 0, 0), x_axis=(1, 0, 0)):
        return model.create_entity("IfcLocalPlacement", PlacementRelTo=parent,
                                   RelativePlacement=axis(location, x_axis))

    def aggregate(parent, children, key):
        if children:
            root_entity("IfcRelAggregates", key, RelatingObject=parent, RelatedObjects=children)

    def property_values(values):
        props = []
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, bool):
                typed = model.create_entity("IfcBoolean", value)
            elif isinstance(value, (int, float)):
                typed = model.create_entity("IfcReal", float(value))
            else:
                typed = model.create_entity("IfcText", str(value))
            props.append(model.create_entity("IfcPropertySingleValue", Name=key, NominalValue=typed))
        return props

    def properties(product, identity, values, name="BIM3117_Source"):
        props = property_values(dict(values))
        pset = root_entity("IfcPropertySet", identity + ":pset:" + name, name, HasProperties=props)
        if product.is_a("IfcTypeObject"):
            product.HasPropertySets = tuple(product.HasPropertySets or ()) + (pset,)
        else:
            root_entity("IfcRelDefinesByProperties", identity + ":pset-rel:" + name,
                        RelatedObjects=[product], RelatingPropertyDefinition=pset)

    def provenance(product, data, **extra):
        if data.get("type_id"):
            extra["TypeUUID"] = data["type_id"]
        properties(product, data["id"], {
            "SourceUUID": data["id"], "ContentRevision": revision,
            "NativeObjectName": data.get("object_name", ""),
            "SourceModel": "FreeCAD Document / FCStd",
            "WorkbenchVersion": snapshot.get("workbench_version", ""), **extra,
        })

    project = root_entity("IfcProject", "project", project_data["label"], project_data["id"])
    project.LongName = project_data.get("number", "") or None
    units = [model.create_entity("IfcSIUnit", UnitType=kind, Name=name) for kind, name in
             (("LENGTHUNIT", "METRE"), ("AREAUNIT", "SQUARE_METRE"), ("VOLUMEUNIT", "CUBIC_METRE"))]
    project.UnitsInContext = model.create_entity("IfcUnitAssignment", Units=units)
    context = model.create_entity("IfcGeometricRepresentationContext", ContextType="Model",
                                  CoordinateSpaceDimension=3, Precision=1e-7,
                                  WorldCoordinateSystem=axis())
    body_context = model.create_entity("IfcGeometricRepresentationSubContext", ContextIdentifier="Body",
                                       ContextType="Model", ParentContext=context, TargetView="MODEL_VIEW")
    project.RepresentationContexts = [context]
    provenance(project, project_data, ProjectNumber=project_data.get("number", ""),
               Author=project_data.get("author", ""),
               RevisionMeaning="SHA-256 content identity; Undo may restore an earlier identity",
               QuantityRule="Straight uniform walls, one side; openings deducted; wall joins excluded",
               CoverageComplete=bool(snapshot.get("coverage", {}).get("complete", False)))
    site = root_entity("IfcSite", "site", "3117 Site", CompositionType="ELEMENT",
                       ObjectPlacement=placement())
    building = root_entity("IfcBuilding", "building", project_data["label"], CompositionType="ELEMENT",
                           ObjectPlacement=placement(site.ObjectPlacement))
    aggregate(project, [site], "aggregate:project")
    aggregate(site, [building], "aggregate:site")
    properties(site, uid("site"), {"ContentRevision": revision,
               "Mapping": "Generated local site container; no survey/georeferencing claimed"})
    properties(building, uid("building"), {"ContentRevision": revision,
               "Mapping": "Generated building container for the single native Project"})

    def surface(name, colour):
        rgb = model.create_entity("IfcColourRgb", Name=name, Red=colour[0], Green=colour[1], Blue=colour[2])
        shading = model.create_entity("IfcSurfaceStyleShading", SurfaceColour=rgb, Transparency=0.0)
        return model.create_entity("IfcSurfaceStyle", Name=name, Side="BOTH", Styles=[shading])

    wall_style = surface("3117 Wall", (0.76, 0.79, 0.82))
    door_style = surface("3117 Generic Door Frame", (0.92, 0.44, 0.12))

    def polygon_prism(vertices, height, location=(0, 0, 0)):
        vertices = list(vertices)
        if vertices[0] != vertices[-1]:
            vertices.append(vertices[0])
        polygon = model.create_entity("IfcPolyline", Points=[point(p) for p in vertices])
        profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polygon)
        return model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile,
                                   Position=axis(location), ExtrudedDirection=direction((0, 0, 1)),
                                   Depth=float(height))

    def prism(length, depth, height, location=(0, 0, 0)):
        return polygon_prism([(0, 0), (length, 0), (length, depth), (0, depth)], height, location)

    def representation(product, items, style=None, representation_type="SweptSolid"):
        shape = model.create_entity("IfcShapeRepresentation", ContextOfItems=body_context,
                                    RepresentationIdentifier="Body", RepresentationType=representation_type, Items=items)
        product.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[shape])
        if style is not None:
            for item in items:
                model.create_entity("IfcStyledItem", Item=item, Styles=[style])

    storeys, types, walls, contained, all_products = {}, {}, {}, {}, {}
    native_materials, layer_sets = {}, {}
    for data in sorted(level_data.values(), key=lambda item: item["id"]):
        storey = root_entity("IfcBuildingStorey", data["id"], data["label"], data["id"],
                             CompositionType="ELEMENT", Elevation=float(data["elevation_m"]),
                             ObjectPlacement=placement(building.ObjectPlacement, (0, 0, data["elevation_m"])))
        provenance(storey, data)
        storeys[data["id"]] = storey
        contained[data["id"]] = []
    aggregate(building, list(storeys.values()), "aggregate:building")
    for data in sorted(snapshot.get("materials", []), key=lambda item: item["id"]):
        material = model.create_entity("IfcMaterial", Name=data["label"],
                                       Description="3117 native Material " + data["id"])
        model.create_entity("IfcMaterialProperties", Name="BIM3117_Source", Material=material,
                            Properties=property_values({"SourceUUID": data["id"], "Code": data.get("code", ""),
                                "ContentRevision": revision, "NativeObjectName": data.get("object_name", ""),
                                "SourceModel": "FreeCAD Document / FCStd"}))
        native_materials[data["id"]] = material

    def assign_type_material(typ, data):
        layers = data.get("layers", [])
        if layers:
            layer_set = model.create_entity("IfcMaterialLayerSet", LayerSetName=data["label"],
                MaterialLayers=[model.create_entity("IfcMaterialLayer", Material=native_materials[layer["material_id"]],
                    LayerThickness=float(layer["thickness_m"]), Name=layer["role"] or "Layer " + str(index),
                    Category=layer["role"] or None) for index, layer in enumerate(layers, 1)])
            layer_sets[data["id"]] = layer_set
            material = layer_set
        elif data.get("material_id"):
            material = native_materials[data["material_id"]]
        else:
            return
        root_entity("IfcRelAssociatesMaterial", data["id"] + ":material", RelatedObjects=[typ], RelatingMaterial=material)

    def type_extras(data):
        extras = {"TypeCode": data.get("code", ""), "Category": data["category"],
                  "MaterialUUID": data.get("material_id", ""),
                  "MaterialLayers": json.dumps(data.get("layers", []), ensure_ascii=False, sort_keys=True, separators=(",", ":"))}
        extras.update({name[:-2].title() + "M": data[name] for name in TYPE_DIMENSIONS[data["category"]]})
        return extras

    for data in sorted(type_data.values(), key=lambda item: item["id"]):
        typ = root_entity("IfcWallType", data["id"], data["label"], data["id"],
                          PredefinedType="STANDARD", Tag=data["id"])
        extras = {"ThicknessM": data["thickness_m"], "MaterialDescription": data.get("material", ""),
                  "Assembly": "Ordered native material layers along local +Y" if data.get("layers") else "Uniform wall; no material layer assembly"}
        if _native_material(data) or data.get("code"):
            extras.update(type_extras(catalogue_types[data["id"]]))
        provenance(typ, data, **extras)
        assign_type_material(typ, data)
        if not _native_material(data) and data.get("material", "").strip():
            material = model.create_entity("IfcMaterial", Name=data["material"])
            root_entity("IfcRelAssociatesMaterial", data["id"] + ":material", RelatedObjects=[typ],
                        RelatingMaterial=material)
        types[data["id"]] = typ
    for data in sorted(snapshot.get("element_types", []), key=lambda item: item["id"]):
        category = data["category"]
        attributes = {"PredefinedType": {"Slab": "FLOOR", "Column": "COLUMN", "Beam": "BEAM", "Door": "DOOR", "Window": "WINDOW"}[category]}
        if category in ("Door", "Window"):
            attributes.update(ParameterTakesPrecedence=False,
                              **{"OperationType" if category == "Door" else "PartitioningType": "NOTDEFINED"})
        typ = root_entity("Ifc" + category + "Type", data["id"], data["label"], data["id"], Tag=data["id"], **attributes)
        extras = type_extras(data)
        if category in ("Door", "Window"):
            extras["DimensionMeaning"] = "Overall wall-cut opening including generic frame; no leaf, glazing or clear passage specification"
        provenance(typ, data, **extras)
        assign_type_material(typ, data)
        types[data["id"]] = typ
    for data in sorted(wall_data.values(), key=lambda item: item["id"]):
        sx, sy = data["start_m"]
        ex, ey = data["end_m"]
        length, depth, height = data["length_m"], data["thickness_m"], data["height_m"]
        ux, uy = (ex-sx)/length, (ey-sy)/length
        wall = root_entity("IfcWall", data["id"], data["label"], data["id"],
                           Tag=data["id"], PredefinedType="STANDARD",
                           ObjectPlacement=placement(storeys[data["base_level_id"]].ObjectPlacement,
                                                     (sx, sy, data["base_offset_m"]), (ux, uy, 0)))
        representation(wall, [prism(length, depth, height)], wall_style)
        provenance(wall, data, WallTypeUUID=data["type_id"], BaseLevelUUID=data["base_level_id"],
                   TopLevelUUID=data["top_level_id"], BaseOffsetM=data["base_offset_m"],
                   TopOffsetM=data["top_offset_m"],
                   QuantityRule="One wall, one side; actual cut solid; no wall joins/layers")
        quantities = data["quantities"]
        values = [("Length", "IfcQuantityLength", "LengthValue", length),
                  ("Width", "IfcQuantityLength", "LengthValue", depth),
                  ("Height", "IfcQuantityLength", "LengthValue", height)]
        for name, key in (("GrossSideArea", "gross_side_area_m2"), ("NetSideArea", "net_side_area_m2")):
            values.append((name, "IfcQuantityArea", "AreaValue", quantities[key]))
        for name, key in (("GrossVolume", "gross_volume_m3"), ("NetVolume", "net_volume_m3")):
            values.append((name, "IfcQuantityVolume", "VolumeValue", quantities[key]))
        qto = root_entity("IfcElementQuantity", data["id"] + ":qto", "Qto_WallBaseQuantities",
                          MethodOfMeasurement="3117: straight uniform wall; one side; no joins",
                          Quantities=[model.create_entity(cls, Name=name, **{attribute: float(value)})
                                      for name, cls, attribute, value in values])
        root_entity("IfcRelDefinesByProperties", data["id"] + ":qto-rel", RelatedObjects=[wall],
                    RelatingPropertyDefinition=qto)
        contained[data["base_level_id"]].append(wall)
        walls[data["id"]] = wall
        all_products[data["id"]] = wall
    for type_id, typ in types.items():
        instances = [walls[data["id"]] for data in sorted(wall_data.values(), key=lambda item: item["id"])
                     if data["type_id"] == type_id]
        if instances:
            root_entity("IfcRelDefinesByType", type_id + ":instances", RelatedObjects=instances,
                        RelatingType=typ)
    window_ids = {item["id"] for item in snapshot.get("windows", [])}
    for data in sorted(snapshot["doors"] + snapshot.get("windows", []), key=lambda item: item["id"]):
        is_window = data["id"] in window_ids
        host = wall_data[data["host_id"]]
        depth = host["thickness_m"]
        width, height = data["width_m"], data["height_m"]
        # Match native boolean padding: max(0.001 mm, thickness_mm * 1e-6).
        padding = max(1e-6, depth * 1e-6)
        identifier = opening_id(data["id"])
        opening = root_entity("IfcOpeningElement", identifier, "Opening — " + data["label"], identifier,
                              PredefinedType="OPENING", Tag=identifier,
                              ObjectPlacement=placement(walls[data["host_id"]].ObjectPlacement,
                                                        (data["offset_m"], -padding, data["sill_m"])))
        representation(opening, [prism(width, depth+2*padding, height)])
        properties(opening, identifier, {"SourceWindowUUID" if is_window else "SourceDoorUUID": data["id"], "HostWallUUID": data["host_id"],
                   "ContentRevision": revision, "BooleanPaddingM": padding})
        root_entity("IfcRelVoidsElement", data["id"] + ":void", RelatingBuildingElement=walls[data["host_id"]],
                    RelatedOpeningElement=opening)
        door = root_entity("IfcWindow" if is_window else "IfcDoor", data["id"], data["label"], data["id"], Tag=data["id"],
                           **({"PredefinedType": "WINDOW", "PartitioningType": "NOTDEFINED"} if is_window else
                              {"PredefinedType": "DOOR", "OperationType": "NOTDEFINED"}),
                           OverallWidth=float(width), OverallHeight=float(height),
                           ObjectPlacement=placement(opening.ObjectPlacement, (0, padding, 0)))
        strip = min(0.05, width/4, height/4)
        if is_window:
            frame = [prism(strip, depth, height), prism(strip, depth, height, (width-strip, 0, 0)),
                     prism(width-2*strip, depth, strip, (strip, 0, 0)),
                     prism(width-2*strip, depth, strip, (strip, 0, height-strip))]
        else:
            frame = [prism(strip, depth, height-strip), prism(strip, depth, height-strip, (width-strip, 0, 0)),
                     prism(width, depth, strip, (0, 0, height-strip))]
        representation(door, frame, door_style)
        provenance(door, data, HostWallUUID=data["host_id"], OffsetM=data["offset_m"], SillM=data["sill_m"],
                   Geometry=("Generic four-bar window frame, no pane/leaf/operation" if is_window else
                             "Generic three-bar frame, no leaf/handing/swing"),
                   DimensionMeaning="Overall wall-cut opening including frame; not clear passage or leaf",
                   FrameVolumeM3=data["frame_volume_m3"])
        root_entity("IfcRelFillsElement", data["id"] + ":fill", RelatingOpeningElement=opening,
                    RelatedBuildingElement=door)
        contained[host["base_level_id"]].append(door)
        all_products[data["id"]] = door

    structural_style = surface("3117 Structural Member", (0.59, 0.66, 0.73))
    slab_data = {item["id"]: item for item in snapshot.get("slabs", [])}

    def structural_qto(product, data, category):
        q = data["quantities"]
        values = [("GrossVolume", "IfcQuantityVolume", "VolumeValue", q["gross_volume_m3"]),
                  ("NetVolume", "IfcQuantityVolume", "VolumeValue", q["net_volume_m3"])]
        if category == "Slab":
            values.extend([("Depth", "IfcQuantityLength", "LengthValue", data["thickness_m"]),
                           ("Perimeter", "IfcQuantityLength", "LengthValue", q["perimeter_m"]),
                           ("GrossArea", "IfcQuantityArea", "AreaValue", q["gross_area_m2"]),
                           ("NetArea", "IfcQuantityArea", "AreaValue", q["net_area_m2"])])
        else:
            values.extend([("Length", "IfcQuantityLength", "LengthValue", data["height_m"] if category == "Column" else data["length_m"]),
                           ("CrossSectionArea", "IfcQuantityArea", "AreaValue", data["width_m"]*data["depth_m"])])
        quantity = root_entity("IfcElementQuantity", data["id"]+":qto", "Qto_"+category+"BaseQuantities",
                               MethodOfMeasurement="3117 native solid; explicit Slab priority only; no other joins",
                               Quantities=[model.create_entity(cls, Name=name, **{attribute: float(value)})
                                           for name, cls, attribute, value in values])
        root_entity("IfcRelDefinesByProperties", data["id"]+":qto-rel", RelatedObjects=[product], RelatingPropertyDefinition=quantity)

    def material_for(product, data):
        typ = catalogue_types.get(data.get("type_id"), {})
        if not _native_material(typ) and data.get("material", "").strip():
            material = model.create_entity("IfcMaterial", Name=data["material"])
            root_entity("IfcRelAssociatesMaterial", data["id"]+":material", RelatedObjects=[product], RelatingMaterial=material)

    for key, category, predefined in (("slabs", "Slab", "FLOOR"), ("columns", "Column", "COLUMN"), ("beams", "Beam", "BEAM")):
        for data in sorted(snapshot.get(key, []), key=lambda item: item["id"]):
            if category == "Slab":
                level_id, origin, axis_x = data["level_id"], (0.0, 0.0, data["base_z_m"]), (1.0, 0.0, 0.0)
                item = polygon_prism(data["boundary_m"], data["thickness_m"])
            elif category == "Column":
                angle = math.radians(data["rotation_deg"])
                level_id = data["base_level_id"]
                origin, axis_x = (data["x_m"], data["y_m"], data["base_z_m"]), (math.cos(angle), math.sin(angle), 0.0)
                item = prism(data["width_m"], data["depth_m"], data["height_m"], (-data["width_m"]/2, -data["depth_m"]/2, 0))
            else:
                level_id = data["level_id"]
                sx, sy = data["start_m"]
                ex, ey = data["end_m"]
                origin, axis_x = (sx, sy, data["base_z_m"]), ((ex-sx)/data["length_m"], (ey-sy)/data["length_m"], 0.0)
                item = prism(data["length_m"], data["width_m"], data["depth_m"], (0, -data["width_m"]/2, 0))
            joins = data.get("join_slab_ids", [])
            for slab_id in joins:
                slab = slab_data[slab_id]
                ux, uy = axis_x[:2]
                points = [(ux*(x-origin[0])+uy*(y-origin[1]), -uy*(x-origin[0])+ux*(y-origin[1]))
                          for x, y in slab["boundary_m"]]
                cutter = polygon_prism(points, slab["thickness_m"], (0, 0, slab["base_z_m"]-origin[2]))
                item = model.create_entity("IfcBooleanResult", Operator="DIFFERENCE", FirstOperand=item, SecondOperand=cutter)
            obj = root_entity("Ifc"+category, data["id"], data["label"], data["id"], Tag=data["id"],
                              PredefinedType=predefined,
                              ObjectPlacement=placement(storeys[level_id].ObjectPlacement,
                                                        (origin[0], origin[1], origin[2]-level_data[level_id]["elevation_m"]), axis_x))
            representation(obj, [item], structural_style, "CSG" if joins else "SweptSolid")
            extras = {"MaterialDescription": data.get("material", ""), "LevelUUID": level_id,
                      "JoinSlabUUIDs": "|".join(joins), "JoinDeductionM3": data["quantities"].get("join_deduction_m3", 0.0),
                      "JoinRule": "Slab takes priority; subtract slab solids from this member only" if joins else "No explicit joins"}
            if category == "Column":
                extras.update(BaseLevelUUID=data["base_level_id"], TopLevelUUID=data["top_level_id"],
                              BaseOffsetM=data["base_offset_m"], TopOffsetM=data["top_offset_m"], RotationDegrees=data["rotation_deg"])
            else:
                extras.update(OffsetM=data["offset_m"], TopZM=data["top_z_m"])
            provenance(obj, data, **extras)
            structural_qto(obj, data, category)
            material_for(obj, data)
            contained[level_id].append(obj)
            all_products[data["id"]] = obj
    authored_products = [data for key, _ in PRODUCT_COLLECTIONS for data in snapshot.get(key, [])]
    for type_id, typ in types.items():
        if type_id in type_data:
            continue  # Existing wall relations above retain their stable identity.
        instances = [all_products[data["id"]] for data in sorted(authored_products, key=lambda item: item["id"])
                     if data.get("type_id") == type_id]
        if instances:
            root_entity("IfcRelDefinesByType", type_id + ":instances", RelatedObjects=instances, RelatingType=typ)
    for data in authored_products:
        type_id = data.get("type_id")
        if type_id not in layer_sets:
            continue
        category = catalogue_types[type_id]["category"]
        # Native walls run +Y from the axis. Native slabs run top-down, while
        # their unchanged IFC prism origin is at the bottom and extrudes +Z.
        usage = model.create_entity("IfcMaterialLayerSetUsage", ForLayerSet=layer_sets[type_id],
                    LayerSetDirection="AXIS2" if category == "Wall" else "AXIS3",
                    DirectionSense="POSITIVE" if category == "Wall" else "NEGATIVE",
                    OffsetFromReferenceLine=0.0 if category == "Wall" else float(data["thickness_m"]))
        root_entity("IfcRelAssociatesMaterial", data["id"] + ":material-usage", RelatedObjects=[all_products[data["id"]]],
                    RelatingMaterial=usage)
    material_rows = {}
    for row in snapshot.get("material_rows", []):
        material_rows.setdefault(row["element_id"], []).append(row)
    for identifier, rows in sorted(material_rows.items()):
        rows = sorted(rows, key=lambda row: row["layer_index"])
        quantities = []
        for row in rows:
            prefix = "Layer" + str(row["layer_index"]) if row["layer_index"] else "Homogeneous"
            for name, key in (("GrossVolume", "gross_volume_m3"), ("DeductionVolume", "deduction_volume_m3"), ("NetVolume", "net_volume_m3")):
                quantities.append(model.create_entity("IfcQuantityVolume", Name=prefix + name,
                                    Description="Native material UUID: " + row["material_id"], VolumeValue=float(row[key])))
        quantity = root_entity("IfcElementQuantity", identifier + ":material-qto", "BIM3117_MaterialQuantities",
                              MethodOfMeasurement="3117 native solid partitions; openings and declared Slab priority only; no costs or density",
                              Quantities=quantities)
        root_entity("IfcRelDefinesByProperties", identifier + ":material-qto-rel", RelatedObjects=[all_products[identifier]],
                    RelatingPropertyDefinition=quantity)
        properties(all_products[identifier], identifier, {"ContentRevision": revision,
                   "QuantityRule": rows[0]["quantity_rule"],
                   "Rows": json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}, "BIM3117_MaterialSource")
    for level_id, products in contained.items():
        if products:
            root_entity("IfcRelContainedInSpatialStructure", level_id + ":containment",
                        RelatedElements=products, RelatingStructure=storeys[level_id])
    model.header.file_description.description = (
        "3117 native IFC4 snapshot; declared native building elements and explicit slab-priority joins",
        "Source content revision: " + revision,
    )
    model.header.file_name.author = (project_data.get("author", "") or "3117 BIM Studio",)
    model.header.file_name.originating_system = "3117 BIM Studio " + snapshot.get("workbench_version", "")
    model.header.file_name.preprocessor_version = "IfcOpenShell " + str(module.version)
    return model


def _mesh_volume(vertices, faces):
    """Closed triangulation volume using translated coordinates for precision."""
    origin = vertices[0]
    points = [tuple(p[i]-origin[i] for i in range(3)) for p in vertices]
    terms = []
    for i in range(0, len(faces), 3):
        a, b, c = (points[faces[i+j]] for j in range(3))
        terms.append((a[0]*(b[1]*c[2]-b[2]*c[1]) -
                      a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6)
    return abs(math.fsum(terms))


def _inside_mesh(point, vertices, faces):
    """Solid-angle winding for a closed, oriented triangulation.

    A fixed ray may graze an opening edge and leave an ambiguous odd hit count
    even when the probe is strictly inside the void. The summed solid angle is
    zero outside material and +/-4*pi inside, without choosing a ray direction.
    Callers use interior probes, never points on the triangulated surface.
    """
    def dot(a, b):
        return sum(x*y for x, y in zip(a, b))

    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

    points = [tuple(vertex[i]-point[i] for i in range(3)) for vertex in vertices]
    lengths = [math.sqrt(dot(vertex, vertex)) for vertex in points]
    angles = []
    for i in range(0, len(faces), 3):
        indices = faces[i:i+3]
        a, b, c = (points[index] for index in indices)
        la, lb, lc = (lengths[index] for index in indices)
        denominator = la*lb*lc + dot(a, b)*lc + dot(b, c)*la + dot(c, a)*lb
        angles.append(2*math.atan2(dot(a, cross(b, c)), denominator))
    return abs(math.fsum(angles)) > 2*math.pi


def validate_ifc(model, snapshot, express_rules=False):
    """Validate schema plus mapped semantics, placements and regenerated solids.

    Full EXPRESS rules are an explicit QA option because upstream's rule
    executor requires pytest, which may not be installed in FreeCAD. A normal
    host export always performs IFC schema validation and all model/geometry
    checks below. Optional EXPRESS failures are never silently ignored.
    """
    module = _ifc()
    project_data, levels, types, walls = _snapshot_contract(snapshot)
    importlib.import_module("ifcopenshell.validate")
    importlib.import_module("ifcopenshell.geom")
    element = importlib.import_module("ifcopenshell.util.element")
    placements = importlib.import_module("ifcopenshell.util.placement")
    unit = importlib.import_module("ifcopenshell.util.unit")
    checks, geometry_report = [], []

    def check(name, condition, details=""):
        checks.append({"name": name, "status": "passed" if condition else "failed", "details": details})

    def near(a, b):
        return math.isclose(float(a), float(b), rel_tol=1e-7, abs_tol=1e-8)

    def find(identifier, cls):
        try:
            obj = model.by_guid(global_id(identifier))
            if not obj.is_a(cls):
                raise IfcExportError("Expected " + cls + ", found " + obj.is_a())
            return obj
        except Exception as error:
            check("identity:" + identifier, False, str(error))
            return None

    def source_matches(obj, data):
        props = element.get_psets(obj).get("BIM3117_Source", {})
        return props.get("SourceUUID") == data["id"] and props.get("ContentRevision") == snapshot["content_revision"]

    def position(obj, expected, x_axis=(1, 0, 0)):
        actual = placements.get_local_placement(obj.ObjectPlacement)
        return all(near(actual[i, 3], expected[i]) and near(actual[i, 0], x_axis[i]) for i in range(3))

    logger = module.validate.json_logger()
    module.validate.validate(model, logger, express_rules=False)
    schema_messages = [{"level": str(item.get("level", "")), "message": str(item.get("message", "")),
                        "instance": str(item.get("instance", ""))} for item in logger.statements]
    check("ifc4-schema", model.schema == "IFC4" and not schema_messages, schema_messages)
    roots = model.by_type("IfcRoot")
    ids = [item.GlobalId for item in roots]
    check("unique-global-ids", len(ids) == len(set(ids)))
    opening_count = len(snapshot["doors"]) + len(snapshot.get("windows", []))
    expected_counts = {"IfcProject": 1, "IfcSite": 1, "IfcBuilding": 1, "IfcBuildingStorey": len(levels),
                       "IfcWallType": len(types), "IfcWall": len(walls), "IfcDoor": len(snapshot["doors"]),
                       "IfcWindow": len(snapshot.get("windows", [])), "IfcSlab": len(snapshot.get("slabs", [])),
                       "IfcColumn": len(snapshot.get("columns", [])), "IfcBeam": len(snapshot.get("beams", [])),
                       "IfcOpeningElement": opening_count, "IfcRelVoidsElement": opening_count,
                       "IfcRelFillsElement": opening_count}
    expected_counts.update({"Ifc" + category + "Type": sum(item["category"] == category for item in snapshot.get("element_types", []))
                            for category in ("Slab", "Column", "Beam", "Door", "Window")})
    catalogue_types = _catalogue_types(snapshot)
    authored_products = [(data, category) for key, category in PRODUCT_COLLECTIONS for data in snapshot.get(key, [])]
    expected_counts["IfcMaterialLayerSet"] = sum(bool(data.get("layers")) for data in catalogue_types.values())
    expected_counts["IfcMaterialLayerSetUsage"] = sum(bool(catalogue_types.get(data.get("type_id"), {}).get("layers"))
                                                    for data, _ in authored_products)
    check("mapped-counts", all(len(model.by_type(cls)) == count for cls, count in expected_counts.items()),
          {cls: len(model.by_type(cls)) for cls in expected_counts})
    check("si-units", unit.calculate_unit_scale(model) == 1.0 and
          {(item.UnitType, item.Name, item.Prefix) for item in model.by_type("IfcSIUnit")} ==
          {("LENGTHUNIT", "METRE", None), ("AREAUNIT", "SQUARE_METRE", None), ("VOLUMEUNIT", "CUBIC_METRE", None)})
    project = find(project_data["id"], "IfcProject")
    site = find(str(uuid5(UUID(project_data["id"]), "site")), "IfcSite")
    building = find(str(uuid5(UUID(project_data["id"]), "building")), "IfcBuilding")
    if project and site and building:
        check("project-hierarchy", element.get_aggregate(site) == project and element.get_aggregate(building) == site)
        check("project-source", source_matches(project, project_data))
    for data in levels.values():
        obj = find(data["id"], "IfcBuildingStorey")
        if obj:
            check("level:" + data["id"], element.get_aggregate(obj) == building and
                  near(obj.Elevation, data["elevation_m"]) and position(obj, (0, 0, data["elevation_m"])) and
                  source_matches(obj, data))
    for data in types.values():
        obj = find(data["id"], "IfcWallType")
        if obj:
            props = element.get_psets(obj).get("BIM3117_Source", {})
            material = element.get_material(obj)
            check("wall-type:" + data["id"], source_matches(obj, data) and
                  near(props.get("ThicknessM", -1), data["thickness_m"]) and
                  props.get("MaterialDescription", "") == data.get("material", "") and
                  (_native_material(data) or not data.get("material", "").strip() or (material and material.Name == data["material"])))

    # Native Material is an IfcMaterialDefinition, not an IfcRoot. Its UUID is
    # carried by IfcMaterialProperties, while product/type GUIDs stay native.
    native_materials = {}
    for material in model.by_type("IfcMaterial"):
        sources = [pset for pset in material.HasProperties if pset.Name == "BIM3117_Source"]
        if not sources:
            continue
        props = {prop.Name: prop.NominalValue.wrappedValue for prop in sources[0].Properties
                 if prop.is_a("IfcPropertySingleValue") and prop.NominalValue is not None}
        identifier = props.get("SourceUUID")
        check("material-source-unique:" + str(identifier), len(sources) == 1 and identifier not in native_materials)
        native_materials[identifier] = (material, props)
    expected_materials = {data["id"]: data for data in snapshot.get("materials", [])}
    check("native-material-count", set(native_materials) == set(expected_materials))
    for identifier, data in expected_materials.items():
        material, props = native_materials.get(identifier, (None, {}))
        check("material-source:" + identifier, material is not None and material.Name == data["label"] and
              props.get("SourceUUID") == identifier and props.get("Code", "") == data.get("code", "") and
              props.get("ContentRevision") == snapshot["content_revision"])

    native_type_materials = {}
    for identifier, data in catalogue_types.items():
        category = data["category"]
        typ = find(identifier, "Ifc" + category + "Type")
        if not typ:
            continue
        expected_instances = {global_id(item["id"]) for item, _ in authored_products if item.get("type_id") == identifier}
        related = [relation for relation in model.by_type("IfcRelDefinesByType") if relation.RelatingType == typ]
        actual_instances = [item.GlobalId for relation in related for item in relation.RelatedObjects]
        check("type-instances:" + identifier, set(actual_instances) == expected_instances and
              len(actual_instances) == len(expected_instances) and len(related) == (1 if expected_instances else 0))
        if category != "Wall" or _native_material(data) or data.get("code"):
            props = element.get_psets(typ).get("BIM3117_Source", {})
            check("type-source:" + identifier, source_matches(typ, data) and typ.Name == data["label"] and
                  props.get("Category") == category and props.get("TypeCode", "") == data.get("code", "") and
                  props.get("MaterialUUID", "") == data.get("material_id", "") and
                  props.get("MaterialLayers") == json.dumps(data.get("layers", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")) and
                  all(near(props.get(name[:-2].title() + "M", -1), data[name]) for name in TYPE_DIMENSIONS[category]))
        if not _native_material(data):
            continue
        relations = [relation for relation in typ.HasAssociations if relation.is_a("IfcRelAssociatesMaterial")]
        material = relations[0].RelatingMaterial if len(relations) == 1 else None
        native_type_materials[identifier] = material
        if data.get("layers"):
            valid = material is not None and material.is_a("IfcMaterialLayerSet")
            layers = material.MaterialLayers if valid else ()
            valid = valid and len(layers) == len(data["layers"])
            if valid:
                valid = all(layer.Material == native_materials.get(expected["material_id"], (None, {}))[0] and
                            near(layer.LayerThickness, expected["thickness_m"]) and
                            (layer.Category or "") == expected["role"]
                            for layer, expected in zip(layers, data["layers"]))
            check("type-material-layers:" + identifier, valid)
        else:
            check("type-material:" + identifier,
                  material == native_materials.get(data["material_id"], (None, {}))[0] and material is not None)
    for data, category in authored_products:
        identifier, type_id = data["id"], data.get("type_id")
        obj = find(identifier, "Ifc" + category)
        if not obj:
            continue
        assigned_type = element.get_type(obj)
        check("product-type:" + identifier, (assigned_type is not None and assigned_type.GlobalId == global_id(type_id))
              if type_id else assigned_type is None)
        typ = catalogue_types.get(type_id, {})
        if not _native_material(typ):
            continue
        relations = [relation for relation in obj.HasAssociations if relation.is_a("IfcRelAssociatesMaterial")]
        if typ.get("layers"):
            usage = relations[0].RelatingMaterial if len(relations) == 1 else None
            check("material-usage:" + identifier, usage is not None and usage.is_a("IfcMaterialLayerSetUsage") and
                  usage.ForLayerSet == native_type_materials.get(type_id) and
                  usage.LayerSetDirection == ("AXIS2" if category == "Wall" else "AXIS3") and
                  usage.DirectionSense == ("POSITIVE" if category == "Wall" else "NEGATIVE") and
                  near(usage.OffsetFromReferenceLine, 0.0 if category == "Wall" else data["thickness_m"]))
        else:
            check("material-inheritance:" + identifier, not relations and
                  element.get_material(obj) == native_type_materials.get(type_id))

    rows_by_element = {}
    for row in snapshot.get("material_rows", []):
        rows_by_element.setdefault(row["element_id"], []).append(row)
    material_qtos = [quantity for quantity in model.by_type("IfcElementQuantity") if quantity.Name == "BIM3117_MaterialQuantities"]
    check("material-quantity-count", len(material_qtos) == len(rows_by_element))
    for identifier, rows in rows_by_element.items():
        obj = find(identifier, "IfcElement")
        if not obj:
            continue
        rows = sorted(rows, key=lambda row: row["layer_index"])
        quantities = element.get_psets(obj, qtos_only=True).get("BIM3117_MaterialQuantities", {})
        expected = {}
        for row in rows:
            prefix = "Layer" + str(row["layer_index"]) if row["layer_index"] else "Homogeneous"
            expected.update({prefix + name: row[key] for name, key in
                             (("GrossVolume", "gross_volume_m3"), ("DeductionVolume", "deduction_volume_m3"), ("NetVolume", "net_volume_m3"))})
        check("material-quantities:" + identifier, set(quantities)-{"id"} == set(expected) and
              all(near(quantities.get(name, -1), value) for name, value in expected.items()))
        props = element.get_psets(obj).get("BIM3117_MaterialSource", {})
        check("material-quantity-source:" + identifier, props.get("ContentRevision") == snapshot["content_revision"] and
              props.get("QuantityRule") == rows[0]["quantity_rule"] and
              props.get("Rows") == json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    settings = module.geom.settings()
    # Local geometry makes volume validation robust against large translations.
    settings.set("use-world-coords", False)
    meshes = {}

    def mesh(obj, expected_volume, identifier, role, expected_bounds=None):
        try:
            shape = module.geom.create_shape(settings, obj)
            flat = shape.geometry.verts
            vertices = [tuple(float(flat[i+j]) for j in range(3)) for i in range(0, len(flat), 3)]
            faces = list(shape.geometry.faces)
            valid = bool(vertices and faces) and len(faces) % 3 == 0
            volume = _mesh_volume(vertices, faces) if valid else 0.0
            matrix = placements.get_local_placement(obj.ObjectPlacement)
            world = [tuple(sum(matrix[i, j]*point[j] for j in range(3))+matrix[i, 3]
                           for i in range(3)) for point in vertices]
            bounds = [[min(p[i] for p in world) for i in range(3)],
                      [max(p[i] for p in world) for i in range(3)]] if world else []
            geometry_report.append({"id": identifier, "ifc_class": role, "volume_m3": volume,
                                    "expected_volume_m3": expected_volume, "world_bounds_m": bounds})
            check("geometry:" + identifier, valid and volume > 0 and near(volume, expected_volume),
                  {"volume_m3": volume, "expected_volume_m3": expected_volume})
            if expected_bounds is not None:
                check("geometry-bounds:" + identifier, bool(bounds) and
                      all(near(bounds[side][axis], expected_bounds[side][axis])
                          for side in range(2) for axis in range(3)),
                      {"world_bounds_m": bounds, "native_bounds_m": expected_bounds})
            meshes[identifier] = (vertices, faces)
        except Exception as error:
            check("geometry:" + identifier, False, str(error))

    for data in walls.values():
        obj = find(data["id"], "IfcWall")
        if not obj:
            continue
        sx, sy = data["start_m"]
        ex, ey = data["end_m"]
        axis = ((ex-sx)/data["length_m"], (ey-sy)/data["length_m"], 0)
        assigned, container = element.get_type(obj), element.get_container(obj)
        props = element.get_psets(obj).get("BIM3117_Source", {})
        check("wall-semantics:" + data["id"], source_matches(obj, data) and
              assigned is not None and assigned.GlobalId == global_id(data["type_id"]) and
              container is not None and container.GlobalId == global_id(data["base_level_id"]) and
              props.get("TopLevelUUID") == data["top_level_id"] and
              near(props.get("BaseOffsetM", math.inf), data["base_offset_m"]) and
              near(props.get("TopOffsetM", math.inf), data["top_offset_m"]))
        check("wall-placement:" + data["id"], position(obj, (sx, sy, data["base_z_m"]), axis))
        qto = element.get_psets(obj, qtos_only=True).get("Qto_WallBaseQuantities", {})
        expected_qto = {"Length": data["length_m"], "Width": data["thickness_m"], "Height": data["height_m"],
                        "GrossSideArea": data["quantities"]["gross_side_area_m2"],
                        "NetSideArea": data["quantities"]["net_side_area_m2"],
                        "GrossVolume": data["quantities"]["gross_volume_m3"],
                        "NetVolume": data["quantities"]["net_volume_m3"]}
        check("wall-quantities:" + data["id"], all(near(qto.get(key, -1), value) for key, value in expected_qto.items()))
        mesh(obj, data["quantities"]["net_volume_m3"], data["id"], "IfcWall")
    window_ids = {item["id"] for item in snapshot.get("windows", [])}
    for data in snapshot["doors"] + snapshot.get("windows", []):
        is_window = data["id"] in window_ids
        category = "IfcWindow" if is_window else "IfcDoor"
        prefix = "window" if is_window else "door"
        obj, opening = find(data["id"], category), find(opening_id(data["id"]), "IfcOpeningElement")
        if not obj or not opening:
            continue
        host = walls[data["host_id"]]
        sx, sy = host["start_m"]
        ex, ey = host["end_m"]
        ux, uy = (ex-sx)/host["length_m"], (ey-sy)/host["length_m"]
        padding = max(1e-6, host["thickness_m"]*1e-6)
        x, z = data["offset_m"], host["base_z_m"]+data["sill_m"]
        door_position = (sx+ux*x, sy+uy*x, z)
        opening_position = (door_position[0]+uy*padding, door_position[1]-ux*padding, z)
        container = element.get_container(obj)
        check(prefix + "-relations:" + data["id"], len(obj.FillsVoids) == 1 and
              obj.FillsVoids[0].RelatingOpeningElement == opening and len(opening.VoidsElements) == 1 and
              opening.VoidsElements[0].RelatingBuildingElement.GlobalId == global_id(data["host_id"]) and
              container is not None and container.GlobalId == global_id(host["base_level_id"]) and
              not getattr(opening, "ContainedInStructure", ()))
        check(prefix + "-source-size:" + data["id"], source_matches(obj, data) and
              near(obj.OverallWidth, data["width_m"]) and near(obj.OverallHeight, data["height_m"]))
        check(prefix + "-placement:" + data["id"], position(obj, door_position, (ux, uy, 0)) and
              position(opening, opening_position, (ux, uy, 0)))
        mesh(obj, data["frame_volume_m3"], data["id"], category)
        if data["host_id"] in meshes:
            vertices, faces = meshes[data["host_id"]]
            # Check several interior depths and locations in the actual IFC cut.
            probes = [(data["offset_m"]+data["width_m"]*fraction,
                       host["thickness_m"]*depth, data["sill_m"]+data["height_m"]*height)
                      for fraction, height in ((0.2, 0.2), (0.5, 0.5), (0.8, 0.8))
                      for depth in (0.1, 0.5, 0.9)]
            check("opening-empty:" + data["id"], all(not _inside_mesh(p, vertices, faces) for p in probes))

    slab_data = {item["id"]: item for item in snapshot.get("slabs", [])}

    def swept_matches(solid, vertices, height, location=(0, 0, 0)):
        """Match the serialized swept profile, not only its volume or bounds."""
        if not solid.is_a("IfcExtrudedAreaSolid") or not near(solid.Depth, height):
            return False
        matrix = placements.get_axis2placement(solid.Position)
        if any(not near(matrix[i, 3], location[i]) for i in range(3)):
            return False
        if any(not near(matrix[i, j], 1.0 if i == j else 0.0) for i in range(3) for j in range(3)):
            return False
        extrusion = solid.ExtrudedDirection.DirectionRatios
        if len(extrusion) != 3 or not all(near(a, b) for a, b in zip(extrusion, (0, 0, 1))):
            return False
        profile = solid.SweptArea
        if not profile.is_a("IfcArbitraryClosedProfileDef") or profile.ProfileType != "AREA" or not profile.OuterCurve.is_a("IfcPolyline"):
            return False
        expected = list(vertices)
        if expected[0] != expected[-1]:
            expected.append(expected[0])
        actual = [point.Coordinates for point in profile.OuterCurve.Points]
        return (len(actual) == len(expected) and all(len(p) == 2 for p in actual)
                and all(near(a, b) for p, q in zip(actual, expected) for a, b in zip(p, q)))

    def join_cutters_match(obj, data, origin, axis, category):
        """Check the base primitive and each subtraction against its source.

        Volumes/bounds alone cannot distinguish equal-volume cuts at different
        locations. This checks the actual serialized IFC boolean operands.
        """
        try:
            representation = next(item for item in obj.Representation.Representations
                                  if item.RepresentationIdentifier == "Body")
            joins = data.get("join_slab_ids", [])
            if len(representation.Items) != 1 or representation.RepresentationType != ("CSG" if joins else "SweptSolid"):
                return False
            current = representation.Items[0]
            for slab_id in reversed(joins):
                if not current.is_a("IfcBooleanResult") or current.Operator != "DIFFERENCE":
                    return False
                slab = slab_data[slab_id]
                expected_z = slab["base_z_m"] - origin[2]
                ux, uy = axis[:2]
                expected = [(ux*(x-origin[0])+uy*(y-origin[1]), -uy*(x-origin[0])+ux*(y-origin[1]))
                            for x, y in slab["boundary_m"]]
                if not swept_matches(current.SecondOperand, expected, slab["thickness_m"], (0, 0, expected_z)):
                    return False
                current = current.FirstOperand
            if category == "Slab":
                return swept_matches(current, data["boundary_m"], data["thickness_m"])
            width = data["width_m"] if category == "Column" else data["length_m"]
            depth = data["depth_m"] if category == "Column" else data["width_m"]
            height = data["height_m"] if category == "Column" else data["depth_m"]
            location = (-width/2, -depth/2, 0) if category == "Column" else (0, -depth/2, 0)
            return swept_matches(current, [(0, 0), (width, 0), (width, depth), (0, depth)], height, location)
        except (AttributeError, RuntimeError, StopIteration, TypeError):
            return False

    for key, category in (("slabs", "Slab"), ("columns", "Column"), ("beams", "Beam")):
        for data in snapshot.get(key, []):
            obj = find(data["id"], "Ifc" + category)
            if not obj:
                continue
            if category == "Slab":
                level_id, origin, axis = data["level_id"], (0, 0, data["base_z_m"]), (1, 0, 0)
            elif category == "Column":
                level_id = data["base_level_id"]
                angle = math.radians(data["rotation_deg"])
                origin, axis = (data["x_m"], data["y_m"], data["base_z_m"]), (math.cos(angle), math.sin(angle), 0)
            else:
                level_id = data["level_id"]
                sx, sy = data["start_m"]
                ex, ey = data["end_m"]
                origin, axis = (sx, sy, data["base_z_m"]), ((ex-sx)/data["length_m"], (ey-sy)/data["length_m"], 0)
            container = element.get_container(obj)
            props = element.get_psets(obj).get("BIM3117_Source", {})
            joins = data.get("join_slab_ids", [])
            material = element.get_material(obj)
            check(category.lower()+"-semantics:"+data["id"], source_matches(obj, data) and
                  container is not None and container.GlobalId == global_id(level_id) and
                  props.get("JoinSlabUUIDs", "") == "|".join(joins) and
                  near(props.get("JoinDeductionM3", -1), data["quantities"].get("join_deduction_m3", 0.0)) and
                  props.get("MaterialDescription", "") == data.get("material", "") and
                  (_native_material(catalogue_types.get(data.get("type_id"), {})) or not data.get("material", "").strip() or
                   (material and material.Name == data["material"])))
            check(category.lower()+"-placement:"+data["id"], position(obj, origin, axis))
            qto = element.get_psets(obj, qtos_only=True).get("Qto_"+category+"BaseQuantities", {})
            values = data["quantities"]
            expected_qto = {"GrossVolume": values["gross_volume_m3"], "NetVolume": values["net_volume_m3"]}
            if category == "Slab":
                expected_qto.update(Depth=data["thickness_m"], Perimeter=values["perimeter_m"],
                                    GrossArea=values["gross_area_m2"], NetArea=values["net_area_m2"])
            else:
                expected_qto.update(Length=data["height_m"] if category == "Column" else data["length_m"],
                                    CrossSectionArea=data["width_m"]*data["depth_m"])
            check(category.lower()+"-quantities:"+data["id"], all(near(qto.get(name, -1), value) for name, value in expected_qto.items()))
            check("join-cutters:"+data["id"], join_cutters_match(obj, data, origin, axis, category))
            mesh(obj, values["net_volume_m3"], data["id"], "Ifc"+category, data["native_bounds_m"])
    express = {"requested": bool(express_rules), "status": "not_requested",
               "reason": "Optional full EXPRESS rules require pytest in the validation environment"}
    if express_rules:
        express_logger = module.validate.json_logger()
        try:
            module.validate.validate(model, express_logger, express_rules=True)
            messages = [str(item.get("message", "")) for item in express_logger.statements]
            express = {"requested": True, "status": "passed" if not messages else "failed", "messages": messages}
            check("express-rules", not messages, messages)
        except Exception as error:
            express = {"requested": True, "status": "failed", "reason": str(error)}
            check("express-rules", False, str(error))
    passed = sum(item["status"] == "passed" for item in checks)
    return {"status": "passed" if passed == len(checks) else "failed", "schema": model.schema,
            "ifcopenshell_version": str(module.version), "source_content_revision": snapshot["content_revision"],
            "checks_passed": passed, "checks": checks, "geometry": geometry_report, "express_rules": express,
            "external_application_review": "not established by this validator"}
