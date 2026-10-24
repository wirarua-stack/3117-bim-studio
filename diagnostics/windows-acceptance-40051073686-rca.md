# Windows Acceptance RCA — Run 40051073686

**Status: FAIL / not release ready.** Evidence artifact: [12561317262](https://github.com/wirarua-stack/3117-bim-studio/actions/runs/40051073686/artifacts/12561317262). Run commit: `b41f54967576b263b1b848a505f062b271eef791`.

## Confirmed gates
- build_unpatched = passed; build_patched = passed; same_toolchain = passed; ifc_runtime = passed; patched_regression = passed; frozen_inputs = passed; cross_suite_identity = passed.
- unpatched_observation = failed (four timed-out original controls). Preserve original sequences and classify distinctly from patched regression.
- native_3117 = failed: exchange stopped after 24 / 47 exchange checks, so 19/651 is incomplete.
- public_zip_gui = failed at publicsmoke, before 248 GUI / 48 packaging counts could complete.
- release_ready = false. No accepted runtime can be sealed.

## Native exchange: evidence and repair candidate
`results/native-patched/output/exchange-launcher-error.json` reports `OSError: [Errno 9] Bad file descriptor` in installed `bim3117_freecad/export_files.py:67` at `os.fsync(file.fileno())` within `with path.open("rb")`.

This is consistent with Windows CRT `fsync` rejecting the read-only file descriptor. It is **not** evidence that disabling fsync or omitting durability is acceptable. Candidate implementation: reopen the *staged file* as `r+b`, call `flush()` then `os.fsync(fileno())`, retain the existing per-file atomic replace/caught-failure rollback and filename/sidecar behavior. Validate Windows read/write descriptor support and permissions first. Add tests proving fsync failure aborts publication with original target intact, no orphaned locks/stage directories, plus successful CSV/IFC readback and Undo/Redo stability. Changes to frozen inputs or the frozen public ZIP require a separately reviewed new candidate and updated lock; **do not silently patch or restamp frozen fixtures**.

## GUI smoke: evidence and investigation
`results/public-gui-patched/publicsmoke/process.json`: `timed_out=true`, elapsed about 900 seconds, returncode 1, original process killed by its controller. `publicsmoke/gui.log` repeatedly reports `Unhandled Base::Exception ... Access violation`, `Attempted to call beginFrame() within a still active frame`, and `Resource update batch pool exhausted (max is 64)`.

Do not classify this as missing-report-only. The native GUI host or render/event-loop path may be failing. Next isolate: compare GUI crash signature and logs of patched regression against public smoke, collect first exception/stack if available, verify Qt/QRhi/RHI environment and actual interactive desktop, run the original smoke unaltered against the built patched GUI, and investigate whether launcher or GPU rendering/environment is causal. Do not suppress access violations or count forced exit as a pass.

## Evidence collection
Artifact upload completed and contains the report, controller logs and partial suites. The intermediate `Collect evidence within checkout` step failed, but `Preserve original evidence on success or failure` succeeded. Investigate the PowerShell Copy-Item failure separately and preserve all existing successful evidence.

## Execution order
1. Repair evidence-copy error using exact job log; avoid rebuilding merely to test the artifact copy.
2. Prepare export fix on a new development candidate, preserving frozen input evidence untouched.
3. Investigate public GUI access violation independently; do not infer export fix resolves graphics crash.
4. Execute targeted native and public GUI tests on Windows; if fixed, run complete A/B Windows acceptance and require all original frozen gates.
5. Seal the **same tested** patched binary only after verified automated acceptance; desktop checklist stays pending; release_ready=false until explicitly authorized.
