# SPDX-License-Identifier: GPL-3.0-or-later
"""FreeCADCmd entrypoint; inspect the JSON report, not only host exit status."""
import json
import os
from pathlib import Path
import sys
import traceback

import FreeCAD as App

sys.path.insert(0, str(Path(__file__).resolve().parent))
destination = Path(os.environ.get("BIM3117_QA_OUTPUT", str(Path.cwd() / "test-artifacts")))
destination.mkdir(parents=True, exist_ok=True)
stage = os.environ.get("BIM3117_QA_STAGE", "foundation")
if stage == "install":
    report = {"status": "running", "freecad": App.Version(), "checks": [], "checks_passed": 0}
    try:
        repository = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(repository / "packaging"))
        from install_support import install
        installation = install(repository, App.getUserAppDataDir())
        report.update(status="passed", installation=installation, checks_passed=1,
                      checks=[{"name": "installed at host-provided user addon directory", "status": "passed"}])
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (destination / "install-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
elif stage == "foundation":
    from freecad_foundation import main
    report = main(destination)
elif stage == "reopen":
    from freecad_reopen import main
    report = main(destination)
elif stage == "architecture":
    from freecad_architecture import main
    report = main(destination)
elif stage == "architecture_reopen":
    from freecad_architecture_reopen import main
    report = main(destination)
elif stage == "exchange":
    from freecad_exchange import main
    report = main(destination)
elif stage == "exchange_reopen":
    from freecad_exchange_reopen import main
    report = main(destination)
elif stage == "building":
    from freecad_building import main
    report = main(destination)
elif stage == "building_reopen":
    from freecad_building_reopen import main
    report = main(destination)
elif stage == "drawing_geometry":
    from freecad_drawing_geometry import main
    report = main(destination)
elif stage == "drawings":
    from freecad_drawings import main
    report = main(destination)
elif stage == "drawings_reopen":
    from freecad_drawings_reopen import main
    report = main(destination)
elif stage == "drawing_render":
    from freecad_drawing_render import main
    report = main(destination)
elif stage == "types":
    from freecad_types import main
    report = main(destination)
elif stage == "types_reopen":
    from freecad_types_reopen import main
    report = main(destination)
elif stage == "types_exchange":
    from freecad_types_exchange import main
    report = main(destination)
elif stage == "types_exchange_reopen":
    from freecad_types_exchange import reopen
    report = reopen(destination)
elif stage == "schedules":
    from freecad_schedules import main
    report = main(destination)
elif stage == "schedules_reopen":
    from freecad_schedules_reopen import main
    report = main(destination)
else:
    raise ValueError("Unknown BIM3117_QA_STAGE; use install, foundation, reopen, architecture, architecture_reopen, exchange, exchange_reopen, building, building_reopen, drawing_geometry, drawings, drawings_reopen, drawing_render, types, types_reopen, types_exchange, types_exchange_reopen, schedules or schedules_reopen")
print(json.dumps({"stage": stage, "status": report["status"], "checks_passed": report["checks_passed"]}, indent=2))
