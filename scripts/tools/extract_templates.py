#!/usr/bin/env python3
"""Reconstruct the parameterized scenario templates from the released data
(response to Reviewer 3, remark 5 and Reviewer 2, remarks 1 and 9).

For every pair_id the 12 English sentences are reduced to one template record
with slots {TIME}, {SIDE_ADJ} and {ENTITY}: the temporal opener is replaced by
{TIME}, the nationality adjective by {SIDE_ADJ} and the entity type by
{ENTITY}. Because the three timeframes differ in the verb form, the template
stores the positive and negative frame for each timeframe separately
(pos_past, pos_present, pos_future, neg_past, neg_present, neg_future) together
with the concrete openers used (opener_past, opener_present, opener_future).

A template is marked `consistent = yes` when the ua and ru variants of every
cell collapse to the same frame, i.e. the pair is a perfect minimal pair.

Templates that share the same six frames (i.e. differ only in the entity type
and/or the concrete temporal openers) are instantiations of the same underlying
*scenario*; they receive a common `scenario_id` (<pair prefix>_s<NNN>) and the
column `scenario_instances` gives the number of pair_ids sharing it.

Outputs: templates.csv (one row per pair_id, 2,200 rows) and
templates_summary.md (distinct scenarios per category).
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # dataset code root (src/v1 in the workspace, dataset/ on GitHub)
DEFAULT_DATA = next((p for p in (ROOT / "data" / "v1.1", ROOT.parent.parent / "data" / "v1") if p.exists()), ROOT / "data" / "v1.1")  # data/v1.1 inside the repository, else the workspace layout; or pass --dir
REPORTS = ROOT / "reports"


TF = ["Past", "Present", "Future"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(REPORTS / "v1.1" / "templates.csv"))
    args = ap.parse_args()
    files = sorted(p for p in Path(args.dir).glob("*.csv") if re.match(r"^\d+-", p.name))
    out: list[dict] = []
    for p in files:
        with p.open(encoding="utf-8") as fh:
            recs = [{k.strip().lower(): v for k, v in r.items()} for r in csv.DictReader(fh)]
        by: dict[str, list[dict]] = collections.OrderedDict()
        for r in recs:
            by.setdefault(r["pair_id"], []).append(r)
        for pid, grp in by.items():
            ent = grp[0]["entity_type"]
            rec = {"file": p.name, "category": grp[0]["category"], "pair_id": pid, "entity_type": ent}
            frames = collections.defaultdict(set)
            openers = collections.defaultdict(set)
            for r in grp:
                s = r["sentence_en"]
                op, rest = s.split(",", 1) if "," in s else ("", s)
                rest = rest.strip()
                nat = "Ukrainian" if r["side"] == "ua" else "Russian"
                frame = ("{TIME} " + rest).replace(f"the {nat} {ent}", "the {SIDE_ADJ} {ENTITY}").replace(nat, "{SIDE_ADJ}")
                frames[(r["sentiment"], r["timeframe"])].add(frame)
                openers[r["timeframe"]].add(op.strip())
            consistent = all(len(v) == 1 for v in frames.values()) and all(len(v) == 1 for v in openers.values())
            for st in ("pos", "neg"):
                for tf in TF:
                    rec[f"{st}_{tf.lower()}"] = " | ".join(sorted(frames[(st, tf)]))
            for tf in TF:
                rec[f"opener_{tf.lower()}"] = " | ".join(sorted(openers[tf]))
            rec["consistent"] = "yes" if consistent else "no"
            out.append(rec)

    # scenario ids: group templates of one file with identical frame sets
    scen_of: dict[tuple, str] = {}
    counts: collections.Counter = collections.Counter()
    per_file: dict[str, int] = collections.OrderedDict()
    for r in out:
        key = (r["file"],) + tuple(r[f"{st}_{tf.lower()}"] for st in ("pos", "neg") for tf in TF)
        if key not in scen_of:
            per_file[r["file"]] = per_file.get(r["file"], 0) + 1
            prefix = r["pair_id"].rsplit("_", 1)[0]
            scen_of[key] = f"{prefix}_s{per_file[r['file']]:03d}"
        r["scenario_id"] = scen_of[key]
        counts[r["scenario_id"]] += 1
    for r in out:
        r["scenario_instances"] = counts[r["scenario_id"]]

    lines = ["# Scenario templates per category", "",
             "| File | pair_ids (templates) | Distinct scenarios | Instances per scenario (min–max) |",
             "|---|---|---|---|"]
    for f, n_scen in per_file.items():
        sids = {r["scenario_id"] for r in out if r["file"] == f}
        inst = [counts[s] for s in sids]
        npairs = sum(1 for r in out if r["file"] == f)
        lines.append(f"| {f} | {npairs} | {n_scen} | {min(inst)}–{max(inst)} |")
    lines.append(f"| **Total** | {len(out)} | {len(scen_of)} | |")
    Path(args.out).with_name("templates_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    n_ok = sum(1 for r in out if r["consistent"] == "yes")
    print(f"{len(out)} templates written to {args.out}; consistent minimal-pair templates: {n_ok}/{len(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
