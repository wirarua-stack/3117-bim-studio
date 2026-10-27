# Windows graphical runner — 3117 BIM Studio acceptance

This is a **runner qualification guide**, not an acceptance result. The default GitHub-hosted Windows 2022 runner was independently measured as OpenGL 1.1.0 / Microsoft GDI Generic and **cannot** qualify for FreeCAD's GUI tests.

## Prerequisites
- Windows 10/11 x64 workstation with an interactive local desktop and GPU driver supporting at least OpenGL 2.0. Check the **actual OpenGL context**, not the adapter marketing specification.
- Reliable storage with >30 GiB free (more may be needed for two FreeCAD source builds), adequate RAM, Windows Build Tools / Visual Studio dependencies as pinned by the project, and access to GitHub.
- Keep this workstation in a logged-in interactive desktop session for GUI tests. An unattended Windows service / Session 0 or disconnected remote session is **not sufficient evidence** of an interactive graphics desktop.
- A repository administrator must register the runner using GitHub's official Settings → Actions → Runners → New self-hosted runner instructions, on a trusted machine. Do not put tokens or secrets in scripts or logs.
- Label the runner **3117-desktop** in addition to its standard `self-hosted`, `Windows`, and `X64` labels. Do not reuse this label for a non-graphical VM.
- Avoid a persistent account containing client or unrelated documents. Treat workflow execution on a self-hosted runner as code execution on the machine.

## Qualification order
1. Start the official runner from an **interactive desktop session**, not a Windows service, with an appropriate unlocked GUI. Confirm the workstation has a real GPU driver.
2. In Actions, manually invoke **Windows graphics capability preflight** with runner=`desktop`. The workflow records `runner-preflight.json`, `opengl.json`, and `runner-qualification.json`; these are **not** FreeCAD acceptance.
3. Require `runner-qualification.json.status = eligible_for_gui_test_attempt`: it checks Windows Session > 0, user-interactive visible window station, monitor/virtual screen, writable local build volume, native WGL >= 2.0, renderer/vendor, and same workflow-run provenance. Known software fallbacks such as GDI Generic are rejected. If any measurement fails, **do not build FreeCAD**. This is only permission to attempt GUI tests, not proof Qt/Coin works.
4. Independently validate a FreeCAD GUI launch and original unmodified `publicsmoke` when an accepted patched host is available. Do not infer that a successful OpenGL probe means Qt/Coin can render correctly.
5. Only after the export candidate has a reviewed integration path and the GUI runner is qualified, manually invoke **3117 Windows acceptance / patched FreeCAD 1.1.4** with runner=`desktop`. Its pre-build desktop+OpenGL qualification gate also fails closed and preserves the raw probe, runner preparation, and decision report.
6. Preserve build logs and evidence, verify frozen inputs, run the original crash sequences, Native 19/651 and Public GUI 248 + package 48 gates. Only seal the exact patched runtime after automated evidence passes, then perform the manual Windows desktop checklist.
7. Keep `release_ready=false` until the authorized release decision. Never merge upstream, publish a release, or weaken a check to satisfy the report.

## If no runner is available
The workflow may remain **queued**. This is not a FreeCAD test failure. Register/label a qualified Windows graphical runner; do not change `runs-on` back to `windows-2022` just to get a green job.

## Fast qualification checks (without a FreeCAD rebuild)

- The separate `Windows desktop GPU qualification contract tests` workflow runs synthetic positive and negative evidence fixtures on a GitHub-hosted Windows runner. Success **does not** qualify that runner.
- The manually dispatched `Windows graphics capability preflight` evaluates the **actual selected runner** and uploads all three JSON files, even if it fails.
- For a real interactive runner select `desktop`, label it `3117-desktop` and invoke the workflow from `acceptance/windows-history-fix`. A service process in Session 0, disconnected/non-visible desktop, no monitor, OpenGL < 2.0 or known software renderer must remain blocked.
- If the workflow remains `queued`, the runner may be absent/offline; do not misreport that as a GUI application failure. A GitHub Actions UI check of runner online status is still required.
- Acceptance has a separate gate; `runner-qualification.json` is never enough for `windows_automated_acceptance_passed` or `release_ready`.
