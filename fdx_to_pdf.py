#!/usr/bin/env python3
"""
FDX to PDF screenplay converter.

Goal: preserve screenplay structure and formatting closely to Final Draft export.

Usage:
    python fdx_to_pdf.py input.fdx output.pdf
"""

from __future__ import annotations

import argparse
import re
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
LINE_HEIGHT = 12
PARA_SPACING = 0

# Absolute x positions from LEFT page edge (inches)
X_CHARACTER = 3.7 * PT_PER_IN
X_DIALOGUE = 2.5 * PT_PER_IN
X_PAREN = 3.0 * PT_PER_IN

# Scene numbers on both sides of scene headings
X_SCENE_NUM_LEFT = 0.95 * PT_PER_IN
X_SCENE_NUM_RIGHT = PAGE_W - 0.95 * PT_PER_IN

RIGHT_TEXT_EDGE = PAGE_W - RIGHT_MARGIN


@dataclass
class Paragraph:
    ptype: str
    text: str
    scene_number: Optional[str] = None
    alignment: Optional[str] = None


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
        "page break": "page break",
        "pagebreak": "page break",
    }
    return mapping.get(t, t)


def collect_text(paragraph_el: ET.Element) -> str:
    chunks: List[str] = []

    # Use recursive search to avoid missing nested text runs.
    for text_el in paragraph_el.iter("Text"):
        chunks.append(text_el.text or "")

    if not chunks:
        return "".join(paragraph_el.itertext())

    return "".join(chunks)


def parse_fdx(path: Path) -> List[Paragraph]:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid FDX/XML: {exc}") from exc

    root = tree.getroot()

    content_paras = root.findall(".//Content/Paragraph")
    para_nodes = content_paras if content_paras else root.findall(".//Paragraph")

    paragraphs: List[Paragraph] = []
    for p in para_nodes:
        paragraphs.append(
            Paragraph(
                ptype=normalize_type(p.attrib.get("Type")),
                text=collect_text(p) or "",
                scene_number=p.attrib.get("Number"),
                alignment=(p.attrib.get("Alignment") or "").strip().lower() or None,
            )
        )

    if not paragraphs:
        raise ValueError("No Paragraph elements found in the FDX file.")

    return paragraphs


def split_preserve_manual_lines(text: str) -> List[str]:
    return text.splitlines() if "\n" in text or "\r" in text else [text]


def tokenize_preserve_spaces(line: str) -> List[str]:
    # keep spaces as tokens so we don't collapse user formatting
    return re.findall(r"\S+|\s+", line)


def wrap_line_to_width(raw_line: str, max_width: float, font_name: str, font_size: int) -> List[str]:
    if raw_line == "":
        return [""]

    tokens = tokenize_preserve_spaces(raw_line)
    lines: List[str] = []
    cur = ""

    def width(s: str) -> float:
        return stringWidth(s, font_name, font_size)

    for t in tokens:
        trial = cur + t
        if width(trial) <= max_width or cur == "":
            cur = trial
            continue

        # start new line when token does not fit
        lines.append(cur.rstrip())
        cur = t.lstrip() if t.isspace() else t

        # hard-break very long non-space tokens
        if not t.isspace() and width(cur) > max_width:
            token = cur
            cur = ""
            while token:
                cut = len(token)
                while cut > 1 and width(token[:cut]) > max_width:
                    cut -= 1
                lines.append(token[:cut])
                token = token[cut:]

    if cur or not lines:
        lines.append(cur.rstrip())

    return lines


def wrap_paragraph_text(text: str, max_width: float, font_name: str, font_size: int) -> List[str]:
    wrapped: List[str] = []
    for logical_line in split_preserve_manual_lines(text):
        wrapped.extend(wrap_line_to_width(logical_line, max_width, font_name, font_size))
    return wrapped if wrapped else [""]


def paragraph_style(p: Paragraph):
    def identity(s: str) -> str:
        return s

    t = p.ptype

    if t == "scene heading":
        return LEFT_MARGIN, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN, lambda s: s.upper(), False
    if t == "character":
        return X_CHARACTER, RIGHT_TEXT_EDGE - X_CHARACTER, lambda s: s.upper(), False
    if t == "dialogue":
        return X_DIALOGUE, RIGHT_TEXT_EDGE - X_DIALOGUE, identity, False
    if t == "parenthetical":
        return X_PAREN, RIGHT_TEXT_EDGE - X_PAREN, identity, False
    if t == "transition":
        return LEFT_MARGIN, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN, lambda s: s.upper(), True
    if t == "shot":
        return LEFT_MARGIN, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN, lambda s: s.upper(), False

    # Honor explicit right-aligned paragraphs from FDX attributes when present.
    if p.alignment == "right":
        return LEFT_MARGIN, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN, identity, True

    return LEFT_MARGIN, PAGE_W - LEFT_MARGIN - RIGHT_MARGIN, identity, False


def draw_page_number(c: canvas.Canvas, page_num: int) -> None:
    c.setFont(FONT_NAME, FONT_SIZE)
    label = f"{page_num}."
    x = RIGHT_TEXT_EDGE - stringWidth(label, FONT_NAME, FONT_SIZE)
    y = PAGE_H - TOP_MARGIN + 18
    c.drawString(x, y, label)


def draw_scene_numbers(c: canvas.Canvas, scene_number: str, y_baseline: float) -> None:
    c.setFont(FONT_NAME, FONT_SIZE)
    left_label = str(scene_number)
    right_label = str(scene_number)

    c.drawString(X_SCENE_NUM_LEFT, y_baseline, left_label)
    right_w = stringWidth(right_label, FONT_NAME, FONT_SIZE)
    c.drawString(X_SCENE_NUM_RIGHT - right_w, y_baseline, right_label)


def render_pdf(paragraphs: Iterable[Paragraph], out_pdf: Path) -> None:
    c = canvas.Canvas(str(out_pdf), pagesize=LETTER)
    c.setTitle(out_pdf.stem)
    c.setAuthor("FDX to PDF Converter")

    page_num = 1
    draw_page_number(c, page_num)

    c.setFont(FONT_NAME, FONT_SIZE)
    y = PAGE_H - TOP_MARGIN

    for p in paragraphs:
        if p.ptype == "page break":
            c.showPage()
            page_num += 1
            draw_page_number(c, page_num)
            c.setFont(FONT_NAME, FONT_SIZE)
            y = PAGE_H - TOP_MARGIN
            continue

        x, max_w, transform, align_right = paragraph_style(p)
        text = transform(p.text or "")

        wrapped = wrap_paragraph_text(text, max_w, FONT_NAME, FONT_SIZE)
        needed_h = max(1, len(wrapped)) * LINE_HEIGHT + PARA_SPACING

        if y - needed_h < BOTTOM_MARGIN:
            c.showPage()
            page_num += 1
            draw_page_number(c, page_num)
            c.setFont(FONT_NAME, FONT_SIZE)
            y = PAGE_H - TOP_MARGIN

        first_line_y = y - FONT_SIZE

        # Scene numbers are printed on both sides of the scene heading line
        if p.ptype == "scene heading" and p.scene_number:
            draw_scene_numbers(c, p.scene_number, first_line_y)

        for line in wrapped:
            draw_y = y - FONT_SIZE
            if align_right:
                lw = stringWidth(line, FONT_NAME, FONT_SIZE)
                c.drawString(RIGHT_TEXT_EDGE - lw, draw_y, line)
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
