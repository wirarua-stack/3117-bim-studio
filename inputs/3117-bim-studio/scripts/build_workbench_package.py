#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a source-only FreeCAD workbench distribution; never bundles the host."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import zipfile


def build(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    spec = importlib.util.spec_from_file_location("bim3117_build_install_support", repo / "packaging" / "install_support.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    info = helper.package_info(repo)
    files = {}
    for source in helper.source_files(repo / "workbench"):
        files[source.relative_to(repo).as_posix()] = source.read_bytes()
    for name in ("LICENSE", "THIRD_PARTY.md"):
        files[name] = (repo / name).read_bytes()
    # The root convenience copy has a different relative link base from the
    # original guide in packaging/. Keep both copies navigable in the ZIP.
    files["INSTALL_TH.md"] = (repo / "packaging" / "INSTALL_TH.md").read_text(
        encoding="utf-8").replace("../docs/", "docs/").encode("utf-8")
    for name in ("install_support.py", "freecad_installer_ui.py", "README.md", "INSTALL_TH.md", "CI_HOSTS.md"):
        files[f"packaging/{name}"] = (repo / "packaging" / name).read_bytes()
    for name in ("Install_3117_BIM_Studio.FCMacro", "Manage_3117_BIM_Studio.FCMacro"):
        files[name] = (repo / "packaging" / name).read_bytes()
    qa_files = [(repo / "tests" / name, f"tests/{name}") for name in
                ("freecad_foundation.py", "freecad_gui_smoke.py", "freecad_gui_reopen.py", "run_freecad_tests.py",
                 "freecad_reopen.py", "freecad_architecture.py", "freecad_architecture_reopen.py",
                 "freecad_architecture_gui.py", "freecad_architecture_gui_reopen.py",
                 "freecad_exchange.py", "freecad_exchange_reopen.py",
                 "freecad_exchange_gui.py", "freecad_exchange_gui_reopen.py",
                 "freecad_building.py", "freecad_building_reopen.py",
                 "freecad_building_gui.py", "freecad_building_gui_reopen.py",
                 "freecad_building_presentation.py",
                 "freecad_drawing_geometry.py", "freecad_drawings.py", "freecad_drawings_reopen.py",
                 "freecad_drawing_render.py", "freecad_drawings_gui.py", "freecad_drawings_gui_reopen.py",
                 "freecad_drawings_presentation.py", "freecad_drawings_exchange.py", "pdf_drawing_review.py",
                 "freecad_headless_gui.py", "freecad_headless_gui_reopen.py",
                 "bonsai_exchange_review.py", "bonsai_building_review.py",
                 "freecad_types.py", "freecad_types_reopen.py", "freecad_types_exchange.py",
                 "freecad_schedules.py", "freecad_schedules_reopen.py",
                 "freecad_types_gui.py", "freecad_types_gui_reopen.py", "freecad_types_presentation.py",
                 "bonsai_types_review.py")]
    qa_files.append((repo / "packaging" / "Run_3117_Smoke_Test.FCMacro", "Run_3117_Smoke_Test.FCMacro"))
    qa_files.append((repo / "packaging" / "Run_3117_Architecture_Test.FCMacro", "Run_3117_Architecture_Test.FCMacro"))
    qa_files.append((repo / "packaging" / "Run_3117_Exchange_Test.FCMacro", "Run_3117_Exchange_Test.FCMacro"))
    qa_files.append((repo / "packaging" / "Run_3117_Building_Test.FCMacro", "Run_3117_Building_Test.FCMacro"))
    qa_files.append((repo / "packaging" / "Run_3117_Drawings_Test.FCMacro", "Run_3117_Drawings_Test.FCMacro"))
    qa_files.append((repo / "packaging" / "Run_3117_Types_Test.FCMacro", "Run_3117_Types_Test.FCMacro"))
    for source, relative in qa_files:
        if source.is_file():
            files[relative] = source.read_bytes()
    if "Run_3117_Smoke_Test.FCMacro" in files and "tests/freecad_gui_smoke.py" not in files:
        raise ValueError("Smoke macro exists but its tests/freecad_gui_smoke.py harness is missing")
    if "tests/run_freecad_tests.py" in files:
        for required in ("tests/freecad_foundation.py", "tests/freecad_reopen.py",
                         "tests/freecad_architecture.py", "tests/freecad_architecture_reopen.py",
                         "tests/freecad_exchange.py", "tests/freecad_exchange_reopen.py",
                         "tests/freecad_building.py", "tests/freecad_building_reopen.py",
                         "tests/freecad_drawing_geometry.py", "tests/freecad_drawings.py",
                         "tests/freecad_drawings_reopen.py", "tests/freecad_drawing_render.py",
                         "tests/freecad_types.py", "tests/freecad_types_reopen.py", "tests/freecad_types_exchange.py",
                         "tests/freecad_schedules.py", "tests/freecad_schedules_reopen.py"):
            if required not in files:
                raise ValueError(f"Host test runner exists but its {required} harness is missing")
    if "Run_3117_Architecture_Test.FCMacro" in files and "tests/freecad_architecture_gui.py" not in files:
        raise ValueError("Architecture macro exists but its GUI harness is missing")
    if "Run_3117_Exchange_Test.FCMacro" in files and "tests/freecad_exchange_gui.py" not in files:
        raise ValueError("Exchange macro exists but its GUI harness is missing")
    if "Run_3117_Building_Test.FCMacro" in files and "tests/freecad_building_gui.py" not in files:
        raise ValueError("Building macro exists but its GUI harness is missing")
    if "Run_3117_Drawings_Test.FCMacro" in files and "tests/freecad_drawings_gui.py" not in files:
        raise ValueError("Drawings macro exists but its GUI harness is missing")
    if "Run_3117_Types_Test.FCMacro" in files and "tests/freecad_types_gui.py" not in files:
        raise ValueError("Types macro exists but its GUI harness is missing")
    for name in ("TYPES_AND_QUANTITIES.md", "HOST_COMPATIBILITY.md", "BONSAI_TYPES_REVIEW.md", "VERIFICATION_v0_4_0.md", "FOUNDATION_WORKBENCH.md", "WALL_DOOR_WORKBENCH.md", "QUANTITY_EXCHANGE.md", "BONSAI_REVIEW.md",
                 "BUILDING_AUTHORING.md", "BONSAI_BUILDING_REVIEW.md", "DRAWINGS_AND_SHEETS.md", "WINDOWS_ACCEPTANCE.md", "VERIFICATION.md", "VERIFICATION_v0_2_0.md", "VERIFICATION_v0_2_1.md", "VERIFICATION_v0_3_0.md",
                 "ACCEPTANCE.md", "ARCHITECTURE.md", "ROADMAP.md", "SOURCES.md", "TEST_ENVIRONMENT.json"):
        source = repo / "docs" / name
        if source.is_file():
            files[f"docs/{name}"] = source.read_bytes()
    evidence_directory = repo / "docs" / "evidence"
    if evidence_directory.is_dir():
        for source in helper.source_files(evidence_directory):
            if source.suffix.lower() == ".json":
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    # Preserve the known failed native/UI sequence as runnable evidence. These
    # are documentation assets, never imported or invoked by the public macros.
    host_evidence = evidence_directory / "v0.5.0" / "host-history-branch"
    if host_evidence.is_dir():
        for source in helper.source_files(host_evidence):
            if source.suffix.lower() in (".json", ".md", ".py", ".fcmacro", ".log", ".fcstd", ".patch"):
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    for name in ("Foundation_Workbench.FCStd", "Foundation_Workbench.png", "Architecture_Workbench.FCStd",
                 "Architecture_Workbench.png", "README.md"):
        sample = repo / "examples" / "freecad" / name
        if sample.is_file():
            files[sample.relative_to(repo).as_posix()] = sample.read_bytes()
    exchange_examples = repo / "examples" / "exchange"
    if exchange_examples.is_dir():
        for source in helper.source_files(exchange_examples):
            if source.suffix.lower() in (".fcstd", ".ifc", ".csv", ".json", ".png", ".md"):
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    building_examples = repo / "examples" / "building"
    if building_examples.is_dir():
        for source in helper.source_files(building_examples):
            if source.suffix.lower() in (".fcstd", ".ifc", ".csv", ".json", ".png", ".md"):
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    for source in helper.source_files(repo / "packaging" / "tests"):
        files[source.relative_to(repo).as_posix()] = source.read_bytes()
    drawing_examples = repo / "examples" / "drawings"
    if drawing_examples.is_dir():
        for source in helper.source_files(drawing_examples):
            if source.suffix.lower() in (".fcstd", ".svg", ".pdf", ".json", ".png", ".md", ".py"):
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    types_examples = repo / "examples" / "types"
    if types_examples.is_dir():
        for source in helper.source_files(types_examples):
            if source.suffix.lower() in (".fcstd", ".ifc", ".csv", ".json", ".png", ".md", ".py"):
                files[source.relative_to(repo).as_posix()] = source.read_bytes()
    manifest = {"project_id": info["project_id"], "version": info["version"],
                "target_freecad_baseline": info["baseline"],
                "distribution": "Source workbench and user-level installer; FreeCAD/Qt are not bundled",
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    folder = f"3117_BIM_Studio_v{info['version']}_FreeCAD"
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="3117-package-", suffix=".zip", dir=output.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, data in sorted(files.items()):
                entry = zipfile.ZipInfo(f"{folder}/{relative}", date_time=(2026, 10, 23, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"file": str(output), "version": info["version"], "files": len(files),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "includes_host_smoke_macro": "Run_3117_Smoke_Test.FCMacro" in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
