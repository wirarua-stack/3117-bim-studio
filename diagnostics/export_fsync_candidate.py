#!/usr/bin/env python3
"""Generate an isolated export fsync candidate from frozen source; never edit inputs/."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

RELATIVE = Path("workbench/bim3117_freecad/export_files.py")
OLD = '''            with path.open("rb") as file:
                os.fsync(file.fileno())
'''
NEW = '''            # Windows' CRT may reject fsync() on a read-only descriptor.
            # Reopen only the private staged file for read/write; never touch
            # the published destination until all staged files are synced.
            with path.open("r+b") as file:
                file.flush()
                os.fsync(file.fileno())
'''

def candidate(frozen_root: Path, output_root: Path) -> dict:
    source = frozen_root / RELATIVE
    data = source.read_bytes()
    original = data.decode("utf-8")
    if original.count(OLD) != 1:
        raise RuntimeError("Frozen export source does not match reviewed patch context")
    patched = original.replace(OLD, NEW).encode("utf-8")
    target = output_root / RELATIVE
    if source.resolve() == target.resolve():
        raise RuntimeError("Refusing to modify frozen inputs")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing candidate: {target}")
    target.write_bytes(patched)
    return {"frozen_sha256": hashlib.sha256(data).hexdigest(),
            "candidate_sha256": hashlib.sha256(patched).hexdigest(),
            "candidate_path": str(target), "frozen_unchanged": source.read_bytes() == data}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frozen-root",type=Path,required=True)
    p.add_argument("--output-root",type=Path,required=True)
    args=p.parse_args()
    print(candidate(args.frozen_root,args.output_root))
if __name__ == "__main__":
    main()
