import json,traceback
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from freecad_types_gui import TypesGuiDriver, exercise_panel_coexistence, installed_ui_fingerprint

def run(output_dir):
 output=Path(output_dir);output.mkdir(exist_ok=True)
 report={'status':'running','checks':[],'steps':[],'checks_passed':0}
 driver=TypesGuiDriver(report); doc=None
 def step(s):
  report['steps'].append(s); print('PROBE_A',s,flush=True)
  (output/'probe-a-report.json').write_text(json.dumps(report,indent=2))
 def check(s,condition):
  step(s+': '+str(condition));assert condition,s
  report['checks'].append({'name':s,'status':'passed'});report['checks_passed']=len(report['checks'])
 try:
  doc=App.openDocument('/tmp/bim3117-v050-ui/evidence-final/Types_Quantities_Workbench.FCStd');doc.recompute();doc.UndoMode=1
  Gui.activateWorkbench('BIM3117Workbench')
  from bim3117_freecad import catalog,services,schedules
  from ui3117.catalog_panel import panel_for_document as catalogue_for_document
  from ui3117.schedule_panel import show_schedules
  project=services.get_project(doc)
  schedule=next(o for o in schedules.list_schedules(project) if o.Label=='Column Schedule')
  panel=show_schedules(project,schedule)
  driver.command('BIM3117_Catalogue');cat=catalogue_for_document(doc.Name)
  material=next(o for o in catalog.list_materials(project) if o.Label=='Concrete')
  cat.tabs.setCurrentIndex(1);cat.refresh();cat.materials_table.selectRow(cat._materials.index(material))
  step('before real duplicate material form')
  driver.action(cat.duplicateMaterialButton.click,'DuplicateMaterialDialog',{'nameEdit':'Concrete Copy'})
  copied=next(o for o in catalog.list_materials(project) if o.Label=='Concrete Copy')
  cat.refresh();cat.materials_table.selectRow(cat._materials.index(copied))
  step('before real delete material button')
  cat.deleteMaterialButton.click();step('material deleted')
  Gui.runCommand('Std_Undo');doc.recompute();Gui.updateGui();step('Undo deletion')
  Gui.runCommand('Std_Undo');doc.recompute();Gui.updateGui();step('Undo creation')
  cat.refresh();panel.refresh();step('before new type branch with two readers')
  exercise_panel_coexistence(driver,project,panel,check,report)
  step('after full real type Undo Redo roundtrip')
  report['status']='passed';report['installed_ui']=installed_ui_fingerprint()
 except BaseException as error:
  report.update(status='failed',error=str(error),traceback=traceback.format_exc());raise
 finally:
  (output/'probe-a-report.json').write_text(json.dumps(report,indent=2))
  driver.close()
  if doc is not None and doc.Name in App.listDocuments():App.closeDocument(doc.Name)
 return report
