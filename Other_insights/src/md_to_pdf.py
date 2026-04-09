"""
Markdown-to-PDF converter using ReportLab.
Handles headings, paragraphs, bullet/numbered lists, bold/italic, tables, and HRs.
"""

import re
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, KeepTogether,
)

SCRIPT_DIR = Path(__file__).parent
BASE_DIR   = SCRIPT_DIR.parent
INPUT_MD   = BASE_DIR / "gap_analysis_report.md"
OUTPUT_PDF = BASE_DIR / "gap_analysis_report.pdf"

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm
USABLE_W = PAGE_W - 2 * MARGIN

# ─── Styles ───────────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#1a3c5e")
DARK = colors.HexColor("#222222")
GREY = colors.HexColor("#555555")

def build_styles():
    return {
        "h1": ParagraphStyle("h1", fontSize=18, leading=24, spaceAfter=8, spaceBefore=16,
                             fontName="Helvetica-Bold", textColor=NAVY),
        "h2": ParagraphStyle("h2", fontSize=14, leading=19, spaceAfter=6, spaceBefore=14,
                             fontName="Helvetica-Bold", textColor=NAVY, borderPad=4),
        "h3": ParagraphStyle("h3", fontSize=11, leading=15, spaceAfter=4, spaceBefore=10,
                             fontName="Helvetica-Bold", textColor=colors.HexColor("#2d5f8a")),
        "body": ParagraphStyle("body", fontSize=9.5, leading=14, spaceAfter=5,
                               fontName="Helvetica", textColor=DARK, alignment=TA_JUSTIFY),
        "italic": ParagraphStyle("italic", fontSize=9.5, leading=14, spaceAfter=6,
                                 fontName="Helvetica-Oblique", textColor=GREY),
        "bullet": ParagraphStyle("bullet", fontSize=9.5, leading=14, spaceAfter=3,
                                 fontName="Helvetica", textColor=DARK, leftIndent=16),
        "tcell": ParagraphStyle("tcell", fontSize=7.5, leading=10, fontName="Helvetica",
                                textColor=DARK),
        "theader": ParagraphStyle("theader", fontSize=7.5, leading=10, fontName="Helvetica-Bold",
                                  textColor=colors.white),
    }

# ─── Inline markup ────────────────────────────────────────────────────────────
def _inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text

# ─── Table builder ────────────────────────────────────────────────────────────
def _build_table(header_cells, body_rows, styles):
    n_cols = len(header_cells)
    col_w = USABLE_W / n_cols

    data = [[Paragraph(_inline(c.strip()), styles["theader"]) for c in header_cells]]
    for row in body_rows:
        cells = [c.strip() for c in row]
        while len(cells) < n_cols:
            cells.append("")
        data.append([Paragraph(_inline(c), styles["tcell"]) for c in cells[:n_cols]])

    tbl = Table(data, colWidths=[col_w] * n_cols, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 7.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING",  (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl

# ─── Parser ───────────────────────────────────────────────────────────────────
def _parse_table_row(line):
    """Split '| a | b | c |' into ['a', 'b', 'c']."""
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]

def _is_separator(line):
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))

def md_to_flowables(md_text, styles):
    flowables = []
    lines = md_text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Blank
        if not stripped:
            flowables.append(Spacer(1, 3))
            i += 1; continue

        # Table detection: line starts with |
        if stripped.startswith("|") and i + 1 < n and _is_separator(lines[i + 1]):
            header = _parse_table_row(stripped)
            i += 2  # skip header + separator
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_parse_table_row(lines[i]))
                i += 1
            flowables.append(Spacer(1, 4))
            flowables.append(_build_table(header, body, styles))
            flowables.append(Spacer(1, 4))
            continue

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(_inline(stripped[2:]), styles["h1"]))
            i += 1; continue

        # H2
        if stripped.startswith("## ") and not stripped.startswith("### "):
            flowables.append(Spacer(1, 6))
            flowables.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.HexColor("#cccccc"), spaceAfter=3))
            flowables.append(Paragraph(_inline(stripped[3:]), styles["h2"]))
            i += 1; continue

        # H3
        if stripped.startswith("### "):
            flowables.append(Paragraph(_inline(stripped[4:]), styles["h3"]))
            i += 1; continue

        # HR
        if stripped in ("---", "***", "___"):
            flowables.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#dddddd"), spaceAfter=6))
            i += 1; continue

        # Full-line italic
        if stripped.startswith("*") and stripped.endswith("*") and stripped.count("*") == 2:
            flowables.append(Paragraph(_inline(stripped[1:-1]), styles["italic"]))
            i += 1; continue

        # Numbered list
        m = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if m:
            flowables.append(Paragraph(f"{m.group(1)}. {_inline(m.group(2))}", styles["bullet"]))
            i += 1; continue

        # Bullet
        if stripped.startswith("- ") or stripped.startswith("* "):
            flowables.append(Paragraph(f"\u2022 {_inline(stripped[2:])}", styles["bullet"]))
            i += 1; continue

        # Regular paragraph
        flowables.append(Paragraph(_inline(stripped), styles["body"]))
        i += 1

    return flowables


def convert(input_path=INPUT_MD, output_path=OUTPUT_PDF):
    md_text  = input_path.read_text(encoding="utf-8")
    styles   = build_styles()
    flows    = md_to_flowables(md_text, styles)

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2 * cm,  bottomMargin=2 * cm,
        title="Demand-Supply Gap Analysis — AB PM-JAY UP",
        author="Other Insights Analytics Pipeline",
    )
    doc.build(flows)
    print(f"PDF written -> {output_path}")


if __name__ == "__main__":
    convert()
