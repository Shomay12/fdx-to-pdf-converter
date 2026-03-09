# FDX to PDF Converter (Python)

Reliable `.fdx` screenplay to PDF converter with screenplay-style formatting.

## Features

- Parses FDX XML in sequential paragraph order (no flattening)
- Supports screenplay element types:
  - Scene Heading
  - Action
  - Character
  - Dialogue
  - Parenthetical
  - Transition
  - Shot
  - General text
- Uses Courier 12pt
- Screenplay margins:
  - Top: 1 inch
  - Bottom: 1 inch
  - Left: 1.5 inch
  - Right: 1 inch
- Indentation rules:
  - Character: 3.7 in
  - Dialogue: 2.5 in
  - Parenthetical: 3.0 in
  - Transition: right aligned

## Install

```bash
pip install reportlab
```

## Usage

```bash
python fdx_to_pdf.py input_script.fdx output_script.pdf
```

Example:

```bash
python fdx_to_pdf.py sample.fdx sample.pdf
```

## Notes

- Scene headings, character names, transitions, and shots are uppercased for screenplay convention.
- Paragraph order is preserved exactly as parsed from FDX.
- The converter performs block-level page breaking to avoid splitting/reordering elements.
