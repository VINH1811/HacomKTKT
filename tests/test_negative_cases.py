import pytest
from pathlib import Path
import zipfile

from app import format_job_error_message
from core.models import DocumentRole
from core.excel_reader import load_workbook_items
from core.tender_package import compare_pl1_pl2_with_bidders
from core.config import EnterpriseConfig


def test_format_job_error_message_non_xlsx_extension():
    # Simulation of ValueError thrown when the extension is not .xlsx
    # load_workbook_items raises ValueError("Hệ thống nhận file .xlsx...")
    exc = RuntimeError(
        "Không đọc được file '000_PHU_LUC_01.xlsx' (PHỤ LỤC 01 - KLMT): ValueError: Hệ thống nhận file .xlsx. Hãy Save As file .xls/.xlsb thành .xlsx trước khi chạy."
    )
    request = {
        "pl1_file": "000_PHU_LUC_01.xlsx",
        "pl1_original": "Bảng KLMT của Hacom.xls",
    }
    msg = format_job_error_message(exc, request)
    assert "File 'Bảng KLMT của Hacom.xls' không đúng định dạng Excel." in msg
    assert "Hãy Save As file .xls/.xlsb thành .xlsx" in msg


def test_format_job_error_message_bad_zip_file():
    # Simulation of BadZipFile (e.g. file renamed to .xlsx but is a text/pdf file)
    exc = RuntimeError(
        "Không đọc được file '002_NhaThauA.xlsx' (Nhà thầu A): BadZipFile: File is not a zip file"
    )
    request = {
        "bidders": [
            {"file": "002_NhaThauA.xlsx", "original_name": "Chào giá Nhà Thầu A Gốc.xlsx"}
        ]
    }
    msg = format_job_error_message(exc, request)
    assert msg == "File 'Chào giá Nhà Thầu A Gốc.xlsx' không phải là file Excel."


def test_format_job_error_message_corrupt_format():
    # Simulation of calamine/openpyxl failure on a corrupt file
    exc = RuntimeError(
        "Không đọc được file '003_NhaThauB.xlsx' (Nhà thầu B): Exception: Corrupted sheet structure"
    )
    request = {
        "bidders": [
            {"file": "003_NhaThauB.xlsx", "original_name": "NhaThauB_BaoGia.xlsx"}
        ]
    }
    msg = format_job_error_message(exc, request)
    assert msg == "File 'NhaThauB_BaoGia.xlsx' không đúng định dạng Excel."


def test_format_job_error_message_backend_error():
    # Lỗi lập trình nội bộ -> thông báo chung, không lộ traceback, không đổ lỗi
    # sai cho định dạng file.
    from app import _GENERIC_PROCESSING_ERROR

    exc1 = AttributeError("'NoneType' object has no attribute 'items'")
    assert format_job_error_message(exc1, None) == _GENERIC_PROCESSING_ERROR

    exc2 = TypeError("unsupported operand type(s) for +: 'NoneType' and 'float'")
    assert format_job_error_message(exc2, None) == _GENERIC_PROCESSING_ERROR

    exc3 = KeyError("item_name")
    assert format_job_error_message(exc3, None) == _GENERIC_PROCESSING_ERROR

    # Even if it happened inside loading, if it is a TypeError, mask as generic.
    exc4 = RuntimeError(
        "Không đọc được file '002_NhaThauA.xlsx' (Nhà thầu A): TypeError: NoneType object"
    )
    msg4 = format_job_error_message(exc4, {
        "bidders": [{"file": "002_NhaThauA.xlsx", "original_name": "A.xlsx"}]
    })
    assert msg4 == _GENERIC_PROCESSING_ERROR


def test_package_pipeline_with_corrupt_files(tmp_path):
    # Integration style test calling compare_pl1_pl2_with_bidders with non-Excel files
    pl1_path = tmp_path / "000_PHU_LUC_01.xlsx"
    pl1_path.write_bytes(b"invalid zip file contents")

    bidder_path = tmp_path / "002_BidderA.xlsx"
    bidder_path.write_bytes(b"invalid zip file contents")

    config = EnterpriseConfig()
    
    with pytest.raises(Exception) as excinfo:
        compare_pl1_pl2_with_bidders(
            pl1_path=pl1_path,
            pl2_path=None,
            bidder_files=[("Bidder A", bidder_path)],
            output_dir=tmp_path / "output",
            config=config
        )
    
    # Check that exception message specifies the failed file name
    assert "Không đọc được file" in str(excinfo.value)
    
    request = {
        "pl1_file": pl1_path.name,
        "pl1_original": "PL01_Gốc_Hacom.xlsx",
        "bidders": [
            {"file": bidder_path.name, "original_name": "BaoGia_NhaThauA.xlsx"}
        ]
    }
    
    friendly_msg = format_job_error_message(excinfo.value, request)
    # Since the loaders run in parallel, either pl1 or bidderA could fail first
    assert "PL01_Gốc_Hacom.xlsx" in friendly_msg or "BaoGia_NhaThauA.xlsx" in friendly_msg
    assert "không phải là file Excel." in friendly_msg
