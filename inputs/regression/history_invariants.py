"""Additional native invariants for provider removal, abort, parent and history.

The archived reproductions remain unchanged. These checks guard against fixes
that merely survive by losing transaction history or 3D group membership.
"""
import hashlib
import json
from pathlib import Path
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _scene_contains_child_root(parent, child):
    """Inspect live Coin nodes without retaining wrappers across history steps."""
    from pivy import coin

    search = coin.SoSearchAction()
    search.setNode(child.ViewObject.RootNode)
    search.setInterest(coin.SoSearchAction.FIRST)
    # Include all display switches: this checks actual scene attachment, not
    # whether camera, clipping or visibility make the child visible in pixels.
    search.setSearchingAll(True)
    search.apply(parent.ViewObject.RootNode)
    return bool(search.isFound())


def start(output_dir):
    output = Path(output_dir)
    report = {'status': 'running', 'freecad': App.Version(), 'steps': [], 'checks': [],
              'addon_modules': [name for name in sys.modules if name.startswith(('bim3117', 'ui3117'))]}
    state = {}

    def write():
        report['checks_passed'] = len(report['checks'])
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def check(name, actual, expected=True):
        if actual != expected:
            raise AssertionError((name, actual, expected))
        report['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'status': 'passed'})

    def history(name, undos, redos):
        doc = state['doc']
        check(name + ' counts', [doc.UndoCount, doc.RedoCount], [undos, redos])

    def drain():
        state['doc'].recompute()
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()

    def commit(label, callback):
        doc = state['doc']
        doc.openTransaction(label)
        callback()
        doc.recompute()
        doc.commitTransaction()
        drain()

    def native(command):
        Gui.runCommand(command)
        drain()

    def child_present(name, expected):
        doc = state['doc']
        child = doc.getObject(name)
        check(name + ' existence', child is not None, expected)
        check(name + ' model parent membership', name in [obj.Name for obj in state['parent'].Group], expected)
        if expected:
            check(name + ' native solid valid', child.Shape.isValid() and len(child.Shape.Solids) == 1)
            check(name + ' native volume', round(child.Shape.Volume, 8), 6.0)
            check(name + ' Coin scene graph contains child root', _scene_contains_child_root(state['parent'], child))

    def add_child(name):
        child = state['doc'].addObject('Part::Feature', name)
        child.Shape = Part.makeBox(1, 2, 3)
        state['parent'].addObject(child)

    def baseline():
        check('no 3117 modules imported', report['addon_modules'], [])
        doc = App.newDocument('PreservedNativeHistory')
        doc.UndoMode = 1
        parent = doc.addObject('App::Part', 'Parent')
        target = doc.addObject('Part::Feature', 'Target')
        target.Shape = Part.makeBox(10, 20, 30)
        target.Label = 'Original'
        parent.addObject(target)
        state.update(doc=doc, parent=parent, target=target)
        drain()
        history('baseline outside transaction', 0, 0)

    def prior_edit():
        commit('Keep earlier target edit', lambda: setattr(state['target'], 'Label', 'Before branch'))
        history('earlier edit retained', 1, 0)

    actions = [('baseline native 3D group and target', baseline), ('commit earlier edit', prior_edit)]

    def add_cycle(index, base_count, prior_label, next_label):
        name = 'Disposable' + str(index)

        def create():
            commit('Create ' + name, lambda: add_child(name))
            child_present(name, True)
            history('create ' + name, base_count + 1, 0)

        def delete():
            commit('Delete ' + name, lambda: state['doc'].removeObject(name))
            child_present(name, False)
            history('delete ' + name, base_count + 2, 0)

        def undo_delete():
            native('Std_Undo')
            child_present(name, True)
            history('undo deletion ' + name, base_count + 1, 1)

        def undo_create():
            native('Std_Undo')
            child_present(name, False)
            history('undo creation ' + name, base_count, 2)

        def branch():
            commit('New branch ' + str(index), lambda: setattr(state['target'], 'Label', next_label))
            child_present(name, False)
            history('new branch ' + str(index), base_count + 1, 0)

        def undo_branch():
            native('Std_Undo')
            check('undo branch label ' + str(index), state['target'].Label, prior_label)
            history('undo branch ' + str(index), base_count, 1)

        def redo_branch():
            native('Std_Redo')
            check('redo branch label ' + str(index), state['target'].Label, next_label)
            child_present(name, False)
            history('redo branch ' + str(index), base_count + 1, 0)

        actions.extend((name + ' ' + label, callback) for label, callback in (
            ('create', create), ('delete', delete), ('Undo deletion', undo_delete),
            ('Undo creation', undo_create), ('new target edit', branch),
            ('Undo edit', undo_branch), ('Redo edit', redo_branch)))

    add_cycle(1, 1, 'Before branch', 'After branch 1')

    def full_rewind_branch():
        native('Std_Undo')
        check('full rewind first label', state['target'].Label, 'Before branch')
        history('full rewind new branch', 1, 1)

    def full_rewind_prior():
        native('Std_Undo')
        check('earlier edit still undoable', state['target'].Label, 'Original')
        history('full rewind earlier edit', 0, 2)

    def full_replay_prior():
        native('Std_Redo')
        check('earlier edit still redoable', state['target'].Label, 'Before branch')
        history('full replay earlier edit', 1, 1)

    def full_replay_branch():
        native('Std_Redo')
        check('new branch still redoable', state['target'].Label, 'After branch 1')
        history('full replay new branch', 2, 0)

    actions.extend([('rewind new branch', full_rewind_branch), ('rewind earlier edit', full_rewind_prior),
                    ('replay earlier edit', full_replay_prior), ('replay new branch', full_replay_branch)])
    add_cycle(2, 2, 'After branch 1', 'After branch 2')
    add_cycle(3, 3, 'After branch 2', 'After branch 3')

    def abort_setup_create():
        commit('Create abort subject', lambda: add_child('AbortSubject'))
        history('abort subject created', 5, 0)

    def abort_setup_delete():
        commit('Delete abort subject', lambda: state['doc'].removeObject('AbortSubject'))
        history('abort subject deleted', 6, 0)

    def abort_setup_restore():
        native('Std_Undo')
        child_present('AbortSubject', True)
        history('abort subject restored pending provider', 5, 1)

    def abort_deletion():
        doc = state['doc']
        doc.openTransaction('Abort deletion after native restore')
        doc.removeObject('AbortSubject')
        doc.recompute()
        doc.abortTransaction()
        drain()
        child_present('AbortSubject', True)
        history('aborted deletion preserves creation history', 5, 0)

    def undo_abort_subject_creation():
        native('Std_Undo')
        child_present('AbortSubject', False)
        history('undo creation after aborted deletion', 4, 1)

    def branch_after_abort():
        commit('Branch after abort restoration', lambda: setattr(state['target'], 'Label', 'After abort branch'))
        history('new branch after aborted deletion', 5, 0)

    def undo_after_abort():
        native('Std_Undo')
        check('undo branch after abort label', state['target'].Label, 'After branch 3')
        history('undo branch after abort', 4, 1)

    def redo_after_abort():
        native('Std_Redo')
        check('redo branch after abort label', state['target'].Label, 'After abort branch')
        history('redo branch after abort', 5, 0)

    def abort_creation():
        doc = state['doc']
        doc.openTransaction('Abort newly created native child')
        add_child('EphemeralAborted')
        doc.recompute()
        doc.abortTransaction()
        drain()
        child_present('EphemeralAborted', False)
        history('direct rollback deletion leaves earlier history', 5, 0)

    actions.extend([('create abort subject', abort_setup_create), ('delete abort subject', abort_setup_delete),
                    ('restore abort subject to pending queue', abort_setup_restore),
                    ('abort deletion of restored child', abort_deletion),
                    ('undo restored child creation', undo_abort_subject_creation),
                    ('new branch after abort', branch_after_abort), ('Undo after abort', undo_after_abort),
                    ('Redo after abort', redo_after_abort), ('abort ephemeral creation', abort_creation)])

    def save_native():
        doc = state['doc']
        path = output / 'NativeHistoryPreserved.FCStd'
        doc.recompute()
        doc.saveAs(str(path))
        history('save retains all five surviving transactions', 5, 0)
        expected = {'sample': str(path), 'sha256': _sha(path), 'objects': sorted(obj.Name for obj in doc.Objects),
                    'target_label': state['target'].Label, 'target_volume': state['target'].Shape.Volume,
                    'parent_members': sorted(obj.Name for obj in state['parent'].Group),
                    'freecad': App.Version(), 'undo_count_before_close': doc.UndoCount}
        (output / 'persistence-expected.json').write_text(json.dumps(expected, indent=2) + '\n')
        report['persistence'] = expected

    def close_with_pending_provider():
        doc = App.newDocument('ClosePendingProvider')
        doc.UndoMode = 1
        doc.openTransaction('Create closing subject')
        subject = doc.addObject('Part::Feature', 'ClosingSubject')
        subject.Shape = Part.makeBox(1, 1, 1)
        doc.recompute()
        doc.commitTransaction()
        doc.openTransaction('Delete closing subject')
        doc.removeObject('ClosingSubject')
        doc.recompute()
        doc.commitTransaction()
        Gui.runCommand('Std_Undo')
        doc.recompute()
        Gui.updateGui()
        check('close control restored subject', doc.getObject('ClosingSubject') is not None)
        name = doc.Name
        App.closeDocument(name)
        check('close with pending provider completes', name not in App.listDocuments())
        App.setActiveDocument(state['doc'].Name)

    def final_existing_document_roundtrip():
        native('Std_Undo')
        history('surviving document Undo after other close', 4, 1)
        check('surviving document undo label', state['target'].Label, 'After branch 3')
        native('Std_Redo')
        history('surviving document Redo after other close', 5, 0)
        check('surviving document redo label', state['target'].Label, 'After abort branch')
        check('surviving solid volume', round(state['target'].Shape.Volume, 8), 6000.0)
        check('saved bytes unchanged after live history operations', _sha(report['persistence']['sample']), report['persistence']['sha256'])
        name = state['doc'].Name
        App.closeDocument(name)
        check('main test document closes', name not in App.listDocuments())

    actions.extend([('save native FCStd without losing history', save_native),
                    ('close another document with pending provider', close_with_pending_provider),
                    ('surviving document native roundtrip and close', final_existing_document_roundtrip)])
    actions = iter(actions)

    def advance():
        try:
            name, action = next(actions)
        except StopIteration:
            report['status'] = 'passed'
            write()
            QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
            return
        try:
            report['steps'].append('before ' + name)
            print('INVARIANT', 'before', name, flush=True)
            write()
            action()
            report['steps'].append('after ' + name)
            write()
        except BaseException as error:
            report.update(status='failed', error=str(error), traceback=traceback.format_exc())
            write()
            traceback.print_exc()
            for name in tuple(App.listDocuments()):
                App.closeDocument(name)
            QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
            return
        QtCore.QTimer.singleShot(500, advance)

    write()
    QtCore.QTimer.singleShot(500, advance)


def reopen(output_dir, source_dir):
    output = Path(output_dir)
    expected = json.loads((Path(source_dir) / 'persistence-expected.json').read_text())
    sample = Path(expected['sample'])
    report = {'status': 'running', 'freecad': App.Version(), 'checks': []}
    doc = None

    def check(name, actual, wanted=True):
        if actual != wanted:
            raise AssertionError((name, actual, wanted))
        report['checks'].append({'name': name, 'actual': actual, 'expected': wanted, 'status': 'passed'})

    try:
        check('saved bytes verified before fresh restore', _sha(sample), expected['sha256'])
        doc = App.openDocument(str(sample))
        doc.recompute()
        check('fresh process restores native object names', sorted(obj.Name for obj in doc.Objects), expected['objects'])
        check('fresh process restores target label', doc.Target.Label, expected['target_label'])
        check('fresh process restores actual solid volume', round(doc.Target.Shape.Volume, 8), round(expected['target_volume'], 8))
        check('fresh process native solid valid', doc.Target.Shape.isValid() and len(doc.Target.Shape.Solids) == 1)
        check('fresh process restores model parent members', sorted(obj.Name for obj in doc.Parent.Group), expected['parent_members'])
        for name in expected['parent_members']:
            check('fresh process Coin scene graph contains ' + name + ' root',
                  _scene_contains_child_root(doc.Parent, doc.getObject(name)))
        doc.UndoMode = 1
        check('new process starts with empty session history', [doc.UndoCount, doc.RedoCount], [0, 0])
        doc.openTransaction('Fresh process label edit')
        doc.Target.Label = 'Fresh edit'
        doc.recompute()
        doc.commitTransaction()
        check('fresh edit adds one native transaction', [doc.UndoCount, doc.RedoCount], [1, 0])
        Gui.runCommand('Std_Undo')
        doc.recompute()
        Gui.updateGui()
        check('fresh native Undo restores label', doc.Target.Label, expected['target_label'])
        Gui.runCommand('Std_Redo')
        doc.recompute()
        Gui.updateGui()
        check('fresh native Redo restores edit', doc.Target.Label, 'Fresh edit')
        check('fresh native roundtrip retains one transaction', [doc.UndoCount, doc.RedoCount], [1, 0])
        check('fresh editing does not overwrite saved fixture', _sha(sample), expected['sha256'])
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        report['checks_passed'] = len(report['checks'])
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
