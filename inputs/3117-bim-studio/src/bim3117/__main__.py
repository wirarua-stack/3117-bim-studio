# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line reference demonstration; no graphical editor is included."""
import argparse
from pathlib import Path
from .demo import create_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Write a reference model and wall schedule")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--ifc", action="store_true", help="Also export IFC4 (requires the ifc extra)")
    args = parser.parse_args()
    document = create_demo()
    args.output.mkdir(parents=True, exist_ok=True)
    document.save(args.output / "room.reference.json")
    document.write_schedule(args.output / "wall_schedule.csv")
    if args.ifc:
        try:
            from .ifc_export import export_ifc
            export_ifc(document, args.output / "room.ifc")
        except ImportError as exc:
            parser.exit(2, f"IFC dependency missing: {exc}. Install with: pip install '.[ifc]'\n")
    rows = document.quantities()
    print(f"Wrote reference outputs to {args.output.resolve()}")
    print(f"Walls: {len(rows)}; doors: {len(document.doors)}; units: metres")
    print(f"Gross wall volume: {sum(r['gross_volume_m3'] for r in rows):.3f} m3")
    print(f"Net wall volume: {sum(r['net_volume_m3'] for r in rows):.3f} m3")
    print("Scope: independent rectangular walls; junction union and BOQ rules are not implemented.")


if __name__ == "__main__":
    main()
