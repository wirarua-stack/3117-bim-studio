"""Run the frozen v0.5.0 installer and six public macros on one attested host.

Each stage starts a fresh GUI process; only the isolated ZIP-specific profile is
shared. This package suite does not replace the separate history-branch gate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import traceback

STAGES = (
    ("install", "packaged-installer-gui-report.json", None),
    ("publicsmoke", "public-smoke-macro-report.json", 24),
    ("publicarchitecture", "public-architecture-macro-report.json", 43),
    ("publicmacro", "public-exchange-macro-report.json", 41),
    ("publicbuilding", "public-building-macro-report.json", 35),
    ("publicdrawings", "public-drawings-macro-report.json", 53),
    ("publictypes", "public-types-macro-report.json", 52),
)
TASK = Path(__file__).resolve().parent
HOST_TASK = Path('/tmp/bim3117-host-fix')
RUNNER = TASK / 'run_package_check.py'
AUTOPILOT = TASK / 'package_autopilot.FCMacro'
FROZEN_ZIP_SHA256 = 'ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7'
HOST_COMMAND = [str(HOST_TASK / 'bin/micromamba'), '--no-rc', 'run',
                '-r', str(HOST_TASK / 'mamba-root'), '-p', str(HOST_TASK / 'sdk'),
                str(HOST_TASK / 'build/bin/FreeCAD')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def pin_host():
    libraries = {}
    for name in ('libFreeCADGui.so', 'libFreeCADApp.so'):
        path = (HOST_TASK / 'build/lib' / name).resolve(strict=True)
        libraries[name] = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
    executable = (HOST_TASK / 'build/bin/FreeCAD').resolve(strict=True)
    return {'created_utc': utc(), 'host_command': HOST_COMMAND,
            'executable': {'path': str(executable), 'sha256': sha(executable)},
            'libraries': libraries,
            'attestation': 'Exact library paths, mapped inode and file SHA at GUI entry and completion'}


def host_unchanged(expected):
    for item in [expected['executable'], *expected['libraries'].values()]:
        if sha(item['path']) != item['sha256']:
            raise RuntimeError('Pinned host binary changed during the batch: ' + item['path'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--run-name', default='patched-host-01', help='New result/profile name; never overwrites a prior run')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_name):
        parser.error('--run-name may contain letters, digits, underscores and hyphens only')
    archive = args.archive.resolve()
    if not archive.is_file() or archive.suffix.lower() != '.zip':
        parser.error('Provide the finalized v0.5.0 FreeCAD ZIP')
    digest = sha(archive)
    if digest != FROZEN_ZIP_SHA256:
        parser.error('This gate requires the exact frozen v0.5.0 FreeCAD ZIP')
    run_root = TASK / 'runs' / args.run_name
    if run_root.exists():
        parser.error('Run name already exists; use a new --run-name to preserve earlier evidence')
    expected_host = pin_host()
    run_root.mkdir(parents=True)
    evidence = run_root / 'evidence'
    evidence.mkdir()
    manifest_path = evidence / 'expected-host.json'
    write_json(manifest_path, expected_host)
    script_hashes = {str(path): sha(path) for path in (RUNNER, AUTOPILOT, Path(__file__))}
    summary_path = evidence / 'package-seven-modes-report.json'
    summary = {'status': 'running', 'archive': str(archive), 'zip_sha256': digest,
               'started_utc': utc(), 'qa_script_sha256': script_hashes, 'stages': [],
               'expected_host': expected_host, 'expected_host_manifest_sha256': sha(manifest_path),
               'scope': 'Exact frozen ZIP public installer plus six unchanged public GUI feature macros on the attested compiled host',
               'host_history_branch_gate': 'not_evaluated_by_package_suite',
               'overall_release_readiness': 'not_determined_by_package_suite',
               'windows_acceptance': 'not_executed',
               'host_gate_scope': 'Combine with separate original native and original 3117 history-branch regressions for this same host. Package passes alone do not establish the history fix.',
               'frozen_legacy_warning': 'The inner public Types macro/report retains its historical FreeCAD 1.1.4 host warning verbatim. This batch does not change or reclassify that archived wording.'}

    def save():
        write_json(summary_path, summary)

    save()
    try:
        for mode, report_name, expected_gui_checks in STAGES:
            if sha(archive) != digest:
                raise RuntimeError('The frozen ZIP changed between package stages')
            if any(sha(path) != value for path, value in script_hashes.items()):
                raise RuntimeError('QA scripts changed between package stages')
            host_unchanged(expected_host)
            row = {'stage': mode, 'status': 'running', 'started_utc': utc(),
                   'expected_gui_checks': expected_gui_checks}
            summary['stages'].append(row)
            save()
            print('PACKAGE_BATCH_START', mode, flush=True)
            output_log = evidence / ('batch-' + mode + '.log')
            with output_log.open('w', encoding='utf-8') as stream:
                result = subprocess.run([sys.executable, str(RUNNER), str(archive), mode,
                                         '--run-root', str(run_root), '--host-manifest', str(manifest_path)],
                                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
            report_path = evidence / report_name
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
            process_path = evidence / ('package-' + mode + '-process.json')
            process = json.loads(process_path.read_text()) if process_path.exists() else {}
            row.update(exit_code=result.returncode, gui_exit_code=process.get('exit_code'),
                       process_status=process.get('status'), finished_utc=utc(), report=str(report_path),
                       process_report=str(process_path), log=str(output_log), checks_passed=report.get('checks_passed'),
                       gui_checks_passed=report.get('gui_checks_passed'), actual_user_data=report.get('actual_user_data'),
                       example=report.get('example'), screenshot=report.get('screenshot'),
                       host_attestation_start=process.get('host_attestation_start'),
                       host_attestation_end=process.get('host_attestation_end'))
            passed = (result.returncode == 0 and process.get('status') == 'passed'
                      and process.get('exit_code') == 0 and report.get('status') == 'passed'
                      and report.get('zip_sha256') == digest
                      and (expected_gui_checks is None or report.get('gui_checks_passed') == expected_gui_checks))
            row['status'] = 'passed' if passed else 'failed'
            save()
            print('PACKAGE_BATCH_RESULT', mode, row['status'], row['gui_checks_passed'], flush=True)
            if not passed:
                row['error'] = report.get('error') or process.get('error') or 'Package stage failed; inspect process/GUI logs'
                print(output_log.read_text(errors='replace')[-8000:], flush=True)
                raise RuntimeError(mode + ': ' + row['error'])
        if sha(archive) != digest or any(sha(path) != value for path, value in script_hashes.items()):
            raise RuntimeError('The frozen ZIP or QA scripts changed during the package batch')
        host_unchanged(expected_host)
        profiles = {row['actual_user_data'] for row in summary['stages']}
        if len(profiles) != 1 or None in profiles:
            raise RuntimeError('The seven package stages did not share one isolated native user-data profile')
        gui_count = sum(row['gui_checks_passed'] or 0 for row in summary['stages'])
        packaging_count = sum(row['checks_passed'] or 0 for row in summary['stages'])
        if gui_count != 248 or packaging_count != 48:
            raise RuntimeError('Unexpected frozen assertion totals: ' + repr((gui_count, packaging_count)))
        summary.update(status='passed', finished_utc=utc(), stages_passed=len(STAGES),
                       public_gui_checks_passed=gui_count, packaging_checks_passed=packaging_count,
                       final_zip_sha256=sha(archive), qa_scripts_unchanged=True, host_binaries_unchanged=True,
                       host_attested_processes=len(STAGES), actual_user_data=next(iter(profiles)))
    except BaseException as error:
        summary.update(status='failed', finished_utc=utc(), error=str(error), traceback=traceback.format_exc())
    finally:
        save()
    print(json.dumps({'status': summary['status'], 'zip_sha256': digest,
                      'stages_passed': sum(row['status'] == 'passed' for row in summary['stages']),
                      'public_gui_checks_passed': summary.get('public_gui_checks_passed'),
                      'report': str(summary_path)}, ensure_ascii=False), flush=True)
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
