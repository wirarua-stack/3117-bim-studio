#!/usr/bin/env python3
"""Run byte-identical archived host regressions against a chosen GUI host.

Every case runs in a disposable process/profile. This is an execution harness,
not an addon workaround: it never clears or substitutes native Undo history.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
DEFAULT_REPOSITORY = Path('/workspace/scratch/9457befac3c8/3117-bim-studio')
CASES = ('minimal-native', 'timed-native', 'timed-non-python', 'unbranched-control',
         'history-invariants', 'original-3117-ui')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify_originals():
    manifest = json.loads((HERE / 'originals-sha256.json').read_text())
    for relative, expected in manifest.items():
        actual = digest(HERE / relative)
        if actual != expected['sha256']:
            raise RuntimeError('Archived regression file changed: ' + relative)
    return manifest


def profile_env(profile, extra, display):
    env = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'FREECAD_USER_HOME', 'FREECAD_USER_DATA',
                 'FREECAD_USER_TEMP', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(name, None)
    env.update(extra)
    for name, child in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
        directory = profile / child
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env.update(DISPLAY=display, QTWEBENGINE_DISABLE_SANDBOX='1', LIBGL_ALWAYS_SOFTWARE='1',
               FONTCONFIG_FILE='/etc/fonts/fonts.conf', FONTCONFIG_PATH='/etc/fonts',
               PYTHONDONTWRITEBYTECODE='1')
    return env


def macro_header(profile, output):
    return '''import sys, json, traceback, platform, hashlib
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
sys.dont_write_bytecode = True
output = Path(OUTPUT)
profile = Path(PROFILE)
def record_host():
    user_data = Path(App.getUserAppDataDir()).resolve()
    assert profile.resolve() in user_data.parents, ('Unexpected profile', str(user_data))
    maps = Path('/proc/self/maps')
    libraries = sorted({line.split()[-1] for line in maps.read_text().splitlines()
                        if '/' in line and any(name in line for name in (
                            'libFreeCAD', 'libQt6Core', 'libQt5Core', 'libCoin', 'libTKBRep'))}) if maps.exists() else []
    report = {'freecad': App.Version(), 'python': sys.version, 'qt': QtCore.qVersion(),
              'platform': platform.platform(), 'gui_up': bool(App.GuiUp),
              'user_data': str(user_data), 'loaded_libraries': libraries,
              'loaded_library_sha256': {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                        for path in libraries if Path(path).is_file()},
              'addon_modules_at_entry': [name for name in sys.modules if name.startswith(('bim3117', 'ui3117'))],
              'addon_directories': sorted(str(path) for path in (user_data / 'Mod').glob('*'))}
    (output / 'host-environment.json').write_text(json.dumps(report, indent=2) + '\\n')
def launcher_error():
    failure = {'status': 'failed', 'traceback': traceback.format_exc()}
    (output / 'launcher-error.json').write_text(json.dumps(failure, indent=2) + '\\n')
    traceback.print_exc()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
'''.replace('OUTPUT', repr(str(output))).replace('PROFILE', repr(str(profile)))


def write_macro(case, profile, output, repository, *, install=False, source_output=None):
    script = macro_header(profile, output)
    if install:
        script += '''sys.path.insert(0, INSTALLER)
def run_tests():
    try:
        record_host()
        from install_support import install
        report = {'status': 'passed', 'installation': install(REPOSITORY, App.getUserAppDataDir())}
        (output / 'install-report.json').write_text(json.dumps(report, indent=2) + '\\n')
    except BaseException:
        launcher_error()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('INSTALLER', repr(str(HERE / 'installer'))).replace('REPOSITORY', repr(str(repository)))
    elif case in ('timed-native', 'timed-non-python'):
        script += '''sys.path.insert(0, __NATIVE_PATH__)
def run_tests():
    try:
        record_host()
        from probe_variants import start
        start(str(output), VARIANT)
    except BaseException:
        launcher_error()
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('__NATIVE_PATH__', repr(str(HERE / 'native'))).replace('VARIANT', repr('feature' if case == 'timed-non-python' else 'yield'))
    elif case == 'original-3117-ui':
        script += '''sys.path.insert(0, __SUPPORT_PATH__)
sys.path.insert(0, __ORIGINAL_PATH__)
def run_tests():
    try:
        record_host()
        from freecad_types_gui_reopen import main
        report = main(str(output))
        print('ORIGINAL_GUI_RESULT', report['status'], report['checks_passed'], flush=True)
    except BaseException:
        launcher_error()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('__SUPPORT_PATH__', repr(str(HERE / 'support'))).replace('__ORIGINAL_PATH__', repr(str(HERE / 'original-ui')))
    elif case == 'history-reopen':
        script += '''sys.path.insert(0, HARNESS)
def run_tests():
    try:
        record_host()
        from history_invariants import reopen
        report = reopen(str(output), SOURCE_OUTPUT)
        print('REOPEN_RESULT', report['status'], report['checks_passed'], flush=True)
    except BaseException:
        launcher_error()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('HARNESS', repr(str(HERE))).replace('SOURCE_OUTPUT', repr(str(source_output)))
    elif case == 'history-invariants':
        script += '''sys.path.insert(0, HARNESS)
def run_tests():
    try:
        record_host()
        from history_invariants import start
        start(str(output))
    except BaseException:
        launcher_error()
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('HARNESS', repr(str(HERE)))
    else:
        module = 'probe_native_control' if case == 'unbranched-control' else 'probe_native'
        script += '''sys.path.insert(0, __NATIVE_PATH__)
def run_tests():
    try:
        record_host()
        from MODULE import run
        report = run(str(output))
        print('NATIVE_RESULT', report['status'], flush=True)
    except BaseException:
        launcher_error()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
QtCore.QTimer.singleShot(1500, run_tests)
'''.replace('__NATIVE_PATH__', repr(str(HERE / 'native'))).replace('MODULE', module)
    path = output / ('install.FCMacro' if install else 'run.FCMacro')
    compile(script, str(path), 'exec')
    path.write_text(script, encoding='utf-8')
    return path


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def launch(host, macro, profile, output, env, report_name, timeout, expected_libraries=None):
    command = [*host, '-u', str(profile / 'user.cfg'), str(macro)]
    launched = stamp()
    timed_out = False
    with (output / 'gui.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_process(process)
            code = process.returncode
    report_path = output / report_name
    raw = json.loads(report_path.read_text()) if report_path.exists() else {}
    log_text = (output / 'gui.log').read_text(errors='replace')
    status = ('timed_out' if timed_out else 'failed_process' if code != 0 else
              'failed_launcher' if (output / 'launcher-error.json').exists() else
              'passed' if raw.get('status') == 'passed' else
              'failed_assertion' if raw.get('status') == 'failed' else 'missing_completed_report')
    identity_path = output / 'host-environment.json'
    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
    actual_libraries = identity.get('loaded_library_sha256', {})
    library_checks = {path: {'expected_sha256': expected,
                             'loaded_sha256': actual_libraries.get(path),
                             'matched': actual_libraries.get(path) == expected}
                      for path, expected in (expected_libraries or {}).items()}
    identity_matches = bool(identity) and all(item['matched'] for item in library_checks.values())
    if status == 'passed' and not identity_matches:
        status = 'failed_host_identity'
    outcome = {'status': status, 'exit_code': code, 'timed_out': timed_out,
               'started_at_utc': launched, 'finished_at_utc': stamp(), 'command': command,
               'raw_report_status': raw.get('status'), 'raw_report': str(report_path),
               'last_steps': raw.get('steps', [])[-5:], 'checks_passed': raw.get('checks_passed'),
               'native_sigsegv_in_log': 'SIGSEGV' in log_text or 'Segmentation fault' in log_text,
               'handleChildren3D_in_log': 'handleChildren3D' in log_text,
               'loaded_host_identity_verified': identity_matches,
               'loaded_library_checks': library_checks,
               'macro_sha256': digest(macro), 'gui_log_sha256': digest(output / 'gui.log')}
    write_json(output / 'external-outcome.json', outcome)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-command-json', required=True, help='JSON array; no shell interpolation')
    parser.add_argument('--output', type=Path, required=True, help='New/empty task directory')
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repository', type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--host-env-json', default='{}', help='Explicit host environment overrides')
    parser.add_argument('--host-library', action='append', default=[], type=Path)
    parser.add_argument('--display', default=':129')
    parser.add_argument('--xvfb', type=Path, help='Start this Xvfb; omitted means use an existing display')
    parser.add_argument('--xvfb-libdir', action='append', default=[])
    parser.add_argument('--xkb-bindir', type=Path)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--ui-timeout', type=int, default=900)
    args = parser.parse_args()
    host = json.loads(args.host_command_json)
    extra = json.loads(args.host_env_json)
    if not isinstance(host, list) or not host or not all(isinstance(item, str) and item for item in host):
        parser.error('--host-command-json must be a nonempty string array')
    if not isinstance(extra, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in extra.items()):
        parser.error('--host-env-json must be a string-to-string object')
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error('--output must be new or empty; prior results are never overwritten')
    root.mkdir(parents=True, exist_ok=True)
    originals = verify_originals()
    cases = args.case or list(CASES)
    summary = {'status': 'running', 'tag': args.tag, 'host_command': host, 'started_at_utc': stamp(),
               'frozen_originals': originals, 'cases': {}, 'windows_status': 'not_executed',
               'host_libraries': {str(path.resolve()): digest(path) for path in args.host_library}}
    summary['harness_sha256'] = {name: digest(HERE / name) for name in ('run_regressions.py', 'history_invariants.py')}
    write_json(root / 'regression-summary.json', summary)
    xvfb = xlog = None
    try:
        if args.xvfb:
            number = args.display.split(':')[-1].split('.')[0]
            if Path('/tmp/.X11-unix/X' + number).exists() or Path('/tmp/.X' + number + '-lock').exists():
                raise RuntimeError('Requested X display already exists; no existing server or lock modified')
            xenv = dict(os.environ)
            if args.xvfb_libdir:
                xenv['LD_LIBRARY_PATH'] = ':'.join(args.xvfb_libdir)
            if args.xkb_bindir:
                xenv['XKB_BINDIR'] = str(args.xkb_bindir)
            xlog = (root / 'xvfb.log').open('w', encoding='utf-8')
            xvfb = subprocess.Popen([str(args.xvfb), args.display, '-screen', '0', '1600x1100x24',
                                     '-nolisten', 'tcp', '-noreset', '-ac'], env=xenv,
                                    stdin=subprocess.DEVNULL, stdout=xlog, stderr=subprocess.STDOUT)
            for _ in range(100):
                if xvfb.poll() is not None:
                    raise RuntimeError('Xvfb exited: ' + (root / 'xvfb.log').read_text(errors='replace'))
                if Path('/tmp/.X11-unix/X' + number).exists():
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Xvfb socket did not become available')
        for case in cases:
            print('RUN', args.tag, case, flush=True)
            verify_originals()
            case_root = root / case
            profile = case_root / 'profile'
            output = case_root / 'evidence'
            output.mkdir(parents=True)
            env = profile_env(profile, extra, args.display)
            if case == 'original-3117-ui':
                installation = case_root / 'installation'
                installation.mkdir()
                macro = write_macro(case, profile, installation, args.repository.resolve(), install=True)
                installed = launch(host, macro, profile, installation, env, 'install-report.json', args.ui_timeout,
                                   summary['host_libraries'])
                if installed['status'] != 'passed':
                    summary['cases'][case] = {'status': 'blocked_by_installation', 'installation': installed}
                    write_json(root / 'regression-summary.json', summary)
                    continue
                fixture = output / 'Types_Quantities_Workbench.FCStd'
                shutil.copy2(HERE / 'fixture/Types_Quantities_Workbench.FCStd', fixture)
                fixture_report = json.loads((HERE / 'fixture/fixture-types-gui-report.json').read_text())
                original_sample = fixture_report['sample']
                fixture_report['sample'] = str(fixture)
                write_json(output / 'types-gui-report.json', fixture_report)
                write_json(output / 'fixture-provenance.json', {
                    'sample_original_path': original_sample, 'sample_sha256': digest(fixture),
                    'original_json_sha256': digest(HERE / 'fixture/fixture-types-gui-report.json'),
                    'adjusted_json_sha256': digest(output / 'types-gui-report.json'),
                    'only_report_field_changed': 'sample', 'native_fixture_bytes_unchanged': True})
                report_name = 'types-gui-reopen-report.json'
            else:
                report_name = 'report.json'
            macro = write_macro(case, profile, output, args.repository.resolve())
            result = launch(host, macro, profile, output, env, report_name,
                            args.ui_timeout if case == 'original-3117-ui' else args.timeout,
                            summary['host_libraries'])
            if case == 'history-invariants' and result['status'] == 'passed':
                reopen_output = case_root / 'reopen-evidence'
                reopen_output.mkdir()
                reopen_macro = write_macro('history-reopen', profile, reopen_output, args.repository.resolve(),
                                           source_output=output)
                reopened = launch(host, reopen_macro, profile, reopen_output, env, 'report.json', args.timeout,
                                  summary['host_libraries'])
                result['fresh_process_reopen'] = reopened
                if reopened['status'] != 'passed':
                    result['status'] = 'failed_fresh_process_reopen'
            summary['cases'][case] = result
            print('RESULT', case, result['status'], result['exit_code'], flush=True)
            write_json(root / 'regression-summary.json', summary)
        verify_originals()
        if any(digest(HERE / name) != expected for name, expected in summary['harness_sha256'].items()):
            raise RuntimeError('Regression harness changed during execution')
        summary['status'] = 'passed' if all(result['status'] == 'passed' for result in summary['cases'].values()) else 'failed'
    except BaseException as error:
        summary.update(status='harness_error', error=str(error))
        raise
    finally:
        if xvfb is not None:
            stop_process(xvfb)
        if xlog is not None:
            xlog.close()
        summary['finished_at_utc'] = stamp()
        write_json(root / 'regression-summary.json', summary)
    print(json.dumps({'status': summary['status'], 'report': str(root / 'regression-summary.json')}), flush=True)
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
