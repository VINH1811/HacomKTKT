from pathlib import Path

import cv2
import numpy as np

from ocr.config import OCRConfig
from ocr.engines import parse_html_tables, parse_markdown_tables
from ocr.grid import build_table, detect_grids
from ocr.schema import infer_columns
from ocr.verify import assemble_rows


def test_dense_19_column_grid_and_schema():
    image = np.full((1000, 1900, 3), 255, np.uint8)
    xs = [50 + i * 95 for i in range(20)]
    ys = [40, 100, 160, 220, 280, 340, 400, 460, 520, 580, 640, 700, 760, 820, 900]
    for x in xs:
        cv2.line(image, (x, ys[0]), (x, ys[-1]), (0, 0, 0), 2)
    for y in ys:
        cv2.line(image, (xs[0], y), (xs[-1], y), (0, 0, 0), 2)

    config = OCRConfig(orientation_with_tesseract=False)
    grids = detect_grids(image, config)
    assert grids
    assert len(grids[0].x_lines) - 1 == 19

    table = build_table(1, 1, image, grids[0], config)
    table.header_rows = 1
    mapping = infer_columns(table)
    assert mapping[0] == "stt"
    assert mapping[2] == "item_name"
    assert mapping[15] == "unit_price"
    assert mapping[18] == "note"


def test_parser_keeps_multiple_tables():
    html = """
    <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
    <table><tr><th>C</th></tr><tr><td>3</td></tr></table>
    """
    tables = parse_html_tables(html)
    assert len(tables) == 2
    assert tables[0][1] == ["1", "2"]
    assert tables[1][1] == ["3"]

    markdown = "| A | B |\n|---|---|\n|1|2|\n\ntext\n\n| C |\n|---|\n|3|"
    md_tables = parse_markdown_tables(markdown)
    assert len(md_tables) == 2


def test_zero_values_are_not_replaced_by_fallback():
    # Minimal record path: ensure compatibility fields preserve explicit zero.
    config = OCRConfig(use_arithmetic_reconciliation=False)
    image = np.full((160, 300, 3), 255, np.uint8)
    xs = [0, 30, 130, 180, 230, 299]
    ys = [0, 50, 100, 159]
    for x in xs:
        cv2.line(image, (x, 0), (x, 159), (0, 0, 0), 1)
    for y in ys:
        cv2.line(image, (0, y), (299, y), (0, 0, 0), 1)
    # This test only guards the expression through a table assembled manually.
    from ocr.models import OCRCell, OCRTable
    table = OCRTable(1, 1, (0, 0, 300, 160), xs, ys, header_rows=1)
    table.column_fields = {0: "item_name", 1: "invited_quantity", 2: "bid_quantity", 3: "unit_price", 4: "amount_bid"}
    values = ["Hạng mục", "0", "0", "100", "0"]
    for col, text in enumerate(values):
        table.cells.append(OCRCell(1, 1, 1, col, (0, 50, 10, 50), text=text, confidence=0.99, engine="test"))
    rows = assemble_rows(table, config)
    assert rows[0]["quantity"] == 0.0
    assert rows[0]["amount"] == 0.0
    assert rows[0]["computed_amount"] == 0.0
