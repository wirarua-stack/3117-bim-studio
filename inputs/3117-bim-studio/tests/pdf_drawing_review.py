#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent review of the two frozen canonical PDFs, outside FreeCAD.

Requires PyMuPDF in an independent QA environment, never installed into the
FreeCAD host. Verifies actual PDF vectors/fonts/text and the native 1:50 fixture
dimensions; optional PNGs make every delivered page available for visual QA.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

import fitz


def review(examples, output, render_directory=None):
    examples, output = Path(examples), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if render_directory is not None:
        render_directory = Path(render_directory)
        render_directory.mkdir(parents=True, exist_ok=True)
    checks, pages = [], []
    report = {"status": "running", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "pymupdf": fitz.VersionBind,
              "checks": checks, "pages": pages,
              "scope": "Independent canonical PDF structure, font, text, vector scale and render review; not a printer or Windows test"}

    def check(name, condition, **details):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed", **details})

    def distance(a, b):
        return math.hypot(a[0]-b[0], a[1]-b[1])

    try:
        for number, expected_height in (("A101", 4500.0), ("A201", 6150.0)):
            path = examples/("3117_" + number + ".pdf")
            metadata = json.loads(path.with_name(path.stem + "_pdf_metadata.json").read_text(encoding="utf-8"))
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            check(number + " published payload matches metadata", metadata["files"][0]["sha256"] == sha256
                  and metadata["files"][0]["bytes"] == path.stat().st_size)
            with fitz.open(path) as document:
                check(number + " is a one-page PDF", document.is_pdf and document.page_count == 1)
                page = document[0]
                width, height = page.rect.width*25.4/72, page.rect.height*25.4/72
                check(number + " nominal A3 landscape page", abs(width-420)<.2 and abs(height-297)<.2,
                      observed_mm=[width,height], tolerance_mm=.2,
                      note="Qt expresses the MediaBox in integer PDF points; drawing vectors use exact millimetres")
                check(number + " has no raster image objects", not page.get_images(full=True))
                fonts = page.get_fonts(full=True)
                programs = {font[3]: len(document.extract_font(font[0])[3]) for font in fonts}
                check(number + " embeds both Sarabun font programs", set(programs)=={"Sarabun-Bold","Sarabun-Regular"}
                      and all(n>1000 for n in programs.values()), embedded_font_bytes=programs)
                text = page.get_text()
                check(number + " has selectable Thai and source revision text",
                      number in text and "6,500" in text and any("\u0e00" <= char <= "\u0e7f" for char in text)
                      and metadata["model_revision"][:16] in text and metadata["drawing_revision"][:16] in text)
                line_segments = []
                paths = page.get_drawings()
                for drawing in paths:
                    for item in drawing["items"]:
                        if item[0] == "l":
                            a,b = item[1:3]
                            line_segments.append(((a.x*25.4/72,a.y*25.4/72),
                                                  (b.x*25.4/72,b.y*25.4/72)))
                check(number + " contains actual vector paths", len(line_segments)>100,
                      path_count=len(paths), line_count=len(line_segments))
                measurements=[]
                for view in metadata["layout"]["views"]:
                    expected = {"view_x":6500.0, "view_y":expected_height}
                    check(number + " " + view["name"] + " retains canonical dimensions and scale",
                          view["scale_denominator"]==50 and len(view["dimensions"])==2
                          and all(math.isclose(d["value_mm"],expected[d["axis"]],abs_tol=.001) for d in view["dimensions"]))
                    for dimension in view["dimensions"]:
                        a,b = dimension["paper_endpoints_mm"]
                        matches=[(p,q) for p,q in line_segments
                                 if (distance(p,a)<.001 and distance(q,b)<.001)
                                 or (distance(p,b)<.001 and distance(q,a)<.001)]
                        check(number + " " + view["name"] + " " + dimension["axis"] + " dimension is present at exact PDF coordinates", bool(matches))
                        observed = distance(*matches[0])
                        required = expected[dimension["axis"]]/50
                        check(number + " " + view["name"] + " " + dimension["axis"] + " has true physical 1:50 length",
                              abs(observed-required)<.001, observed_paper_mm=observed,
                              expected_paper_mm=required, tolerance_mm=.001)
                        measurements.append({"view":view["name"],"axis":dimension["axis"],
                                             "native_mm":expected[dimension["axis"]],"paper_mm":observed})
                check(number + " all text is inside the paper", all(0<=block[0]<=block[2]<=page.rect.width
                      and 0<=block[1]<=block[3]<=page.rect.height for block in page.get_text("blocks")))
                item={"file":path.name,"sha256":sha256,"paper_mm":[width,height],"measurements":measurements,
                      "model_revision":metadata["model_revision"],"drawing_revision":metadata["drawing_revision"]}
                if render_directory is not None:
                    png=render_directory/(path.stem+".png")
                    page.get_pixmap(dpi=144,alpha=False).save(png)
                    item["rendered_page"]=str(png)
                    item["png_sha256"]=hashlib.sha256(png.read_bytes()).hexdigest()
                pages.append(item)
        report["status"]="passed"
    except BaseException as error:
        report.update(status="failed",error=str(error),traceback=traceback.format_exc())
        raise
    finally:
        report["checks_passed"]=len(checks)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples",type=Path,default=Path(__file__).resolve().parents[1]/"examples/drawings")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--render-directory",type=Path)
    args=parser.parse_args()
    result=review(args.examples,args.output,args.render_directory)
    print(json.dumps({"status":result["status"],"checks_passed":result["checks_passed"],"pages":len(result["pages"])}))
