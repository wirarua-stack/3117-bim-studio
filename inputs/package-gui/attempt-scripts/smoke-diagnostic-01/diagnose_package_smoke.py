#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Observe the unchanged public smoke macro in a new disposable GUI profile."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ARCHIVE = Path('/workspace/scratch/9457befac3c8/deliverables/3117_BIM_Studio_v0_5_0_FreeCAD.zip')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', required=True)
    args = parser.parse_args()
    if not args.run_name.replace('-', '').isalnum():
        parser.error('Use an alphanumeric diagnostic run name')
    root = TASK / 'runs' / args.run_name
    if root.exists():
        parser.error('The diagnostic run already exists; previous evidence is preserved')
    spec = importlib.util.spec_from_file_location('package_batch', TASK / 'run_package_batch.py')
    batch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch)
    host = batch.pin_host()
    evidence = root / 'evidence'
    evidence.mkdir(parents=True)
    manifest = evidence / 'expected-host.json'
    batch.write_json(manifest, host)
    record = {'status': 'running', 'scope': 'Read-only widget-lifetime observation of the unchanged public smoke macro; not a seven-mode package gate',
              'expected_host': host, 'zip_sha256': batch.sha(ARCHIVE),
              'qa_script_sha256': {name: batch.sha(TASK / name) for name in
                  ('diagnose_package_smoke.py', 'run_package_batch.py', 'run_package_check.py', 'package_autopilot.FCMacro')},
              'stages': []}
    batch.write_json(evidence / 'diagnosis-summary.json', record)
    for mode in ('install', 'publicsmoke'):
        command = [sys.executable, str(TASK / 'run_package_check.py'), str(ARCHIVE), mode,
                   '--run-root', str(root), '--host-manifest', str(manifest), '--trace']
        result = subprocess.run(command, stdin=subprocess.DEVNULL)
        process = json.loads((evidence / ('package-' + mode + '-process.json')).read_text())
        record['stages'].append({'mode': mode, 'command': command, 'exit_code': result.returncode,
                                 'process_status': process['status']})
        batch.write_json(evidence / 'diagnosis-summary.json', record)
        if result.returncode:
            break
    record['status'] = 'diagnostic_observation_complete'
    batch.write_json(evidence / 'diagnosis-summary.json', record)
    print(json.dumps(record, indent=2), flush=True)


if __name__ == '__main__':
    main()
