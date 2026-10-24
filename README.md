# 3117 BIM Studio — Windows acceptance

**Native Windows runner readiness passed. FreeCAD compilation and runtime acceptance remain pending.**

See [the complete Thai guide](README_TH.md),
[build route](docs/WINDOWS_BUILD.md), and
[acceptance contract](docs/ACCEPTANCE_CONTRACT.md).

This kit builds unpatched and patched FreeCAD 1.1.4 from the pinned source,
runs the preserved history regression matrix, then the frozen 3117 v0.5.0
native suite (19 processes / 651 checks) and public GUI suite
(installer plus six macros / 248 GUI + 48 package checks).

```powershell
pwsh -NoProfile -File .\Start-WindowsAcceptance.ps1 -WorkRoot C:\3117Acceptance\run-01 -Jobs 2
```

The controller requires a native Windows x64 host with the documented tools,
disk space, and visible desktop. It preserves source and evidence hashes,
isolates profiles and IFC dependencies, and checks actual loaded host DLLs.
Offline preparation is never counted as Windows acceptance.

## Current GitHub status

The repository is [wirarua-stack/3117-bim-studio](https://github.com/wirarua-stack/3117-bim-studio),
with active branch
[`acceptance/windows-history-fix`](https://github.com/wirarua-stack/3117-bim-studio/tree/acceptance/windows-history-fix).

[Windows runner readiness run 39934642607](https://github.com/wirarua-stack/3117-bim-studio/actions/runs/39934642607)
passed at commit
[`1139434ce9bc2ca4bb2813bea1623e5c249c316c`](https://github.com/wirarua-stack/3117-bim-studio/commit/1139434ce9bc2ca4bb2813bea1623e5c249c316c).
Its native Windows observations record a writable work directory with more than
the required 30 GiB available, desktop session 2, a visible window station, and
one monitor. These observations cover runner readiness; FreeCAD compilation,
Qt GUI checks, crash/Undo/Redo/save/reopen regressions, and the complete 3117
suites still need execution.

The [raw readiness JSON](evidence/ci/runner-readiness-39934642607.json) is retained
with [artifact provenance and SHA-256](evidence/ci/runner-readiness-39934642607.provenance.json).
The linked run records the particular runner instance used at that time;
subsequent acceptance runs must repeat their own environment and desktop gates.

The acceptance workflow supports this branch and manual dispatch. Installer
packaging follows successful acceptance. The upstream proposal remains a draft;
no upstream submission or merge has been performed.

[PREPARATION_STATUS.json](PREPARATION_STATUS.json) is the unchanged historical
snapshot from **2026-10-23 09:25:33 UTC**, before repository setup and the Windows
readiness run at **09:49:32 UTC**. Its missing-target blocker describes that
earlier snapshot, not the current GitHub state. Its offline results remain
Linux preparation evidence.

`release_ready` remains `false`. After the automated suites pass, complete the
[Windows desktop checklist W01–W62](inputs/3117-bim-studio/docs/WINDOWS_ACCEPTANCE.md)
before preparing the trial installer from the tested binaries.

The original project source is preserved in `inputs/3117-bim-studio/`.
License: [GPL-3.0-or-later](LICENSE); dependencies retain their own notices.
