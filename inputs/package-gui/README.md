# Frozen v0.5.0 package GUI gate on the compiled host

This suite runs the exact frozen ZIP against the compiled validation host. The initial package attempt and a read-only diagnostic preserved a failure in screenshot preparation: temporary parent Qt wrappers invalidated the returned tree wrappers. The paired parent-lifetime diagnostic isolated that launcher prerequisite; the full corrected retry has a separate result below. No original assertion or frozen public macro was edited.

## Invocation

```bash
python /tmp/bim3117-host-fix/package-gui/run_package_batch.py /workspace/scratch/9457befac3c8/deliverables/3117_BIM_Studio_v0_5_0_FreeCAD.zip --run-name patched-host-02
```

Use a new `--run-name` for a retry. Existing run directories are refused, so a failed attempt remains reviewable. Run under the same approved GUI/Xvfb execution environment used by the root task.

The host command is pinned by the batch:

```text
/tmp/bim3117-host-fix/bin/micromamba --no-rc run -r /tmp/bim3117-host-fix/mamba-root -p /tmp/bim3117-host-fix/sdk /tmp/bim3117-host-fix/build/bin/FreeCAD --python-path /tmp/bim3117-host-fix/ifc-runtime
```

The supported `--python-path` option is required because this embedded FreeCAD Python ignores `PYTHONPATH`. The outer autopilot also retains one `Gui.getMainWindow()` reference for its whole lifetime. The source validation build uses `FREECAD_USE_PYSIDE=OFF` and `FREECAD_USE_SHIBOKEN=OFF`; its dynamic wrapper path requires this parent reference for the unchanged public smoke expression. This differs from the official AppImage's compiled PySide/Shiboken wrapper path. The launcher does not filter, replace or skip widgets. See `launcher-correction.json` and the paired fresh-profile probe for the exact evidence.

Display `:130` must be unused. The existing root-owned `/usr/bin/xkbcomp` helper must still match `/tmp/bim3117-host-fix/owned-xkb-helper.json`; this suite checks it and never creates, removes or changes a system helper. Do not run after the root task has cleaned up that helper.

## Preserved test scope

The ZIP must have SHA-256:

```text
ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7
```

The installer and all public macros are extracted from those exact bytes. Every extracted manifest file is verified before each stage, and the selected public macro is compared directly with its ZIP member. The original seven-stage order is unchanged:

| Stage | Expected GUI assertions |
| --- | ---: |
| Install | No feature assertions; six installer/package assertions |
| Foundation smoke | 24 |
| Wall / Door architecture | 43 |
| Quantities / Exchange | 41 |
| Building authoring | 35 |
| Drawings / Sheets | 53 |
| Types / Quantities | 52 |

Expected totals are **248 GUI assertions plus 48 packaging assertions**, using the existing unchanged assertion expressions. Host attestation is a separate execution gate and does not inflate either count.

Original QA scripts are retained byte-for-byte in `originals/`, with source locations and SHA-256 recorded in `original-qa-provenance.json`. `static-verification.json` records the initial adaptation; `static-verification-corrected.json` records the corrected launcher hashes and verifies unchanged stage order, public-suite definitions, packaging assertion expressions and dialog response function. The initial record also contains public macro hashes read from the frozen ZIP. Earlier outer script versions and their hashes remain in `attempt-scripts/`.

## Host attestation and process outcomes

At batch start, `expected-host.json` pins the compiled executable and `libFreeCADGui.so` / `libFreeCADApp.so` paths and SHA-256. All stages must use the same pinned files.

The autopilot records `/proc/self/exe` and `/proc/self/maps` in every GUI process at entry and package completion. It requires exactly the expected GUI/App library paths, checks mapped inode identity against the file, and hashes the mapped files. Unexpected, duplicate, replaced or mismatched libraries fail the stage. The runner also checks the pinned files before and after execution.

Each stage has its own external process record with the real GUI exit code, timeout state, native signal markers, command, public macro hash, GUI log hash and both attestations. An incomplete report, a nonzero exit, a native signal, a failed assertion or failed host attestation is not a pass. The runner starts only its own process groups and terminates those groups on timeout. It refuses a pre-existing X display without changing that display or its lock.

Seven fresh GUI processes share one isolated Thai-named profile for the exact ZIP. Fonts are copied only into that profile. Results for the invocation above are written beneath:

```text
/tmp/bim3117-host-fix/package-gui/runs/patched-host-02/evidence/
```

The aggregate report is `package-seven-modes-report.json`.

The completed `patched-host-02` run passed **7/7 modes, 248 public GUI assertions and 48 packaging assertions**. All seven GUI processes exited with code 0 and passed both host attestations. `final-independent-check.json` records the read-only outcome review, and `package-cleanup.json` records that the package processes and display `:130` exited. This result uses the two launcher prerequisites described above.

`public-artifacts/` preserves 47 original output files (FCStd models, reports, screenshots and CSV/IFC/SVG/PDF exports) byte-for-byte outside the disposable profile. `artifact-copy-provenance.json` records every original path, copied path, size and SHA-256. The earlier two failed smoke reports remain failed with 23 passed checks in their own evidence trees; they do not contribute to the accepted totals.

## Historical warning and separate history gate

The frozen public Types macro and inner report retain the historical warning about the original FreeCAD 1.1.4 Linux history-branch failure. Those bytes and that wording remain unchanged. They are archival package content, not a new result for the patched host.

The adapted outer report explicitly uses `host_history_branch_gate: not_evaluated_by_package_suite`. Combine it with the separately executed original no-addon and original 3117 history-branch regressions for the **same attested host hashes**. These package checks alone do not establish the host fix or production readiness. Windows acceptance is not executed by this Linux suite.
