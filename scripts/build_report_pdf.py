#!/usr/bin/env python3
"""Build a styled PDF report and append the project's captured evidence images."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "report" / "report_draft.md"
OUTPUT = ROOT / "output" / "pdf" / "lab_network_programming_report.pdf"
SCREENSHOTS = ROOT / "screenshots"

NAVY = colors.HexColor("#18324B")
BLUE = colors.HexColor("#176B87")
PALE = colors.HexColor("#EAF2F6")
GRID = colors.HexColor("#C7D2DA")
INK = colors.HexColor("#202A33")


def normalize(text: str) -> str:
    return (text.replace("\u2011", "-").replace("\u2013", "-")
            .replace("\u2014", "-").replace("\u2212", "-")
            .replace("\u00a0", " "))


def inline_markup(text: str) -> str:
    text = html.escape(normalize(text), quote=False)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text.replace("  ", " ")


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells)


def add_table(lines: list[str], width: float, body_style: ParagraphStyle) -> LongTable:
    rows = [split_table_row(line) for line in lines if not is_table_separator(line)]
    if not rows:
        return LongTable([[]])
    ncols = max(len(row) for row in rows)
    weights = [max(14, min(36, max(len(row[i]) if i < len(row) else 0 for row in rows))) for i in range(ncols)]
    total = sum(weights)
    widths = [width * value / total for value in weights]
    cell_style = ParagraphStyle("TableCell", parent=body_style, fontSize=7.4, leading=9.2, spaceAfter=0)
    head_style = ParagraphStyle("TableHead", parent=cell_style, textColor=colors.white, fontName="Helvetica-Bold")
    data = []
    for ridx, row in enumerate(rows):
        row = row + [""] * (ncols - len(row))
        style = head_style if ridx == 0 else cell_style
        data.append([Paragraph(inline_markup(value), style) for value in row])
    return LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1, spaceBefore=5, spaceAfter=9,
                     style=TableStyle([
                         ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                         ("VALIGN", (0, 0), (-1, -1), "TOP"),
                         ("LEFTPADDING", (0, 0), (-1, -1), 5),
                         ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                         ("TOPPADDING", (0, 0), (-1, -1), 4),
                         ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                         ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                     ]))


def header_footer(canvas, doc):
    canvas.saveState()
    page_w, page_h = letter
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, page_h - 35, page_w - doc.rightMargin, page_h - 35)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#526575"))
    canvas.drawString(doc.leftMargin, page_h - 27, "NETWORK PROGRAMMING | INTERNET ARCHIVE COLLECTION")
    canvas.line(doc.leftMargin, 33, page_w - doc.rightMargin, 33)
    canvas.drawString(doc.leftMargin, 21, "Single-run macOS comparison; platform limits disclosed")
    canvas.drawRightString(page_w - doc.rightMargin, 21, f"{doc.page}")
    canvas.restoreState()


def build_story(text: str, content_width: float):
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=23,
                                leading=27, textColor=NAVY, alignment=TA_LEFT, spaceAfter=6),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=base["Heading2"], fontName="Helvetica", fontSize=13,
                                   leading=17, textColor=BLUE, spaceAfter=13),
        "h1": ParagraphStyle("Section", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=15,
                             leading=18, textColor=NAVY, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "h2": ParagraphStyle("Subsection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11,
                             leading=14, textColor=BLUE, spaceBefore=8, spaceAfter=4, keepWithNext=True),
        "body": ParagraphStyle("ReportBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9.1,
                               leading=12.4, textColor=INK, alignment=TA_LEFT, spaceAfter=6),
        "meta": ParagraphStyle("Meta", parent=base["BodyText"], fontSize=9, leading=12, textColor=INK, spaceAfter=2),
        "bullet": ParagraphStyle("Bullet", parent=base["BodyText"], fontSize=8.8, leading=11.7, textColor=INK,
                                 leftIndent=13, firstLineIndent=-8, spaceAfter=3),
        "caption": ParagraphStyle("Caption", parent=base["BodyText"], fontSize=9, leading=12,
                                  textColor=NAVY, alignment=TA_CENTER, spaceAfter=8),
        "appendix": ParagraphStyle("Appendix", parent=base["Heading1"], fontSize=18, leading=22,
                                    textColor=NAVY, spaceAfter=9),
    }
    lines = text.splitlines()
    story = []
    in_meta = True
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            story.append(add_table(table_lines, content_width, styles["body"]))
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline_markup(line[2:]), styles["title"]))
            story.append(Spacer(1, 2))
        elif line.startswith("## "):
            if line == "## Executive summary":
                in_meta = False
            if line == "## 5. Firewall, rate limiting, and concurrency":
                story.append(PageBreak())
            if line == "## 6. Machine-learning analysis: classification and regression":
                story.append(PageBreak())
            heading = Paragraph(inline_markup(line[3:]), styles["subtitle"] if in_meta else styles["h1"])
            story.append(heading)
            if in_meta:
                story.append(Spacer(1, 4))
        elif line.startswith("### "):
            story.append(Paragraph(inline_markup(line[4:]), styles["h2"]))
            in_meta = False
        elif line.startswith("- "):
            bullet = line[2:]
            if bullet.startswith("[x] "):
                bullet = "Completed - " + bullet[4:]
            elif bullet.startswith("[ ] "):
                bullet = "Pending - " + bullet[4:]
            story.append(Paragraph("&#8226; " + inline_markup(bullet), styles["bullet"]))
            in_meta = False
        else:
            # Keep the front-page team/course/date/status block visually compact.
            style = styles["meta"] if in_meta and line.startswith("**") else styles["body"]
            paragraph = Paragraph(inline_markup(line), style)
            lookahead = i + 1
            while lookahead < len(lines) and not lines[lookahead].strip():
                lookahead += 1
            if lookahead < len(lines) and lines[lookahead].strip().startswith("|"):
                table_lines = []
                while lookahead < len(lines) and lines[lookahead].strip().startswith("|"):
                    table_lines.append(lines[lookahead].strip())
                    lookahead += 1
                story.append(KeepTogether([paragraph, add_table(table_lines, content_width, styles["body"])]))
                i = lookahead - 1
            else:
                story.append(paragraph)
            if not line.startswith("**Team:") and not line.startswith("**Course:") and not line.startswith("**Report date:") and not line.startswith("**Status:"):
                in_meta = False
        i += 1
    return story


def add_evidence(story, width: float, height: float, styles):
    evidence = [
        ("iftop_en0.png", "iftop on en0: live interface-level connections; background traffic may be present."),
        ("nload_en0.png", "nload on en0: live total interface throughput, not scraper-only traffic."),
        ("api_conversations.png", "Wireshark TCP Conversations for api_r1.pcap."),
        ("bs4_conversations.png", "Wireshark TCP Conversations for bs4_r1.pcap."),
        ("selenium_conversations.png", "Wireshark TCP Conversations for selenium_r1.pcap."),
        ("selenium_io_graph.png", "Selenium I/O Graph with 1-second intervals; packet rate varies across the run."),
        ("selenium_rtt_graph.png", "TCP RTT graph for one selected Selenium stream; diagnostic only, not end-to-end latency."),
        ("mac_pf_firewall_demo.png", "macOS PF block and recovery demonstration. This is a documented platform substitute, not UFW."),
    ]
    story.extend([PageBreak(), Paragraph("Appendix A - Captured evidence", styles["appendix"]),
                  Paragraph("These screenshots document the Mac interface monitors, packet analysis, and the scoped macOS PF demonstration. The macOS evidence does not satisfy a strict Linux UFW/ss requirement.", styles["body"])])
    for index, (filename, caption) in enumerate(evidence):
        path = SCREENSHOTS / filename
        if not path.exists():
            continue
        if index > 0:
            story.append(PageBreak())
        story.append(Paragraph(inline_markup(caption), styles["caption"]))
        img = Image(str(path))
        img.drawWidth, img.drawHeight = img._restrictSize(width, height)
        story.append(img)
        story.append(Spacer(1, 5))
        story.append(Paragraph(inline_markup(filename), ParagraphStyle("Filename", parent=styles["caption"], fontSize=7.5, textColor=colors.HexColor("#697987"))))


def add_ml_figures(story, width: float, height: float, styles):
    figures = [
        ("report/ml/figures/holdout_confusion_matrices.png", "Expanded 17,727-item paired popularity experiment: holdout confusion matrices."),
        ("report/ml/phase2/figures/phase2_confusion_genre_classical.png", "Three-genre classifier holdout confusion matrix; genre accuracy is not popularity accuracy."),
        ("report/ml/phase2/figures/phase2_confusion_juvenile_classical.png", "Archive juvenile-marker classifier holdout confusion matrix."),
    ]
    story.extend([PageBreak(), Paragraph("Appendix B - Machine-learning figures", styles["appendix"]),
                  Paragraph("These figures use the expanded coworker experiments and their saved holdout results. The children-audience experiment is not included because its labels remain provisional pending human review.", styles["body"])])
    for filename, caption in figures:
        path = ROOT / filename
        if not path.exists():
            continue
        story.append(PageBreak())
        story.append(Paragraph(inline_markup(caption), styles["caption"]))
        img = Image(str(path))
        img.drawWidth, img.drawHeight = img._restrictSize(width, height)
        story.append(img)
        story.append(Spacer(1, 5))
        story.append(Paragraph(inline_markup(Path(filename).name), ParagraphStyle("MLFilename", parent=styles["caption"], fontSize=7.5, textColor=colors.HexColor("#697987"))))


def main():
    source = SOURCE.read_text(encoding="utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=letter, rightMargin=0.62 * inch, leftMargin=0.62 * inch,
                            topMargin=0.68 * inch, bottomMargin=0.62 * inch,
                            title="Website Data Collection Efficiency and Network Behavior",
                            author="Issa and Mohammad", subject="Internet Archive API, BS4, and Selenium comparison")
    styles = getSampleStyleSheet()
    caption = ParagraphStyle("AppendixCaption", parent=styles["BodyText"], fontSize=9, leading=12,
                             textColor=NAVY, alignment=TA_CENTER, spaceAfter=8)
    story = build_story(source, doc.width)
    appendix_title = ParagraphStyle("AppendixTitle", parent=styles["Heading1"], fontSize=18, leading=22,
                                    textColor=NAVY, spaceAfter=9)
    appendix_body = ParagraphStyle("AppendixBody", parent=styles["BodyText"], fontSize=9, leading=12,
                                   textColor=INK, spaceAfter=6)
    add_evidence(story, doc.width, doc.height - 1.1 * inch,
                 {"caption": caption, "body": appendix_body, "appendix": appendix_title})
    add_ml_figures(story, doc.width, doc.height - 1.1 * inch,
                   {"caption": caption, "body": appendix_body, "appendix": appendix_title})
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
