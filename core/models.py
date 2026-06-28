from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional


class DocumentRole(str, Enum):
    HSMT = "HSMT"
    HSDT = "HSDT"


class RowType(str, Enum):
    GROUP = "group"
    DETAIL = "detail"
    COMPONENT = "component"
    SUMMARY = "summary"


class MatchKind(str, Enum):
    EXACT_STRUCTURE = "exact_structure"
    EXACT_CODE = "exact_code"
    EXACT_NAME = "exact_name"
    ROW_NEAR = "row_near"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    RERANKED = "reranked"
    MISSING = "missing"
    EXTRA = "extra"


class Severity(str, Enum):
    OK = "OK"
    INFO = "THÔNG TIN"
    REVIEW = "CẦN KIỂM TRA"
    WARNING = "CẢNH BÁO"
    CRITICAL = "BẤT THƯỜNG"


@dataclass(slots=True)
class CompareThresholds:
    price_warn_pct: float = 0.10
    price_critical_pct: float = 0.25
    price_warn_abs: float = 100_000.0
    price_critical_abs: float = 1_000_000.0
    quantity_warn_pct: float = 0.05
    quantity_critical_pct: float = 0.15
    component_warn_pct: float = 0.10
    component_critical_pct: float = 0.25
    technical_warn_pct: float = 0.05
    name_review_score: float = 0.78
    name_reject_score: float = 0.58
    material_review_score: float = 0.72
    material_reject_score: float = 0.45
    brand_review_score: float = 0.80
    brand_reject_score: float = 0.45
    origin_review_score: float = 0.85
    origin_reject_score: float = 0.50
    math_tolerance_pct: float = 0.005
    robust_z_warn: float = 2.5
    robust_z_critical: float = 3.5
    min_bidders_for_consensus: int = 3


@dataclass(slots=True)
class ItemRecord:
    source_id: str
    role: DocumentRole
    bidder: str
    workbook: str
    sheet: str
    row_number: int
    stt: str = ""
    item_code: str = ""
    item_name: str = ""
    unit: str = ""
    reference_quantity: Optional[float] = None
    bid_quantity: Optional[float] = None
    price_main: Optional[float] = None
    price_aux: Optional[float] = None
    price_labor: Optional[float] = None
    price_management: Optional[float] = None
    price_profit: Optional[float] = None
    unit_price_total: Optional[float] = None
    reference_amount: Optional[float] = None
    bid_amount: Optional[float] = None
    material: str = ""
    brand: str = ""
    origin: str = ""
    note: str = ""
    technical_specs: dict[str, Any] = field(default_factory=dict)
    section_path: tuple[str, ...] = field(default_factory=tuple)
    section_codes: tuple[str, ...] = field(default_factory=tuple)
    row_type: RowType = RowType.DETAIL
    raw: dict[str, Any] = field(default_factory=dict)
    normalized_stt: str = ""
    normalized_code: str = ""
    normalized_name: str = ""
    normalized_unit: str = ""
    normalized_path: str = ""
    structural_key: str = ""
    data_quality_flags: list[str] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return self.row_type is RowType.GROUP

    @property
    def is_comparable(self) -> bool:
        return self.row_type in {RowType.DETAIL, RowType.COMPONENT}

    @property
    def quantity(self) -> Optional[float]:
        if self.role is DocumentRole.HSDT:
            return self.bid_quantity if self.bid_quantity is not None else self.reference_quantity
        return self.reference_quantity if self.reference_quantity is not None else self.bid_quantity

    @property
    def amount(self) -> Optional[float]:
        if self.role is DocumentRole.HSDT:
            return self.bid_amount if self.bid_amount is not None else self.reference_amount
        return self.reference_amount if self.reference_amount is not None else self.bid_amount

    @property
    def price_components(self) -> dict[str, Optional[float]]:
        return {
            "VL chính": self.price_main,
            "VL phụ": self.price_aux,
            "NC&M": self.price_labor,
            "CF quản lý": self.price_management,
            "Lợi nhuận": self.price_profit,
        }

    @property
    def display_key(self) -> str:
        return self.stt.strip() or self.item_code.strip() or self.item_name.strip() or f"{self.sheet}!{self.row_number}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["role"] = self.role.value
        data["row_type"] = self.row_type.value
        return data


@dataclass(slots=True)
class WorkbookData:
    path: Path
    role: DocumentRole
    bidder: str
    items: list[ItemRecord]
    warnings: list[str] = field(default_factory=list)
    sheet_info: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)
    read_engine: str = ""
    read_seconds: float = 0.0
    formula_issues: list[dict[str, Any]] = field(default_factory=list)
    external_link_count: int = 0


@dataclass(slots=True)
class MaterialRequirement:
    source_sheet: str
    source_row: int
    system: str
    item_name: str
    requirement_text: str
    allowed_brands: tuple[str, ...] = field(default_factory=tuple)
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""
    normalized_name: str = ""


@dataclass(slots=True)
class MatchResult:
    reference_index: Optional[int]
    candidate_index: Optional[int]
    kind: MatchKind
    score: float
    structure_score: float = 0.0
    code_score: float = 0.0
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    reranker_score: float = 0.0
    unit_score: float = 0.0
    row_distance: Optional[int] = None
    reason: str = ""


@dataclass(slots=True)
class FieldDifference:
    field: str
    reference_value: Any
    candidate_value: Any
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    similarity: Optional[float] = None
    severity: Severity = Severity.OK
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass(slots=True)
class ComparedItem:
    canonical_id: str
    bidder: str
    reference: Optional[ItemRecord]
    candidate: Optional[ItemRecord]
    match: MatchResult
    quantity_delta: Optional[float] = None
    quantity_delta_pct: Optional[float] = None
    price_delta: Optional[float] = None
    price_delta_pct: Optional[float] = None
    amount_delta: Optional[float] = None
    consensus_price: Optional[float] = None
    consensus_mad: Optional[float] = None
    robust_z: Optional[float] = None
    anomaly_score: float = 0.0
    severity: Severity = Severity.OK
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    differences: list[FieldDifference] = field(default_factory=list)
    pl2_category: str = ""
    pl2_requirement: str = ""
    pl2_match_score: float = 0.0
    pl2_status: str = ""

    def to_flat_dict(self) -> dict[str, Any]:
        r, c = self.reference, self.candidate
        return {
            "Mã chuẩn": self.canonical_id,
            "Nhà thầu so sánh": self.bidder,
            "Sheet chuẩn": r.sheet if r else "",
            "Dòng chuẩn": r.row_number if r else None,
            "STT chuẩn": r.stt if r else "",
            "Mã hiệu chuẩn": r.item_code if r else "",
            "Tên hạng mục chuẩn": r.item_name if r else "",
            "ĐVT chuẩn": r.unit if r else "",
            "KL nhà thầu chuẩn": r.quantity if r else None,
            "Đơn giá chuẩn": r.unit_price_total if r else None,
            "Thành tiền chuẩn": r.amount if r else None,
            "Sheet đối chiếu": c.sheet if c else "",
            "Dòng đối chiếu": c.row_number if c else None,
            "STT đối chiếu": c.stt if c else "",
            "Mã hiệu đối chiếu": c.item_code if c else "",
            "Tên hạng mục đối chiếu": c.item_name if c else "",
            "ĐVT đối chiếu": c.unit if c else "",
            "KL nhà thầu đối chiếu": c.quantity if c else None,
            "Đơn giá đối chiếu": c.unit_price_total if c else None,
            "Thành tiền đối chiếu": c.amount if c else None,
            "VL chính chuẩn": r.price_main if r else None,
            "VL chính đối chiếu": c.price_main if c else None,
            "VL phụ chuẩn": r.price_aux if r else None,
            "VL phụ đối chiếu": c.price_aux if c else None,
            "NC&M chuẩn": r.price_labor if r else None,
            "NC&M đối chiếu": c.price_labor if c else None,
            "CF quản lý chuẩn": r.price_management if r else None,
            "CF quản lý đối chiếu": c.price_management if c else None,
            "Lợi nhuận chuẩn": r.price_profit if r else None,
            "Lợi nhuận đối chiếu": c.price_profit if c else None,
            "Vật tư/Quy cách chuẩn": r.material if r else "",
            "Vật tư/Quy cách đối chiếu": c.material if c else "",
            "Thương hiệu chuẩn": r.brand if r else "",
            "Thương hiệu đối chiếu": c.brand if c else "",
            "Xuất xứ chuẩn": r.origin if r else "",
            "Xuất xứ đối chiếu": c.origin if c else "",
            "Nhóm vật tư PL02": self.pl2_category,
            "Yêu cầu PL02": self.pl2_requirement,
            "Điểm ghép PL02": self.pl2_match_score,
            "Trạng thái PL02": self.pl2_status,
            "Kiểu khớp": self.match.kind.value,
            "Điểm khớp": self.match.score,
            "Điểm cấu trúc": self.match.structure_score,
            "Điểm từ vựng": self.match.lexical_score,
            "Điểm ngữ nghĩa": self.match.semantic_score,
            "Điểm reranker": self.match.reranker_score,
            "Lệch KL": self.quantity_delta,
            "Lệch KL (%)": self.quantity_delta_pct,
            "Lệch đơn giá": self.price_delta,
            "Lệch đơn giá (%)": self.price_delta_pct,
            "Lệch thành tiền": self.amount_delta,
            "Trung vị giá các HSDT": self.consensus_price,
            "Robust Z": self.robust_z,
            "Số thông số khác biệt": len(self.differences),
            "Điểm bất thường": self.anomaly_score,
            "Mức độ": self.severity.value,
            "Cờ đánh giá": " | ".join(self.flags),
            "Ghi chú": " | ".join(self.notes),
        }

    def iter_difference_rows(self) -> Iterable[dict[str, Any]]:
        for diff in self.differences:
            yield {
                "Mã chuẩn": self.canonical_id,
                "Nhà thầu": self.bidder,
                "Sheet": (self.reference or self.candidate).sheet if (self.reference or self.candidate) else "",
                "STT": (self.reference or self.candidate).stt if (self.reference or self.candidate) else "",
                "Tên hạng mục": (self.reference or self.candidate).item_name if (self.reference or self.candidate) else "",
                "Thông số": diff.field,
                "Giá trị chuẩn": diff.reference_value,
                "Giá trị đối chiếu": diff.candidate_value,
                "Sai lệch": diff.delta,
                "Sai lệch (%)": diff.delta_pct,
                "Độ tương đồng": diff.similarity,
                "Mức độ": diff.severity.value,
                "Nhận xét": diff.message,
            }


@dataclass(slots=True)
class ComparisonSummary:
    reference_name: str
    bidder_count: int
    total_reference_items: int
    total_rows: int
    exact_matches: int
    fuzzy_matches: int
    missing_items: int
    extra_items: int
    review_rows: int
    warning_rows: int
    critical_rows: int
    total_reference_amount: float
    bidder_totals: dict[str, float]
    generated_at: str


@dataclass(slots=True)
class ComparisonResult:
    rows: list[ComparedItem]
    summary: ComparisonSummary
    warnings: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)

    def iter_flat(self) -> Iterable[dict[str, Any]]:
        for row in self.rows:
            yield row.to_flat_dict()

    def iter_differences(self) -> Iterable[dict[str, Any]]:
        for row in self.rows:
            yield from row.iter_difference_rows()
