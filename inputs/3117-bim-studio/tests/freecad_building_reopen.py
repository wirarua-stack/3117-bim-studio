# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed-host restore of the v0.3.0 two-storey authoring fixture."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def main(output_dir):
    output = Path(output_dir)
    report = {"status":"running","freecad":App.Version(),"python":sys.version,
              "platform":platform.platform(),"gui_up":bool(App.GuiUp),"checks":[]}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name":name,"status":"passed"})

    def near(actual, expected):
        return abs(float(actual)-float(expected)) < max(1e-8,abs(float(expected))*1e-8)

    try:
        previous=json.loads((output/"building-test-report.json").read_text(encoding="utf-8"))
        check("source Building Authoring suite passed", previous["status"]=="passed")
        sample=Path(previous["sample"])
        check("source FCStd matches its recorded file hash", hashlib.sha256(sample.read_bytes()).hexdigest()==previous["sample_sha256"])
        check("new element proxies are not preregistered in this fresh process", "bim3117_freecad.elements" not in sys.modules)
        doc=App.openDocument(str(sample));doc.recompute()
        from bim3117_freecad import services,snapshot,exchange
        from bim3117_freecad.model import kind
        project=services.get_project(doc)
        check("all native proxy kinds restore from the installed add-on",
              all(getattr(obj,"Proxy",None) is not None and not isinstance(obj.Proxy,str) for obj in doc.Objects))
        check("all authored and derived UUIDs survive restore",
              {obj.Name:obj.BIM3117Id for obj in doc.Objects}==previous["element_ids"])
        data=snapshot.capture(project)
        check("content revision survives fresh-process recompute",data["content_revision"]==previous["content_revision"])
        for category,values in previous["expected_net_volumes_m3"].items():
            check(f"restored {category} volumes match independent fixture values",
                  all(near((services.wall_body(obj) if category=="Wall" else obj).Shape.Volume/1e9,values[obj.BIM3117Id])
                      for obj in doc.Objects if kind(obj)==category))
        beams=services.list_beams(project);columns=services.list_columns(project)
        check("all directed slab joins restore their references",all(len(obj.JoinSlabs)==1 for obj in beams+columns))
        check("window hosts restore alongside Door relationships",
              all(window.Host in services.list_walls(project) for window in services.list_windows(project)))
        slab=next(obj for obj in services.list_slabs(project) if near(obj.Level.Elevation.Value,3000))
        services.edit_slab(slab,thickness_mm=200)
        changed=snapshot.capture(project)
        check("editing a restored slab updates joined members and content revision",
              changed["content_revision"]!=data["content_revision"]
              and all(near(beam.Shape.BoundBox.ZMax,2800) for beam in beams if slab in beam.JoinSlabs)
              and all(near(column.Shape.BoundBox.ZMax,2800) for column in columns if slab in column.JoinSlabs))
        doc.undo();doc.recompute()
        check("Undo after fresh restore returns the canonical revision",snapshot.capture(project)["content_revision"]==data["content_revision"])
        result=exchange.export_ifc(project,output/"Building_Authoring_Reopened.ifc",overwrite=True)
        import ifcopenshell
        old=ifcopenshell.open(str(output/"Building_Authoring_Workbench.ifc"));new=ifcopenshell.open(result["files"][0])
        classes=("IfcSlab","IfcColumn","IfcBeam","IfcWall","IfcDoor","IfcWindow","IfcOpeningElement")
        check("fresh export preserves every authored and opening GlobalId",
              all({item.GlobalId for item in old.by_type(name)}=={item.GlobalId for item in new.by_type(name)} for name in classes))
        check("fresh exported IFC passes native geometry/metadata validation",result["validation"]["status"]=="passed")
        check("read edit Undo and export never overwrite the source sample",hashlib.sha256(sample.read_bytes()).hexdigest()==previous["sample_sha256"])
        report.update(status="passed",checks_passed=len(report["checks"]),content_revision=data["content_revision"],
                      sample=str(sample),ifc_result=result)
        return report
    except BaseException as error:
        report.update(status="failed",error=str(error),traceback=traceback.format_exc(),checks_passed=len(report["checks"]))
        raise
    finally:
        (output/"building-reopen-test-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
