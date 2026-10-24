# Bonsai application review — v0.2.1

Date: 2026-10-23. This review opened the **actual native-exported IFC** in Bonsai running inside Blender, inspected the resulting Blender scene, and captured the visible application. It is separate from the FreeCAD exporter's own IfcOpenShell readback.

**Result: 41 application, geometry, metadata and full EXPRESS checks passed; 42 checks passed including the verified visible GUI capture.** The [application report](evidence/v0.2.1/bonsai-application-report.json) and [Bonsai screenshot](../examples/exchange/Bonsai_Native_IFC_Review.png) are the recorded evidence. Check counts are assertions within this fixture review, not independent unit-test counts or a benchmark.

Bonsai uses IfcOpenShell itself. This proves import and inspection in another application, with independent measurements and ray casts against Blender meshes. It does not prove another IFC geometry engine, Revit interoperability, or Windows desktop acceptance. The recorded run was on Linux; Windows remains pending.

## 1. Exact fixture and provenance

The following files belong to the same native test run and must be kept together:

| Input | Purpose |
|---|---|
| [Quantity_Exchange_Workbench.ifc](../examples/exchange/Quantity_Exchange_Workbench.ifc) | Native IFC4 payload opened in Bonsai |
| [exchange-snapshot.json](../examples/exchange/exchange-snapshot.json) | Authored UUIDs, placements, levels, dimensions and content revision |
| [linux-exchange-report.json](evidence/v0.2.1/linux-exchange-report.json) | Passing installed-FreeCAD suite with independently expected wall volumes |
| [Quantity_Exchange_Workbench_ifc_metadata.json](../examples/exchange/Quantity_Exchange_Workbench_ifc_metadata.json) | Export coverage, validation and payload provenance |

IFC SHA-256:

```text
a62ab703c0170ba9134d0c81ae0ba7932ab04d6ff7da6e44fc6fb01a005aac25
```

Native content revision:

```text
31b79c638cc70358bb6d8fa92005a1922ca7fd248332650582ce19d636da6cf0
```

The fixture has three authored Walls, three Doors, three Openings, one shared WallType and three Storeys at -3, 0 and 3 m. Exactly six authored Blender mesh products are present: three walls and three door frames. Derived native WallBody objects do not create duplicate IFC walls. Grid is explicitly reported as a reference omission in export coverage.

| Wall | Independently expected net volume | Observed Blender mesh volume | Absolute error |
|---|---:|---:|---:|
| W201, horizontal wall | 3.222 m³ | 3.2220001252591595 m³ | 1.253 × 10⁻⁷ m³ |
| Diagonal basement | 2.380 m³ | 2.3799996745487713 m³ | 3.255 × 10⁻⁷ m³ |
| Reversed wall | 2.064 m³ | 2.0639995403289615 m³ | 4.597 × 10⁻⁷ m³ |

The final fixture's total native net wall volume is **7.666 m³**. The 3.222 → 3.582 m³ level-edit case is exercised in the native suite before restoring the baseline; 3.582 m³ is not the final exported W201 volume. FreeCAD assigned the actual wall label W201 because its requested W200 label conflicted with the type label; identity comparisons use UUIDs.

Measurements use `max(2e-6, abs(expected) * 2e-6)` tolerance. Triangle volumes are accumulated with a translated origin, Python double-precision determinants and `math.fsum`; this limits cancellation from global coordinates. The mesh geometry itself is unchanged.

## 2. Actual runtime and official artifacts

| Component | Recorded runtime |
|---|---|
| Exporting host | FreeCAD 1.1.4, embedded Python 3.11.14, bundled IfcOpenShell 0.8.4 |
| Reviewing application | Blender 4.5.14 LTS, build `62c1db4208e8` |
| Blender Python | 3.11.15 |
| Bonsai | `0.9.0-post1-py311` |
| Bonsai's IfcOpenShell | `0.9.0.post1` |
| OS and display | Linux x86_64, isolated profile, Xvfb GUI at 1600 × 1100, software OpenGL |
| Full schema / EXPRESS validation | **0 findings** in the Bonsai runtime |

Official sources used for the application and extension:

- [Bonsai installation instructions](https://docs.bonsaibim.org/studio/quickstart/installation.html).
- [Bonsai extension version history](https://extensions.blender.org/add-ons/bonsai/versions/).
- [Exact Bonsai 0.9.0-post1 Python 3.11 Linux x64 ZIP](https://extensions.blender.org/download/sha256:c6e486d096a05584c18fa03ae92ac7799998a4bb6d975161c698d02aa5bb79e2/add-on-bonsai-v0.9.0-post1-py311-linux-x64.zip).
- [Exact Blender 4.5.14 Linux x64 archive](https://download.blender.org/release/Blender4.5/blender-4.5.14-linux-x64.tar.xz).
- [Official Blender 4.5.14 checksums](https://download.blender.org/release/Blender4.5/blender-4.5.14.sha256).

The actual archives were hashed before use. Blender's archive hash was compared with the official checksum list; the Bonsai hash matched the content-addressed official download URL.

| Archive | Bytes | SHA-256 |
|---|---:|---|
| `blender-4.5.14-linux-x64.tar.xz` | 378,045,212 | `9ba871ff2ecd36526b77432745980b7e6664ecd0c7ca11c48849073dcfe06da3` |
| `add-on-bonsai-v0.9.0-post1-py311-linux-x64.zip` | 170,349,791 | `c6e486d096a05584c18fa03ae92ac7799998a4bb6d975161c698d02aa5bb79e2` |

The 3117 package does not redistribute these binaries. The review script does not download or install dependencies, and nothing is installed into FreeCAD's Python/Qt environment.

## 3. What the script verifies

[tests/bonsai_exchange_review.py](../tests/bonsai_exchange_review.py) is a portable parameterization of the script used for this review. It retains the same import, numeric, metadata, geometry and EXPRESS assertions. The parameterized wrapper was syntax checked; the accepted application evidence was produced by the original equivalent script before path parameterization.

The script calls Bonsai's public `bpy.ops.bim.load_project` operator, then checks the active Bonsai IFC and its real Blender objects. It verifies metre scale, counts, unique GlobalIds, native UUIDs, content revision, shared type and base-level containment. For each wall, it compares Blender triangle volume with the independently expected native fixture value, checks transformed world bounds, and compares imported quantity properties with the mesh volume.

For each door, it checks the host → opening → filling relationships, frame volume and world placement. Rays through the wall thickness must miss material inside the opening and hit material beside and above it. Rays also confirm the generic three-sided frame has an open centre and solid jamb. Door dimensions describe the overall wall cut including the frame; no leaf, swing or handing is represented.

The final checks run full `ifcopenshell.validate.validate(..., express_rules=True)` in Bonsai's separate runtime and confirm that opening the model did not change the source IFC bytes. This fixture-specific harness expects three walls and three doors; it is not a general acceptance test for arbitrary IFC files.

## 4. Run the portable review

Use a newly started Blender process with a disposable review profile. **The harness clears the current Blender scene.** Install and enable Bonsai in that profile using its official instructions, save preferences, then close Blender before running the harness. Keep the profile separate from an authoring session.

The commands below are run from the repository root. Set the Blender path for your installation. These variables select a dedicated profile; create the directories before first launching Blender to install/enable the add-on.

```bash
export BIM3117_BLENDER="/absolute/path/to/blender"
export BIM3117_REVIEW_PROFILE="$PWD/out/bonsai-profile"
export BLENDER_USER_CONFIG="$BIM3117_REVIEW_PROFILE/config"
export BLENDER_USER_SCRIPTS="$BIM3117_REVIEW_PROFILE/scripts"
export BLENDER_USER_EXTENSIONS="$BIM3117_REVIEW_PROFILE/extensions"
mkdir -p "$BLENDER_USER_CONFIG" "$BLENDER_USER_SCRIPTS" "$BLENDER_USER_EXTENSIONS"
```

For the application and geometry checks in background mode:

```bash
"$BIM3117_BLENDER" --background --python-exit-code 1 \
  --python tests/bonsai_exchange_review.py -- \
  --ifc examples/exchange/Quantity_Exchange_Workbench.ifc \
  --snapshot examples/exchange/exchange-snapshot.json \
  --native-report docs/evidence/v0.2.1/linux-exchange-report.json \
  --output out/bonsai-background-review
```

Expected report: `status: passed`, `background: true`, `review_mode: background_application`, `visual_review.status: not_run`, and **41 checks**. This runs Bonsai import and Blender mesh checks without a visible GUI; it does not satisfy the screenshot review.

For an actual visible application review:

```bash
"$BIM3117_BLENDER" --window-geometry 0 0 1600 1100 \
  --python tests/bonsai_exchange_review.py -- \
  --ifc examples/exchange/Quantity_Exchange_Workbench.ifc \
  --snapshot examples/exchange/exchange-snapshot.json \
  --native-report docs/evidence/v0.2.1/linux-exchange-report.json \
  --output out/bonsai-gui-review \
  --gui-hold-seconds 0
```

Use a fresh output directory on every run. Existing report, screenshot or capture sentinel files are rejected to keep evidence from different runs separate. The four paths can alternatively be supplied through `BIM3117_REVIEW_IFC`, `BIM3117_REVIEW_SNAPSHOT`, `BIM3117_REVIEW_NATIVE_REPORT` and `BIM3117_REVIEW_OUTPUT`. Place script arguments after Blender's `--` separator.

On a successful GUI import, the script redraws the application, writes `capture.ready`, and records `status: geometry_passed_capture_pending` with **41 checks**. `--gui-hold-seconds 0` leaves the window open for inspection; the default waits 12 seconds and then closes the dedicated Blender process. Read the report's status and error fields; an application process exit code alone is not acceptance.

## 5. Capture and inspect the visible GUI

The recorded Linux run used an external X11 root framebuffer capture through Pillow `ImageGrab`. An initial attempt using Blender's internal screenshot operator produced an entirely black PNG. That image was rejected after inspection. A PNG existing on disk is insufficient evidence of a visible application.

After `capture.ready` appears, capture the active review display using the operating system's screenshot tool. Save it as `Bonsai_Native_IFC_Review.png` in that run's output directory. In an isolated Linux/X11 review display, the following equivalent capture can be run from a separate system Python that already has Pillow available:

```bash
export BIM3117_REVIEW_OUTPUT="$PWD/out/bonsai-gui-review"
# DISPLAY must identify the display containing this Blender review window.
python - <<'PY'
import json
import os
from pathlib import Path
from PIL import ImageGrab

out = Path(os.environ["BIM3117_REVIEW_OUTPUT"])
assert (out / "capture.ready").is_file(), "Blender has not finished its GUI checks"
report_path = out / "bonsai-application-report.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["status"] == "geometry_passed_capture_pending"
picture = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
nonblack = any(high > 0 for low, high in picture.convert("RGB").getextrema())
assert nonblack, "Captured framebuffer is black"
picture.save(out / "Bonsai_Native_IFC_Review.png")
report["gui_capture"] = {
    "method": "X11 root framebuffer via Pillow ImageGrab",
    "image_size": list(picture.size),
    "nonblack": nonblack,
}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

Open the PNG and inspect it at normal size. Confirm it shows the real Bonsai application and imported model, not a black screen, another application or a stale image. Check that the three walls and door frames are visible, openings pass through the walls, and the scene tree/project panel exposes the expected model. The recorded 1600 × 1100 capture passed this visual inspection, showing IFC4, three wall/door instances, the signed storeys and the real openings.

Only after that inspection, complete the review record. The following snippet records that the reviewer has actually performed the preceding visual check; it does not perform that check automatically:

```bash
python - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["BIM3117_REVIEW_OUTPUT"])
path = out / "bonsai-application-report.json"
report = json.loads(path.read_text(encoding="utf-8"))
assert report["status"] == "geometry_passed_capture_pending"
assert not report["background"] and report["checks_passed"] == 41
assert report["gui_capture"]["nonblack"]
assert (out / "Bonsai_Native_IFC_Review.png").is_file()
report["checks"].append({
    "name": "actual Bonsai GUI framebuffer captured with visible pixels",
    "status": "passed",
})
report["visual_review"] = {"status": "passed", "method": "visible screenshot inspected by reviewer"}
report["checks_passed"] = len(report["checks"])
report["status"] = "passed"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

The completed GUI review contains **42 passed checks**, a nonblack capture and a recorded visual inspection. Keep the report and screenshot with the exact IFC, snapshot and native report used. A newly generated fixture has new UUIDs and potentially a new content revision; it needs its own application review rather than reusing this record.
