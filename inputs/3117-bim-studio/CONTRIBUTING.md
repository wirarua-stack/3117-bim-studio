# Contributing

Start with the acceptance case in the issue. Keep changes focused on one user workflow and record which host/library versions were exercised.

## Development

Use a Python virtual environment. `python -m pip install -e .` installs the dependency-free reference core. `python -m pip install -e ".[ifc]"` adds the tested optional IFC adapter. Run `python -m unittest discover -s tests -v`.

Production FreeCAD uses its own Python/Qt runtime. Do not install arbitrary PySide or Qt wheels over the host runtime. The reference-core test environment is separate.

## Pull requests

Explain the concrete problem, behavior changed, acceptance evidence and limitations. All document mutations must use a transaction and preserve IDs and unit semantics. A host adapter change requires actual FreeCAD evidence before it can be described as supported.

Do not include private project models or credentials. Add a minimal synthetic fixture when a geometry bug needs reproduction. Contributions must be licensed under GPL-3.0-or-later for new project code. Retain notices on third-party material; do not paste upstream code without checking its license. Declare substantial AI-assisted code in the PR and review it with the same rigor as other contributions.

Upstream fixes should be contributed upstream when practical. Follow that project's own contribution policy when opening an upstream PR.
