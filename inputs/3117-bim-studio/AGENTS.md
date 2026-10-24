# Development guidance for contributors and coding agents

- Read README.md, docs/ARCHITECTURE.md, docs/ACCEPTANCE.md and the current issue before editing.
- Current release is a v0.5.0 Types and Quantities development candidate. Keep Linux evidence and pending Windows acceptance distinct; do not claim Revit parity or cross-application IFC verification without evidence.
- v0.5.0 Pilot/production acceptance is blocked by the proven native FreeCAD 1.1.4 Linux history-branch crash in docs/HOST_COMPATIBILITY.md. Preserve the original failed sequence and no-addon repro; do not clear Undo history, reorder a test silently, or claim feature-only passes resolve this blocker.
- Production model authority is FreeCAD Document / FCStd. Reference JSON is a test fixture, not a second editable master.
- Preserve stable IDs, explicit unit conversions, level/type/host semantics, transaction rollback and Undo/Redo.
- Use FreeCAD/OCCT for production geometry. Do not substitute display meshes for design definitions or quantity solids.
- Keep the authored Wall → Door/Window → derived WallBody dependency graph acyclic. WallBody is a calculated result, not a second authored wall or a second quantity row.
- Treat .rvt/.rfa support, MEP design and structural calculations as out of the current scope.
- Use the host's Qt/PySide runtime. Do not add a second Qt runtime to FreeCAD.
- Do not publish client files, secrets or fabricated benchmark results.
- Add tests only for material behavior and risks. Report skipped dependencies and untested host paths explicitly.
- Do not publish a remote repository or send messages from automation unless the user has authorized that action.

- Native snapshot/export uses committed document content; content revisions are hashes, not monotonically increasing history counters.
- Keep all export omissions explicit, one row per authored UUID, SI units, no silent overwrite, and validate IFC readback before publication.
- Preserve per-file atomic replacement / caught-failure rollback wording; do not claim crash-atomic multi-file export.

- Slab/Beam use Level + Offset as their TOP datum; thickness/depth extend down. Columns are vertical rectangular members.
- Limited joins are Slab priority over Column/Beam only. Preserve one connected positive-volume solid and authored dimensions; keep cuts and quantities in the same transaction.
- Keep old empty-building category hashes compatible; new CSV sidecars appear only for nonempty categories. Current metadata determines bundle membership.
- DrawingSet/View/Sheet are persistent native definitions outside Project.Group. Keep them out of building content hashes and IFC products; report their omission in coverage.
- Drawing publication requires both a fresh model revision and a fresh drawing revision. Preview/export must not add native objects, history entries, or persistent render caches.
- Use actual OCCT cuts and global hidden-line projection. A3 sheets have one or two views at an explicit scale; reject overflow rather than silently changing scale.
- Use only the host Qt runtime for PDF; bundle the unmodified Sarabun fonts with their OFL notice and source checksums. Do not install fonts system-wide.

- Native Material/ElementType and optional WallType catalogue fields live in Project.Group; typed dimensions are derived caches and geometry resolves the linked Type directly.
- Shared Type preflight must evaluate all proposed openings and Slab cutters simultaneously before opening the transaction; invalid proposals must preserve the Redo branch.
- Wall layers grow along local +Y from zero; Slab layers run top-down. Actual material intersections must conserve gross/net product volume; do not add material rows again to product totals.
- ScheduleSet/Schedule are native definitions outside Project.Group. Keep expected filter UUIDs on broken links; exclude schedule definitions from building hashes but require both model and schedule revisions for row edits/publication.
- Preserve legacy hashes and six category CSV bytes for documents without catalogue features. Material assignment coverage must disclose unassigned products; infer no prices, densities or global overlap deductions.
