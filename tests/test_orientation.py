from __future__ import annotations

import numpy as np

from ocr.config import OCRConfig
from ocr.models import OCRPage, OCRTable
from ocr.orientation import OrientationProbe, semantic_text_score
import ocr.pipeline as pipeline


def test_semantic_score_prefers_valid_vietnamese_table_header():
    good = "STT Diễn giải Đơn vị Khối lượng Mã hiệu Thương hiệu Xuất xứ Đơn giá Thành tiền Ghi chú"
    bad = "WRI DAT V30 dvV0EC LVisc BUND RATAN KkUELDTCEXTLE"
    good_score, hits = semantic_text_score(good)
    bad_score, _ = semantic_text_score(bad)
    assert good_score >= 30
    assert good_score > bad_score + 20
    assert "dien giai" in hits
    assert "thanh tien" in hits


def test_orientation_selection_uses_semantic_probe(monkeypatch):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    page = OCRPage(page=1, image=image, rotation=0, source="test")
    config = OCRConfig(orientation_probe_min_gap=6.0)

    monkeypatch.setattr(
        pipeline,
        "probe_upright_pair",
        lambda image, config: {
            0: OrientationProbe(0.0, available=True),
            180: OrientationProbe(45.0, keyword_hits=("stt", "dien giai"), available=True),
        },
    )

    calls = []
    def fake_candidate(page_number, candidate_image, recognizer, config, rotation_label):
        calls.append(rotation_label)
        return [OCRTable(page_number, 1, (0, 0, 10, 10), [0, 10], [0, 10])], 1.0

    monkeypatch.setattr(pipeline, "_candidate_tables", fake_candidate)
    tables = pipeline._select_orientation_and_tables(page, object(), config)
    assert tables
    assert calls == [180]
    assert page.rotation == 180
    assert page.orientation_method == "semantic-header-probe"
    assert page.orientation_scores[180] == 45.0


def test_dense_boq_header_rows_do_not_stop_at_second_thin_row():
    from ocr.models import OCRCell
    from ocr.schema import infer_header_rows

    # heights: 13, 13, 24, 25, 13... tương tự trang 2 PDF hồi quy.
    y_lines = [0, 13, 26, 50, 75, 88, 101, 114]
    table = OCRTable(page=1, table_index=1, bbox=(0, 0, 190, 114),
                     x_lines=list(range(0, 200, 10))[:20], y_lines=y_lines)
    # Cần cell ở cột 18 để n_cols = 19.
    table.cells = [OCRCell(page=1, table_index=1, row=0, col=18, bbox=(0, 0, 1, 1))]
    assert infer_header_rows(table) == 4
