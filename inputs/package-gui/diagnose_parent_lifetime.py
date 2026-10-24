#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare transient and retained main-window wrapper lifetimes on the same host.

This supplemental diagnostic uses separate fresh profiles, no 3117 installation,
no model commands, and no modifications to the host or frozen public tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import run_package_batch as batch
import run_package_check as launch

TASK = Path(__file__).resolve().parent

MACRO = r'''
import hashlib, json, os, traceback
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
import shiboken6

_output = Path(os.environ['PARENT_WRAPPER_EVIDENCE'])
_expected = json.loads(Path(os.environ['PARENT_WRAPPER_HOST']).read_text())
_retain = os.environ['PARENT_WRAPPER_RETAIN'] == '1'
_retained_main_window = Gui.getMainWindow() if _retain else None

def _run():
    report = {'status': 'running', 'retain_parent': _retain,
              'freecad': App.Version(), 'qt': QtCore.qVersion(),
              'scope': 'No model commands; compare the same temporary-parent tree expression with an optional persistent main-window wrapper',
              'trees': [], 'host': {}}
    try:
        executable = Path('/proc/self/exe').resolve(strict=True)
        report['host']['executable'] = {'path': str(executable),
            'sha256': hashlib.sha256(Path('/proc/self/exe').read_bytes()).hexdigest()}
        assert report['host']['executable'] == _expected['executable']
        maps = []
        for line in Path('/proc/self/maps').read_text().splitlines():
            parts = line.split(maxsplit=5)
            if len(parts) == 6 and parts[5].startswith('/'):
                maps.append((parts[5], int(parts[4])))
        for name, expected in _expected['libraries'].items():
            matches = [row for row in maps if Path(row[0]).name == name or Path(row[0]).name.startswith(name + '.')]
            path = Path(expected['path'])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert {str(Path(row[0]).resolve(strict=True)) for row in matches} == {str(path)}
            assert {row[1] for row in matches} == {path.stat().st_ino}
            assert digest == expected['sha256']
            report['host'][name] = {'path': str(path), 'sha256': digest,
                'mapped_inodes': sorted({row[1] for row in matches}), 'matches': True}
        # Match the original smoke test's expression; do not prefetch, replace,
        # filter, or cache the child wrappers before this exact iteration.
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            row = {'python_type': type(tree).__name__, 'is_valid': shiboken6.isValid(tree)}
            report['trees'].append(row)
            try:
                tree.expandAll()
                row['expand_all'] = 'returned'
                row['object_name'] = tree.objectName()
                row['cpp_class'] = tree.metaObject().className()
            except Exception as error:
                row['expand_all'] = 'raised'
                row['error'] = str(error)
        report['status'] = 'observation_complete'
    except BaseException as error:
        report.update(status='diagnostic_failed', error=str(error), traceback=traceback.format_exc())
    (_output / 'parent-wrapper-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PARENT_WRAPPER_DIAGNOSIS', json.dumps(report), flush=True)
    QtCore.QTimer.singleShot(100, QtWidgets.QApplication.quit)

QtCore.QTimer.singleShot(1500, _run)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', required=True)
    args = parser.parse_args()
    if not args.run_name.replace('-', '').isalnum():
        parser.error('Use an alphanumeric diagnostic run name')
    root = TASK / 'runs' / args.run_name
    if root.exists():
        parser.error('Previous evidence is never overwritten')
    evidence = root / 'evidence'
    evidence.mkdir(parents=True)
    manifest = evidence / 'expected-host.json'
    expected = batch.pin_host()
    batch.write_json(manifest, expected)
    macro = evidence / 'parent-wrapper.FCMacro'
    macro.write_text(MACRO)
    summary = {'status': 'running', 'scope': __doc__, 'expected_host': expected,
               'launcher_sha256': batch.sha(Path(__file__)), 'macro_sha256': batch.sha(macro), 'cases': []}
    launch.check_owned_xkb_helper()
    for retain in (False, True):
        if Path('/tmp/.X11-unix/X130').exists() or Path('/tmp/.X130-lock').exists():
            raise RuntimeError('Display :130 is already in use')
        name = 'retained' if retain else 'temporary'
        out = evidence / name
        out.mkdir()
        profile = root / 'profiles' / name
        env = dict(os.environ)
        for key in ('PYTHONHOME', 'PYTHONPATH', 'FREECAD_USER_HOME', 'FREECAD_USER_DATA', 'FREECAD_USER_TEMP',
                    'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
            env.pop(key, None)
        for key, child in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
            folder = profile / child
            folder.mkdir(parents=True)
            env[key] = str(folder)
        env.update(DISPLAY=':130', QTWEBENGINE_DISABLE_SANDBOX='1', LIBGL_ALWAYS_SOFTWARE='1',
                   PYTHONDONTWRITEBYTECODE='1', PARENT_WRAPPER_EVIDENCE=str(out),
                   PARENT_WRAPPER_HOST=str(manifest), PARENT_WRAPPER_RETAIN='1' if retain else '0')
        xenv = dict(env)
        xenv['LD_LIBRARY_PATH'] = str(launch.ASSETS / 'xvfb/root/usr/lib/x86_64-linux-gnu') + ':' + str(launch.ASSETS / 'squashfs-root/usr/lib')
        xenv['XKB_BINDIR'] = str(launch.ASSETS / 'xvfb/root/usr/bin')
        command = [*expected['host_command'], '-u', str(profile / 'user.cfg'), str(macro)]
        record = {'case': name, 'retain_parent': retain, 'command': command, 'exit_code': None, 'timed_out': False}
        app = xvfb = None
        try:
            with (out / 'xvfb.log').open('w') as xlog, (out / 'gui.log').open('w') as log:
                xvfb = subprocess.Popen([str(launch.ASSETS / 'xvfb/root/usr/bin/Xvfb'), ':130', '-screen', '0',
                    '1440x1000x24', '-nolisten', 'tcp', '-noreset', '-ac'], env=xenv, stdin=subprocess.DEVNULL,
                    stdout=xlog, stderr=subprocess.STDOUT, start_new_session=True)
                for _ in range(100):
                    if xvfb.poll() is not None:
                        raise RuntimeError('Xvfb exited')
                    if Path('/tmp/.X11-unix/X130').exists():
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Xvfb socket unavailable')
                app = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    record['exit_code'] = app.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    record['timed_out'] = True
        finally:
            launch.stop_owned_group(app)
            launch.stop_owned_group(xvfb)
            record['cleanup'] = {'app_exited': app is None or app.poll() is not None,
                                 'xvfb_exited': xvfb is None or xvfb.poll() is not None}
        record['report'] = launch.read_json(out / 'parent-wrapper-report.json')
        record['native_sigsegv_in_log'] = 'SIGSEGV' in (out / 'gui.log').read_text(errors='replace')
        batch.write_json(out / 'external-outcome.json', record)
        summary['cases'].append(record)
        batch.write_json(evidence / 'main-window-lifetime-diagnosis.json', summary)
        print(json.dumps({'case': name, 'exit_code': record['exit_code'], 'report': record['report']}), flush=True)
    batch.host_unchanged(expected)
    summary['status'] = 'diagnostic_observation_complete'
    summary['host_binaries_unchanged'] = True
    batch.write_json(evidence / 'main-window-lifetime-diagnosis.json', summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
