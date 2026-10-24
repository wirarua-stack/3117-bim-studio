# Third-party components and licensing

Verified against the linked upstream sources on **2026-10-23**.

Newly authored 3117 BIM Studio code is distributed under **GPL-3.0-or-later**. This does not change any upstream license, grant rights to third-party assets, or establish that every possible future package combination is compatible. The project's `LICENSE` and individual file notices govern the project's released code.

## What this release distributes

This release does **not** bundle FreeCAD, Bonsai, Blender, IfcOpenShell, That Open Components, web-ifc, or their binary distributions. It contains new project code and documentation referencing those tools, and the two unmodified Sarabun font files identified below. The workbench reuses a separately installed FreeCAD host and its Qt/PySide, Coin/Pivy and geometry runtime. The native IFC exporter uses IfcOpenShell from the separately installed FreeCAD Python runtime; CSV does not require it. Drawing PDF output uses that same host's QtSvg/QPdfWriter. The independent reference demo has its own optional pinned dependency. Instructions to install a dependency are distinct from redistributing its binaries or source.

The bundled Sarabun fonts retain their own **SIL Open Font License 1.1**, copyright and reserved-name notices in [OFL.txt](workbench/bim3117_freecad/fonts/OFL.txt). They are not relicensed as GPL. [SOURCE.json](workbench/bim3117_freecad/fonts/SOURCE.json) records each original download URL, size and SHA-256. The host loads these fonts only into this application; it does not install them system-wide. Self-contained SVG exports include the font data and OFL text, and PDFs embed the font programs used on the page. Other upstream runtimes remain separately installed.

## Component inventory

| Component | Role in this project | Verified upstream license | Distribution status |
| --- | --- | --- | --- |
| [FreeCAD](https://github.com/FreeCAD/FreeCAD) | Desktop host and authoring document; baseline uses FCStd | Core [LICENSE](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE): GNU LGPL v2.1. Individual source notices and dependencies require their own audit. | User-installed host; not bundled |
| [IfcOpenShell Python](https://github.com/IfcOpenShell/IfcOpenShell) | Native IFC4 exchange adapter and independent reference demonstration | Upstream component table: LGPL-3.0-or-later, with upstream dependency notes. [LGPL text at v0.9.0](https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/COPYING.LESSER). | Installed separately; not bundled |
| [Bonsai](https://bonsaibim.org/) | Actual cross-application IFC validation in isolated Blender; see versioned evidence | IfcOpenShell component table: GPL-3.0-or-later | Validation environment only; no copied upstream code or binaries |
| [That Open Components](https://github.com/ThatOpen/engine_components) | Candidate for a later web review/viewer application | [MIT](https://github.com/ThatOpen/engine_components/blob/main/LICENSE.md) | Not a current bundled dependency |
| [web-ifc](https://github.com/ThatOpen/engine_web-ifc) | Candidate IFC parser/writer for later browser features | [MPL-2.0](https://github.com/ThatOpen/engine_web-ifc/blob/main/LICENSE.md) | Not a current bundled dependency |
| [Sarabun](https://github.com/google/fonts/tree/main/ofl/sarabun) | Thai/Latin drawing labels and title blocks | SIL Open Font License 1.1; bundled upstream OFL text governs the font files | Unmodified Regular and Bold TTFs, OFL.txt and SOURCE.json are bundled |

This table is an evaluated-component inventory, not an installed-package bill of materials. The list of packages actually installed for a test run or shipped in a release must be generated from that environment. Other host components such as Qt, geometry libraries, fonts, and plugins are not covered by declaring the host's core license alone.

## Interpretation for contributors

- The FreeCAD host and 3117 Workbench remain identifiable projects. Preserve upstream attribution and do not imply upstream sponsorship.
- FreeCAD's historical standalone BIM add-on is not the current integration target. BIM is integrated into FreeCAD starting with v1.0; see the [upstream migration note](https://github.com/yorikvanhavre/BIM_Workbench).
- IfcOpenShell is a multi-component repository. Its LGPL libraries and GPL Bonsai code must not be treated as interchangeable license categories.
- If future code is adapted from Bonsai or another project, record its original path, commit, copyright notices, applicable license, and modifications. Do not relabel copied code as solely original 3117 work.
- MIT dependencies require preservation of their copyright and permission notice when relevant copies are distributed.
- LGPL and MPL redistribution obligations depend on the included component, modifications, and packaging form. Review the actual source and executable package against the upstream texts; merely naming a license in this table does not satisfy all distribution requirements.
- A native IFC authoring architecture remains a future ADR option. Referencing Bonsai does not mean this scaffold implements that architecture; the selected initial authoring baseline is the FreeCAD document/FCStd workflow.

## Release gate: attribution and dependency manifest

Before distributing a standalone installer, bundled dependency archive, or release that includes upstream code:

1. Generate a manifest/SBOM listing component name, exact version or commit, upstream URL, artifact checksum, SPDX license expression, source/binary origin, and whether it was modified.
2. Inspect transitive packages and optional plugins actually included, including geometry engines, UI libraries, fonts, templates and example data. Do not infer their licenses from a top-level repository badge.
3. Include applicable license texts and copyright notices with the release and provide a user-visible third-party notices location.
4. Make required covered source and modification source available in the form required by the relevant license, with a durable source/rebuild reference tied to that release.
5. Check applicable replacement/relinking and installation requirements for LGPL components and covered-source obligations for MPL components against the actual packaging method.
6. Keep a reproducible build description and preserve the tested compatibility matrix. Do not substitute a moving `latest` release for the version that passed the checks.
7. Review code-license compatibility before introducing a new dependency or copying implementation code. Separate distribution only when that reflects the actual architecture and license terms.

## Future assets have separate licenses

The proposed software license does not automatically license BIM component libraries, manufacturer objects, textures, photographs, logos, fonts, example projects, training material, or client models. Every contributed asset must identify its creator/source, redistribution permission, license, attribution, and relevant version. Client data must not be published as a test fixture merely because the software repository is public. Prefer original, synthetic fixtures whose publication rights are established.

Detailed capability evidence and archived-document caveats are recorded in [docs/SOURCES.md](docs/SOURCES.md).

## v0.2.1 executed compatibility environments

The native host verification used FreeCAD1.1.4 with its bundled IfcOpenShell0.8.4. Separate adapter/reference checks used IfcOpenShell0.9.0.post1. Actual IFC application review used Blender4.5.14 LTS and Bonsai0.9.0-post1-py311 with IfcOpenShell0.9.0.post1. These runtime binaries and the isolated test fonts/dependencies are not included in the 3117 package. Exact source URLs, artifact hashes and observed builds are in `docs/evidence/v0.2.1/` and `docs/TEST_ENVIRONMENT.json`.
