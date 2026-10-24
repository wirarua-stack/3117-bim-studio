"""Launch one unchanged packaged public macro in a fresh attested GUI process."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
import zipfile

TASK = Path(__file__).resolve().parent
HOST_TASK = Path('/tmp/bim3117-host-fix')
ASSETS = Path('/tmp/bim3117-freecad')
DISPLAY = ':130'
FROZEN_ZIP_SHA256 = 'ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7'
MACRO_FILES = {'install': 'Install_3117_BIM_Studio.FCMacro',
               'publicmacro': 'Run_3117_Exchange_Test.FCMacro',
               'publicbuilding': 'Run_3117_Building_Test.FCMacro',
               'publicarchitecture': 'Run_3117_Architecture_Test.FCMacro',
               'publicsmoke': 'Run_3117_Smoke_Test.FCMacro',
               'publicdrawings': 'Run_3117_Drawings_Test.FCMacro',
               'publictypes': 'Run_3117_Types_Test.FCMacro'}
REPORT_FILES = {'install': 'packaged-installer-gui-report.json',
                'publicmacro': 'public-exchange-macro-report.json',
                'publicbuilding': 'public-building-macro-report.json',
                'publicarchitecture': 'public-architecture-macro-report.json',
                'publicsmoke': 'public-smoke-macro-report.json',
                'publicdrawings': 'public-drawings-macro-report.json',
                'publictypes': 'public-types-macro-report.json'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        return {'status': 'invalid_json_report', 'error': str(error)}


def stop_owned_group(process):
    """Stop only the process group created with start_new_session=True here."""
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def check_owned_xkb_helper():
    marker = read_json(HOST_TASK / 'owned-xkb-helper.json')
    path = Path(marker.get('path', '/nonexistent-owned-helper'))
    target = ASSETS / 'xvfb/root/usr/bin/xkbcomp'
    if (str(path) != '/usr/bin/xkbcomp' or marker.get('target') != str(target)
            or not path.is_symlink() or os.readlink(path) != str(target)):
        raise RuntimeError('The root task-owned xkbcomp helper is unavailable; this runner does not create or modify system helpers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('mode', choices=MACRO_FILES)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--host-manifest', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    mode = args.mode
    run_root = args.run_root.resolve(strict=True)
    if not run_root.is_relative_to((TASK / 'runs').resolve()):
        parser.error('--run-root must be inside this isolated package-gui/runs directory')
    host_manifest = args.host_manifest.resolve(strict=True)
    expected_host = read_json(host_manifest)
    host = expected_host.get('host_command')
    if not isinstance(host, list) or not host or not all(isinstance(item, str) for item in host):
        parser.error('Host manifest must contain the compiled host argv')
    digest = sha(archive)
    if digest != FROZEN_ZIP_SHA256:
        parser.error('The archive is not the exact frozen v0.5.0 ZIP')
    output = run_root / 'evidence'
    output.mkdir(exist_ok=True)
    process_path = output / ('package-' + mode + '-process.json')
    report_path = output / REPORT_FILES[mode]
    log_path = output / ('package-' + mode + '-gui.log')
    if any(path.exists() for path in (process_path, report_path, log_path)):
        parser.error('This stage already has evidence; use a new batch run name')
    case = run_root / 'ทดสอบ_แพ็กเกจ_โฮสต์แก้ไข_v050' / digest[:12]
    profile = case / 'โปรไฟล์_ทดสอบ'
    extracted = case / 'แตกไฟล์'
    record = {'stage': mode, 'status': 'starting', 'started_utc': utc(), 'exit_code': None,
              'timed_out': False, 'zip_sha256': digest, 'archive': str(archive), 'profile': str(profile),
              'report': str(report_path), 'host_manifest': str(host_manifest),
              'host_manifest_sha256': sha(host_manifest),
              'autopilot_sha256': sha(TASK / 'package_autopilot.FCMacro'),
              'runner_sha256': sha(Path(__file__))}
    app = xvfb = None
    report = {}
    try:
        check_owned_xkb_helper()
        if Path('/tmp/.X11-unix/X130').exists() or Path('/tmp/.X130-lock').exists():
            raise RuntimeError('Display :130 already exists; no existing server or lock is modified')
        for item in [expected_host['executable'], *expected_host['libraries'].values()]:
            if sha(item['path']) != item['sha256']:
                raise RuntimeError('Pinned host binary changed before this stage: ' + item['path'])
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            if not all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names):
                raise RuntimeError('Unsafe ZIP member path')
            roots = {name.split('/')[0] for name in names}
            if len(roots) != 1:
                raise RuntimeError('Expected one package root')
            package_root_name = roots.pop()
            root = extracted / package_root_name
            if not root.exists():
                package.extractall(extracted)
            manifest = json.loads((root / 'MANIFEST.json').read_text())
            if manifest['version'] != '0.5.0':
                raise RuntimeError('Unexpected package version')
            if not all(sha(root / name) == value for name, value in manifest['sha256'].items()):
                raise RuntimeError('Extracted package differs from the frozen manifest')
            macro = root / MACRO_FILES[mode]
            original_macro_bytes = package.read(package_root_name + '/' + MACRO_FILES[mode])
            if macro.read_bytes() != original_macro_bytes:
                raise RuntimeError('Public macro differs from the frozen ZIP')
        record.update(public_macro=str(macro), public_macro_sha256=sha(macro),
                      frozen_public_macro_sha256=hashlib.sha256(original_macro_bytes).hexdigest(),
                      frozen_public_macro_bytes_unchanged=True)
        env = dict(os.environ)
        for name in ('PYTHONHOME', 'PYTHONPATH', 'FREECAD_USER_HOME', 'FREECAD_USER_DATA',
                     'FREECAD_USER_TEMP', 'QT_QPA_PLATFORM', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
            env.pop(name, None)
        for name, child in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
            folder = profile / child
            folder.mkdir(parents=True, exist_ok=True)
            env[name] = str(folder)
        fonts = profile / 'data' / 'fonts'
        fonts.mkdir(parents=True, exist_ok=True)
        for source in (root / 'workbench/bim3117_freecad/fonts').glob('*.ttf'):
            destination = fonts / source.name
            if not destination.exists():
                shutil.copy2(source, destination)
        env.update(DISPLAY=DISPLAY, QTWEBENGINE_DISABLE_SANDBOX='1', LIBGL_ALWAYS_SOFTWARE='1',
                   FONTCONFIG_FILE='/etc/fonts/fonts.conf', FONTCONFIG_PATH='/etc/fonts',
                   PYTHONPATH=str(HOST_TASK / 'ifc-runtime'), PYTHONDONTWRITEBYTECODE='1',
                   BIM3117_PACKAGE_ROOT=str(root), BIM3117_PACKAGE_EVIDENCE=str(output),
                   BIM3117_PACKAGE_STAGE=mode, BIM3117_PACKAGE_SHA256=digest,
                   BIM3117_HOST_MANIFEST=str(host_manifest), BIM3117_HOST_MANIFEST_SHA256=sha(host_manifest))
        if args.trace:
            env['BIM3117_PACKAGE_TRACE'] = '1'
        xenv = dict(env)
        xenv['LD_LIBRARY_PATH'] = str(ASSETS / 'xvfb/root/usr/lib/x86_64-linux-gnu') + ':' + str(ASSETS / 'squashfs-root/usr/lib')
        xenv['XKB_BINDIR'] = str(ASSETS / 'xvfb/root/usr/bin')
        with (output / ('package-' + mode + '-xvfb.log')).open('w', encoding='utf-8') as xlog:
            xvfb = subprocess.Popen([str(ASSETS / 'xvfb/root/usr/bin/Xvfb'), DISPLAY, '-screen', '0', '1440x1000x24',
                                     '-nolisten', 'tcp', '-noreset', '-ac'], env=xenv,
                                    stdin=subprocess.DEVNULL, stdout=xlog, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                for _ in range(100):
                    if xvfb.poll() is not None:
                        raise RuntimeError('Xvfb failed; inspect its stage log')
                    if Path('/tmp/.X11-unix/X130').exists():
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Xvfb socket did not become available')
                command = [*host, '-u', str(profile / 'user.cfg'),
                           str(TASK / 'package_autopilot.FCMacro'), str(macro)]
                record['command'] = command
                with log_path.open('w', encoding='utf-8') as log:
                    app = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    record['pid'] = app.pid
                    print('FreeCAD package check', mode, 'pid', app.pid, flush=True)
                    try:
                        record['exit_code'] = app.wait(timeout=args.timeout)
                    except subprocess.TimeoutExpired:
                        record['timed_out'] = True
                        stop_owned_group(app)
                        record['exit_code'] = app.returncode
            finally:
                stop_owned_group(app)
                stop_owned_group(xvfb)
        report = read_json(report_path)
        start = read_json(output / ('package-' + mode + '-host-start.json'))
        end = read_json(output / ('package-' + mode + '-host-end.json'))
        record.update(raw_report_status=report.get('status'), host_attestation_start=start,
                      host_attestation_end=end, host_attested=(start.get('status') == 'passed' and end.get('status') == 'passed'))
        log_text = log_path.read_text(errors='replace')
        record.update(native_sigsegv_in_log=('SIGSEGV' in log_text or 'Segmentation fault' in log_text),
                      handleChildren3D_in_log='handleChildren3D' in log_text, gui_log_sha256=sha(log_path))
        if record['timed_out']:
            record['status'] = 'timed_out'
        elif record['exit_code'] != 0:
            record['status'] = 'failed_process'
        elif record['native_sigsegv_in_log']:
            record['status'] = 'failed_native_signal'
        elif not record['host_attested']:
            record['status'] = 'failed_host_attestation'
        elif report.get('status') != 'passed':
            record['status'] = 'failed_assertion' if report.get('status') == 'failed' else 'missing_completed_report'
        else:
            record['status'] = 'passed'
        if sha(archive) != digest or sha(macro) != record['public_macro_sha256']:
            raise RuntimeError('Frozen archive or extracted public macro changed during execution')
        for item in [expected_host['executable'], *expected_host['libraries'].values()]:
            if sha(item['path']) != item['sha256']:
                raise RuntimeError('Pinned host changed during the stage: ' + item['path'])
    except BaseException as error:
        record.update(status='failed_harness', error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        stop_owned_group(app)
        stop_owned_group(xvfb)
        record['finished_utc'] = utc()
        process_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exit_code': record['exit_code'], 'status': record['status'],
                      'raw_report_status': report.get('status'), 'checks': report.get('checks_passed'),
                      'zip_sha256': digest, 'error': record.get('error') or report.get('error'),
                      'report': str(report_path)}, ensure_ascii=False), flush=True)
    if record['status'] != 'passed' and log_path.exists():
        print(log_path.read_text(errors='replace')[-5000:], flush=True)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
