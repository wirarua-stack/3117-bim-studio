#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy completed public-macro outputs byte-for-byte out of an isolated profile."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

TASK = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', required=True)
    args = parser.parse_args()
    if not args.run_name.replace('-', '').isalnum():
        parser.error('Use the recorded alphanumeric batch run name')
    run = TASK / 'runs' / args.run_name
    evidence = run / 'evidence'
    summary_path = evidence / 'package-seven-modes-report.json'
    summary = json.loads(summary_path.read_text())
    if summary['status'] not in ('passed', 'failed'):
        parser.error('The batch must be complete before artifacts are copied')
    profiles = {stage['actual_user_data'] for stage in summary['stages'] if stage.get('actual_user_data')}
    if len(profiles) != 1:
        parser.error('Expected exactly one attested batch user-data profile')
    source = (Path(profiles.pop()) / 'BIM3117_Test_Reports').resolve(strict=True)
    if not source.is_relative_to(run.resolve(strict=True)):
        parser.error('Source must stay inside this disposable batch profile')
    target = evidence / 'public-artifacts'
    provenance = evidence / 'artifact-copy-provenance.json'
    if target.exists() or provenance.exists():
        parser.error('Previously copied evidence is never overwritten')
    files = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            parser.error('A public output unexpectedly contains a symlink')
        if path.is_file() and '__pycache__' not in path.parts:
            files.append(path)
    if not files:
        parser.error('No completed public-macro artifacts found')
    target.mkdir()
    records = []
    for path in files:
        digest = sha(path)
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        if sha(destination) != digest or sha(path) != digest:
            raise RuntimeError('Artifact changed during byte-preserving copy: ' + str(path))
        records.append({'source': str(path), 'copy_relative_to_evidence': str(destination.relative_to(evidence)),
                        'sha256': digest, 'bytes': destination.stat().st_size})
    report = {'status': 'byte_preserving_copy_verified', 'source_summary': str(summary_path),
              'source_summary_sha256': sha(summary_path), 'raw_batch_status': summary['status'],
              'scope': 'Only BIM3117_Test_Reports outputs are copied; installed runtime and profile/config/cache trees are excluded. Raw test report bytes are not edited.',
              'copy_script_sha256': sha(Path(__file__)), 'files': records,
              'total_bytes': sum(row['bytes'] for row in records)}
    provenance.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'files': len(records), 'bytes': report['total_bytes'],
                      'provenance': str(provenance)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
