from __future__ import annotations

from collections import Counter
from pathlib import Path

from .config import EnterpriseConfig
from .matcher import match_items
from .models import (
    ComparedItem,
    FieldDifference,
    DocumentRole,
    ItemRecord,
    MatchKind,
    MatchResult,
    Severity,
    WorkbookData,
)


def _most_common(values: list[str]) -> str:
    cleaned = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not cleaned:
        return ""
    counts = Counter(value.casefold() for value in cleaned)
    winner = counts.most_common(1)[0][0]
    candidates = [value for value in cleaned if value.casefold() == winner]
    return max(candidates, key=len)


class _DSU:
    def __init__(self, bidder_ids: list[int]):
        self.parent = list(range(len(bidder_ids)))
        self.rank = [0] * len(bidder_ids)
        self.bidders = [{bidder_ids[i]} for i in range(len(bidder_ids))]

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union_if_no_bidder_conflict(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if self.bidders[ra] & self.bidders[rb]:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.bidders[ra] |= self.bidders[rb]
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def build_peer_consensus(
    bidders: list[WorkbookData],
    config: EnterpriseConfig,
) -> tuple[WorkbookData, list[ComparedItem], dict]:
    """Build a neutral multi-bidder catalogue from all pairwise matches."""
    comparable = [[item for item in workbook.items if item.is_comparable] for workbook in bidders]
    nodes: list[tuple[int, int, ItemRecord]] = []
    node_index: dict[tuple[int, int], int] = {}
    for bidder_idx, items in enumerate(comparable):
        for item_idx, item in enumerate(items):
            node_index[(bidder_idx, item_idx)] = len(nodes)
            nodes.append((bidder_idx, item_idx, item))

    dsu = _DSU([bidder_idx for bidder_idx, _, _ in nodes])
    edges: list[tuple[float, int, int, MatchResult]] = []
    accepted_kinds = {
        MatchKind.EXACT_STRUCTURE,
        MatchKind.EXACT_CODE,
        MatchKind.EXACT_NAME,
        MatchKind.ROW_NEAR,
        MatchKind.FUZZY,
        MatchKind.SEMANTIC,
        MatchKind.RERANKED,
    }
    minimum = max(0.60, config.thresholds.name_reject_score)
    for left_idx in range(len(bidders)):
        for right_idx in range(left_idx + 1, len(bidders)):
            matches = match_items(comparable[left_idx], comparable[right_idx], config)
            for match in matches:
                if match.kind not in accepted_kinds or match.reference_index is None or match.candidate_index is None:
                    continue
                if match.score < minimum and match.kind not in {
                    MatchKind.EXACT_STRUCTURE,
                    MatchKind.EXACT_CODE,
                    MatchKind.EXACT_NAME,
                }:
                    continue
                a = node_index[(left_idx, match.reference_index)]
                b = node_index[(right_idx, match.candidate_index)]
                edges.append((float(match.score), a, b, match))
    edges.sort(key=lambda value: value[0], reverse=True)
    for _, a, b, _ in edges:
        dsu.union_if_no_bidder_conflict(a, b)

    components: dict[int, list[int]] = {}
    for index in range(len(nodes)):
        components.setdefault(dsu.find(index), []).append(index)
    ordered_components = sorted(
        components.values(),
        key=lambda component: min((nodes[index][2].sheet, nodes[index][2].row_number) for index in component),
    )

    consensus_items: list[ItemRecord] = []
    rows: list[ComparedItem] = []
    bidder_names = [workbook.bidder for workbook in bidders]
    for cluster_index, component in enumerate(ordered_components, start=1):
        cluster_items = [nodes[index][2] for index in component]
        member_by_bidder = {nodes[index][0]: nodes[index][2] for index in component}
        representative = max(cluster_items, key=lambda item: (len(item.item_name), bool(item.item_code), -item.row_number))
        canonical_id = f"PEER-{cluster_index:07d}"
        consensus = ItemRecord(
            source_id=canonical_id,
            role=DocumentRole.HSMT,
            bidder="DANH MỤC ĐỒNG THUẬN NGANG HÀNG",
            workbook="peer_consensus",
            sheet=_most_common([item.sheet for item in cluster_items]) or representative.sheet,
            row_number=cluster_index,
            stt=_most_common([item.stt for item in cluster_items]),
            item_code=_most_common([item.item_code for item in cluster_items]),
            item_name=_most_common([item.item_name for item in cluster_items]) or representative.item_name,
            unit=_most_common([item.unit for item in cluster_items]),
            material=_most_common([item.material for item in cluster_items]),
            note="Cụm được tạo từ ghép đa chiều giữa tất cả nhà thầu; không lấy nhà thầu nào làm chuẩn.",
            section_path=representative.section_path,
            section_codes=representative.section_codes,
            row_type=representative.row_type,
            normalized_stt=representative.normalized_stt,
            normalized_code=representative.normalized_code,
            normalized_name=representative.normalized_name,
            normalized_unit=representative.normalized_unit,
            normalized_path=representative.normalized_path,
            structural_key=representative.structural_key,
        )
        consensus_items.append(consensus)

        for bidder_idx, bidder_name in enumerate(bidder_names):
            candidate = member_by_bidder.get(bidder_idx)
            if candidate is None:
                match = MatchResult(None, None, MatchKind.MISSING, 0.0, reason="Nhà thầu không có hạng mục trong cụm ngang hàng")
                row = ComparedItem(canonical_id, bidder_name, consensus, None, match)
                row.severity = Severity.CRITICAL
                row.anomaly_score = 45.0
                row.flags = ["Thiếu hạng mục so với danh mục đồng thuận của các nhà thầu"]
                row.differences = [FieldDifference(
                    field="Hạng mục",
                    reference_value=consensus.item_name,
                    candidate_value="",
                    severity=Severity.CRITICAL,
                    message=row.flags[0],
                )]
            else:
                kind = MatchKind.EXACT_NAME if candidate.normalized_name == consensus.normalized_name else MatchKind.FUZZY
                match = MatchResult(
                    reference_index=cluster_index - 1,
                    candidate_index=candidate.row_number,
                    kind=kind,
                    score=1.0 if kind is MatchKind.EXACT_NAME else 0.80,
                    lexical_score=1.0 if kind is MatchKind.EXACT_NAME else 0.80,
                    reason="Ghép đa chiều từ tất cả cặp nhà thầu; không có baseline.",
                )
                row = ComparedItem(canonical_id, bidder_name, consensus, candidate, match)
            rows.append(row)

    reference = WorkbookData(
        path=Path("peer_consensus.virtual.xlsx"),
        role=DocumentRole.HSMT,
        bidder="DANH MỤC ĐỒNG THUẬN NGANG HÀNG",
        items=consensus_items,
        warnings=[],
        sheet_info=[{"mode": "multiway_peer_clustering", "clusters": len(consensus_items)}],
        read_engine="virtual",
    )
    stats = {
        "nodes": len(nodes),
        "pairwise_edges": len(edges),
        "clusters": len(consensus_items),
        "singleton_clusters": sum(len(component) == 1 for component in ordered_components),
        "principle": "all-pairs matching + constrained connected components; no bidder baseline",
    }
    return reference, rows, stats
