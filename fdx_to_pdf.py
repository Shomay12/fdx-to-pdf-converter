#!/usr/bin/env python3
"""
FDX to PDF screenplay converter.

Goal: preserve screenplay structure and formatting closely to Final Draft export.

Usage:
    python fdx_to_pdf.py input.fdx output.pdf
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


# --- Screenplay layout constants (Letter, inches) ---
PT_PER_IN = 72.0
PAGE_W, PAGE_H = LETTER

TOP_MARGIN = 1.0 * PT_PER_IN
BOTTOM_MARGIN = 1.0 * PT_PER_IN
LEFT_MARGIN = 1.5 * PT_PER_IN
RIGHT_MARGIN = 1.0 * PT_PER_IN

FONT_NAME = "Courier"
FONT_SIZE = 12
LINE_HEIGHT = 12  # 12pt leading for screenplay-like layout
PARA_SPACING = 0  # Screenplays usually rely on line spacing, not extra paragraph gap

# Absolute x positions from LEFT page edge (inches), per prompt
X_CHARACTER = 3.7 * PT_PER_IN
X_DIALOGUE = 2.5 * PT_PER_IN
X_PAREN = 3.0 * PT_PER_IN

RIGHT_TEXT_EDGE = PAGE_W - RIGHT_MARGIN


@dataclass
class Paragraph:
    ptype: str
    text: str
    scene_number: Optional[str] = None


def normalize_type(raw_type: Optional[str]) -> str:
    t = (raw_type or "General").strip().lower()
    mapping = {
        "scene heading": "scene heading",
        "sceneheading": "scene heading",
        "action": "action",
        "character": "character",
        "dialogue": "dialogue",
        "parenthetical": "parenthetical",
        "transition": "transition",
        "shot": "shot",
        "general": "general",
        "lyrics": "dialogue",
    }
    return mapping.get(t, t)


def collect_text(paragraph_el: ET.Element) -> str:
    """Collect paragraph text in source order, preserving internal spacing/newlines.

    Important: we do NOT collapse whitespace globally.
    """
    chunks: List[str] = []

    # FDX typically stores visible content in <Text> nodes under <Paragraph>.
    for text_el in paragraph_el.findall("Text"):
        chunks.append(text_el.text or "")

    # If no Text nodes exist, fall back to element text content.
    if not chunks:
        fallback = "".join(paragraph_el.itertext())
        return fallback

    return "".join(chunks)


def parse_fdx(path: Path) -> List[Paragraph]:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid FDX/XML: {exc}") from exc

    root = tree.getroot()

    # Preserve sequential order from screenplay content area.
    content_paras = root.findall(".//Content/Paragraph")
    para_nodes = content_paras if content_paras else root.findall(".//Paragraph")

    paragraphs: List[Paragraph] = []
    for p in para_nodes:
        ptype = normalize_type(p.attrib.get("Type"))
        scene_number = p.attrib.get("Number")
        text = collect_text(p)

        # Keep intentionally blank lines only where meaningful in screenplay flow.
        # We preserve empty lines if the paragraph type suggests structure.
        if text is None:
            text = ""

        paragraphs.append(Paragraph(ptype=ptype, text=text, scene_number=scene_number))

    if not paragraphs:
        raise ValueError("No Paragraph elements found in the FDX file.")

    return paragraphs


def split_preserve_manual_lines(text: str) -> List[str]:
    # Preserve author-entered line breaks.
    return text.splitlines() if "\n" in text or "\r" in text else [text]


def wrap_line_to_width(raw_line: str, max_width: float, font_name: str, font_size: int) -> List[str]:
    if raw_line == "":
        return [""]

    words = raw_line.split(" ")
    lines: List[str] = []
    cur = ""

    def width(s: str) -> float:
        return stringWidth(s, font_name, font_size)

    for w in words:
        trial = w if cur == "" else f"{cur} {w}"
        if width(trial) <= max_width:
            cur = trial
            continue

        if cur:
            lines.append(cur)
            cur = w
        else:
            # Single overlong token: hard-break by characters.
            token = w
            while token and width(token) > max_width:
                cut = len(token)
                while cut > 1 and width(token[:cut]) > max_width:
                    cut -= 1
                lines.append(token[:cut])
                token = token[cut:]
            cur = token

    if cur or not lines:
        lines.append(cur)

    return lines


def wrap_paragraph_text(text: str, max_width: float, font_name: str, font_size: int) -> List[str]:
    wrapped: List[str] = []
    for logical_line in split_preserve_manual_lines(text):
        wrapped.extend(wrap_line_to_width(logical_line, max_width, font_name, font_size))
    return wrapped if wrapped else [""]


def paragraph_style(p: Paragraph):
    """Return (x, max_width, transform_text_fn, align_right)"""

    def identity(s: str) -> str:
        return s

    t = p.ptype

    if t == "scene heading":
        x = LEFT_MARGIN
        max_w = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
        return x, max_w, lambda s: s.upper(), False

    if t == "character":
        x = X_CHARACTER
        max_w = RIGHT_TEXT_EDGE - x
        return x, max_w, lambda s: s.upper(), False

    if t == "dialogue":
        x = X_DIALOGUE
        max_w = RIGHT_TEXT_EDGE - x
        return x, max_w, identity, False

    if t == "parenthetical":
        x = X_PAREN
        max_w = RIGHT_TEXT_EDGE - x
        return x, max_w, identity, False

    if t == "transition":
        x = LEFT_MARGIN
        max_w = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
        return x, max_w, lambda s: s.upper(), True

    if t == "shot":
        x = LEFT_MARGIN
        max_w = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
        return x, max_w, lambda s: s.upper(), False

    # action, general, unknown
    x = LEFT_MARGIN
    max_w = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
    return x, max_w, identity, False


def draw_page_number(c: canvas.Canvas, page_num: int) -> None:
    c.setFont(FONT_NAME, FONT_SIZE)
    page_label = f"{page_num}."
    x = RIGHT_TEXT_EDGE - stringWidth(page_label, FONT_NAME, FONT_SIZE)
    y = PAGE_H - TOP_MARGIN + 18
    c.drawString(x, y, page_label)


def render_pdf(paragraphs: Iterable[Paragraph], out_pdf: Path) -> None:
    c = canvas.Canvas(str(out_pdf), pagesize=LETTER)
    c.setTitle(out_pdf.stem)
    c.setAuthor("FDX to PDF Converter")

    page_num = 1
    draw_page_number(c, page_num)

    c.setFont(FONT_NAME, FONT_SIZE)
    y = PAGE_H - TOP_MARGIN

    for p in paragraphs:
        x, max_w, transform, align_right = paragraph_style(p)
        text = transform(p.text or "")

        wrapped = wrap_paragraph_text(text, max_w, FONT_NAME, FONT_SIZE)
        needed_h = max(1, len(wrapped)) * LINE_HEIGHT + PARA_SPACING

        # Page-break before rendering block, preserving structure order.
        if y - needed_h < BOTTOM_MARGIN:
            c.showPage()
            page_num += 1
            draw_page_number(c, page_num)
            c.setFont(FONT_NAME, FONT_SIZE)
            y = PAGE_H - TOP_MARGIN

        for line in wrapped:
            draw_y = y - FONT_SIZE
            if align_right:
                lw = stringWidth(line, FONT_NAME, FONT_SIZE)
                rx = RIGHT_TEXT_EDGE - lw
                c.drawString(rx, draw_y, line)
            else:
                c.drawString(x, draw_y, line)
            y -= LINE_HEIGHT

        y -= PARA_SPACING

    c.save()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert Final Draft .fdx screenplay to formatted PDF")
    p.add_argument("input_fdx", type=Path, help="Path to input .fdx file")
    p.add_argument("output_pdf", type=Path, help="Path to output .pdf file")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input_fdx.exists():
        print(f"ERROR: Input file not found: {args.input_fdx}", file=sys.stderr)
        return 2

    if args.input_fdx.suffix.lower() != ".fdx":
        print("WARNING: Input file extension is not .fdx (continuing anyway)", file=sys.stderr)

    try:
        paragraphs = parse_fdx(args.input_fdx)
        render_pdf(paragraphs, args.output_pdf)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"OK: Converted {args.input_fdx} -> {args.output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
