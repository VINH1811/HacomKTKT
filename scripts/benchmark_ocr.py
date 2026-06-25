from __future__ import annotations

import argparse
import json
from pathlib import Path


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--truth", required=True, help="JSONL ground truth")
    p.add_argument("--pred", required=True, help="JSONL prediction")
    args = p.parse_args()
    truth = {x["id"]: x for x in map(json.loads, Path(args.truth).read_text(encoding="utf-8").splitlines())}
    pred = {x["id"]: x for x in map(json.loads, Path(args.pred).read_text(encoding="utf-8").splitlines())}
    exact = 0; total = 0; edits = 0; chars = 0
    for key, t in truth.items():
        expected = str(t.get("text", "")); got = str(pred.get(key, {}).get("text", ""))
        total += 1; exact += expected == got
        edits += levenshtein(expected, got); chars += max(len(expected), 1)
    print(json.dumps({"cells": total, "exact_match": exact/max(total,1), "CER": edits/max(chars,1)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
