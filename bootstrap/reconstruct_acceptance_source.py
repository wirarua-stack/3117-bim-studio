#!/usr/bin/env python3
"""Reconstruct the exact 3117 acceptance source from a verified text payload and existing Git blobs."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

PACKAGE = "inputs/3117_BIM_Studio_v0_5_0_FreeCAD.zip"
PACKAGE_SHA256 = "ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7"
TEXT_ARCHIVE_SHA256 = "22b75c6de39354192e5a41468218cc937c74c6df72afa42f6038bb56a77cde15"
EXPECTED_INPUT_COUNT = 898
EXPECTED_SEALED_COUNT = 947


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def fetch_blob(repo: str, sha: str, token: str) -> bytes:
    url = f"https://api.github.com/repos/{repo}/git/blobs/{sha}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "3117-acceptance-bootstrap",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    if payload.get("encoding") != "base64":
        raise RuntimeError(f"Unexpected GitHub blob encoding for {sha}: {payload.get('encoding')}")
    data = base64.b64decode(payload["content"], validate=False)
    if git_blob_sha(data) != sha:
        raise RuntimeError(f"Git blob SHA mismatch after fetch: {sha}")
    return data


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:xz") as tf:
        root = destination.resolve()
        for member in tf.getmembers():
            target = (destination / member.name).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"Unsafe archive member: {member.name}")
        tf.extractall(destination)


def verify_seal(root: Path) -> None:
    seal_path = root / "SHA256.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    files = seal.get("files")
    if not isinstance(files, list) or len(files) != EXPECTED_SEALED_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_SEALED_COUNT} sealed files, got {len(files) if isinstance(files, list) else 'invalid'}")
    input_count = sum(1 for entry in files if str(entry.get("path", "")).startswith("inputs/"))
    if input_count != EXPECTED_INPUT_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_INPUT_COUNT} frozen input files, got {input_count}")
    for entry in files:
        path = root / entry["path"]
        if not path.is_file():
            raise FileNotFoundError(entry["path"])
        if path.stat().st_size != entry["bytes"]:
            raise RuntimeError(f"Byte length mismatch: {entry['path']}")
        if digest(path) != entry["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch: {entry['path']}")


def reconstruct(payload: Path, binary_map: Path, output: Path, repo: str, token: str) -> None:
    if digest(payload) != TEXT_ARCHIVE_SHA256:
        raise RuntimeError("Text bootstrap archive SHA-256 mismatch")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    safe_extract(payload, output)

    seal = json.loads((output / "SHA256.json").read_text(encoding="utf-8"))
    sha_map = json.loads(binary_map.read_text(encoding="utf-8"))
    missing = [entry for entry in seal["files"] if not (output / entry["path"]).is_file()]
    package_entries = [entry for entry in missing if entry["path"] == PACKAGE]
    blob_entries = [entry for entry in missing if entry["path"] != PACKAGE]
    if len(package_entries) != 1:
        raise RuntimeError(f"Expected one generated package entry, got {len(package_entries)}")

    cache: dict[str, bytes] = {}
    for entry in blob_entries:
        expected_sha256 = entry["sha256"]
        git_sha = sha_map.get(expected_sha256)
        if not git_sha:
            raise RuntimeError(f"No pre-uploaded Git blob mapped for {entry['path']}")
        if git_sha not in cache:
            cache[git_sha] = fetch_blob(repo, git_sha, token)
        data = cache[git_sha]
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RuntimeError(f"Fetched binary did not match seal: {entry['path']}")
        path = output / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    package = output / PACKAGE
    subprocess.run(
        [
            os.environ.get("PYTHON", "python"),
            str(output / "inputs/3117-bim-studio/scripts/build_workbench_package.py"),
            "--repo",
            str(output / "inputs/3117-bim-studio"),
            "--output",
            str(package),
        ],
        check=True,
    )
    if digest(package) != PACKAGE_SHA256:
        raise RuntimeError("Generated v0.5.0 workbench ZIP does not match frozen package hash")
    verify_seal(output)


def replace_checkout(source: Path, checkout: Path) -> None:
    for child in checkout.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    for source_path in source.iterdir():
        target = checkout / source_path.name
        if source_path.is_dir():
            shutil.copytree(source_path, target)
        else:
            shutil.copy2(source_path, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--binary-map", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    with tempfile.TemporaryDirectory(prefix="3117-source-bootstrap-") as temp:
        assembled = Path(temp) / "acceptance-kit"
        reconstruct(args.payload, args.binary_map, assembled, args.repo, token)
        replace_checkout(assembled, args.checkout.resolve())
    print(json.dumps({"status":"verified","sealed_files":EXPECTED_SEALED_COUNT,"frozen_inputs":EXPECTED_INPUT_COUNT,"release_ready":False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
