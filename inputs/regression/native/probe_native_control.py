import json, traceback
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

def run(output_dir):
    output=Path(output_dir);output.mkdir(exist_ok=True)
    report={'status':'running','steps':[],'addon_imported':False}
    def step(s):
        report['steps'].append(s)
        print('NATIVE_PROBE',s,flush=True)
        (output/'report.json').write_text(json.dumps(report,indent=2))
    def drain():
        QtWidgets.QApplication.processEvents()
        Gui.updateGui()
    doc=App.newDocument('NativeUndoBranch')
    doc.UndoMode=1
    target=doc.addObject('App::FeaturePython','Target')
    target.Label='Original'
    doc.recompute();drain();step('baseline target')
    doc.openTransaction('Create disposable feature')
    material=doc.addObject('App::FeaturePython','Disposable')
    doc.recompute();doc.commitTransaction();drain();step('created disposable feature')
    doc.openTransaction('Delete disposable feature')
    doc.removeObject(material.Name)
    doc.recompute();doc.commitTransaction();drain();step('deleted disposable feature')
    Gui.runCommand('Std_Undo');doc.recompute();drain();step('Undo deletion')
    Gui.runCommand('Std_Undo');doc.recompute();drain();step('Undo creation')
    Gui.runCommand('Std_Redo');doc.recompute();drain();step('Redo creation')
    Gui.runCommand('Std_Redo');doc.recompute();drain();step('Redo deletion')
    assert target.Label=='Original'
    assert doc.getObject('Disposable') is None
    report['status']='passed'
    report['user_data']=App.getUserAppDataDir()
    step('all passed')
    App.closeDocument(doc.Name)
    return report
