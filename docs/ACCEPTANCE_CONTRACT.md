# Windows acceptance contract

The frozen workbench is **3117 BIM Studio v0.5.0 development candidate**. The
host base is FreeCAD 1.1.4 commit
`4fd3bf320d9566a27e60069fc8387448aaa3a094`. Only the reviewed three-line
`src/Gui/Document.cpp` history-provider patch is applied to the patched host.

## Evidence required by the automated gate

| Gate | Required evidence |
| --- | --- |
| Build provenance | Native Windows x64; pinned source and dependency archives; compiler/CMake identities; compiled PySide/Shiboken; same dependency signature for unpatched and patched hosts |
| Original history regression | All six original cases attempted on both hosts; exact frozen source hashes; native Windows process exits and DLL identities; no timeouts or launcher substitutions |
| Patched history | Six passing cases, including 127 history invariant checks, a separate process with 13 reopen checks, and 27 original 3117 UI checks |
| Native 3117 | Nineteen fresh processes; all 651 checks; installed workbench modules; native geometry and IFC readback; no skipped dependencies |
| Public ZIP GUI | Exact frozen ZIP; installer and six public GUI macros; 248 GUI checks plus 48 package checks; Thai paths; actual Qt windows and DLL identities |
| Cross-suite identity | The same patched FreeCAD binaries and compatible IFC runtime across the patched regression/native/public GUI runs |
| Frozen inputs | All input file hashes unchanged before and after execution |

Windows baseline behavior is an observation. A passing unpatched Windows
baseline is possible and must be reported as such. The Linux crash outcome is
never copied into a Windows result. A baseline timeout, missing attestation,
missing case or launcher error is inconclusive and blocks comparison.

Reports are checked by their content, expected counts and native host identity.
An exit code of zero, an installer success message, or the existence of an old
JSON file is insufficient. Fresh output directories prevent old reports from
being reused. No command clears Undo history or changes the original sequence.

## Desktop and release boundary

The frozen [Windows acceptance checklist](../inputs/3117-bim-studio/docs/WINDOWS_ACCEPTANCE.md)
contains W01–W62. Automation exercises many of these behaviors, but does not
certify every item. In particular, physical A3 printing at 100% (W47), actual
IFC inspection in the named external BIM application (W60), user interaction,
installation/upgrade/restore/uninstall on a target Windows desktop (W12), and
the visual review of text, navigation, selection and dialogs remain recorded
desktop acceptance activities. A Windows Server runner result does not claim
Windows 10/11 workstation or GPU-driver coverage.

The collector therefore records these separately:

- `windows_automated_acceptance_passed`: only true after the complete native
  Windows evidence passes.
- `windows_desktop_acceptance`: pending until the checklist has real results.
- `release_ready`: false in this validation kit.

An installer for user trials must be assembled from the exact accepted patched
host, include its dependency/license notices and source/patch provenance, and
be tested in a clean target desktop profile. This kit does not assemble or
publish a FreeCAD binary distribution automatically.

## GitHub operation

The workflow runs on the exact `acceptance/windows-history-fix` branch when
relevant files are pushed, or through manual dispatch after the workflow is in
the default branch. Its permissions are read-only and it uploads evidence for
seven days. It does not open the upstream proposal, create a release or merge
changes. Action versions are pinned to full commits.

The standard `windows-2022` runner is an execution route to try, subject to the
recorded disk/desktop preflight. The `desktop` option selects an **existing**
self-hosted Windows x64 runner with the label `3117-desktop`, running in a
logged-in interactive session. Creating a runner, purchasing capacity, changing
account permissions, and running a service as administrator are not part of
this workflow.

References: [GitHub runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[manual workflow execution](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
