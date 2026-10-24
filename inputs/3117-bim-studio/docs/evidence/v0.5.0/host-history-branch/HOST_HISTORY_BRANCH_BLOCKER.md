# Native GUI Undo/Redo history branch blocker

**Current classification: `failed_native_host`; overall release readiness is false.** This v0.5.0 development candidate has a reproducible native crash on the tested Linux FreeCAD 1.1.4 GUI host. Passing model, catalogue, quantity, export and ordinary GUI workflows do not clear this separate acceptance gate.

The tested host identifies itself as FreeCAD **1.1.4**, revision **4fd3bf320d9566a27e60069fc8387448aaa3a094**, dated 2026-09-28. Tests ran in isolated XDG profiles with an actual FreeCAD GUI, Xvfb and software OpenGL. **Windows behavior for this sequence remains unknown.**

## Reproducing sequence

In a fresh document with native Undo enabled:

1. Create a baseline target object.
2. Create a disposable object in one committed document transaction.
3. Delete the disposable object in another committed transaction.
4. Invoke native `Std_Undo` to restore the deleted object.
5. Invoke native `Std_Undo` again to undo its creation.
6. Commit a new edit to the baseline target's `Label`, which discards the previous Redo branch.
7. Invoke native `Std_Undo` on that edit.
8. Invoke native `Std_Redo`.

The final Redo crashes the tested native process. In the workbench, an equivalent sequence uses Material Duplicate, Material Delete, two native Undo operations, then a Type edit and native Undo/Redo. No second document is required.

## Isolation and controls

| Case | Result | Evidence |
|---|---|---|
| Plain `App::FeaturePython`, no addon or custom Proxy | Native SIGSEGV on final Redo | `native/minimal-native/` |
| Same native sequence, returning to the main GUI event loop for 500 ms after every operation | Same SIGSEGV, including `Gui::Document::handleChildren3D+0x3a` and `Gui::Document::redo+0xa5` | `native/timed-native/` |
| Ordinary non-Python `Part::Feature`, with the same event-loop settling | Native SIGSEGV on final Redo | `native/timed-non-python/` |
| Create/delete, Undo twice, then Redo twice **without a new edit branch** | Passed | `native/unbranched-control/` |

`App::Feature` is not a registered document-object type on this host; the non-Python control therefore used `Part::Feature`. The timed reports explicitly record empty addon-module and user-addon-directory lists. The native controls need no restored FCStd, modeless readers, 3117 classes, view-provider Proxy, or secondary document.

The native crash stops Python before its report can finalize, so raw progress reports retain `status: running`. Each adjacent `external-outcome.json` records the actual process outcome, last completed step, and SIGSEGV evidence. These are failed host gates, not passed test reports.

## Impact and release treatment

The crash can lose unsaved state in the running FreeCAD process. No safe native-API workaround preserving full Undo history has been established. Event-loop settling and changing to an ordinary native `Part::Feature` do not avoid the crash. No global Undo clearing, core production change, host binary patch, or external issue publication was performed during this triage.

Local binary inspection indicates a non-null stale view-provider pointer in a deferred child-processing list: the failing virtual call occurs after a null check, `redo()` drains the list, and `undo()` does not. This is an inference supported by the isolated reproduction and disassembly, not a complete memory-debugger diagnosis. The parent investigation owns any primary-source comparison or alternative-host conclusion.

Keep the candidate label and this gate visible until a host correction or a demonstrated safe integration change passes the original failure sequence. Ordinary GUI workflows can be checked independently, with this unresolved host result retained separately.

## Reproduction files

The `native/` directory preserves the exact executed Python probes, launchers, native logs, raw reports, and external classifications. Standalone `.FCMacro` files inline those tested definitions, replacing only the runner import with a temporary output directory and inline invocation. The packaged standalone filenames were not separately rerun.

Run a crash macro only in a **fresh disposable FreeCAD process**. It can terminate that process. `reproduce_minimal_native.FCMacro` exercises the minimal sequence; the two timed macros reproduce the event-loop and non-Python variants. `control_unbranched_history.FCMacro` provides the passing control.

`host-blocker-report.json` is the machine-readable result. `SHA256.json` identifies the preserved evidence bytes.

## Suggested Thai release notice

รุ่นนี้ยังเป็น development candidate และยังไม่ผ่านเกณฑ์ความพร้อมสำหรับ release: พบ FreeCAD 1.1.4 บน Linux ปิดตัวลงเมื่อสร้างและลบวัตถุ ย้อน Undo สองครั้ง แล้วเริ่มการแก้ไขใหม่ก่อน Undo/Redo ปัญหาทำซ้ำได้ด้วยวัตถุพื้นฐานของ FreeCAD โดยไม่ติดตั้ง 3117 และอาจทำให้ข้อมูลที่ยังไม่บันทึกสูญหาย การทดสอบ workflow ปกติที่ผ่านจึงไม่ครอบคลุมกรณีนี้ ยังไม่มีวิธีแก้ผ่าน native API ที่ยืนยันได้โดยคงประวัติ Undo ทั้งหมด และยังไม่ได้ทดสอบลำดับนี้บน Windows
