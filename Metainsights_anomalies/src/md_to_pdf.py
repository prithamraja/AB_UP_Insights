# =============================================================================
# Markdown to PDF converter using ReportLab
# Converts reports/executive_metainsight_report.md to .pdf
#
# Run from project root:
#   python src/md_to_pdf.py
# =============================================================================

import os
import re
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT    = os.path.join(BASE_DIR, "reports", "executive_metainsight_report.md")
OUTPUT   = os.path.join(BASE_DIR, "reports", "executive_metainsight_report.pdf")


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def build_styles():
    base = getSampleStyleSheet()

    styles = {}

    styles["h1"] = ParagraphStyle(
        "h1",
        fontSize=20, leading=26, spaceAfter=10, spaceBefore=20,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a2e"),
    )
    styles["h2"] = ParagraphStyle(
        "h2",
        fontSize=15, leading=20, spaceAfter=6, spaceBefore=18,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#16213e"),
        borderPad=4,
    )
    styles["h3"] = ParagraphStyle(
        "h3",
        fontSize=12, leading=16, spaceAfter=4, spaceBefore=12,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#0f3460"),
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontSize=10, leading=15, spaceAfter=6, spaceBefore=0,
        fontName="Helvetica", textColor=colors.HexColor("#222222"),
    )
    styles["italic"] = ParagraphStyle(
        "italic",
        fontSize=10, leading=15, spaceAfter=8, spaceBefore=0,
        fontName="Helvetica-Oblique", textColor=colors.HexColor("#555555"),
    )
    styles["bullet"] = ParagraphStyle(
        "bullet",
        fontSize=10, leading=15, spaceAfter=3, spaceBefore=0,
        fontName="Helvetica", textColor=colors.HexColor("#222222"),
        leftIndent=16, bulletIndent=0,
    )

    return styles


# ---------------------------------------------------------------------------
# Inline markup: **bold** and *italic* → ReportLab XML tags
# ---------------------------------------------------------------------------

def inline_markup(text: str) -> str:
    """Convert **bold** and *italic* markdown to ReportLab XML."""
    # Escape XML special chars first (except & which we handle carefully)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # *italic* (single asterisk not preceded/followed by *)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


# ---------------------------------------------------------------------------
# Parse Markdown lines into ReportLab flowables
# ---------------------------------------------------------------------------

def md_to_flowables(md_text: str, styles: dict) -> list:
    flowables = []
    lines = md_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line
        if not stripped:
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # H1
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = inline_markup(stripped[2:].strip())
            flowables.append(Spacer(1, 6))
            flowables.append(Paragraph(text, styles["h1"]))
            i += 1
            continue

        # H2
        if stripped.startswith("## ") and not stripped.startswith("### "):
            text = inline_markup(stripped[3:].strip())
            flowables.append(Spacer(1, 8))
            flowables.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.HexColor("#cccccc"), spaceAfter=4))
            flowables.append(Paragraph(text, styles["h2"]))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            text = inline_markup(stripped[4:].strip())
            flowables.append(Paragraph(text, styles["h3"]))
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            flowables.append(Spacer(1, 6))
            flowables.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor("#dddddd"), spaceAfter=6))
            i += 1
            continue

        # Italic line (*text* or _text_ at full line level)
        if stripped.startswith("*") and stripped.endswith("*") and stripped.count("*") == 2:
            text = inline_markup(stripped[1:-1])
            flowables.append(Paragraph(text, styles["italic"]))
            i += 1
            continue

        # Numbered list item
        m = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if m:
            text = inline_markup(m.group(2))
            flowables.append(Paragraph(f"{m.group(1)}. {text}", styles["bullet"]))
            i += 1
            continue

        # Bullet list item
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = inline_markup(stripped[2:])
            flowables.append(Paragraph(f"• {text}", styles["bullet"]))
            i += 1
            continue

        # Regular paragraph
        text = inline_markup(stripped)
        flowables.append(Paragraph(text, styles["body"]))
        i += 1

    return flowables


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def convert(input_path: str = INPUT, output_path: str = OUTPUT):
    with open(input_path, encoding="utf-8") as f:
        md_text = f.read()

    styles = build_styles()
    flowables = md_to_flowables(md_text, styles)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title="PM-JAY UP Analytical Findings Report",
        author="Automated MetaInsight Analysis",
    )
    doc.build(flowables)
    print(f"PDF written -> {output_path}")


if __name__ == "__main__":
    convert()
