from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(slots=True)
class OCRCandidate:
    text: str
    confidence: float
    engine: str
    variant: str = ""


@dataclass(slots=True)
class OCRCell:
    page: int
    table_index: int
    row: int
    col: int
    bbox: tuple[int, int, int, int]
    text: str = ""
    confidence: float = 0.0
    engine: str = ""
    candidates: list[OCRCandidate] = field(default_factory=list)
    field: str = ""
    numeric_value: Optional[float] = None
    status: str = "empty"
    review_reason: str = ""
    image_path: str = ""
    reconciled: bool = False


@dataclass(slots=True)
class OCRTable:
    page: int
    table_index: int
    bbox: tuple[int, int, int, int]
    x_lines: list[int]
    y_lines: list[int]
    cells: list[OCRCell] = field(default_factory=list)
    header_rows: int = 1
    column_fields: dict[int, str] = field(default_factory=dict)
    structure_confidence: float = 0.0
    source: str = "opencv-grid"
    warnings: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return max((c.row for c in self.cells), default=-1) + 1

    @property
    def n_cols(self) -> int:
        return max((c.col for c in self.cells), default=-1) + 1

    def matrix(self) -> list[list[str]]:
        matrix = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.n_rows and 0 <= cell.col < self.n_cols:
                matrix[cell.row][cell.col] = cell.text
        return matrix


@dataclass(slots=True)
class OCRPage:
    page: int
    image: np.ndarray
    rotation: int
    source: str
    tables: list[OCRTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_dpi: float = 0.0
    orientation_method: str = "geometry-osd"
    orientation_scores: dict[int, float] = field(default_factory=dict)
    orientation_keywords: dict[int, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class OCRDocument:
    source_path: Path
    pages: list[OCRPage]
    rows: list[dict]
    warnings: list[str] = field(default_factory=list)
    audit: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
