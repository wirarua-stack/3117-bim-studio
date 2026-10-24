# Host compatibility — v0.5.0 development candidate

**Pilot/production acceptance is blocked on the tested Linux FreeCAD 1.1.4 GUI host. Windows acceptance remains pending.** Types, material quantities, schedules, persistence and IFC have separate passing evidence; those results do not resolve the native history failure described here.

**สำหรับผู้ทดลอง:** พบ FreeCAD ปิดตัวจากลำดับสร้าง–ลบวัตถุ–Undo สองครั้ง–แก้ไขใหม่–Undo/Redo โดยทำซ้ำได้ด้วยวัตถุ Part มาตรฐานและไม่ติดตั้ง 3117 อาการนี้อาจทำให้งานที่ยังไม่บันทึกสูญหาย ใช้ candidate กับโครงการทดสอบหรือสำเนาที่บันทึกไว้ ยังไม่มีวิธีแก้ผ่าน API ที่พิสูจน์ว่ารักษา history ครบ จึงยังไม่รับรองงานจริง และยังไม่ได้ทดสอบลำดับนี้บน Windows

## Observed host and failure

The tested host is the official Linux x86_64 FreeCAD **1.1.4** AppImage, commit `4fd3bf320d9566a27e60069fc8387448aaa3a094`, Python 3.11.14, Qt 6.8.3, with Xvfb and software rendering. The AppImage SHA-256 is `f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`.

Local regression identifier: **FREECAD-1.1.4-GUI-UNDO-BRANCH**. This is an internal identifier, not a published upstream issue number. No upstream issue or message has been sent.

1. Create a target object outside a transaction.
2. Create a disposable object in one committed native transaction.
3. Delete the disposable object in a second committed transaction.
4. Invoke native `Std_Undo` twice, restoring the deletion and then undoing creation.
5. Commit a new edit to the target's `Label`, which branches from the current history state.
6. Invoke native `Std_Undo`, then `Std_Redo` on this edit.

The final Redo crashes. Matching frames include `Gui::Document::handleChildren3D(Gui::ViewProvider*, bool)+0x3a` and `Gui::Document::redo(int)+0xa5`. Some launchers report exit 1 after FreeCAD's signal handler; the non-Python timed process reports 139. The raw progress reports remain `running` because the native termination bypasses Python finalization. Their external outcomes and logs classify the crash; a stale or incomplete JSON file is never treated as a completed pass.

## Isolation evidence

| Case | Result | What it establishes |
|---|---|---|
| Actual 3117 Material Duplicate/Delete, two Undos, shared Column Type edit, Undo/Redo | SIGSEGV | The failure is reachable through an ordinary authoring workflow |
| Fresh profile, plain `App::FeaturePython`, no addon or custom proxies | Same crash | 3117, modeless readers and FCStd restore are not required |
| Same native sequence with a 500 ms return to the top-level GUI event loop after every step | Same crash | Normal event-loop settling does not avoid the failure |
| Plain non-Python `Part::Feature`, same settling | Same crash | A Python object/view-provider proxy is not required |
| Create/delete, Undo twice, Redo twice without branching into a new edit | Passed | Ordinary unbranched history works in this control |

The timed native reports record empty addon module and user Mod-directory lists. No second document is used. `App::Feature` is not a document object type in this host, so the non-Python probe uses `Part::Feature` explicitly.

The [native blocker report](evidence/v0.5.0/host-history-branch/host-blocker-report.json) binds the cases and external outcomes; [native evidence hashes](evidence/v0.5.0/host-history-branch/SHA256.json) bind the preserved scripts and logs. The [original UI regression](evidence/v0.5.0/host-history-branch/ui/regression-report.json) retains the exact crashing fresh-GUI harness, helper, fixture and log. See its [replay instructions](evidence/v0.5.0/host-history-branch/ui/README.md).

## Source diagnosis and limits

The exact host C++ source queues raw view-provider pointers while GUI transactions are active. GUI Undo does not drain the deferred list; GUI Redo later visits it. Opening a new transaction discards the old Redo branch and can free the providers owned by that branch. This source lifecycle and the native traces support the stale-pointer explanation. This is a source-backed diagnosis, not a memory-debugger proof of every affected path.

The inspected upstream `main` commit `dc1ab881ca0bbea9735e92938a660acee339679e` has the same relevant Undo/Redo and transaction-removal functions. That source comparison does not test a weekly binary, another release or Windows. No alternative host is certified by this investigation.

The [primary-source review](evidence/v0.5.0/host-history-branch/source-review/FREECAD_HISTORY_BRANCH_SOURCE_REVIEW.md) and [source manifest](evidence/v0.5.0/host-history-branch/source-review/source-manifest.json) identify the immutable official source URLs, hashes and method comparisons. An [optional core patch direction](evidence/v0.5.0/host-history-branch/source-review/untested-provider-removal.patch) is included for developer review only: it has **not been applied, compiled or tested** and is not part of the installed Workbench.

`Gui.updateGui()` and GUI-document `update()` do not drain the deferred provider list. The public Python GUI document exposes no zero-step Undo/Redo flush. The C++ zero-step path rejects the operation before draining. No safe public-API workaround preserving full history was established. The Workbench does not clear Undo history, replace native Redo, or patch host binaries to suppress the evidence.

## How the candidate reports acceptance

The feature suites retain their checks for type edits, normal Undo/Redo, material lifecycle, fresh restoration and concurrent readers. Cases are isolated to inspect those features without deliberately triggering the known process crash in the public macro. Types GUI feature reports carry both their feature result and `host_history_branch_gate: "failed_native_host"`, with `overall_release_ready: false`.

The combined crashing sequence remains a separate failed regression, with its original source and native controls. Moving a feature case to an isolated lifecycle is not a fix for that regression. Counts from the interrupted run are not added to passing totals. A passing public macro or successful ZIP installation does not change the blocked release status.

The mutual refresh loop between the Schedules and Quantities panels was a separate Workbench issue and has been fixed. Clean readers no longer continually invalidate each other after read-only capture/recompute. Actual concurrent-panel edit/Undo/Redo checks cover that correction, without claiming it fixes native history branching.

## Reproduction and next gate

The [minimal standalone macro](evidence/v0.5.0/host-history-branch/native/reproduce_minimal_native.FCMacro), [event-loop variant](evidence/v0.5.0/host-history-branch/native/reproduce_timed_native.FCMacro), [non-Python variant](evidence/v0.5.0/host-history-branch/native/reproduce_timed_non_python.FCMacro), and [passing unbranched control](evidence/v0.5.0/host-history-branch/native/control_unbranched_history.FCMacro) are for a disposable FreeCAD process/profile. The failing macros can terminate the whole process, so close other documents and save all work before a deliberate reproduction. They create their own synthetic document and temporary output directory. The packaged macros inline the executed probe definitions; the exact original launchers and logs are also preserved. The new standalone filenames were compiled, not separately rerun.

Before Pilot acceptance:

1. Fix the host lifecycle or identify a supported host where the original native and 3117 sequences both pass. Record exact build and source hashes.
2. Repeat the failed branch sequence without clearing history or skipping the final Redo; verify object identity, native properties, scene graph and later edits.
3. Rerun the affected native/GUI and persistence regressions with the candidate on that exact host.
4. Execute the Windows installation, upgrade, reopen and user-workflow gates on Windows itself.

Normal saving and reopening provide an inspectable checkpoint for the supplied model; they do not prove that arbitrary branching operations are safe. No full recovery guarantee, release date or Windows behavior is inferred from these Linux results.
