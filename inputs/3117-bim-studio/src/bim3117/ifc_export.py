# SPDX-License-Identifier: GPL-3.0-or-later
"""IFC4 snapshot for the reference model. Requires optional IfcOpenShell.

Walls are separate extrusions, not junction-resolved solids. Doors have a
simplified rectangular leaf, not a production door family. IFC entities,
types, storey containment, void/fill relations and SI quantities are real.

API references:
https://docs.ifcopenshell.org/ifcopenshell-python/geometry_creation.html
https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/feature/add_feature/index.html
https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/feature/add_filling/index.html
"""
from pathlib import Path
from uuid import UUID, uuid5
import numpy as np
import ifcopenshell
import ifcopenshell.guid
from ifcopenshell.api import aggregate, context, feature, geometry, pset, root, spatial, unit
from ifcopenshell.api import type as ifc_type
from .io import atomic_path


def guid(uuid_text):
    return ifcopenshell.guid.compress(UUID(uuid_text).hex)


def export_ifc(document, path):
    document.validate()
    model = ifcopenshell.file(schema="IFC4")
    namespace = UUID(document.id)

    def entity(ifc_class, name, identity=None, key=None):
        obj = root.create_entity(model, ifc_class=ifc_class, name=name)
        obj.GlobalId = guid(identity or str(uuid5(namespace, key or name)))
        return obj

    project = entity("IfcProject", document.name, document.id)
    units = [unit.add_si_unit(model, unit_type=kind) for kind in
             ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    unit.assign_unit(model, units=units)
    model_context = context.add_context(model, context_type="Model")
    model_context.Precision = 1e-6
    body = context.add_context(model, context_type="Model", context_identifier="Body",
                               target_view="MODEL_VIEW", parent=model_context)
    site = entity("IfcSite", "Reference site", key="site")
    building = entity("IfcBuilding", "Reference building", key="building")
    aggregate.assign_object(model, products=[site], relating_object=project)
    aggregate.assign_object(model, products=[building], relating_object=site)
    geometry.edit_object_placement(model, product=site)
    geometry.edit_object_placement(model, product=building)
    levels, types, walls = {}, {}, {}
    for level in document.levels.values():
        obj = entity("IfcBuildingStorey", level.name, level.id)
        obj.Elevation = level.elevation
        obj.CompositionType = "ELEMENT"
        aggregate.assign_object(model, products=[obj], relating_object=building)
        matrix = np.eye(4)
        matrix[2, 3] = level.elevation
        geometry.edit_object_placement(model, product=obj, matrix=matrix, is_si=True)
        levels[level.id] = obj
    for typ in document.wall_types.values():
        obj = entity("IfcWallType", typ.name, typ.id)
        obj.PredefinedType = "STANDARD"
        properties = pset.add_pset(model, product=obj, name="BIM3117_WallType")
        pset.edit_pset(model, pset=properties, properties={"Thickness": typ.thickness,
                                                         "ThicknessUnit": "m"})
        types[typ.id] = obj

    def placement(wall, offset=0.0, transverse=0.0, sill=0.0):
        length, _, _, elevation = document.wall_dimensions(wall)
        x = (wall.end[0] - wall.start[0]) / length
        y = (wall.end[1] - wall.start[1]) / length
        matrix = np.eye(4)
        matrix[:3, 0] = (x, y, 0.0)
        matrix[:3, 1] = (-y, x, 0.0)
        matrix[:3, 3] = (wall.start[0] + offset*x - transverse*y,
                         wall.start[1] + offset*y + transverse*x, elevation + sill)
        return matrix

    quantities = {row["element_id"]: row for row in document.quantities()}
    for wall in document.walls.values():
        length, thickness, height, _ = document.wall_dimensions(wall)
        obj = entity("IfcWall", wall.name, wall.id)
        ifc_type.assign_type(model, related_objects=[obj], relating_type=types[wall.type_id])
        spatial.assign_container(model, products=[obj], relating_structure=levels[wall.base_level_id])
        representation = geometry.add_wall_representation(model, context=body, length=length,
                                                          height=height, thickness=thickness)
        geometry.assign_representation(model, product=obj, representation=representation)
        geometry.edit_object_placement(model, product=obj, matrix=placement(wall), is_si=True)
        row = quantities[wall.id]
        qto = pset.add_qto(model, product=obj, name="Qto_WallBaseQuantities")
        pset.edit_qto(model, qto=qto, properties={"Length": length, "Width": thickness,
             "Height": height, "GrossSideArea": row["gross_side_area_m2"],
             "NetSideArea": row["net_side_area_m2"], "GrossVolume": row["gross_volume_m3"],
             "NetVolume": row["net_volume_m3"]})
        walls[wall.id] = obj
    for door in document.doors.values():
        wall = document.walls[door.host_id]
        _, thickness, _, _ = document.wall_dimensions(wall)
        opening = entity("IfcOpeningElement", f"Opening - {door.name}",
                         str(uuid5(UUID(door.id), "opening")))
        opening.PredefinedType = "OPENING"
        representation = geometry.add_wall_representation(model, context=body, length=door.width,
                           height=door.height, thickness=thickness + 0.02)
        geometry.assign_representation(model, product=opening, representation=representation)
        geometry.edit_object_placement(model, product=opening,
            matrix=placement(wall, door.offset, -0.01, door.sill), is_si=True)
        feature.add_feature(model, feature=opening, element=walls[wall.id])
        obj = entity("IfcDoor", door.name, door.id)
        obj.OverallWidth, obj.OverallHeight = door.width, door.height
        obj.PredefinedType, obj.OperationType = "DOOR", "NOTDEFINED"
        spatial.assign_container(model, products=[obj], relating_structure=levels[wall.base_level_id])
        leaf_thickness = min(0.04, thickness)
        representation = geometry.add_wall_representation(model, context=body, length=door.width,
                                         height=door.height, thickness=leaf_thickness)
        geometry.assign_representation(model, product=obj, representation=representation)
        geometry.edit_object_placement(model, product=obj,
            matrix=placement(wall, door.offset, (thickness - leaf_thickness) / 2, door.sill), is_si=True)
        feature.add_filling(model, opening=opening, element=obj)
    with atomic_path(path) as temporary:
        model.write(str(temporary))
    return model
