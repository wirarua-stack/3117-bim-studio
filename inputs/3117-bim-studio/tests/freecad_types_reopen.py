# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed-host restore and legacy hash compatibility for v0.5.0."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def main(output_dir):
    output = Path(output_dir)
    report = {"status":"running", "freecad":App.Version(), "python":sys.version,
              "platform":platform.platform(), "gui_up":bool(App.GuiUp), "checks":[]}
    documents = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name":name,"status":"passed"})

    def near(actual, expected):
        return abs(float(actual)-float(expected)) < max(1e-7,abs(float(expected))*1e-8)

    try:
        previous=json.loads((output/"types-test-report.json").read_text(encoding="utf-8"))
        check("source type/material suite passed",previous["status"]=="passed")
        sample=Path(previous["sample"])
        check("FCStd file matches recorded source bytes",hashlib.sha256(sample.read_bytes()).hexdigest()==previous["sample_sha256"])
        check("catalogue proxies are not preregistered in this fresh process","bim3117_freecad.catalog" not in sys.modules)
        doc=App.openDocument(str(sample));documents.append(doc.Name);doc.recompute()
        from bim3117_freecad import services,catalog,snapshot
        from bim3117_freecad.model import kind
        project=services.get_project(doc)
        check("all native proxies restore through installed modules",all(getattr(obj,"Proxy",None) is not None and not isinstance(obj.Proxy,str) for obj in doc.Objects))
        check("all authored and derived UUIDs survive save and restore",{obj.Name:obj.BIM3117Id for obj in doc.Objects}==previous["element_ids"])
        check("ordered material and type definitions survive restore",
              {obj.BIM3117Id:catalog.type_definition(obj) for obj in catalog.list_types(project)}==previous["type_definitions"])
        check("all six categories retain their native type links and expected IDs",
              {obj.BIM3117Id:(catalog.instance_type(obj).BIM3117Id if catalog.instance_type(obj) else "")
               for obj in project.Group if kind(obj) in catalog.INSTANCE_KINDS}==previous["instance_types"])
        check("all native frame cut and member volumes survive restore",
              all(near(obj.Shape.Volume,previous["native_volumes"][obj.BIM3117Id]) for obj in project.Group
                  if obj.BIM3117Id in previous["native_volumes"]))
        revision=snapshot.capture(project)["content_revision"]
        check("authored content revision survives fresh process recompute",revision==previous["content_revision"])
        check("typed dimensional properties restore read-only editor modes",
              all("ReadOnly" in obj.getEditorMode(prop) for obj in project.Group
                  if kind(obj) in catalog.CATEGORIES[1:] and catalog.instance_type(obj) is not None
                  for prop in catalog.DIMENSIONS[kind(obj)]))
        cutter=next(obj for obj in catalog.list_types(project,"Slab") if obj.Label=="Shared cutter 100")
        joined=next(obj for obj in services.list_beams(project) if obj.Label=="Union cutter beam")
        old=joined.Shape.Volume
        catalog.edit_type(cutter,thickness_mm=180)
        check("freshly restored shared cutter type updates both slabs and joined beam",near(joined.Shape.Volume,6000*300*270)
              and all(near(obj.Thickness.Value,180) for obj in catalog.type_dependents(cutter)))
        doc.undo();doc.recompute()
        check("Undo after restore returns the original geometry and hash",near(joined.Shape.Volume,old) and snapshot.capture(project)["content_revision"]==revision)
        check("editing restored objects does not overwrite the source FCStd",hashlib.sha256(sample.read_bytes()).hexdigest()==previous["sample_sha256"])

        root=Path(__file__).resolve().parents[1]
        fixtures=[("exchange/Quantity_Exchange_Workbench.FCStd","exchange/exchange-snapshot.json"),
                  ("building/Building_Authoring_Workbench.FCStd","building/building-snapshot.json")]
        for native_name,json_name in fixtures:
            source=root/"examples"/native_name
            source_bytes=hashlib.sha256(source.read_bytes()).hexdigest()
            expected=json.loads((root/"examples"/json_name).read_text(encoding="utf-8"))["content_revision"]
            olddoc=App.openDocument(str(source));documents.append(olddoc.Name);olddoc.recompute()
            oldproject=services.get_project(olddoc)
            check("legacy "+native_name+" retains its exact authored hash",snapshot.capture(oldproject)["content_revision"]==expected)
            legacy=next(obj for obj in oldproject.Group if kind(obj)=="WallType")
            check("legacy restore does not silently add catalogue properties", "MaterialRef" not in legacy.PropertiesList and "LayerMaterials" not in legacy.PropertiesList)
            check("legacy source FCStd remains byte identical",hashlib.sha256(source.read_bytes()).hexdigest()==source_bytes)
            if "building/" in native_name:
                slab=services.list_slabs(oldproject)[0]
                before=slab.Thickness.Value
                services.edit_slab(slab,thickness_mm=before+10)
                check("legacy untyped slab dimensions remain directly editable",near(slab.Thickness.Value,before+10) and "ElementType" not in slab.PropertiesList)
                olddoc.undo();olddoc.recompute()
                check("legacy edit Undo recovers the exact pre-catalogue content revision",snapshot.capture(oldproject)["content_revision"]==expected)
        report.update(status="passed",checks_passed=len(report["checks"]),content_revision=revision,sample=str(sample))
        return report
    except BaseException as error:
        report.update(status="failed",error=str(error),traceback=traceback.format_exc(),checks_passed=len(report["checks"]))
        raise
    finally:
        (output/"types-reopen-test-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        for name in documents:
            if name in App.listDocuments():
                App.closeDocument(name)
