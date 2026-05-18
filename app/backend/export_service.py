"""
export_service.py
Handles TXT / CSV / Excel export of transcription segments.
Each segment: { start: float, end: float, speaker: str, text: str }
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict

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


def export_transcript(transcript_path: str, format: str, export_dir: Path) -> str:
    """Load JSON segments and export in the requested format."""
    with open(transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    stem = Path(transcript_path).stem
    base_path = Path(export_dir) / f"export_{stem}"

    if format == "txt":
        out = export_txt(segments, base_path)
    elif format == "csv":
        out = export_csv(segments, base_path)
    elif format == "excel":
        out = export_excel(segments, base_path)
    else:
        raise ValueError(f"Unknown export format: {format}")

    return str(out)
