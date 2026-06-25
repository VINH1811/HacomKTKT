import cv2
import numpy as np

from ocr.config import OCRConfig
from ocr.grid import detect_grid


def test_detect_simple_wired_table():
    img = np.full((600, 1000, 3), 255, np.uint8)
    for x in [50, 150, 500, 700, 950]:
        cv2.line(img, (x, 50), (x, 550), (0, 0, 0), 2)
    for y in [50, 100, 160, 220, 280, 340, 400, 460, 550]:
        cv2.line(img, (50, y), (950, y), (0, 0, 0), 2)
    det = detect_grid(img, OCRConfig())
    assert det is not None
    assert len(det.x_lines) >= 5
    assert len(det.y_lines) >= 8
