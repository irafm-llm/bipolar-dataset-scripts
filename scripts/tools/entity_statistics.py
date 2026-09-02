#!/usr/bin/env python3
"""Entity-level descriptive statistics (response to Reviewer 2, remark 8).

Produces
  entity_statistics.csv          one row per (category, entity_type): number of
                                 pair_ids (scenario templates) and rows using it
  entity_statistics_summary.md   per-category counts, inventory size,
                                 concentration (share of rows covered by the 10
                                 most frequent roles), sector composition and
                                 the overall top-30 roles across the dataset.

Sector assignment is a transparent keyword lexicon (see SECTORS) applied to the
entity label; it is meant as a descriptive aid, not as a gold annotation.
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


SECTORS = {
    "military/security": r"soldier|commander|officer|general|sniper|gunner|pilot|drone|artillery|infantry|naval|navy|air defen|military|army|marine|paratrooper|sapper|engineer unit|recon|security service|border|checkpoint|guard|militia|special forces|tank|intelligence|police|sheriff|patrol|garrison|battalion|platoon|squad|veteran|conscript|reservist|warden|customs",
    "government/political": r"president|minister|parliament|governor|mayor|council|spokesperson|press secretary|official|deputy|senator|chancellor|cabinet|secretary|administrator|ombudsman|party|politician|head of state|envoy|commissioner|regulator|registrar|clerk|treasurer|auditor|tax|budget|procurement|ministry|agency|authority|municipal|city|regional|district|state|national",
    "diplomatic/international": r"diplomat|ambassador|UN |OSCE|Red Cross|envoy|negotiator|mediator|attaché|consul|international|observer|monitor|liaison|EU ",
    "justice/legal": r"judge|prosecutor|lawyer|attorney|court|legal|notary|bailiff|investigator|inspector|detective|forensic|rights",
    "humanitarian/civil society": r"volunteer|aid|NGO|charity|humanitarian|relief|refugee|shelter|activist|community|civil society|religious|priest|pastor|imam|rabbi|chaplain|foundation|donor|coordinator",
    "health": r"doctor|nurse|medic|paramedic|surgeon|physician|hospital|clinic|health|pharmac|psycholog|veterinar|ambulance|epidemiolog",
    "media/education/culture": r"journalist|reporter|editor|blogger|broadcaster|photograph|teacher|professor|lecturer|student|school|university|librarian|museum|artist|writer|historian|scientist|researcher|academic",
    "economy/infrastructure": r"business|company|factory|farmer|worker|manager|director|entrepreneur|trader|merchant|banker|shop|railway|port|airport|utility|energy|power|water|grid|logistics|transport|driver|construction|telecom|cyber|IT |operator|technician|miner|fisher",
    "civilian (generic)": r"^citizen$|^man$|^woman$|^child$|resident|villager|pensioner|elderly|parent|mother|father|family|neighbour|neighbor|passenger|commuter|civilian",
}


def sector(label: str) -> str:
    for name, pat in SECTORS.items():
        if re.search(pat, label, re.I):
            return name
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(REPORTS / "v1.1"))
    args = ap.parse_args()
    files = sorted(p for p in Path(args.dir).glob("*.csv") if re.match(r"^\d+-", p.name))
    per_cat: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    per_cat_pairs: dict[str, dict[str, set]] = collections.defaultdict(lambda: collections.defaultdict(set))
    cat_file = {}
    for p in files:
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r = {k.strip().lower(): v for k, v in r.items()}
                per_cat[r["category"]][r["entity_type"]] += 1
                per_cat_pairs[r["category"]][r["entity_type"]].add(r["pair_id"])
                cat_file[r["category"]] = p.name
    out = Path(args.out)
    rows = []
    for cat in per_cat:
        for ent, n in per_cat[cat].most_common():
            rows.append({"file": cat_file[cat], "category": cat, "entity_type": ent,
                         "sector": sector(ent), "pair_ids": len(per_cat_pairs[cat][ent]),
                         "rows": n, "share_of_category_rows": round(n / sum(per_cat[cat].values()), 4)})
    with (out / "entity_statistics.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    overall = collections.Counter()
    overall_pairs = collections.Counter()
    for cat in per_cat:
        for ent, n in per_cat[cat].items():
            overall[ent] += n
            overall_pairs[ent] += len(per_cat_pairs[cat][ent])
    lines = ["# Entity-type statistics", "",
             f"Distinct entity types overall: {len(overall)}; (category, entity) combinations: {len(rows)}", "",
             "| File | Category | Entity types | Templates per type (min–median–max) | Rows covered by top-10 types | Military/security share of rows | Largest sector |",
             "|---|---|---|---|---|---|---|"]
    for cat in sorted(per_cat, key=lambda c: cat_file[c]):
        c = per_cat[cat]
        pairs = sorted(len(per_cat_pairs[cat][e]) for e in c)
        med = pairs[len(pairs) // 2]
        total = sum(c.values())
        top10 = sum(n for _, n in c.most_common(10)) / total
        sec = collections.Counter()
        for e, n in c.items():
            sec[sector(e)] += n
        mil = sec["military/security"] / total
        lines.append(f"| {cat_file[cat]} | {cat} | {len(c)} | {pairs[0]}–{med}–{pairs[-1]} | {top10:.0%} | {mil:.0%} | {sec.most_common(1)[0][0]} |")
    lines += ["", "## Sector composition of all rows (keyword lexicon)", ""]
    sec_all = collections.Counter()
    for ent, n in overall.items():
        sec_all[sector(ent)] += n
    tot = sum(sec_all.values())
    for s, n in sec_all.most_common():
        lines.append(f"- {s}: {n} rows ({n / tot:.1%}), {sum(1 for e in overall if sector(e) == s)} entity types")
    lines += ["", "## 30 most frequent entity types (rows across all categories, number of categories)", ""]
    cats_of = collections.Counter()
    for cat in per_cat:
        for e in per_cat[cat]:
            cats_of[e] += 1
    for e, n in overall.most_common(30):
        lines.append(f"- {e}: {n} rows, {overall_pairs[e]} templates, {cats_of[e]} categories")
    gendered = [e for e in overall if re.search(r"\b(man|woman|men|women|mother|father|wife|husband|boy|girl|-man|-woman)\b", e)]
    lines += ["", f"Gender-marked entity labels: {gendered if gendered else 'none'}", ""]
    (out / "entity_statistics_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
