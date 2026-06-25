from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from .config import EnterpriseConfig
from .models import ItemRecord, MatchKind, MatchResult, RowType
from .text_normalizer import normalize_name, token_set


# ---------------------------------------------------------------------------
# Internal matching proposal
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Proposal:
    ref_idx: int
    cand_idx: int
    kind: MatchKind
    score: float
    structure: float = 0.0
    code: float = 0.0
    lexical: float = 0.0
    semantic: float = 0.0
    reranker: float = 0.0
    unit: float = 0.0
    row_distance: Optional[int] = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Optional local-only AI models
# ---------------------------------------------------------------------------


class LocalSemanticEncoder:
    """Load a local multilingual embedding model without network access.

    Qwen3-Embedding and BGE-M3 can both be loaded through
    ``SentenceTransformer``. A hub model identifier is deliberately not
    accepted: ``model_path`` must exist locally and ``local_files_only`` is
    always enabled.
    """

    def __init__(self, model_path: str, batch_size: int = 32):
        self.model = None
        self.batch_size = max(1, int(batch_size))

        path = Path(model_path) if model_path else None
        self.is_qwen3 = bool(path and "qwen3" in str(path).lower())

        if not path or not path.exists():
            return

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(
                str(path),
                local_files_only=True,
                trust_remote_code=True,
            )
        except Exception:
            # Fail closed: the rules/TF-IDF pipeline remains fully usable.
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> Optional[np.ndarray]:
        if not self.model or not texts:
            return None

        kwargs = {
            "batch_size": self.batch_size,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }

        # Qwen3 Embedding supports an instruction for query-side vectors.
        if is_query and self.is_qwen3:
            kwargs["prompt"] = (
                "Given a baseline bill-of-quantities line, retrieve the "
                "contractor line that describes the same work item, hierarchy, "
                "unit, material and technical specification."
            )

        try:
            vectors = self.model.encode(texts, **kwargs)
        except TypeError:
            # Older sentence-transformers versions may not accept ``prompt``.
            kwargs.pop("prompt", None)
            vectors = self.model.encode(texts, **kwargs)

        return np.asarray(vectors, dtype=np.float32)


class LocalReranker:
    """Optional local CrossEncoder-compatible reranker.

    The adapter never downloads models. If the supplied local model cannot be
    loaded, matching continues with deterministic rules, lexical similarity and
    optional local embeddings.
    """

    def __init__(self, model_path: str, batch_size: int = 16):
        self.model = None
        self.batch_size = max(1, int(batch_size))

        path = Path(model_path) if model_path else None
        if not path or not path.exists():
            return

        try:
            from sentence_transformers import CrossEncoder

            self.model = CrossEncoder(
                str(path),
                local_files_only=True,
                trust_remote_code=True,
                prompts={
                    "boq_matching": (
                        "Judge whether the contractor BOQ line refers to the same "
                        "work item as the baseline BOQ line. Consider hierarchy, "
                        "code, description, unit, material, brand, origin and "
                        "technical specification; ignore price differences."
                    )
                },
                default_prompt_name="boq_matching",
            )
        except Exception:
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, pairs: list[tuple[str, str]]) -> Optional[np.ndarray]:
        if not self.model or not pairs:
            return None

        try:
            import torch

            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
                activation_fn=torch.nn.Sigmoid(),
            )
        except (ImportError, TypeError):
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )

        values = np.asarray(scores, dtype=np.float32).reshape(-1)

        # Some CrossEncoders return logits instead of probabilities.
        if np.any((values < 0.0) | (values > 1.0)):
            values = 1.0 / (1.0 + np.exp(-values))

        return values


# ---------------------------------------------------------------------------
# Normalization and scoring helpers
# ---------------------------------------------------------------------------


def _sheet(item: ItemRecord) -> str:
    return normalize_name(item.sheet or "")


def _row_type(item: ItemRecord) -> RowType:
    return item.row_type


def _same_sheet(a: ItemRecord, b: ItemRecord) -> bool:
    return _sheet(a) == _sheet(b)


def _unit_score(a: ItemRecord, b: ItemRecord) -> float:
    """Return 1 for equal units, 0 for conflicting units, 0.5 if unknown."""

    if not a.normalized_unit or not b.normalized_unit:
        return 0.5
    return 1.0 if a.normalized_unit == b.normalized_unit else 0.0


def _path_score(a: ItemRecord, b: ItemRecord) -> float:
    if not a.normalized_path or not b.normalized_path:
        return 0.5
    return fuzz.token_set_ratio(a.normalized_path, b.normalized_path) / 100.0


def _sheet_score(a: ItemRecord, b: ItemRecord) -> float:
    left = _sheet(a)
    right = _sheet(b)
    if not left or not right:
        return 0.5
    if left == right:
        return 1.0
    return fuzz.token_set_ratio(left, right) / 100.0


def _compact(text: str) -> str:
    return "".join(ch for ch in normalize_name(text or "") if ch.isalnum())


def _acronym(text: str) -> str:
    tokens = [token for token in normalize_name(text or "").split() if token]
    return "".join(token[0] for token in tokens if token[0].isalnum())


def _abbreviation_score(left: str, right: str) -> float:
    """Conservative abbreviation score for shortened BOQ descriptions.

    The function only returns a strong score when the compact short form equals
    the initials of the longer phrase or when all short-form characters match
    ordered token initials. This helps examples such as a contractor shortening
    a long heading while avoiding an unrestricted substring match.
    """

    left_norm = normalize_name(left or "")
    right_norm = normalize_name(right or "")
    if not left_norm or not right_norm:
        return 0.0

    left_compact = _compact(left_norm)
    right_compact = _compact(right_norm)
    if not left_compact or not right_compact:
        return 0.0

    if left_compact == right_compact:
        return 1.0

    # Determine the shorter candidate abbreviation.
    short, long_text = (
        (left_compact, right_norm)
        if len(left_compact) <= len(right_compact)
        else (right_compact, left_norm)
    )

    if len(short) < 2 or len(short) > 16:
        return 0.0

    long_acronym = _acronym(long_text)
    if short == long_acronym:
        return 1.0

    # Ordered initials, allowing the long phrase to contain filler words.
    position = 0
    for char in long_acronym:
        if position < len(short) and char == short[position]:
            position += 1
    if position == len(short):
        return 0.90

    return 0.0


def _lexical_score(a: ItemRecord, b: ItemRecord) -> float:
    """Compare name, material and code without using prices."""

    left = " ".join(
        filter(
            None,
            [
                a.normalized_name,
                normalize_name(a.material or ""),
                a.normalized_code,
            ],
        )
    )
    right = " ".join(
        filter(
            None,
            [
                b.normalized_name,
                normalize_name(b.material or ""),
                b.normalized_code,
            ],
        )
    )

    if not left or not right:
        return 0.0

    wratio = fuzz.WRatio(left, right) / 100.0
    token_ratio = fuzz.token_set_ratio(left, right) / 100.0

    left_tokens = token_set(left)
    right_tokens = token_set(right)
    jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)

    abbreviation = _abbreviation_score(
        a.normalized_name or "",
        b.normalized_name or "",
    )

    base = 0.45 * wratio + 0.40 * token_ratio + 0.15 * jaccard
    return max(base, 0.90 * abbreviation)


def _technical_text(item: ItemRecord) -> str:
    technical_specs = item.technical_specs or {}
    return " ".join(
        f"{normalize_name(str(key))} {normalize_name(str(value))}"
        for key, value in sorted(technical_specs.items(), key=lambda pair: str(pair[0]))
    )


def _combined_text(item: ItemRecord, *, include_sheet: bool = True) -> str:
    """Build local retrieval text.

    ``include_sheet=False`` is used for cross-sheet retrieval so that different
    contractor sheet names do not prevent otherwise identical items from being
    shortlisted.
    """

    parts = []
    if include_sheet:
        parts.append(_sheet(item))

    parts.extend(
        [
            item.normalized_path,
            item.normalized_stt,
            item.normalized_code,
            item.normalized_name,
            item.normalized_unit,
            normalize_name(item.material or ""),
            normalize_name(item.brand or ""),
            normalize_name(item.origin or ""),
            _technical_text(item),
        ]
    )

    return " | ".join(part for part in parts if part)


def _is_reliable_cross_sheet_code(code: str) -> bool:
    """Reject very short/generic codes for global code matching."""

    compact = _compact(code)
    if len(compact) < 3:
        return False

    # Pure numeric sequence numbers such as 001/002 are often reused per sheet.
    if compact.isdigit() and len(compact) < 5:
        return False

    return True


def _row_distance(a: ItemRecord, b: ItemRecord) -> Optional[int]:
    # Row proximity is meaningful only inside the same normalized sheet.
    if not _same_sheet(a, b):
        return None
    return abs(a.row_number - b.row_number)


def _proposal_sort_key(proposal: _Proposal) -> tuple:
    distance = proposal.row_distance if proposal.row_distance is not None else 10**9
    return (
        -proposal.score,
        -proposal.lexical,
        -proposal.unit,
        -proposal.structure,
        distance,
        proposal.ref_idx,
        proposal.cand_idx,
    )


def _make_result(proposal: _Proposal) -> MatchResult:
    return MatchResult(
        proposal.ref_idx,
        proposal.cand_idx,
        proposal.kind,
        proposal.score,
        structure_score=proposal.structure,
        code_score=proposal.code,
        lexical_score=proposal.lexical,
        semantic_score=proposal.semantic,
        reranker_score=proposal.reranker,
        unit_score=proposal.unit,
        row_distance=proposal.row_distance,
        reason=proposal.reason,
    )


def _assign(
    proposal: _Proposal,
    results: list[MatchResult],
    used_ref: set[int],
    used_cand: set[int],
) -> bool:
    """Assign one pair while enforcing strict one-to-one semantics."""

    if proposal.ref_idx in used_ref or proposal.cand_idx in used_cand:
        return False

    used_ref.add(proposal.ref_idx)
    used_cand.add(proposal.cand_idx)
    results.append(_make_result(proposal))
    return True


def _assign_sorted(
    proposals: list[_Proposal],
    results: list[MatchResult],
    used_ref: set[int],
    used_cand: set[int],
    *,
    minimum_score: float = 0.0,
) -> None:
    for proposal in sorted(proposals, key=_proposal_sort_key):
        if proposal.score >= minimum_score:
            _assign(proposal, results, used_ref, used_cand)


def _deduplicate_proposals(proposals: list[_Proposal]) -> list[_Proposal]:
    """Keep the highest-scoring proposal for each reference/candidate pair."""

    best: dict[tuple[int, int], _Proposal] = {}
    for proposal in proposals:
        key = (proposal.ref_idx, proposal.cand_idx)
        current = best.get(key)
        if current is None or _proposal_sort_key(proposal) < _proposal_sort_key(current):
            best[key] = proposal
    return list(best.values())


def _remaining_by_sheet_and_type(
    items: list[ItemRecord],
    used: set[int],
) -> dict[tuple[str, RowType], list[int]]:
    groups: dict[tuple[str, RowType], list[int]] = defaultdict(list)
    for idx, item in enumerate(items):
        if idx not in used:
            groups[(_sheet(item), _row_type(item))].append(idx)
    return groups


def _remaining_by_type(
    items: list[ItemRecord],
    used: set[int],
) -> dict[RowType, list[int]]:
    groups: dict[RowType, list[int]] = defaultdict(list)
    for idx, item in enumerate(items):
        if idx not in used:
            groups[_row_type(item)].append(idx)
    return groups


def _tfidf_shortlist(
    refs: list[ItemRecord],
    cands: list[ItemRecord],
    ref_pool: list[int],
    cand_pool: list[int],
    *,
    top_k: int,
    include_sheet: bool,
    global_pass: bool,
    reject_score: float,
) -> list[_Proposal]:
    """Sparse character TF-IDF nearest-neighbour retrieval.

    This function never builds a dense N x M similarity matrix. It produces a
    small nearest-neighbour shortlist and then applies detailed local scores.
    """

    if not ref_pool or not cand_pool:
        return []

    ref_texts = [
        _combined_text(refs[ri], include_sheet=include_sheet)
        for ri in ref_pool
    ]
    cand_texts = [
        _combined_text(cands[ci], include_sheet=include_sheet)
        for ci in cand_pool
    ]

    if not any(ref_texts) or not any(cand_texts):
        return []

    try:
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            max_features=120_000,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(cand_texts + ref_texts)
        cand_matrix = matrix[: len(cand_texts)]
        ref_matrix = matrix[len(cand_texts) :]

        neighbour_count = max(1, min(int(top_k), len(cand_pool)))
        nearest = NearestNeighbors(
            n_neighbors=neighbour_count,
            metric="cosine",
            algorithm="brute",
            n_jobs=-1,
        )
        nearest.fit(cand_matrix)
        distances, indices = nearest.kneighbors(ref_matrix)
    except ValueError:
        return []

    proposals: list[_Proposal] = []

    for local_ri, ri in enumerate(ref_pool):
        ref = refs[ri]

        for distance, local_ci in zip(distances[local_ri], indices[local_ri]):
            ci = cand_pool[int(local_ci)]
            cand = cands[ci]

            tfidf = max(0.0, min(1.0, 1.0 - float(distance)))
            lexical = _lexical_score(ref, cand)
            path = _path_score(ref, cand)
            unit = _unit_score(ref, cand)
            sheet = _sheet_score(ref, cand)

            if global_pass:
                # Sheet is a soft signal only. Identical or abbreviated item
                # names are allowed to match across differently named sheets.
                score = (
                    0.48 * tfidf
                    + 0.32 * lexical
                    + 0.10 * unit
                    + 0.06 * path
                    + 0.04 * sheet
                )
                threshold = max(reject_score, 0.68)
                reason = "TF-IDF + RapidFuzz toàn cục, không bắt buộc cùng sheet"
            else:
                score = (
                    0.46 * tfidf
                    + 0.34 * lexical
                    + 0.12 * path
                    + 0.08 * unit
                )
                threshold = reject_score
                reason = "TF-IDF ký tự + RapidFuzz trong cùng sheet"

            if score < threshold:
                continue

            proposals.append(
                _Proposal(
                    ri,
                    ci,
                    MatchKind.FUZZY,
                    score,
                    structure=path,
                    lexical=max(tfidf, lexical),
                    unit=unit,
                    row_distance=_row_distance(ref, cand),
                    reason=reason,
                )
            )

    return proposals


# ---------------------------------------------------------------------------
# Main matcher
# ---------------------------------------------------------------------------


def match_items(
    reference: list[ItemRecord],
    candidate: list[ItemRecord],
    config: EnterpriseConfig,
) -> list[MatchResult]:
    """Match baseline BOQ rows with contractor rows.

    Matching order:

    1. Exact structural key inside the same sheet and row type.
    2. Exact code inside the same sheet and row type.
    3. Exact normalized name globally across sheets.
    4. Strict reliable-code fallback across sheets.
    5. Row-near matching for files sharing the same template.
    6. Sparse TF-IDF/RapidFuzz shortlist in the same sheet.
    7. Sparse TF-IDF/RapidFuzz shortlist globally by row type.
    8. Optional local embedding and reranker.
    9. Explicit MISSING and EXTRA records.

    The crucial rule is that sheet names are never a hard requirement for exact
    item names. This prevents a baseline item in ``2 - PHAN TU HA THE`` from
    being marked missing when the same item appears in contractor sheet
    ``1. HT điện``.
    """

    refs = [item for item in reference if item.is_comparable]
    cands = [item for item in candidate if item.is_comparable]

    results: list[MatchResult] = []
    used_ref: set[int] = set()
    used_cand: set[int] = set()

    reject_score = float(config.thresholds.name_reject_score)

    # ------------------------------------------------------------------
    # 1. Exact structural key inside the same normalized sheet + row type
    # ------------------------------------------------------------------
    ref_by_structure: dict[tuple[str, RowType, str], list[int]] = defaultdict(list)
    cand_by_structure: dict[tuple[str, RowType, str], list[int]] = defaultdict(list)

    for ri, item in enumerate(refs):
        if item.structural_key:
            ref_by_structure[
                (_sheet(item), _row_type(item), item.structural_key)
            ].append(ri)

    for ci, item in enumerate(cands):
        if item.structural_key:
            cand_by_structure[
                (_sheet(item), _row_type(item), item.structural_key)
            ].append(ci)

    structural_proposals: list[_Proposal] = []
    for key in sorted(
        set(ref_by_structure) & set(cand_by_structure),
        key=lambda value: (value[0], str(value[1]), value[2]),
    ):
        for ri in ref_by_structure[key]:
            for ci in cand_by_structure[key]:
                ref = refs[ri]
                cand = cands[ci]
                lexical = _lexical_score(ref, cand)
                unit = _unit_score(ref, cand)
                distance = abs(ref.row_number - cand.row_number)
                code_equal = bool(
                    ref.normalized_code
                    and ref.normalized_code == cand.normalized_code
                )

                score = min(0.99, 0.96 + 0.02 * lexical + 0.01 * unit)
                structural_proposals.append(
                    _Proposal(
                        ri,
                        ci,
                        MatchKind.EXACT_STRUCTURE,
                        score,
                        structure=1.0,
                        code=1.0 if code_equal else 0.0,
                        lexical=lexical,
                        unit=unit,
                        row_distance=distance,
                        reason="Trùng sheet, loại dòng và khóa cấu trúc",
                    )
                )

    _assign_sorted(
        structural_proposals,
        results,
        used_ref,
        used_cand,
    )

    # ---------------------------------------------------------------
    # 2. Exact code inside the same normalized sheet + row type
    # ---------------------------------------------------------------
    cand_by_same_sheet_code: dict[tuple[str, RowType, str], list[int]] = defaultdict(list)
    for ci, item in enumerate(cands):
        if ci not in used_cand and item.normalized_code:
            cand_by_same_sheet_code[
                (_sheet(item), _row_type(item), item.normalized_code)
            ].append(ci)

    code_proposals: list[_Proposal] = []
    for ri, ref in enumerate(refs):
        if ri in used_ref or not ref.normalized_code:
            continue

        key = (_sheet(ref), _row_type(ref), ref.normalized_code)
        for ci in cand_by_same_sheet_code.get(key, []):
            if ci in used_cand:
                continue

            cand = cands[ci]
            lexical = _lexical_score(ref, cand)
            path = _path_score(ref, cand)
            unit = _unit_score(ref, cand)
            distance = abs(ref.row_number - cand.row_number)
            score = 0.76 + 0.12 * lexical + 0.08 * path + 0.04 * unit

            code_proposals.append(
                _Proposal(
                    ri,
                    ci,
                    MatchKind.EXACT_CODE,
                    min(score, 0.99),
                    structure=path,
                    code=1.0,
                    lexical=lexical,
                    unit=unit,
                    row_distance=distance,
                    reason="Trùng mã hiệu trong cùng sheet và cùng loại dòng",
                )
            )

    _assign_sorted(code_proposals, results, used_ref, used_cand)

    # -----------------------------------------------------------------
    # 3. Exact normalized name GLOBALLY, sheet name is only a soft signal
    # -----------------------------------------------------------------
    # FIX: the old implementation used
    #   (_sheet(item), item.row_type, item.normalized_name)
    # as the dictionary key. That made identical items fail whenever the two
    # workbooks used different sheet names. The new key intentionally excludes
    # sheet and keeps only row type + normalized item name.
    cand_by_global_name: dict[tuple[RowType, str], list[int]] = defaultdict(list)
    for ci, item in enumerate(cands):
        if ci not in used_cand and item.normalized_name:
            cand_by_global_name[(_row_type(item), item.normalized_name)].append(ci)

    exact_name_proposals: list[_Proposal] = []
    for ri, ref in enumerate(refs):
        if ri in used_ref or not ref.normalized_name:
            continue

        key = (_row_type(ref), ref.normalized_name)
        for ci in cand_by_global_name.get(key, []):
            if ci in used_cand:
                continue

            cand = cands[ci]
            unit = _unit_score(ref, cand)
            path = _path_score(ref, cand)
            sheet = _sheet_score(ref, cand)
            same_sheet = _same_sheet(ref, cand)

            # Exact name is the strongest signal. Same sheet receives a small
            # tie-break bonus but a different sheet never blocks the match.
            score = 0.91 + 0.04 * unit + 0.03 * path + 0.02 * sheet
            score = min(score, 0.995)

            reason = (
                "Trùng tên sau chuẩn hóa trong cùng sheet"
                if same_sheet
                else "Trùng tên sau chuẩn hóa, khác tên sheet"
            )

            exact_name_proposals.append(
                _Proposal(
                    ri,
                    ci,
                    MatchKind.EXACT_NAME,
                    score,
                    structure=path,
                    lexical=1.0,
                    unit=unit,
                    row_distance=_row_distance(ref, cand),
                    reason=reason,
                )
            )

    _assign_sorted(exact_name_proposals, results, used_ref, used_cand)

    # -------------------------------------------------------------
    # 4. Strict reliable-code fallback across differently named sheets
    # -------------------------------------------------------------
    cand_by_global_code: dict[tuple[RowType, str], list[int]] = defaultdict(list)
    for ci, item in enumerate(cands):
        if (
            ci not in used_cand
            and item.normalized_code
            and _is_reliable_cross_sheet_code(item.normalized_code)
        ):
            cand_by_global_code[(_row_type(item), item.normalized_code)].append(ci)

    global_code_proposals: list[_Proposal] = []
    for ri, ref in enumerate(refs):
        if (
            ri in used_ref
            or not ref.normalized_code
            or not _is_reliable_cross_sheet_code(ref.normalized_code)
        ):
            continue

        key = (_row_type(ref), ref.normalized_code)
        for ci in cand_by_global_code.get(key, []):
            if ci in used_cand:
                continue

            cand = cands[ci]
            lexical = _lexical_score(ref, cand)
            path = _path_score(ref, cand)
            unit = _unit_score(ref, cand)
            sheet = _sheet_score(ref, cand)

            # A repeated code across sheets is accepted only when description or
            # hierarchy also provides supporting evidence.
            if lexical < 0.55 and path < 0.72:
                continue
            if unit == 0.0 and lexical < 0.82:
                continue

            score = (
                0.70
                + 0.14 * lexical
                + 0.08 * path
                + 0.05 * unit
                + 0.03 * sheet
            )

            global_code_proposals.append(
                _Proposal(
                    ri,
                    ci,
                    MatchKind.EXACT_CODE,
                    min(score, 0.97),
                    structure=path,
                    code=1.0,
                    lexical=lexical,
                    unit=unit,
                    row_distance=_row_distance(ref, cand),
                    reason="Trùng mã hiệu tin cậy, khác tên sheet",
                )
            )

    _assign_sorted(global_code_proposals, results, used_ref, used_cand)

    # ------------------------------------------------------------
    # 5. Row-near pass for workbooks sharing the same BOQ template
    # ------------------------------------------------------------
    refs_by_sheet = _remaining_by_sheet_and_type(refs, used_ref)
    cands_by_sheet = _remaining_by_sheet_and_type(cands, used_cand)

    row_near_proposals: list[_Proposal] = []
    for key, ref_pool in refs_by_sheet.items():
        cand_pool = cands_by_sheet.get(key, [])
        if not cand_pool:
            continue

        for ri in ref_pool:
            ref = refs[ri]
            nearby = sorted(
                cand_pool,
                key=lambda ci: abs(cands[ci].row_number - ref.row_number),
            )[:8]

            for ci in nearby:
                if ci in used_cand:
                    continue

                cand = cands[ci]
                distance = abs(cand.row_number - ref.row_number)
                if distance > 35:
                    continue

                lexical = _lexical_score(ref, cand)
                path = _path_score(ref, cand)
                unit = _unit_score(ref, cand)
                proximity = max(0.0, 1.0 - distance / 35.0)
                score = (
                    0.58 * lexical
                    + 0.22 * path
                    + 0.12 * unit
                    + 0.08 * proximity
                )

                if score < max(reject_score, 0.68):
                    continue

                row_near_proposals.append(
                    _Proposal(
                        ri,
                        ci,
                        MatchKind.ROW_NEAR,
                        score,
                        structure=path,
                        lexical=lexical,
                        unit=unit,
                        row_distance=distance,
                        reason="Cùng sheet, cùng loại dòng và gần vị trí",
                    )
                )

    _assign_sorted(row_near_proposals, results, used_ref, used_cand)

    # -----------------------------------------------------------------
    # 6. Sparse TF-IDF shortlist inside the same sheet and row type
    # -----------------------------------------------------------------
    refs_by_sheet = _remaining_by_sheet_and_type(refs, used_ref)
    cands_by_sheet = _remaining_by_sheet_and_type(cands, used_cand)

    fuzzy_proposals: list[_Proposal] = []
    for key, ref_pool in refs_by_sheet.items():
        cand_pool = cands_by_sheet.get(key, [])
        fuzzy_proposals.extend(
            _tfidf_shortlist(
                refs,
                cands,
                ref_pool,
                cand_pool,
                top_k=config.fuzzy_top_k,
                include_sheet=True,
                global_pass=False,
                reject_score=reject_score,
            )
        )

    # -----------------------------------------------------------------
    # 7. Global sparse TF-IDF fallback by row type, not by sheet
    # -----------------------------------------------------------------
    # This second shortlist is the important fallback for workbooks whose sheet
    # names/order differ. It still avoids a dense N*M matrix by retrieving only
    # top-k candidates per remaining row.
    refs_by_type = _remaining_by_type(refs, used_ref)
    cands_by_type = _remaining_by_type(cands, used_cand)

    global_top_k = max(int(config.fuzzy_top_k), 8)
    for row_type, ref_pool in refs_by_type.items():
        cand_pool = cands_by_type.get(row_type, [])
        fuzzy_proposals.extend(
            _tfidf_shortlist(
                refs,
                cands,
                ref_pool,
                cand_pool,
                top_k=global_top_k,
                include_sheet=False,
                global_pass=True,
                reject_score=reject_score,
            )
        )

    fuzzy_proposals = _deduplicate_proposals(fuzzy_proposals)

    # ---------------------------------------------------------------
    # 8. Optional local embedding enrichment and semantic retrieval
    # ---------------------------------------------------------------
    encoder = (
        LocalSemanticEncoder(
            config.embedding_model_path,
            config.semantic_batch_size,
        )
        if config.enable_semantic_matching
        else None
    )

    if encoder and encoder.available:
        remaining_ref = sorted(
            ri for ri in range(len(refs)) if ri not in used_ref
        )
        remaining_cand = sorted(
            ci for ci in range(len(cands)) if ci not in used_cand
        )

        ref_vectors = encoder.encode(
            [_combined_text(refs[ri], include_sheet=False) for ri in remaining_ref],
            is_query=True,
        )
        cand_vectors = encoder.encode(
            [_combined_text(cands[ci], include_sheet=False) for ci in remaining_cand],
            is_query=False,
        )

        if ref_vectors is not None and cand_vectors is not None:
            ref_position = {idx: pos for pos, idx in enumerate(remaining_ref)}
            cand_position = {idx: pos for pos, idx in enumerate(remaining_cand)}

            # Enrich existing TF-IDF/RapidFuzz proposals.
            for proposal in fuzzy_proposals:
                if (
                    proposal.ref_idx not in ref_position
                    or proposal.cand_idx not in cand_position
                ):
                    continue

                semantic = float(
                    np.dot(
                        ref_vectors[ref_position[proposal.ref_idx]],
                        cand_vectors[cand_position[proposal.cand_idx]],
                    )
                )
                proposal.semantic = max(0.0, min(1.0, semantic))
                proposal.score = min(
                    1.0,
                    0.54 * proposal.score
                    + 0.36 * proposal.semantic
                    + 0.10 * proposal.unit,
                )
                proposal.kind = MatchKind.SEMANTIC
                proposal.reason += " + embedding local"

            # Global semantic nearest-neighbour retrieval by row type.
            remaining_refs_by_type = _remaining_by_type(refs, used_ref)
            remaining_cands_by_type = _remaining_by_type(cands, used_cand)

            for row_type, ref_pool_all in remaining_refs_by_type.items():
                ref_pool = [ri for ri in ref_pool_all if ri in ref_position]
                cand_pool = [
                    ci
                    for ci in remaining_cands_by_type.get(row_type, [])
                    if ci in cand_position
                ]

                if not ref_pool or not cand_pool:
                    continue

                cand_matrix = np.asarray(
                    [cand_vectors[cand_position[ci]] for ci in cand_pool],
                    dtype=np.float32,
                )
                ref_matrix = np.asarray(
                    [ref_vectors[ref_position[ri]] for ri in ref_pool],
                    dtype=np.float32,
                )

                top_k = max(
                    1,
                    min(int(config.semantic_top_k), len(cand_pool)),
                )

                nearest = NearestNeighbors(
                    n_neighbors=top_k,
                    metric="cosine",
                    algorithm="brute",
                    n_jobs=-1,
                )
                nearest.fit(cand_matrix)
                distances, indices = nearest.kneighbors(ref_matrix)

                for local_ri, ri in enumerate(ref_pool):
                    ref = refs[ri]

                    for distance, local_ci in zip(
                        distances[local_ri],
                        indices[local_ri],
                    ):
                        ci = cand_pool[int(local_ci)]
                        cand = cands[ci]

                        semantic = max(
                            0.0,
                            min(1.0, 1.0 - float(distance)),
                        )
                        lexical = _lexical_score(ref, cand)
                        path = _path_score(ref, cand)
                        unit = _unit_score(ref, cand)
                        sheet = _sheet_score(ref, cand)

                        score = (
                            0.56 * semantic
                            + 0.20 * lexical
                            + 0.12 * path
                            + 0.08 * unit
                            + 0.04 * sheet
                        )

                        if semantic < 0.46:
                            continue
                        if score < max(0.52, reject_score - 0.06):
                            continue

                        fuzzy_proposals.append(
                            _Proposal(
                                ri,
                                ci,
                                MatchKind.SEMANTIC,
                                score,
                                structure=path,
                                lexical=lexical,
                                semantic=semantic,
                                unit=unit,
                                row_distance=_row_distance(ref, cand),
                                reason=(
                                    "Qwen3/BGE embedding nearest-neighbour local "
                                    "theo loại dòng, không bắt buộc cùng sheet"
                                ),
                            )
                        )

    fuzzy_proposals = _deduplicate_proposals(fuzzy_proposals)

    # -----------------------------------------
    # Optional local CrossEncoder reranker
    # -----------------------------------------
    reranker = (
        LocalReranker(
            config.reranker_model_path,
            config.reranker_batch_size,
        )
        if config.enable_reranker
        else None
    )

    if reranker and reranker.available and fuzzy_proposals:
        shortlist = sorted(
            fuzzy_proposals,
            key=_proposal_sort_key,
        )[: min(len(fuzzy_proposals), 20_000)]

        pairs = [
            (
                _combined_text(refs[proposal.ref_idx], include_sheet=False),
                _combined_text(cands[proposal.cand_idx], include_sheet=False),
            )
            for proposal in shortlist
        ]

        reranker_scores = reranker.predict(pairs)
        if reranker_scores is not None:
            for proposal, reranker_score in zip(shortlist, reranker_scores):
                proposal.reranker = float(reranker_score)
                proposal.score = min(
                    1.0,
                    0.65 * proposal.score + 0.35 * proposal.reranker,
                )
                proposal.kind = MatchKind.RERANKED
                proposal.reason += " + reranker local"

    # Final one-to-one assignment of fuzzy/semantic/reranked candidates.
    _assign_sorted(
        _deduplicate_proposals(fuzzy_proposals),
        results,
        used_ref,
        used_cand,
        minimum_score=reject_score,
    )

    # ------------------------------------------------------------
    # 9. Explicit unmatched rows; never silently drop duplicates
    # ------------------------------------------------------------
    for ri in range(len(refs)):
        if ri not in used_ref:
            results.append(
                MatchResult(
                    ri,
                    None,
                    MatchKind.MISSING,
                    0.0,
                    reason="Không tìm thấy hạng mục tương ứng",
                )
            )

    for ci in range(len(cands)):
        if ci not in used_cand:
            results.append(
                MatchResult(
                    None,
                    ci,
                    MatchKind.EXTRA,
                    0.0,
                    reason="Hạng mục phát sinh ngoài baseline",
                )
            )

    # Stable output order for deterministic reports and tests.
    results.sort(
        key=lambda match: (
            refs[match.reference_index].sheet
            if match.reference_index is not None
            else cands[match.candidate_index].sheet,
            refs[match.reference_index].row_number
            if match.reference_index is not None
            else cands[match.candidate_index].row_number,
            match.candidate_index if match.candidate_index is not None else -1,
        )
    )

    return results
