"""
export_service.py
Handles TXT / CSV / Excel export of transcription segments.
Each segment: { start: float, end: float, speaker: str, text: str }
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union

logger = logging.getLogger(__name__)


def _fmt_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS"""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _fmt_range(start: float, end: float) -> str:
    return f"{_fmt_time(start)}-{_fmt_time(end)}"


def pad_visual(text: str, target_width: int) -> str:
    """Pad a string with spaces to match target visual width (treating non-ASCII as width 2)"""
    visual_len = sum(2 if ord(c) > 127 else 1 for c in text)
    padding = max(0, target_width - visual_len)
    return text + (" " * padding)


def wrap_text(text: str, max_chars: int = 50) -> List[str]:
    """Wrap text into list of lines, each <= max_chars visual width"""
    lines = []
    current_line = []
    current_len = 0
    for char in text:
        char_len = 2 if ord(char) > 127 else 1
        if current_len + char_len > max_chars:
            lines.append("".join(current_line))
            current_line = [char]
            current_len = char_len
        else:
            current_line.append(char)
            current_len += char_len
    if current_line:
        lines.append("".join(current_line))
    return lines or [""]


def export_txt(segments: List[Dict], export_path: Path) -> Path:
    """Export plain text: 時間 | 話者 | 文字起こし with perfect column alignment and wrapping"""
    export_path = Path(export_path).with_suffix(".txt")
    with open(export_path, "w", encoding="utf-8") as f:
        # Headers
        time_hdr = pad_visual("時間", 8)
        speaker_hdr = pad_visual("話者", 10)
        f.write(f"{time_hdr} | {speaker_hdr} | 文字起こし\n")
        f.write("-" * 80 + "\n")
        
        for seg in segments:
            time_str = _fmt_time(seg.get("start", 0))
            speaker = seg.get("speaker", "Unknown")
            # Translate default "Speaker N" to "話者N" for Japanese style
            if speaker.startswith("Speaker "):
                speaker = speaker.replace("Speaker ", "話者")
                
            text = seg.get("text", "").strip()
            text_lines = wrap_text(text, 50)
            
            time_col = pad_visual(time_str, 8)
            spk_col = pad_visual(speaker, 10)
            f.write(f"{time_col} | {spk_col} | {text_lines[0]}\n")
            
            for line in text_lines[1:]:
                time_empty = pad_visual("", 8)
                spk_empty = pad_visual("", 10)
                f.write(f"{time_empty} | {spk_empty} | {line}\n")
    logger.info(f"TXT exported: {export_path}")
    return export_path


def export_doc(segments: List[Dict], export_path: Path) -> Path:
    """Export MS Word readable HTML-based .doc transcript"""
    export_path = Path(export_path).with_suffix(".doc")
    with open(export_path, "w", encoding="utf-8") as f:
        f.write(
            "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
            "xmlns:w='urn:schemas-microsoft-com:office:word' "
            "xmlns='http://www.w3.org/TR/REC-html40'>\n"
            "<head>\n"
            "<meta charset='utf-8'>\n"
            "<title>Transcript</title>\n"
            "<style>\n"
            "body { font-family: 'MS Gothic', 'Meiryo', 'Arial', sans-serif; font-size: 10.5pt; color: #1e293b; }\n"
            "h2 { color: #1e3a5f; border-bottom: 2px solid #1e3a5f; padding-bottom: 5px; }\n"
            "table { border-collapse: collapse; width: 100%; margin-top: 15px; }\n"
            "th, td { border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }\n"
            "th { background-color: #1e3a5f; color: white; font-weight: bold; }\n"
            "tr:nth-child(even) { background-color: #f8fafc; }\n"
            ".time-cell { font-weight: bold; color: #0f172a; width: 20%; }\n"
            ".text-cell { line-height: 1.5; }\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            "<h2>文字起こしデータ書き出し / Transcript Export</h2>\n"
            "<table>\n"
            "<thead>\n"
            "<tr>\n"
            "<th>時間 / 話者 (Time / Speaker)</th>\n"
            "<th>文字起こし (Transcript)</th>\n"
            "</tr>\n"
            "</thead>\n"
            "<tbody>\n"
        )
        for seg in segments:
            time_str = _fmt_range(seg.get("start", 0), seg.get("end", 0))
            speaker = seg.get("speaker", "Unknown")
            if speaker.startswith("Speaker "):
                speaker = speaker.replace("Speaker ", "話者")
            text = seg.get("text", "").strip().replace("\n", "<br/>")
            
            f.write(
                "<tr>\n"
                f"<td class='time-cell'><b>{time_str}</b><br/>{speaker}</td>\n"
                f"<td class='text-cell'>{text}</td>\n"
                "</tr>\n"
            )
            
        f.write(
            "</tbody>\n"
            "</table>\n"
            "</body>\n"
            "</html>\n"
        )
    logger.info(f"DOC exported: {export_path}")
    return export_path


def export_csv(segments: List[Dict], export_path: Path) -> Path:
    """Export CSV with columns: Time, Speaker, Transcript"""
    export_path = Path(export_path).with_suffix(".csv")
    with open(export_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Time", "Speaker", "Transcript"])
        for seg in segments:
            time_str = _fmt_range(seg.get("start", 0), seg.get("end", 0))
            speaker = seg.get("speaker", "Unknown")
            text = seg.get("text", "").strip()
            writer.writerow([time_str, speaker, text])
    logger.info(f"CSV exported: {export_path}")
    return export_path


def export_excel(segments: List[Dict], export_path: Path) -> Path:
    """Export styled Excel workbook: Time | Speaker | Transcript"""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        logger.warning("openpyxl not installed — falling back to CSV")
        return export_csv(segments, export_path)

    export_path = Path(export_path).with_suffix(".xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transcript"

    # Header style
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11, name="Noto Sans JP")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = ["Time", "Speaker", "Transcript"]
    col_widths = [24, 16, 90]

    for col_idx, (header, width) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 22

    # Data rows
    for row_idx, seg in enumerate(segments, start=2):
        time_str = _fmt_range(seg.get("start", 0), seg.get("end", 0))
        speaker = seg.get("speaker", "Unknown")
        text = seg.get("text", "").strip()

        # Alternate row shading
        fill_color = "F0F4FA" if row_idx % 2 == 0 else "FFFFFF"
        row_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

        data = [time_str, speaker, text]
        for col_idx, value in enumerate(data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = row_fill
            cell.border = border
            cell.font = Font(name="Noto Sans JP", size=10)
            if col_idx == 3:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="top")

    # Freeze header row
    ws.freeze_panes = "A2"

    wb.save(export_path)
    logger.info(f"Excel exported: {export_path}")
    return export_path


def export_pdf(
    segments: List[Dict],
    export_path: Path,
    max_chars_per_page: int = 1000,
    pdf_template: str = "corporate",
    job_filename: Optional[str] = None,
    job_duration: Union[float, str, None] = None,
    font_size: Optional[float] = None,
    row_padding: Optional[float] = None
) -> Path:
    """Export formatted A4 PDF transcript using ReportLab, dynamically styled by the selected template."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
    except ImportError:
        logger.error("ReportLab library not available for PDF export")
        raise RuntimeError("ReportLab library not installed. PDF export is not supported.")

    export_path = Path(export_path).with_suffix(".pdf")

    # 1. Register a standard Windows Japanese TrueType font
    japanese_font_name = "Helvetica"
    font_registered = False

    font_paths = [
        r"C:\Windows\Fonts\yugothm.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\msmincho.ttc",
    ]

    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("JapaneseFont", fp))
                japanese_font_name = "JapaneseFont"
                font_registered = True
                logger.info(f"Registered Japanese TTF font: {fp}")
                break
            except Exception as e:
                logger.warning(f"Failed to register TTF font {fp}: {e}")

    if not font_registered:
        # Fall back to ReportLab CJK built-in CID Font
        try:
            from reportlab.pdfbase.cidfonts import CIDFont
            pdfmetrics.registerFont(CIDFont('HeiseiMin-W3'))
            japanese_font_name = 'HeiseiMin-W3'
            font_registered = True
            logger.info("Registered Japanese CID standard font: HeiseiMin-W3")
        except Exception as e:
            logger.warning(f"Failed to register CJK CID font: {e}")

    # Resolve selected template options (10 Premium Templates)
    t_opt = {
        "primary_bg": colors.HexColor("#1e3a5f"),
        "primary_text": colors.white,
        "row_alt_bg": colors.HexColor("#f8fafc"),
        "row_base_bg": colors.white,
        "title_color": colors.HexColor("#1e3a5f"),
        "grid_color": colors.HexColor("#cbd5e1"),
        "text_color": colors.HexColor("#1e293b"),
        "font": japanese_font_name,
        "margin_lr": 24,
        "margin_tb": 36,
        "padding": 3,
        "fontSize": 8,
        "leading": 11,
        "grid_width": 0.5,
        "no_grid_vertical": False,
        "meta_text_color": colors.HexColor("#64748b"),
        "line_color": colors.HexColor("#e2e8f0"),
        "banner_text": "SmartGrid Transcript AI - Corporate Slate Report"
    }

    if pdf_template == "eco":
        t_opt.update({
            "primary_bg": colors.white,
            "primary_text": colors.black,
            "row_alt_bg": colors.white,
            "title_color": colors.black,
            "grid_color": colors.HexColor("#475569"),
            "text_color": colors.black,
            "padding": 2,
            "banner_text": "SmartGrid Transcript AI - Eco-Friendly Minimalist Report"
        })
    elif pdf_template == "cyberpunk":
        t_opt.update({
            "primary_bg": colors.HexColor("#090d16"),
            "primary_text": colors.HexColor("#06b6d4"),
            "row_alt_bg": colors.HexColor("#111827"),
            "row_base_bg": colors.HexColor("#030712"),
            "title_color": colors.HexColor("#06b6d4"),
            "grid_color": colors.HexColor("#14b8a6"),
            "text_color": colors.HexColor("#e2e8f0"),
            "meta_text_color": colors.HexColor("#0d9488"),
            "line_color": colors.HexColor("#14b8a6"),
            "padding": 3.5,
            "banner_text": "SmartGrid Transcript AI - Cyberpunk Tech Obsidian Report"
        })
    elif pdf_template == "emerald":
        t_opt.update({
            "primary_bg": colors.HexColor("#064e3b"),
            "primary_text": colors.white,
            "row_alt_bg": colors.HexColor("#f0fdf4"),
            "title_color": colors.HexColor("#064e3b"),
            "grid_color": colors.HexColor("#a7f3d0"),
            "banner_text": "SmartGrid Transcript AI - Royal Emerald Report"
        })
    elif pdf_template == "amber":
        t_opt.update({
            "primary_bg": colors.HexColor("#78350f"),
            "primary_text": colors.HexColor("#fef3c7"),
            "row_alt_bg": colors.HexColor("#fffbeb"),
            "title_color": colors.HexColor("#78350f"),
            "grid_color": colors.HexColor("#fde68a"),
            "banner_text": "SmartGrid Transcript AI - Warm Amber Editorial Report"
        })
    elif pdf_template == "serif_court":
        t_opt.update({
            "primary_bg": colors.white,
            "primary_text": colors.black,
            "row_alt_bg": colors.white,
            "title_color": colors.black,
            "grid_color": colors.black,
            "text_color": colors.black,
            "margin_lr": 36,
            "margin_tb": 54,
            "padding": 4.5,
            "grid_width": 0.75,
            "no_grid_vertical": True,
            "banner_text": "SmartGrid Transcript AI - Formal Court Serif Report"
        })
    elif pdf_template == "cherry_blossom":
        t_opt.update({
            "primary_bg": colors.HexColor("#be185d"),
            "primary_text": colors.white,
            "row_alt_bg": colors.HexColor("#fdf2f8"),
            "title_color": colors.HexColor("#be185d"),
            "grid_color": colors.HexColor("#fbcfe8"),
            "banner_text": "SmartGrid Transcript AI - Cherry Blossom Sakura Report"
        })
    elif pdf_template == "crimson":
        t_opt.update({
            "primary_bg": colors.HexColor("#881337"),
            "primary_text": colors.white,
            "row_alt_bg": colors.HexColor("#fff1f2"),
            "title_color": colors.HexColor("#881337"),
            "grid_color": colors.HexColor("#fecdd3"),
            "banner_text": "SmartGrid Transcript AI - Executive Crimson Report"
        })
    elif pdf_template == "indigo":
        t_opt.update({
            "primary_bg": colors.HexColor("#4338ca"),
            "primary_text": colors.white,
            "row_alt_bg": colors.HexColor("#f5f3ff"),
            "title_color": colors.HexColor("#4338ca"),
            "grid_color": colors.HexColor("#ddd6fe"),
            "banner_text": "SmartGrid Transcript AI - Modern Indigo Report"
        })
    elif pdf_template == "accessibility":
        t_opt.update({
            "primary_bg": colors.black,
            "primary_text": colors.white,
            "row_alt_bg": colors.white,
            "title_color": colors.black,
            "grid_color": colors.black,
            "text_color": colors.black,
            "margin_lr": 20,
            "margin_tb": 28,
            "padding": 5,
            "fontSize": 9,
            "leading": 13,
            "grid_width": 1.0,
            "banner_text": "SmartGrid Transcript AI - High-Contrast Accessible Report"
        })
    elif pdf_template == "compact_terminal":
        t_opt.update({
            "primary_bg": colors.white,
            "primary_text": colors.black,
            "row_alt_bg": colors.white,
            "row_base_bg": colors.white,
            "title_color": colors.black,
            "grid_color": colors.HexColor("#7f8c8d"),
            "text_color": colors.black,
            "margin_lr": 18,
            "margin_tb": 24,
            "padding": 0.5,
            "fontSize": 7.5,
            "leading": 9.5,
            "grid_width": 0.5,
            "no_grid_vertical": False,
            "meta_text_color": colors.HexColor("#7f8c8d"),
            "line_color": colors.HexColor("#7f8c8d"),
            "banner_text": "SmartGrid Transcript AI - Compact Terminal Grid"
        })

    if font_size is not None:
        t_opt["fontSize"] = float(font_size)
        t_opt["leading"] = float(font_size) + 3.0
    if row_padding is not None:
        t_opt["padding"] = float(row_padding)

    # 2. Paginate segments based on max characters per page
    pages_data = [[]]
    curr_chars = 0
    for seg in segments:
        text = seg.get("text", "").strip()
        seg_len = len(text)
        if curr_chars + seg_len > max_chars_per_page and len(pages_data[-1]) > 0:
            pages_data.append([])
            curr_chars = 0
        pages_data[-1].append(seg)
        curr_chars += seg_len

    # 3. Build document layout
    doc = SimpleDocTemplate(
        str(export_path),
        pagesize=A4,
        rightMargin=t_opt["margin_lr"],
        leftMargin=t_opt["margin_lr"],
        topMargin=t_opt["margin_tb"],
        bottomMargin=t_opt["margin_tb"]
    )

    styles = getSampleStyleSheet()

    # Dynamic Custom Paragraph Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName=t_opt["font"],
        fontSize=13,
        leading=16,
        textColor=t_opt["title_color"],
        spaceAfter=4,
        alignment=1 # Center
    )

    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['Normal'],
        fontName=t_opt["font"],
        fontSize=8,
        leading=10,
        textColor=t_opt["meta_text_color"],
        spaceAfter=4,
        alignment=0 # Left
    )

    header_cell_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontName=t_opt["font"],
        fontSize=8.5,
        leading=11,
        textColor=t_opt["primary_text"],
        alignment=1 # Center
    )

    body_cell_center = ParagraphStyle(
        'BodyCellCenter',
        parent=styles['Normal'],
        fontName=t_opt["font"],
        fontSize=t_opt["fontSize"],
        leading=t_opt["leading"],
        textColor=t_opt["text_color"],
        alignment=1 # Center
    )

    body_cell_left = ParagraphStyle(
        'BodyCellLeft',
        parent=styles['Normal'],
        fontName=t_opt["font"],
        fontSize=t_opt["fontSize"],
        leading=t_opt["leading"],
        textColor=t_opt["text_color"],
        alignment=0 # Left
    )

    story = []

    # Title Banner
    if pdf_template != "compact_terminal":
        story.append(Paragraph("<b>文字起こしデータ書き出し / Transcript Export</b>", title_style))
        story.append(Spacer(1, 4))

    # Build story flow
    for page_idx, page_segs in enumerate(pages_data):
        if page_idx > 0:
            story.append(PageBreak())

        # Metadata banner on each page
        if pdf_template != "compact_terminal":
            story.append(Paragraph(
                f"<b>ページ {page_idx + 1} / Page {page_idx + 1}</b> (最小文字数設定: {max_chars_per_page}文字 / Min Chars Per Page: {max_chars_per_page})",
                meta_style
            ))

        # Build table
        table_data = [[
            Paragraph("<b>時間 / Time</b>", header_cell_style),
            Paragraph("<b>話者 / Speaker</b>", header_cell_style),
            Paragraph("<b>文字起こし / Transcript</b>", header_cell_style)
        ]]

        for seg in page_segs:
            if pdf_template == "compact_terminal":
                time_str = _fmt_time(seg.get("start", 0))
            else:
                time_str = _fmt_range(seg.get("start", 0), seg.get("end", 0))
            speaker = seg.get("speaker", "Unknown")
            if speaker.startswith("Speaker "):
                speaker = speaker.replace("Speaker ", "話者")
            text = seg.get("text", "").strip()

            table_data.append([
                Paragraph(time_str, body_cell_center),
                Paragraph(speaker, body_cell_center),
                Paragraph(text, body_cell_left)
            ])

        # Dynamic Columns adaptation to margin size (3 columns: Time, Speaker, Transcript)
        printable_width = 595.27 - (2 * t_opt["margin_lr"])
        col_time = int(printable_width * 0.18)
        col_speaker = int(printable_width * 0.14)
        col_txt = int(printable_width - col_time - col_speaker)
        col_widths = [col_time, col_speaker, col_txt]

        t = Table(table_data, colWidths=col_widths, repeatRows=1)

        t_styles = [
            ('BACKGROUND', (0,0), (-1,0), t_opt["primary_bg"]),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), t_opt["padding"]),
            ('TOPPADDING', (0,0), (-1,-1), t_opt["padding"]),
        ]

        if pdf_template == "compact_terminal":
            t_styles.extend([
                ('LINEAFTER', (0, 0), (0, -1), t_opt["grid_width"], t_opt["grid_color"]),
                ('LINEAFTER', (1, 0), (1, -1), t_opt["grid_width"], t_opt["grid_color"]),
                ('LINEBELOW', (0, 0), (-1, 0), t_opt["grid_width"], t_opt["grid_color"]),
            ])
        elif t_opt["no_grid_vertical"]:
            t_styles.extend([
                ('LINEABOVE', (0,0), (-1,0), t_opt["grid_width"], t_opt["grid_color"]),
                ('LINEBELOW', (0,0), (-1,0), t_opt["grid_width"], t_opt["grid_color"]),
                ('LINEBELOW', (0,-1), (-1,-1), t_opt["grid_width"], t_opt["grid_color"]),
            ])
        else:
            t_styles.append(('GRID', (0,0), (-1,-1), t_opt["grid_width"], t_opt["grid_color"]))

        # Alternating row colors
        for row_idx in range(1, len(table_data)):
            bg = t_opt["row_alt_bg"] if row_idx % 2 == 0 else t_opt["row_base_bg"]
            t_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))

        t.setStyle(TableStyle(t_styles))
        story.append(t)

    # 4. Built doc decorator callbacks
    def add_page_decorations(canvas, doc):
        canvas.saveState()
        canvas.setFont(t_opt["font"], 8)
        canvas.setFillColor(t_opt["meta_text_color"])

        # Calculate horizontal positions dynamically
        margin = t_opt["margin_lr"]
        width_end = 595.27 - margin

        # Top page header line (skip if compact_terminal)
        if pdf_template != "compact_terminal":
            canvas.drawString(margin, 841.89 - margin + 12, t_opt["banner_text"])
            canvas.setStrokeColor(t_opt["line_color"])
            canvas.setLineWidth(0.5)
            canvas.line(margin, 841.89 - margin + 6, width_end, 841.89 - margin + 6)

        # Bottom page footer line
        if isinstance(job_duration, (int, float)):
            formatted_duration = _fmt_time(job_duration)
        elif isinstance(job_duration, str) and job_duration.strip():
            formatted_duration = job_duration.strip()
        else:
            formatted_duration = "00:00"
        footer_text = f"ファイル名 / File: {job_filename or 'Unknown'}   |   録音時間 / Duration: {formatted_duration}   |   ページ {doc.page} / Page {doc.page}"
        canvas.drawCentredString(297.63, 15, footer_text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_decorations, onLaterPages=add_page_decorations)
    logger.info(f"PDF exported: {export_path} using template {pdf_template}")
    return export_path


def export_transcript(
    transcript_path: str,
    format: str,
    export_dir: Path,
    max_chars_per_page: int = 1000,
    pdf_template: str = "corporate",
    job_filename: Optional[str] = None,
    job_duration: Union[float, str, None] = None,
    font_size: Optional[float] = None,
    row_padding: Optional[float] = None
) -> str:
    """Load JSON segments and export in the requested format."""
    with open(transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    stem = Path(transcript_path).stem
    base_path = Path(export_dir) / f"export_{stem}"

    if format == "txt":
        out = export_txt(segments, base_path)
    elif format == "doc":
        out = export_doc(segments, base_path)
    elif format == "pdf":
        out = export_pdf(segments, base_path, max_chars_per_page, pdf_template, job_filename, job_duration, font_size, row_padding)
    else:
        raise ValueError(f"Unknown export format: {format}")

    return str(out)
