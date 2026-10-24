# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only SVG/PDF publication from native drawing definitions.

Uses the existing per-file atomic bundle publisher with caught-failure rollback
and metadata last. The model AND drawing revisions are checked before staging
and immediately before publication. PDF painting uses the host Qt only.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from . import drawing_render
from .export_files import ExportFileError, publish_bundle
from .model import FoundationError


SVG_NS = "http://www.w3.org/2000/svg"


def output_paths(path, format="pdf"):
    if format not in ("pdf", "svg"):
        raise FoundationError("Drawing export format must be pdf or svg")
    requested = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    if requested.suffix.lower() != "." + format or not requested.stem.strip():
        raise FoundationError(f"Choose a nonempty .{format} filename for this drawing")
    return [str(requested), str(requested.with_name(requested.stem + f"_{format}_metadata.json"))]


def _capture(sheet, expected_model_revision=None, expected_drawing_revision=None):
    from . import drawings
    captured = drawings.capture_sheet(sheet)
    if expected_model_revision is not None and captured["model_revision"] != expected_model_revision:
        raise FoundationError("The model changed since the drawing preview; refresh the sheet before export")
    if expected_drawing_revision is not None and captured["drawing_revision"] != expected_drawing_revision:
        raise FoundationError("The drawing definition changed since the preview; refresh the sheet before export")
    return captured


def _check_current(sheet, captured):
    from . import drawings
    current = drawings.capture_sheet(sheet)
    if (current["model_revision"] != captured["model_revision"]
            or current["drawing_revision"] != captured["drawing_revision"]):
        raise FoundationError("The model or drawing changed during export; no new files were published")


def _validate_svg(svg, captured):
    try:
        root = ET.fromstring(svg)
        if root.tag != "{" + SVG_NS + "}svg" or root.get("viewBox") != "0 0 420 297":
            raise ValueError("Unexpected SVG paper coordinates")
        if root.get("width") != "420mm" or root.get("height") != "297mm":
            raise ValueError("SVG physical paper size is not A3 landscape")
        metadata = root.find("{" + SVG_NS + "}metadata")
        provenance = json.loads(metadata.text)
        if any(provenance[key] != captured[key] for key in ("model_revision", "drawing_revision")):
            raise ValueError("SVG provenance differs from captured source")
        if list(root.iter("{" + SVG_NS + "}image")):
            raise ValueError("Unexpected raster image in vector drawing")
        groups = [item for item in root.iter("{" + SVG_NS + "}g") if item.get("id", "").startswith("view-")]
        if len(groups) != len(captured["views"]):
            raise ValueError("SVG view inventory differs from captured sheet")
    except (ET.ParseError, AttributeError, TypeError, ValueError, KeyError) as error:
        raise FoundationError("SVG readback validation failed; no drawing files were published") from error
    return {"status": "passed", "page_count": 1, "paper_mm": [420.0, 297.0],
            "view_count": len(groups), "vector_geometry": True, "embedded_sarabun_fonts": True,
            "source_revisions_match": True}


def _write_pdf(path, svg, captured):
    drawing_render.ensure_fonts(required=True)
    from PySide import QtCore, QtGui, QtSvg
    geometry_svg, text_records = _pdf_layers(svg)
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(geometry_svg))
    if not renderer.isValid():
        raise FoundationError("The host Qt renderer could not load the drawing SVG")
    writer = QtGui.QPdfWriter(str(path))
    writer.setResolution(600)
    page = QtGui.QPageLayout(QtGui.QPageSize(QtGui.QPageSize.A3),
                            QtGui.QPageLayout.Landscape, QtCore.QMarginsF(0, 0, 0, 0),
                            QtGui.QPageLayout.Millimeter)
    page.setMode(QtGui.QPageLayout.FullPageMode)
    if not writer.setPageLayout(page):
        raise FoundationError("The host Qt PDF writer could not set A3 landscape")
    writer.setCreator("3117 BIM Studio / native FreeCAD drawing export")
    writer.setTitle(str(captured["sheet"]["number"]) + " - " + str(captured["sheet"]["name"]))
    if hasattr(writer, "setAuthor"):
        writer.setAuthor(str(captured["sheet"].get("author", "")))
    painter = QtGui.QPainter()
    if not painter.begin(writer):
        raise FoundationError("The host Qt PDF writer could not open the staged drawing file")
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        # Scale millimetres to the writer's coordinate units explicitly. Using
        # integer writer.width()/height() would introduce avoidable rounding.
        units_per_mm = writer.resolution() / 25.4
        painter.scale(units_per_mm, units_per_mm)
        renderer.render(painter, QtCore.QRectF(0, 0, 420, 297))
        _paint_pdf_text(painter, text_records)
    finally:
        ended = painter.end()
    if not ended:
        raise FoundationError("The host Qt PDF painter did not finish writing the sheet")
    del painter, writer, renderer
    return _validate_pdf(path)


def _pdf_layers(svg):
    """Separate our own paper-space text for an embedded-font PDF layer.

    QtSvg may paint SVG text as glyph outlines, which looks right but loses
    searchable text and font subsets. Geometry still uses the exact preview
    SVG; only the generated text nodes are painted through QPainter.drawText.
    No geometry, label, size, position or anchor is independently recomputed.
    """
    root = ET.fromstring(svg)
    records = []
    for parent in root.iter():
        for element in list(parent):
            if element.tag != "{" + SVG_NS + "}text":
                continue
            if any(child.tag != "{" + SVG_NS + "}title" for child in element):
                raise FoundationError("The generated PDF text layer contains unsupported nested text")
            record = dict(element.attrib)
            # SVG <title> stores the full label for accessibility, not visible
            # characters. Its tail contains our fitted display label.
            record["text"] = (element.text or "") + "".join(child.tail or "" for child in element)
            records.append(record)
            parent.remove(element)
    if not records:
        raise FoundationError("The generated drawing has no text layer")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), records


def _paint_pdf_text(painter, records):
    from PySide import QtCore, QtGui
    for record in records:
        x, y, size = (float(record[key]) for key in ("x", "y", "font-size"))
        anchor = record.get("text-anchor", "start")
        if anchor not in ("start", "middle", "end"):
            raise FoundationError("The generated drawing has an unsupported PDF text anchor")
        angle = 0.0
        if "transform" in record:
            match = re.fullmatch(r"rotate\(([\d.+-]+) ([\d.+-]+) ([\d.+-]+)\)", record["transform"])
            if match is None or (float(match[2]), float(match[3])) != (x, y):
                raise FoundationError("The generated drawing has an unsupported PDF text transform")
            angle = float(match[1])
        font = QtGui.QFont(drawing_render.FONT_FAMILY)
        # A large integral pixel size avoids rounding our 2.2–7 mm paper fonts.
        # The local painter transform maps its metrics back to exact mm.
        font.setPixelSize(1000)
        font.setBold(int(record.get("font-weight", 400)) >= 600)
        font.setHintingPreference(QtGui.QFont.PreferNoHinting)
        painter.save()
        try:
            painter.translate(x, y)
            painter.rotate(angle)
            painter.scale(size / 1000.0, size / 1000.0)
            painter.setFont(font)
            painter.setPen(QtGui.QColor(record.get("fill", drawing_render.INK)))
            metrics = QtGui.QFontMetricsF(font, painter.device())
            width = metrics.horizontalAdvance(record["text"])
            offset = -width if anchor == "end" else (-width / 2 if anchor == "middle" else 0.0)
            painter.drawText(QtCore.QPointF(offset, 0), record["text"])
        finally:
            painter.restore()


def _validate_pdf(path):
    """Check actual Qt-written PDF framing, page inventory and MediaBox.

    This is a focused structural readback gate, not a general PDF conformance
    validator. The release suite additionally renders and inspects the pages.
    """
    data = Path(path).read_bytes()
    try:
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-128:]:
            raise ValueError("Missing PDF header/trailer")
        pages = len(re.findall(rb"/Type\s*/Page\b", data))
        if pages != 1:
            raise ValueError("Expected exactly one PDF page")
        box = re.search(rb"/MediaBox\s*\[\s*([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s+([\d.+-]+)\s*\]", data)
        if box is None:
            raise ValueError("Missing PDF media box")
        x0, y0, x1, y1 = map(float, box.groups())
        width, height = (x1 - x0) * 25.4 / 72.0, (y1 - y0) * 25.4 / 72.0
        if not math.isclose(width, 420.0, abs_tol=.2) or not math.isclose(height, 297.0, abs_tol=.2):
            raise ValueError("PDF physical paper size is not A3 landscape")
        if re.search(rb"/Subtype\s*/Image\b", data):
            raise ValueError("Unexpected raster image in vector drawing PDF")
        if b"/FontFile2" not in data and b"/FontFile3" not in data:
            raise ValueError("The PDF contains no embedded drawing font")
    except (ValueError, TypeError) as error:
        raise FoundationError("PDF readback validation failed; no drawing files were published: " + str(error)) from error
    return {"status": "passed", "page_count": pages, "paper_mm": [width, height],
            "vector_geometry": True, "embedded_fonts": True, "text_layer": "host QPainter text from the preview SVG",
            "engine": "FreeCAD host Qt QSvgRenderer / QPainter / QPdfWriter",
            "readback_scope": "Header/trailer, one page, physical MediaBox, no raster image objects, embedded font program"}


def export_sheet(sheet, path, format="pdf", overwrite=False,
                 expected_model_revision=None, expected_drawing_revision=None):
    captured = _capture(sheet, expected_model_revision, expected_drawing_revision)
    rendered = drawing_render.render_sheet(captured)
    paths = [Path(item) for item in output_paths(path, format)]
    validation = dict(rendered["validation"])
    # Reject malformed geometry/provenance before opening a publication stage.
    validation["svg"] = _validate_svg(rendered["svg"], captured)
    if format == "pdf":
        drawing_render.ensure_fonts(required=True)

    def writer(staged):
        if format == "svg":
            staged[0].write_text(rendered["svg"], encoding="utf-8")
            validation["svg"] = _validate_svg(staged[0].read_text(encoding="utf-8"), captured)
        else:
            validation["pdf"] = _write_pdf(staged[0], rendered["svg"], captured)
        metadata = {"export_schema": 1, "format": format,
                    "source": "FreeCAD native drawing definitions / FCStd", "editable_master": False,
                    "model_revision": captured["model_revision"], "drawing_revision": captured["drawing_revision"],
                    "capture": captured, "layout": rendered["layout"], "validation": validation,
                    "files": [{"name": paths[0].name, "bytes": staged[0].stat().st_size,
                               "sha256": hashlib.sha256(staged[0].read_bytes()).hexdigest()}],
                    "publication": "Payload replaced atomically per file; this metadata is the final completion marker. Verify its payload hash. Caught failures roll back; the bundle is not crash-atomic.",
                    "freshness": "Compare both model_revision and drawing_revision with a fresh native sheet capture; exports do not update when the model changes.",
                    "annotation_policy": rendered["layout"]["annotation_policy"],
                    "fonts": drawing_render._font_assets()[3]}
        staged[-1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    try:
        publish_bundle(paths, writer, overwrite=overwrite,
                       before_commit=lambda: _check_current(sheet, captured))
    except ExportFileError as error:
        raise FoundationError(str(error)) from error
    return {"format": format, "files": [str(path) for path in paths], "metadata_path": str(paths[-1]),
            "model_revision": captured["model_revision"], "drawing_revision": captured["drawing_revision"],
            "validation": validation}
