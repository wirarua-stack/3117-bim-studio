# Source-only workbench packaging

The v0.5.0 distribution is a **development candidate with a known native host blocker**, described in [HOST_COMPATIBILITY.md](../docs/HOST_COMPATIBILITY.md). Passing installation and feature macros does not pass that separate history-branch acceptance gate.

The installer runs inside the user's FreeCAD and uses its Python and Qt runtime. It never downloads FreeCAD, invokes pip, writes to Program Files, modifies another add-on, or publishes a repository. The initial target baseline is FreeCAD **1.1.4**; Windows runtime verification is a separate release gate.

## Build

From the repository root with a development Python:

```bash
python -m unittest discover -s packaging/tests -v
python scripts/build_workbench_package.py --output out/3117_BIM_Studio_v0_5_0_FreeCAD.zip
```

The ZIP includes workbench sources, the two installation macros, installer helpers, installation guide, project license, third-party notices, and per-file SHA-256 manifest. It also includes Foundation, Wall/Door, Quantity/Exchange, Building and Drawings native, fresh-process and GUI harnesses, their nineteen-stage host runner and six GUI test macros. The builder rejects a smoke macro without its GUI harness or a host runner without its native/reopen harnesses.

Foundation, Wall/Door, Quantity/Exchange, Building and Drawings scope, Windows acceptance, verification, architecture and source-reference documents are included when present, together with JSON evidence from `docs/evidence/` and native examples/screenshots in `examples/freecad/` and coherent exchange outputs in `examples/exchange/` and `examples/building/`, plus native drawing definitions, vector SVG/PDF, metadata and actual FreeCAD previews in `examples/drawings/`. The release builder must run after verification records and the examples are finalized. The manifest detects accidental content changes when compared; it is not a digital signature or a claim of trusted provenance. FreeCAD/Qt/IfcOpenShell binaries are not bundled. The reference core is a separate source package.

## Installation behavior

- The destination is the exact host user profile's `Mod/BIM3117`.
- Source files are staged before replacing the active folder. Failure during promotion attempts to restore the prior folder; any failed recovery leaves the prior folder in its backup location for manual restoration.
- Only an installation bearing this project's receipt can be replaced or uninstalled. Unknown folders are left untouched.
- Version backups and uninstall archives are outside `Mod`, in `BIM3117_Backups`; they are never automatically deleted.
- Restore moves one selected own backup into place and preserves the previous version as another backup.
- Filesystem links/reparse points, relative user paths and backup path traversal are rejected. A per-profile exclusive lock prevents concurrent installers.
- Both macros ask for the extracted distribution directory when their source location is unavailable. They must not be moved alone without the helper files.
- All running FreeCAD windows must be restarted after a change. The helper does not hot-reload Python code or change `.FCStd` files.

Tests use temporary directories and synthetic payloads. Passing them is not evidence of a Windows GUI installation or a working BIM command. Record the host version/build, OS, exact ZIP checksum and GUI/model tests separately before making a support claim.

## Native host verification

The repository's `.github/workflows/freecad-host.yml` downloads pinned official FreeCAD 1.1.4 artifacts for Linux and Windows, verifies their SHA-256 values, and uses the same isolated user profile for nineteen separate host processes: install, Foundation, Foundation reopen, Wall/Door, Wall/Door reopen, Exchange, Exchange reopen, Building, Building reopen, Drawing geometry, Drawings, Drawings reopen Drawing render/publication, Types/Types reopen, Types exchange/Types exchange reopen and Schedules/Schedules reopen. It checks JSON reports as well as exit codes because FreeCAD can report Python errors without a failing process exit. The workbench source directory is not added to `sys.path` as a substitute for installation.

Workflow authoring or static checks do not count as an executed Windows result. The Windows runner and [interactive Windows acceptance](../docs/WINDOWS_ACCEPTANCE.md) remain distinct gates. See [CI_HOSTS.md](CI_HOSTS.md) for exact artifact pins, action provenance and the report contract; see [VERIFICATION.md](../docs/VERIFICATION.md) for recorded executions.

See [INSTALL_TH.md](INSTALL_TH.md) for end-user instructions. Metadata follows the upstream [Package Metadata](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Package_Metadata.md) format; no GitHub URL is invented for this unpublished project.

`Run_3117_Exchange_Test.FCMacro` and its actual Qt dialog/export harness are included. CSV/IFC dependencies are checked in the host; the installer does not install IfcOpenShell automatically.

`Run_3117_Building_Test.FCMacro` exercises Slab/Column/Beam/Window, bounded joins, native Undo/Redo and expanded quantity rows. Public GUI harnesses are deferred until the macro returns control to the event loop so native Undo/Redo actions remain enabled.

`Run_3117_Drawings_Test.FCMacro` exercises actual View/Sheet forms, native Undo/Redo, live preview, two source hashes, SVG/PDF and overwrite consent. The workbench bundles unmodified Sarabun Regular/Bold with their OFL notice and source checksums; fonts load only into the application. No FreeCAD/Qt runtime is bundled.

## v0.5.0 Types and Quantities

`Run_3117_Types_Test.FCMacro` exercises the actual catalogue/layers/type-assignment and schedule source-edit/publication dialogs. New native/fresh-process suites cover combined shared-type geometry proposals, material conservation/assignment coverage and preserved invalid-proposal Redo. `examples/types` contains the synthetic typed FCStd, coherent IFC/CSV and nine schedule bundles. `docs/TYPES_AND_QUANTITIES.md` specifies native authority, quantity rules and current limitations.
