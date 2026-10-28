# Native Export fsync repair — isolated installation integration

**Status:** diagnostic development candidate only. No automated Windows FreeCAD acceptance, pilot, or release approval.

## Provenance and isolation
- Source: the fixed `inputs/3117-bim-studio/` tree from `inputs.lock.json`. Frozen `inputs/` and original `3117_BIM_Studio_v0_5_0_FreeCAD.zip` remain byte-identical.
- Repair: the already separately tested `diagnostics/export_fsync_candidate.py` changes only `workbench/bim3117_freecad/export_files.py`: staged file is reopened in `r+b` mode before `flush()` and `os.fsync()`. The existing atomic replace and caught-exception rollback are not removed.
- Preparation: `diagnostics/prepare_export_integration.py` makes an isolated source copy and audits each source file, rejecting all deltas except that one file. It refuses overlapping/stale staging locations and reports frozen and candidate SHA-256.
- Native Python installer test: `diagnostics/verify_export_integration.py` installs the frozen source into a disposable user profile, upgrades to the isolated candidate using the original package installer, confirms the installed module/receipt hash, exercises synthetic CSV/IFC **byte** readback and metadata-last publication, fsync failure, revision failure, second-replace rollback, and restores the original installation from a backup.
- The unchanged original `test_export_files.py` safety cases execute against the copied candidate source, and the original isolated fsync tests also run.
- CI retains source and integration reports separately, checks all frozen input hashes before and after, and never uploads a patched `v0.5.0` public ZIP claiming to be the frozen one.

## How to verify

GitHub → Actions → **Windows export fsync candidate checks** → select branch `acceptance/windows-history-fix` → Run workflow. The push trigger also executes on changed candidate scripts. Inspect `windows-export-integration-evidence` with `source-provenance.json` and `installed-export-integration.json`. These are Windows **Python/installer** results only; no FreeCADCmd host, native geometry/IFC schema, or Qt GUI is invoked.

## Remaining review gates

1. Review whether to promote this one-file code change into a **new** separately versioned and re-locked workbench candidate. Keep the original frozen ZIP/hash as baseline evidence.
2. Exercise the original 19 native stages (including exchange 47 checks, and all 651) using an explicitly pinned new candidate, real FreeCADCmd, validated host manifest, a fresh isolated profile, exact installer receipts, and unchanged original macros. Do not mix source/host identities.
3. Repeat the public GUI on qualified interactive Windows GPU runner and full A/B acceptance with a reviewed updated lock/test plan. Never count these diagnostic results as passing the existing frozen-v0.5.0 acceptance gate.
4. Keep `release_ready=false` until full evidence plus manual desktop checklist are reviewed.
