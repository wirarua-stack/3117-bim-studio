# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed FreeCAD acceptance for native shared types and ordered materials."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App

from bim3117_freecad import catalog, services, snapshot
from bim3117_freecad.model import FoundationError, kind, mm
from bim3117_freecad import building, elements


def near(actual, expected):
    return abs(float(actual)-float(expected)) <= max(1e-7, abs(float(expected))*1e-8)


def observation(doc):
    result = []
    for obj in doc.Objects:
        item = [obj.Name, obj.Label, kind(obj), getattr(obj, "BIM3117Id", "")]
        for prop in ("Code", "Material", "MaterialRefId", "ElementTypeId", "WallTypeId", "HostId",
                     "LayerMaterialIds", "LayerThicknesses", "LayerRoles"):
            item.append(getattr(obj, prop, None))
        for prop in ("Thickness", "Width", "Height", "Depth", "Offset", "Sill", "StartX", "StartY", "EndX", "EndY"):
            item.append(mm(obj, prop) if prop in obj.PropertiesList else None)
        if "Shape" in obj.PropertiesList:
            shape = obj.Shape
            item.append(shape.isNull())
            if not shape.isNull():
                box = shape.BoundBox
                item.append([round(value, 6) for value in (shape.Volume, box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax)])
        result.append(item)
    return result


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Native materials/types, shared dimensions, complete proposal preflight and FCStd"}
    documents = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    def rejects(name, operation):
        try:
            operation()
        except FoundationError:
            check(name, True)
        else:
            raise AssertionError(name + ": accepted")

    def undo(doc):
        doc.undo(); doc.recompute()

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("core modules load from the isolated installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed)
                  for module in (catalog, services, snapshot, building, elements)))
        project = services.create_project("Type catalogue acceptance", "TQ-050", "3117 BIM")
        doc = project.Document; documents.append(doc.Name)
        base, top = services.list_levels(project)
        concrete = catalog.create_material(project, "คอนกรีต", "CONC")
        finish = catalog.create_material(project, "Finish", "FIN")
        steel = catalog.create_material(project, "Steel", "STL")
        check("materials are persistent native project members with UUID and code",
              kind(concrete) == "Material" and concrete in project.Group
              and catalog.material_definition(concrete) == {"id": concrete.BIM3117Id, "name": "คอนกรีต", "code": "CONC"})
        before_undo = doc.UndoCount
        material_copy = catalog.duplicate_material(concrete,"Concrete copy")
        check("material duplication is one transaction with new identity and empty code",
              doc.UndoCount==before_undo+1 and material_copy.BIM3117Id!=concrete.BIM3117Id and material_copy.Code=="")
        copy_name = material_copy.Name
        catalog.delete_material(material_copy)
        check("unused material deletion removes only the selected entry",doc.getObject(copy_name) is None and concrete in project.Group)
        rejects("duplicate material codes are rejected", lambda: catalog.create_material(project, "Duplicate code", "CONC"))
        rejects("nonpositive layer thickness is rejected before creation",
                lambda: catalog.create_type(project, "Invalid layer", "Slab", layers=[{"material": concrete, "thickness_mm": 0}]))
        rejects("layers on frame types are rejected", lambda: catalog.create_type(project, "Invalid frame", "Door",
                layers=[{"material": concrete, "thickness_mm": 20}]))
        rejects("material and layers cannot be independent competing authorities", lambda: catalog.create_type(project, "Conflict", "Slab",
                material=concrete, layers=[{"material": finish, "thickness_mm": 20}]))
        wall_type = catalog.create_type(project, "Wall layered", "Wall", code="W200", layers=[
            {"material": finish, "thickness_mm": 20, "role": "Finish"},
            {"material": concrete, "thickness_mm": 160, "role": "Core"},
            {"material": finish, "thickness_mm": 20, "role": "Finish"}])
        check("ordered layers retain repeated material identity and determine total thickness",
              wall_type.LayerMaterialIds == [finish.BIM3117Id, concrete.BIM3117Id, finish.BIM3117Id]
              and wall_type.LayerThicknesses == [20,160,20] and near(wall_type.Thickness.Value,200))
        wall = services.create_wall(project, "Wall A", wall_type, base, top, end_x_mm=6000)
        door = services.create_door(project, "Door A", wall, offset_mm=500)
        window = services.create_window(project, "Window A", wall, offset_mm=3000)
        door_type = catalog.create_type(project, "Door 900", "Door", width_mm=900, height_mm=2100, material=steel, code="D900")
        window_type = catalog.create_type(project, "Window 1200", "Window", width_mm=1200, height_mm=1200, material=steel)
        catalog.assign_type(door,door_type); catalog.assign_type(window,window_type)
        check("typed openings resolve dimensions and native material from their types",
              catalog.instance_type(door) == door_type and near(door.Width.Value,900)
              and door.Material == steel.Label and window.Material == steel.Label)
        doc.clearUndos()
        prior = snapshot.capture(project)["content_revision"]
        old_volume = wall.Body.Shape.Volume
        catalog.edit_type(door_type,width_mm=1000)
        changed = snapshot.capture(project)["content_revision"]
        check("a shared opening edit is one transaction and updates the real wall cut",
              doc.UndoCount == 1 and near(door.Width.Value,1000)
              and near(old_volume-wall.Body.Shape.Volume,100*2100*200) and changed != prior)
        undo(doc)
        check("Undo restores shared dimensions native solids and original content hash",
              near(door.Width.Value,900) and near(wall.Body.Shape.Volume,old_volume)
              and snapshot.capture(project)["content_revision"] == prior)
        before, redo = observation(doc), doc.RedoCount
        rejects("typed instance dimensional mismatch is rejected before mutation", lambda: services.edit_door(door,width_mm=999))
        check("rejected typed instance edit preserves complete native state and Redo", observation(doc) == before and doc.RedoCount == redo)
        doc.redo(); doc.recompute()
        check("prior Redo remains executable after the rejected command", near(door.Width.Value,1000))
        services.edit_door(door,width_mm=1000,offset_mm=600)
        check("equal legacy dialog echoes are accepted while instance location stays editable", near(door.Offset.Value,600))
        before_width = door.Width.Value
        door.Width = 700
        check("raw typed dimensional writes are restored without a second authority", near(door.Width.Value,before_width))
        old_layers = list(wall_type.LayerThicknesses)
        wall_type.LayerThicknesses = [30,160,20]
        check("raw layer vector writes cannot bypass atomic layer validation", list(wall_type.LayerThicknesses) == old_layers)
        old_category = str(door_type.Category)
        door_type.Category = "Slab"
        check("native type category is immutable", str(door_type.Category) == old_category)
        doc.recompute()
        rejects("assigned type deletion is guarded", lambda: catalog.delete_type(door_type))
        rejects("referenced native material deletion is guarded", lambda: catalog.delete_material(finish))
        rejects("wrong-category assignment is rejected", lambda: catalog.assign_type(door,window_type))
        rejects("required instance references cannot silently become missing", lambda: services.edit_door(door,host=None))
        rejects("walls cannot detach their required WallType", lambda: catalog.assign_type(wall,None))
        clone = catalog.duplicate_type(door_type,"Door alternate")
        check("duplicate type gets a distinct UUID and independent empty code",
              clone.BIM3117Id != door_type.BIM3117Id and clone.Code == "" and near(clone.Width.Value,door_type.Width.Value)
              and clone.MaterialRef == steel)
        doc.clearUndos()
        catalog.edit_instance(door,{"name":"Door combined", "element_type":clone,"offset_mm":700})
        check("type Label and placement edit together in one transaction",
              doc.UndoCount == 1 and door.Label == "Door combined" and door.ElementType == clone and near(door.Offset.Value,700))
        undo(doc)
        check("combined row Undo restores all edited fields", door.Label == "Door A" and door.ElementType == door_type and near(door.Offset.Value,600))
        catalog.assign_type(door,None)
        check("detach preserves effective dimensions and material and restores editable native fields",
              door.ElementType is None and door.ElementTypeId == "" and near(door.Width.Value,1000)
              and door.Material == steel.Label and "ReadOnly" not in door.getEditorMode("Width"))
        services.edit_door(door,width_mm=950)
        check("detached dimensional editing changes the real opening", near(door.Width.Value,950))
        catalog.assign_type(door,door_type)
        clone_name = clone.Name
        catalog.delete_type(clone)
        check("unused duplicate type can be deleted", clone_name not in [obj.Name for obj in doc.Objects])
        legacy_type = services.create_wall_type(project,"Legacy text",180,"Legacy block")
        legacy_clone = catalog.duplicate_type(legacy_type,"Legacy text copy")
        check("legacy WallType duplication preserves its descriptive text", legacy_clone.Material == "Legacy block")
        catalog.delete_type(legacy_clone)

        slab_type = catalog.create_type(project,"Slab 150","Slab",layers=[
            {"material": finish,"thickness_mm":30,"role":"Top"},
            {"material": concrete,"thickness_mm":120,"role":"Core"}])
        slab = services.create_slab(project,"Floor main",top,[(-500,-500),(6500,-500),(6500,4000),(-500,4000)])
        column = services.create_column(project,"Column A",base,top,x_mm=1500,y_mm=1500)
        beam = services.create_beam(project,"Beam A",top,start_mm=(0,2500),end_mm=(6000,2500))
        column_type = catalog.create_type(project,"Column 300x400","Column",width_mm=300,depth_mm=400,material=concrete)
        beam_type = catalog.create_type(project,"Beam 300x450","Beam",width_mm=300,depth_mm=450,material=concrete)
        catalog.assign_type(slab,slab_type); catalog.assign_type(column,column_type); catalog.assign_type(beam,beam_type)
        services.join_slab(column,slab); services.join_slab(beam,slab)
        check("typed member dimensions drive gross geometry and directed cuts",
              near(column.Shape.Volume,300*400*2850) and near(beam.Shape.Volume,6000*300*300))
        doc.clearUndos()
        catalog.edit_type(slab_type,layers=[{"material":finish,"thickness_mm":50,"role":"Top"},
                                         {"material":concrete,"thickness_mm":150,"role":"Core"}])
        check("layer edit fans out to slab geometry and both joined member kinds in one transaction",
              doc.UndoCount == 1 and near(slab.Thickness.Value,200)
              and near(column.Shape.Volume,300*400*2800) and near(beam.Shape.Volume,6000*300*250))
        undo(doc)
        check("layer edit Undo restores original cutter and member volumes", near(slab.Thickness.Value,150)
              and near(column.Shape.Volume,300*400*2850) and near(beam.Shape.Volume,6000*300*300))
        catalog.edit_type(column_type,width_mm=350)
        catalog.edit_type(beam_type,depth_mm=500)
        check("Column and Beam shared section changes rebuild their joined native solids",
              near(column.Shape.Volume,350*400*2850) and near(beam.Shape.Volume,6000*300*350))
        catalog.edit_material(concrete,name="Concrete renamed",code="C-NEW")
        check("native material rename propagates through homogeneous and layered types",
              column.Material == "Concrete renamed" and "Concrete renamed" in slab.Material
              and wall_type.MaterialRef is None and "Concrete renamed" in wall_type.Material)
        concrete.Label = "Concrete raw rename"; doc.recompute()
        check("raw valid material rename refreshes derived type and instance descriptions",
              column.Material == "Concrete raw rename" and "Concrete raw rename" in slab.Material)

        # Each individual replacement cutter is safe; their combined replacement
        # removes the whole member. A serial one-cutter preflight misses this.
        cutter_type = catalog.create_type(project,"Shared cutter 100","Slab",thickness_mm=100,material=concrete)
        left = services.create_slab(project,"Cutter left",top,[(0,4500),(3000,4500),(3000,5500),(0,5500)],thickness_mm=100)
        right = services.create_slab(project,"Cutter right",top,[(3000,4500),(6000,4500),(6000,5500),(3000,5500)],thickness_mm=100)
        catalog.assign_types([left,right],cutter_type)
        joined = services.create_beam(project,"Union cutter beam",top,start_mm=(0,5000),end_mm=(6000,5000),depth_mm=450)
        services.join_slab(joined,left); services.join_slab(joined,right)
        check("fixture single-cutter proposals are individually valid",
              all(len(elements.expected_solid(joined,slab_overrides={item.BIM3117Id:elements.slab_edit_solid(item,{"Thickness":450})}).Solids)==1
                  for item in (left,right)))
        catalog.edit_type(cutter_type,thickness_mm=150); undo(doc)
        before, redo = observation(doc), doc.RedoCount
        rejects("combined shared-type cutters cannot remove an entire member", lambda: catalog.edit_type(cutter_type,thickness_mm=450))
        check("combined cutter rejection leaves prior solids type and Redo intact", observation(doc)==before and doc.RedoCount==redo and redo>0)
        doc.redo(); doc.recompute()
        check("successful shared cutter Redo rebuilds both cutters and one connected member",
              near(left.Thickness.Value,150) and near(right.Thickness.Value,150) and near(joined.Shape.Volume,6000*300*300))

        # Both windows grow in X and Z. Either proposal alone stays disjoint, but
        # their combined rectangles overlap at the diagonally opposed corners.
        diagonal_wall = services.create_wall(project,"Diagonal opening wall",legacy_type,base,top,
                                             start_y_mm=8000,end_y_mm=8000,end_x_mm=6000)
        high = services.create_window(project,"High window",diagonal_wall,offset_mm=0,width_mm=900,height_mm=900,sill_mm=1000)
        low = services.create_window(project,"Low window",diagonal_wall,offset_mm=1000,width_mm=900,height_mm=900,sill_mm=0)
        diagonal_type = catalog.create_type(project,"Diagonal 900","Window",width_mm=900,height_mm=900,material=steel)
        catalog.assign_types([high,low],diagonal_type)
        for obj in (high,low):
            building.validate_opening_proposal(diagonal_wall,obj.Label,"Window",
                {"Offset":mm(obj,"Offset"),"Sill":mm(obj,"Sill"),"Width":1200,"Height":1200},obj)
        check("diagonal fixture proposals are individually valid",True)
        catalog.edit_type(diagonal_type,width_mm=1000,height_mm=1000); undo(doc)
        before, redo = observation(doc), doc.RedoCount
        rejects("simultaneous shared opening growth checks proposed rectangles together",
                lambda: catalog.edit_type(diagonal_type,width_mm=1200,height_mm=1200))
        check("combined opening rejection preserves both frames wall cut and Redo", observation(doc)==before and doc.RedoCount==redo and redo>0)
        doc.redo(); doc.recompute()
        check("touching shared openings remain valid after Redo", near(high.Width.Value,1000) and near(low.Height.Value,1000)
              and near(diagonal_wall.Body.Shape.Volume,(6000*3000-2*1000*1000)*180))
        diagonal_type.Width = 7000; doc.recompute()
        check("raw shared-type dimension edits validate all dependent opening bounds",
              near(diagonal_type.Width.Value,1000) and near(high.Width.Value,1000) and near(low.Width.Value,1000))

        # Raw malformed properties must be rejected on capture, then explicit
        # supported commands offer recovery without deleting the authored object.
        door.ElementType = None
        check("raw type-link clearing retains the expected UUID and invalidates geometry",
              door.ElementType is None and door.ElementTypeId == door_type.BIM3117Id and door.Shape.isNull())
        rejects("capture rejects a missing assigned type",lambda:snapshot.capture(project))
        catalog.assign_type(door,door_type)
        check("supported reassignment repairs a broken type link and real opening", not door.Shape.isNull() and door.ElementType==door_type)
        door_type.MaterialRef = None
        check("raw material reference clearing preserves its expected ID and invalidates dependent geometry",
              door_type.MaterialRefId == steel.BIM3117Id and door.Shape.isNull())
        rejects("capture rejects a missing type material reference",lambda:snapshot.capture(project))
        catalog.edit_type(door_type,material=steel)
        check("explicit material reassignment repairs type instances and upstream wall status",
              door_type.MaterialRef==steel and bool(door.Shape.Solids) and not wall.ValidationMessage)
        slab_type.LayerMaterials = []
        check("raw layer material removal retains the ordered expected IDs",
              list(slab_type.LayerMaterialIds)==[finish.BIM3117Id,concrete.BIM3117Id] and slab.Shape.isNull())
        catalog.edit_type(slab_type,layers=[{"material":finish,"thickness_mm":30,"role":"Top"},
                                         {"material":concrete,"thickness_mm":120,"role":"Core"}])
        check("explicit ordered-layer repair rebuilds slab and joined member geometry",bool(slab.Shape.Solids)
              and bool(column.Shape.Solids) and bool(beam.Shape.Solids))
        services.validate_document(doc,check_shapes=True)
        data = snapshot.capture(project)
        sample = output/"Types_Quantities_Workbench.FCStd"
        doc.saveAs(str(sample))
        report.update(status="passed", checks_passed=len(report["checks"]), sample=str(sample),
                      sample_sha256=hashlib.sha256(sample.read_bytes()).hexdigest(),
                      element_ids={obj.Name:obj.BIM3117Id for obj in doc.Objects},
                      content_revision=data["content_revision"],
                      type_definitions={obj.BIM3117Id:catalog.type_definition(obj) for obj in catalog.list_types(project)},
                      instance_types={obj.BIM3117Id:(catalog.instance_type(obj).BIM3117Id if catalog.instance_type(obj) else "")
                                      for obj in project.Group if kind(obj) in catalog.INSTANCE_KINDS},
                      native_volumes={obj.BIM3117Id:obj.Shape.Volume for obj in project.Group
                                      if kind(obj) in ("Slab","Column","Beam","Door","Window","WallBody")})
        return report
    except BaseException as error:
        report.update(status="failed",error=str(error),traceback=traceback.format_exc(),checks_passed=len(report["checks"]))
        raise
    finally:
        (output/"types-test-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        for name in documents:
            if name in App.listDocuments():
                App.closeDocument(name)
