from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

import app as app_module

app = app_module.app


def _xlsx_bytes(headers: list[str], row: list[object]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_health_reports_comparison_and_ocr():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "8.3.0"
    assert body["package_mode"] is True
    assert body["ocr_mode"] is True
    assert body["excel_engine"] in {"calamine", "openpyxl", "auto"}


def test_ocr_route_is_available():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/ocr" in paths
    assert "/api/compare-package" in paths
    assert "/api/compare-bidders" in paths
    assert "/api/compare-tender" in paths


def test_compare_package_api_accepts_one_bidder(monkeypatch):
    class _NoopExecutor:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(app_module, "_JOB_EXECUTOR", _NoopExecutor())
    client = TestClient(app)
    pl1 = _xlsx_bytes(
        ["Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu"],
        ["CAP-01", "Cáp điện", "m", 100],
    )
    bidder = _xlsx_bytes(
        ["Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu", "Khối lượng nhà thầu", "Đơn giá tổng hợp"],
        ["CAP-01", "Cáp điện", "m", 100, 100, 120_000],
    )
    response = client.post(
        "/api/compare-package",
        data={"bidder_names": "Nhà thầu A"},
        files=[
            ("pl1", ("pl1.xlsx", pl1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ("files", ("a.xlsx", bidder, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ],
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
