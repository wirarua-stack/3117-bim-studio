# GUI history-branch regression — failed on FreeCAD 1.1.4 Linux

The exact fresh GUI harness and its helper are archived before isolating the normal feature cases. `reopen-gui.log` records a native SIGSEGV in `Gui::Document::handleChildren3D` during `Gui::Document::redo`. This remains a failed release gate. The Python `finally` block did not run, so no completed check count is attributed to this run.

The failure is triggered by a real history branch: create a disposable Material, delete it, Undo twice, edit a surviving Type, Undo, then Redo. The archived harness preserves the complete original sequence, including its other schedule and document guard checks. The separate native evidence reproduces the failure without the 3117 addon, custom proxies, reader panels or restored files.

## Reproduce the archived original GUI run

Use a disposable FreeCAD 1.1.4 GUI process with the final 3117 addon installed. This reproduction can terminate the entire process and lose its unsaved documents; save all work and close other documents before starting it. Copy `original_freecad_types_gui.py` and `original_freecad_types_gui_reopen.py` into an isolated harness directory as `freecad_types_gui.py` and `freecad_types_gui_reopen.py`. Put that directory before the repository `tests` directory on the test-only `sys.path`; the remaining driver helpers come from `tests`. Do not put the workbench source on `sys.path`: the native addon must load from its installed location.

Copy this directory's `Types_Quantities_Workbench.FCStd` and `fixture-types-gui-report.json` into a temporary output directory; rename the JSON to `types-gui-report.json` and update only its `sample` path to the copied FCStd. Use only this synthetic fixture.

In the GUI macro, set `output_dir` to that temporary directory and defer the entry point exactly as the archived runner does:

```python
from PySide import QtCore

def run_regression():
    from freecad_types_gui_reopen import main
    main(output_dir)

QtCore.QTimer.singleShot(1500, run_regression)
```

Let the macro return to FreeCAD's event loop before the callback starts. Calling `main(output_dir)` directly at macro top level can retain the macro's native transaction context and stop the test before it reaches the intended history sequence. The original `.FCMacro` is retained as historical execution context; its absolute temporary paths are not portable.

The isolated feature acceptance run exercises type/schedule roundtrips before the disposable-material lifecycle. Its feature count does not pass or replace this history-branch gate. Every new feature report records `host_history_branch_gate: failed_native_host` and `overall_release_ready: false` until a preserving-history host fix is verified.
