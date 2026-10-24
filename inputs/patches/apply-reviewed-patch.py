#!/usr/bin/env python3
"""Apply the reviewed source-only insertion to exactly pinned FreeCAD source."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_cpp", type=Path)
    args = parser.parse_args()
    source = args.document_cpp
    before = source.read_bytes()
    original_sha = "8c2efdcd569b4c1a4fe378bb756a6d8b9bc4b0faf0a764e2efff0933350a47b6"
    if sha(before) == original_sha:
        newline = b"\r\n"
    elif b"\r" not in before and sha(before.replace(b"\n", b"\r\n")) == original_sha:
        newline = b"\n"
    else:
        raise SystemExit("Refusing a different or already modified source revision")
    context = newline.join([
        b"        ViewProvider* viewProvider = it->second;",
        b"",
        b"        auto itC = d->_CoinMap.find(viewProvider->getRoot());",
    ])
    replacement = newline.join([
        b"        ViewProvider* viewProvider = it->second;",
        b"",
        b"        // A detached provider may be destroyed when its transaction is discarded.",
        b"        d->_redoViewProviders.remove(it->second);",
        b"",
        b"        auto itC = d->_CoinMap.find(viewProvider->getRoot());",
    ])
    if before.count(context) != 1:
        raise SystemExit("Refusing missing or ambiguous insertion context")
    after = before.replace(context, replacement, 1)
    if after.count(b"d->_redoViewProviders.remove(it->second);") != 1:
        raise SystemExit("Unexpected patched queue-removal count")
    source.write_bytes(after)
    print(json.dumps({
        "source": str(source.resolve()),
        "before_sha256": sha(before),
        "after_sha256": sha(after),
        "newlines": "CRLF" if newline == b"\r\n" else "LF",
        "inserted_lines": 3,
        "status": "source_patch_applied_not_compiled_or_runtime_tested",
    }, indent=2))


if __name__ == "__main__":
    main()
