from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

archive = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
macro_files = {'install': 'Install_3117_BIM_Studio.FCMacro',
               'publicmacro': 'Run_3117_Exchange_Test.FCMacro',
               'publicbuilding': 'Run_3117_Building_Test.FCMacro',
               'publicarchitecture': 'Run_3117_Architecture_Test.FCMacro',
               'publicsmoke': 'Run_3117_Smoke_Test.FCMacro',
               'publicdrawings': 'Run_3117_Drawings_Test.FCMacro',
               'publictypes': 'Run_3117_Types_Test.FCMacro'}
report_files = {'install': 'packaged-installer-gui-report.json',
                'publicmacro': 'public-exchange-macro-report.json',
                'publicbuilding': 'public-building-macro-report.json',
                'publicarchitecture': 'public-architecture-macro-report.json',
                'publicsmoke': 'public-smoke-macro-report.json',
                'publicdrawings': 'public-drawings-macro-report.json',
                'publictypes': 'public-types-macro-report.json'}
assert mode in macro_files
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
task = Path('/tmp/bim3117-release-v050')
assets = Path('/tmp/bim3117-freecad')
case = task / 'ทดสอบ_แพ็กเกจ_v050' / digest[:12]
profile = case / 'โปรไฟล์_ทดสอบ'
output = task / 'evidence'
output.mkdir(parents=True, exist_ok=True)
extracted = case / 'แตกไฟล์'
with zipfile.ZipFile(archive) as package:
    names = package.namelist()
    assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names)
    roots = {name.split('/')[0] for name in names}
    assert len(roots) == 1
    root = extracted / roots.pop()
    if not root.exists():
        package.extractall(extracted)
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    assert manifest['version'] == '0.5.0'
    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == value
               for name, value in manifest['sha256'].items())
env = dict(os.environ)
for name in ('PYTHONHOME', 'PYTHONPATH', 'FREECAD_USER_HOME', 'FREECAD_USER_DATA', 'FREECAD_USER_TEMP'):
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
env.update(DISPLAY=':108', QTWEBENGINE_DISABLE_SANDBOX='1', LIBGL_ALWAYS_SOFTWARE='1',
           FONTCONFIG_FILE='/etc/fonts/fonts.conf', FONTCONFIG_PATH='/etc/fonts',
           BIM3117_PACKAGE_ROOT=str(root), BIM3117_PACKAGE_EVIDENCE=str(output),
           BIM3117_PACKAGE_STAGE=mode, BIM3117_PACKAGE_SHA256=digest)
if len(sys.argv) > 3 and sys.argv[3] == 'trace':
    env['BIM3117_PACKAGE_TRACE'] = '1'
macro = root / macro_files[mode]
report_name = report_files[mode]
report_path = output / report_name
if report_path.exists():
    report_path.unlink()
xenv = dict(env)
xenv['LD_LIBRARY_PATH'] = str(assets / 'xvfb/root/usr/lib/x86_64-linux-gnu') + ':' + str(assets / 'squashfs-root/usr/lib')
xenv['XKB_BINDIR'] = str(assets / 'xvfb/root/usr/bin')
with (output / ('package-' + mode + '-xvfb.log')).open('w') as xlog:
    xvfb = subprocess.Popen([str(assets / 'xvfb/root/usr/bin/Xvfb'), ':108', '-screen', '0', '1440x1000x24',
                             '-nolisten', 'tcp', '-noreset', '-ac'], env=xenv, stdout=xlog, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            if xvfb.poll() is not None:
                raise RuntimeError('Xvfb failed')
            if Path('/tmp/.X11-unix/X108').exists():
                break
            time.sleep(.1)
        log_path = output / ('package-' + mode + '-gui.log')
        with log_path.open('w') as log:
            app = subprocess.Popen([str(assets / 'squashfs-root/AppRun'), '-u', str(profile / 'user.cfg'),
                                    str(task / 'package_autopilot.FCMacro'), str(macro)], env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            try:
                print('FreeCAD package check', mode, 'pid', app.pid, flush=True)
                exit_code = app.wait(timeout=300)
            except subprocess.TimeoutExpired:
                app.terminate()
                try:
                    app.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    app.kill()
                exit_code = 124
    finally:
        xvfb.terminate()
        try:
            xvfb.wait(timeout=5)
        except subprocess.TimeoutExpired:
            xvfb.kill()
report = json.loads(report_path.read_text()) if report_path.exists() else {}
process_record = {'stage': mode, 'exit_code': exit_code, 'status': report.get('status'),
                  'zip_sha256': digest, 'archive': str(archive), 'profile': str(profile),
                  'public_macro': str(macro), 'report': str(report_path),
                  'autopilot_sha256': hashlib.sha256((task / 'package_autopilot.FCMacro').read_bytes()).hexdigest(),
                  'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(output / ('package-' + mode + '-process.json')).write_text(
    json.dumps(process_record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'exit_code': exit_code, 'status': report.get('status'),
                  'checks': report.get('checks_passed'), 'zip_sha256': digest,
                  'error': report.get('error'), 'report': str(report_path)}, ensure_ascii=False))
print(log_path.read_text(errors='replace')[-3000:] if report.get('status') != 'passed' else 'Exact packaged macro and installed file hashes passed')
assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
sys.exit(0 if exit_code == 0 and report.get('status') == 'passed' else 1)
