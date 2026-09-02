#!/usr/bin/env python3
"""Exact and near-duplicate analysis of the English sentences (and RU/UK where
present), within each category file and across all files.

Levels reported
  L1 exact        identical strings
  L2 normalised   identical after lower-casing, removing punctuation/quotes and
                  collapsing whitespace
  L3 frame        identical after additionally masking the three manipulated
                  elements (temporal opener, nationality adjective, entity
                  type). Rows of the SAME pair_id are expected to collide here
                  (that is the minimal-pair design); only collisions between
                  DIFFERENT pair_ids are reported -> "template reuse".
  L4 near         token-set Jaccard similarity >= THRESHOLD between sentences of
                  different pair_ids after L3 masking (near-duplicate
                  scenarios, e.g. the same sentence with one word changed).

Output: duplicates_report.md (Markdown) and duplicates_near.csv (all L3/L4
pairs) in the current directory.
"""
from __future__ import annotations

import argparse
import collections
import csv
import itertools
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # dataset code root (src/v1 in the workspace, dataset/ on GitHub)
DEFAULT_DATA = next((p for p in (ROOT / "data" / "v1.1", ROOT.parent.parent / "data" / "v1") if p.exists()), ROOT / "data" / "v1.1")  # data/v1.1 inside the repository, else the workspace layout; or pass --dir
REPORTS = ROOT / "reports"


THRESHOLD = 0.9
PUNCT = re.compile(r"[^\w\s]")


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", PUNCT.sub(" ", s.lower())).strip()


def mask(r: dict) -> str:
    s = r["sentence_en"]
    s = s.split(",", 1)[1] if "," in s else s              # drop temporal opener
    s = s.replace("Ukrainian", "{NAT}").replace("Russian", "{NAT}")
    s = s.replace(r["entity_type"], "{ENTITY}")
    return normalise(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DATA))
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--out", default=str(REPORTS / "v1.1"), help="directory for duplicates_report.md and duplicates_near.csv")
    args = ap.parse_args()
    files = sorted(p for p in Path(args.dir).glob("*.csv") if re.match(r"^\d+-", p.name))
    allrecs: list[dict] = []
    for p in files:
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r = {k.strip().lower(): v for k, v in r.items()}
                r["file"] = p.name
                allrecs.append(r)

    lines = ["# Duplicate analysis", "", f"Directory: `{args.dir}`  Rows: {len(allrecs)}", ""]
    # L1 / L2 within file and global, per language
    for lang in ("sentence_en", "ru", "uk"):
        recs = [r for r in allrecs if r.get(lang)]
        for level, key in (("L1 exact", lambda r: r[lang]), ("L2 normalised", lambda r: normalise(r[lang]))):
            within = 0
            for f in files:
                c = collections.Counter(key(r) for r in recs if r["file"] == f.name)
                within += sum(v - 1 for v in c.values() if v > 1)
            cg = collections.Counter(key(r) for r in recs)
            glob = sum(v - 1 for v in cg.values() if v > 1)
            lines.append(f"- {lang} {level}: within-file surplus rows = {within}, global surplus rows = {glob}")
    lines.append("")

    # L3 frame reuse across different pair_ids (within and across files)
    frames = collections.defaultdict(set)
    for r in allrecs:
        frames[mask(r)].add((r["file"], r["pair_id"]))
    reuse = {k: v for k, v in frames.items() if len(v) > 1}
    lines.append(f"## L3 frame reuse (identical sentence after masking opener/nationality/entity) between different pair_ids: {len(reuse)} frames")
    out_rows = []
    for k, v in sorted(reuse.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- x{len(v)} {sorted(v)}: '{k[:90]}'")
        out_rows.append({"level": "L3", "similarity": 1.0, "pairs": ";".join(f"{a}:{b}" for a, b in sorted(v)), "text": k})
    lines.append("")

    # L4 near duplicates: Jaccard on token sets of masked frames, different pair_ids
    uniq = {}
    for r in allrecs:
        uniq.setdefault(mask(r), (r["file"], r["pair_id"]))
    items = [(k, frozenset(k.split()), v) for k, v in uniq.items()]
    # blocking by first two tokens to keep it tractable
    blocks = collections.defaultdict(list)
    for k, toks, v in items:
        for t in list(toks)[:]:
            pass
        blocks[" ".join(k.split()[:2])].append((k, toks, v))
    near = []
    seen = set()
    for blk in blocks.values():
        for (k1, t1, v1), (k2, t2, v2) in itertools.combinations(blk, 2):
            if v1[1] == v2[1] and v1[0] == v2[0]:
                continue
            j = len(t1 & t2) / len(t1 | t2)
            if j >= args.threshold and (k1, k2) not in seen:
                seen.add((k1, k2))
                near.append((j, v1, v2, k1, k2))
    near.sort(reverse=True)
    lines.append(f"## L4 near-duplicate frames (Jaccard >= {args.threshold}, different pair_ids, same 2-token prefix block): {len(near)} pairs")
    for j, v1, v2, k1, k2 in near[:200]:
        lines.append(f"- {j:.2f} {v1} ~ {v2}\n    - '{k1[:100]}'\n    - '{k2[:100]}'")
        out_rows.append({"level": "L4", "similarity": round(j, 3), "pairs": f"{v1[0]}:{v1[1]};{v2[0]}:{v2[1]}", "text": k1 + " || " + k2})
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "duplicates_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (out / "duplicates_near.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["level", "similarity", "pairs", "text"])
        w.writeheader()
        w.writerows(out_rows)
    print("\n".join(lines[:12]))
    hard = [l for l in lines if (" L1 " in l or " L2 " in l) and "surplus rows = 0, global surplus rows = 0" not in l and l.startswith("- ")]
    n_fail = len(hard) + len(near)
    print(f"\nRESULT: {len(hard)} exact/normalised duplicate line(s), {len(near)} near-duplicate pair(s) (L3 frame reuse is the documented scenario structure and does not fail)" + (" — FAIL" if n_fail else " — OK"))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
