#!/usr/bin/env python3
"""Automated structural and minimal-pair validation of the dataset.

Checks performed on every category file <dir>/*.csv (entity_inventory.csv
excluded):

  C0  files       - all expected category files present (22 by default,
                    --files to override or "none")
  C1  schema      - header is exactly pair_id,category,entity_type,timeframe,
                    side,sentiment,sentence_en,ru,uk; UTF-8; no BOM
  C2  design      - exactly 100 pair_id values; each pair_id has exactly 12 rows
                    covering all 3 timeframes x 2 sides x 2 sentiments once
  C3  labels      - timeframe in {Past,Present,Future}, side in {ua,ru},
                    sentiment in {pos,neg}; category label identical in all rows
                    and consistent with the file name; entity_type constant
                    within a pair_id and present in entity_inventory.csv
  C4  side sym.   - for every (pair_id,timeframe,sentiment) the ua and ru English
                    sentences are identical after mapping Ukrainian->X /
                    Russian->X (lexical symmetry of the minimal pair)
  C5  frame sym.  - pos and neg sentences of the same (pair_id,timeframe,side)
                    share the temporal opener and the actor phrase
                    "the <Nationality> <entity_type>" (structural symmetry)
  C6  tense       - temporal opener is consistent with the timeframe label
                    (Past openers: In YYYY<=2024, Last ..., ago, Earlier this
                    year, During the previous ...; Present: Today, This ...,
                    Right now, At present, These days, Currently, Tonight;
                    Future: Tomorrow, Next ..., Later this year, In the coming
                    weeks, Soon, In the near future, By the end of the year,
                    In YYYY>=2026) and the main verb group matches (Future:
                    "the <Nationality> <entity> will ..."; Past/Present: not)
  C7  translation - ru and uk non-empty, Cyrillic, no Latin letter at all
                    letters, no spreadsheet error token (#VALUE!, #N/A, ...),
                    ru != uk, nationality token present and matching `side`
                    (ua: украин*/україн*, ru: росси*/русск*/росі*), temporal
                    opener present where deterministic (year present for
                    "In YYYY" sentences)
  C8  uniqueness  - no duplicated sentence_en / ru / uk within the file; no
                    duplicated sentence_en across all files (reported globally)

Outputs a Markdown report (default validation_report.md) with a per-file table
and the list of all failures, and exits with status 1 if any check fails.
"""
from __future__ import annotations

import argparse
import collections
import json
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # dataset code root (src/v1 in the workspace, dataset/ on GitHub)
DEFAULT_DATA = next((p for p in (ROOT / "data" / "v1.1", ROOT.parent.parent / "data" / "v1") if p.exists()), ROOT / "data" / "v1.1")  # data/v1.1 inside the repository, else the workspace layout; or pass --dir
REPORTS = ROOT / "reports"


EXPECTED_HEADER = ["pair_id", "category", "entity_type", "timeframe", "side",
                   "sentiment", "sentence_en", "ru", "uk"]
TIMEFRAMES = {"Past", "Present", "Future"}
SIDES = {"ua", "ru"}
SENTIMENTS = {"pos", "neg"}
SIDE_ADJ = {"ua": "Ukrainian", "ru": "Russian"}

PAST_RE = re.compile(r"^(Last (year|month|winter|spring|summer|autumn),|"
                     r".* ago,|Earlier this year,|During the previous \w+,)")
YEAR_RE = re.compile(r"^In (\d{4}),")
REFERENCE_YEAR = 2026  # overridden by --reference-year / run_manifest.json; v1.x design year
PRESENT_RE = re.compile(r"^(Today,|This (week|month|morning|afternoon|year),|Right now,|"
                        r"At present,|These days,|Currently,|Tonight,)")
FUTURE_RE = re.compile(r"^(Tomorrow,|Next (week|month|year),|Later this year,|"
                       r"In the coming \w+,|Soon,|In the near future,|By the end of the year,)")
LATIN_WORD = re.compile(r"[A-Za-z]")
SHEET_ERR = re.compile(r"#(VALUE|N/A|NAME|REF|DIV/0|NUM|NULL)[!?]?")
NAT_TOKEN = {
    ("ua", "ru"): re.compile(r"украин", re.I),
    ("ua", "uk"): re.compile(r"україн", re.I),
    ("ru", "ru"): re.compile(r"росси|русск", re.I),
    ("ru", "uk"): re.compile(r"росі|російськ", re.I),
}
CHECKS = ["C0 files", "C1 schema", "C2 design", "C3 labels", "C4 side-sym", "C5 frame-sym",
          "C6 tense", "C7 translation", "C8 unique"]


def opener(s: str) -> str:
    return s.split(",")[0] + "," if "," in s else s.split(" ")[0]


def tf_of_opener(s: str) -> str | None:
    m = YEAR_RE.match(s)
    if m:  # explicit year: Past below, Future above the reference year; the reference year itself is never used
        y = int(m.group(1))
        return "Past" if y < REFERENCE_YEAR else "Future" if y > REFERENCE_YEAR else None
    if PAST_RE.match(s):
        return "Past"
    if PRESENT_RE.match(s):
        return "Present"
    if FUTURE_RE.match(s):
        return "Future"
    return None


def load(path: Path):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    rows = list(csv.reader(text.lstrip("﻿").splitlines()))
    return bom, rows[0], rows[1:]


def validate_file(path: Path, inventory: dict[str, set[str]], fails: list, counts: dict, n_templates: int = 100,
                  english_only: bool = False):
    """Append failures as (file, check, pair_id, message); update per-check counters."""
    f = path.name
    bom, header, rows = load(path)
    n_fail_before = len(fails)

    def fail(check, pid, msg):
        fails.append((f, check, pid, msg))

    # C1 schema
    if bom:
        fail("C1 schema", "-", "file starts with a UTF-8 BOM")
    if [h.strip() for h in header] != EXPECTED_HEADER:
        fail("C1 schema", "-", f"header is {header}")
    hl = [h.strip().lower() for h in header]
    idx = {h: i for i, h in enumerate(hl)}
    has_tr = "ru" in idx and "uk" in idx

    def col(r, name):
        i = idx.get(name)
        return r[i] if i is not None and i < len(r) else ""

    recs = [{h: col(r, h) for h in EXPECTED_HEADER} for r in rows]
    counts[f]["rows"] = len(recs)

    # C2 design
    by_pid = collections.defaultdict(list)
    for r in recs:
        by_pid[r["pair_id"]].append(r)
    counts[f]["pairs"] = len(by_pid)
    if len(by_pid) != n_templates:
        fail("C2 design", "-", f"{len(by_pid)} pair_ids (expected {n_templates})")
    cells_ok = 0
    for pid, grp in by_pid.items():
        cells = collections.Counter((r["timeframe"], r["side"], r["sentiment"]) for r in grp)
        expected = {(t, s, p) for t in TIMEFRAMES for s in SIDES for p in SENTIMENTS}
        if len(grp) != 12 or set(cells) != expected or any(v != 1 for v in cells.values()):
            fail("C2 design", pid, f"{len(grp)} rows, cells={sorted(cells.items())}")
        else:
            cells_ok += 1
    counts[f]["pairs_complete"] = cells_ok

    # C3 labels
    cats = {r["category"] for r in recs}
    if len(cats) != 1:
        fail("C3 labels", "-", f"multiple category labels {cats}")
    cat = next(iter(cats)) if cats else ""
    slug = re.sub(r"[^a-z0-9]+", "_", cat.lower()).strip("_")
    if slug and slug != path.stem.split("-", 1)[-1]:
        fail("C3 labels", "-", f"category '{cat}' does not match file name")
    counts[f]["category"] = cat
    for pid, grp in by_pid.items():
        ents = {r["entity_type"] for r in grp}
        if len(ents) != 1:
            fail("C3 labels", pid, f"entity_type varies within pair: {ents}")
    ents_all = {r["entity_type"] for r in recs}
    counts[f]["entities"] = len(ents_all)
    missing_inv = ents_all - inventory.get(cat, set())
    if missing_inv:
        fail("C3 labels", "-", f"entity types not in entity_inventory.csv: {sorted(missing_inv)[:5]}")
    extra_inv = inventory.get(cat, set()) - ents_all
    if extra_inv:
        fail("C3 labels", "-", f"inventory lists unused entity types: {sorted(extra_inv)[:5]}")
    for r in recs:
        if r["timeframe"] not in TIMEFRAMES or r["side"] not in SIDES or r["sentiment"] not in SENTIMENTS:
            fail("C3 labels", r["pair_id"], f"bad label {r['timeframe']}/{r['side']}/{r['sentiment']}")

    # C4 side symmetry
    sym_ok = 0
    by_cell = collections.defaultdict(dict)
    for r in recs:
        by_cell[(r["pair_id"], r["timeframe"], r["sentiment"])][r["side"]] = r
    for (pid, tf, st), d in by_cell.items():
        if "ua" in d and "ru" in d:
            a = d["ua"]["sentence_en"].replace("Ukrainian", "X")
            b = d["ru"]["sentence_en"].replace("Russian", "X")
            if a == b and "X" in a:
                sym_ok += 1
            else:
                fail("C4 side-sym", pid, f"{tf}/{st}: '{d['ua']['sentence_en'][:60]}' vs '{d['ru']['sentence_en'][:60]}'")
    counts[f]["side_pairs"] = len(by_cell)
    counts[f]["side_pairs_ok"] = sym_ok

    # C5 frame symmetry (pos vs neg)
    frame_ok = 0
    by_frame = collections.defaultdict(dict)
    for r in recs:
        by_frame[(r["pair_id"], r["timeframe"], r["side"])][r["sentiment"]] = r
    for (pid, tf, sd), d in by_frame.items():
        if "pos" in d and "neg" in d:
            p, n = d["pos"]["sentence_en"], d["neg"]["sentence_en"]
            if sd not in SIDE_ADJ:   # invalid side already failed C3; keep validating instead of crashing
                fail("C5 frame-sym", pid, f"{tf}/{sd}: unknown side value, actor check skipped")
                continue
            actor = f"the {SIDE_ADJ[sd]} {d['pos']['entity_type']}"
            if opener(p) == opener(n) and actor in p and actor in n:
                frame_ok += 1
            else:
                fail("C5 frame-sym", pid, f"{tf}/{sd}: opener/actor mismatch ('{p[:50]}' | '{n[:50]}')")
    counts[f]["frames"] = len(by_frame)
    counts[f]["frames_ok"] = frame_ok

    # C6 tense
    tense_ok = 0
    for r in recs:
        s, tf = r["sentence_en"], r["timeframe"]
        if r["side"] not in SIDE_ADJ:   # invalid side already failed C3
            fail("C6 tense", r["pair_id"], f"{tf}: unknown side value, verb check skipped")
            continue
        ok = tf_of_opener(s) == tf
        actor_will = f"the {SIDE_ADJ[r['side']]} {r['entity_type']} will "
        if tf == "Future":
            ok = ok and actor_will in s
        else:
            ok = ok and actor_will not in s
        if ok:
            tense_ok += 1
        else:
            fail("C6 tense", r["pair_id"], f"{tf}: '{s[:70]}'")
    counts[f]["tense_ok"] = tense_ok

    # C7 translation
    tr_ok = 0
    if english_only:
        tr_ok = len(recs)  # skipped by request (English-only run)
    elif not has_tr:
        fail("C7 translation", "-", "ru/uk columns missing")
    else:
        for r in recs:
            errs = []
            for lang in ("ru", "uk"):
                v = r[lang]
                if not v.strip():
                    errs.append(f"{lang} empty")
                    continue
                if SHEET_ERR.search(v):
                    errs.append(f"{lang} spreadsheet error '{v}'")
                m = LATIN_WORD.search(v)
                if m:
                    errs.append(f"{lang} Latin residue '{m.group()}'")
                if not NAT_TOKEN[(r["side"], lang)].search(v):
                    errs.append(f"{lang} nationality token missing")
                ym = re.match(r"^In (20\d\d),", r["sentence_en"])
                if ym and ym.group(1) not in v:
                    errs.append(f"{lang} year {ym.group(1)} missing")
            if r["ru"] and r["ru"] == r["uk"]:
                errs.append("ru == uk")
            if errs:
                fail("C7 translation", r["pair_id"], f"{r['timeframe']}/{r['side']}/{r['sentiment']}: " + "; ".join(errs))
            else:
                tr_ok += 1
    counts[f]["translation_ok"] = tr_ok

    # C8 uniqueness (within file)
    for lang in ("sentence_en", "ru", "uk"):
        c = collections.Counter(r[lang] for r in recs if r[lang])
        dups = {k: v for k, v in c.items() if v > 1}
        for k, v in dups.items():
            pids = sorted({r["pair_id"] for r in recs if r[lang] == k})
            fail("C8 unique", ",".join(pids), f"{lang} duplicated x{v}: '{k[:70]}'")
    counts[f]["unique_en"] = len({r["sentence_en"] for r in recs})
    counts[f]["fails"] = len(fails) - n_fail_before
    return recs


def expected_file_names(spec: str | None) -> set[str]:
    """C0: the category files a release must contain (default: the 22 categories of the generator config)."""
    if spec == "none":
        return set()
    if spec:
        # The generator supplies the expected categories as a comma-separated
        # list. Parse that form before constructing a Path: with all 22 long
        # filenames, Path.exists() can otherwise raise ENAMETOOLONG.
        if "," in spec:
            return {x.strip() for x in spec.split(",") if x.strip()}
        p = Path(spec)
        if p.is_file():
            return {l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}
        return {spec.strip()}
    cfg = ROOT / "generator" / "generator_config.json"
    if not cfg.exists():
        return set()
    cats = json.loads(cfg.read_text(encoding="utf-8"))["categories"]
    return {f"{c['id']}-{c['slug']}.csv" for c in cats}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DATA))
    ap.add_argument("--report", default=None, help="default: reports/<version>/validation_report.md (see --version)")
    ap.add_argument("--version", default="v1.1", help="report subdirectory")
    ap.add_argument("--n-templates", type=int, default=100, help="expected number of pair_ids per file")
    ap.add_argument("--reference-year", type=int, default=None, help="year that separates Past from Future year openers (default: run_manifest.json in --dir, else 2026)")
    ap.add_argument("--english-only", action="store_true", help="skip the translation checks (C7); the ru/uk columns may be empty")
    ap.add_argument("--files", default=None, help="comma-separated expected category file names, or a path to a text file with one name per line; default: the 22 categories of generator/generator_config.json; 'none' disables C0")
    args = ap.parse_args()
    d = Path(args.dir)
    inventory: dict[str, set[str]] = collections.defaultdict(set)
    inv_path = d / "entity_inventory.csv"
    if inv_path.exists():
        with inv_path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                inventory[r["category"]].add(r["entity"])
    global REFERENCE_YEAR
    manifest = d / "run_manifest.json"
    if args.reference_year:
        REFERENCE_YEAR = args.reference_year
    elif manifest.exists():
        try:
            REFERENCE_YEAR = int(json.loads(manifest.read_text(encoding="utf-8")).get("reference_year") or REFERENCE_YEAR)
        except (ValueError, json.JSONDecodeError):
            pass
    files = sorted(p for p in d.glob("*.csv") if re.match(r"^\d+-", p.name))
    fails: list = []
    expected_files = expected_file_names(args.files)
    for name in sorted(expected_files - {p.name for p in files}):
        fails.append((name, "C0 files", "-", "expected category file missing"))
    for p in files:
        if expected_files and p.name not in expected_files:
            fails.append((p.name, "C0 files", "-", "unexpected category file (not in the expected list)"))
    counts: dict = collections.defaultdict(dict)
    all_en: dict[str, list[str]] = collections.defaultdict(list)
    for p in files:
        recs = validate_file(p, inventory, fails, counts, args.n_templates, args.english_only)
        for r in recs:
            all_en[r["sentence_en"]].append(p.name)
    cross = {k: v for k, v in all_en.items() if len(v) > 1}
    for k, v in cross.items():
        fails.append(("(global)", "C8 unique", "-", f"sentence_en appears in {sorted(set(v))}: '{k[:70]}'"))

    total_rows = sum(c["rows"] for c in counts.values())
    lines = [f"# Automated validation report for `{d}`", "", f"Reference year for year openers: {REFERENCE_YEAR}" + ("; translation checks skipped (--english-only)" if args.english_only else ""), "",
             f"Files: {len(files)}  Rows: {total_rows}  Failures: {len(fails)}", "",
             "| File | Rows | pair_ids | Complete pairs (12/12) | Side-sym. EN pairs | Frame-sym. (pos/neg) | Tense-consistent rows | Translation-consistent rows | Unique EN | Failures |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for p in files:
        c = counts[p.name]
        lines.append(f"| {p.name} | {c['rows']} | {c['pairs']} | {c['pairs_complete']}/{c['pairs']} | "
                     f"{c['side_pairs_ok']}/{c['side_pairs']} | {c['frames_ok']}/{c['frames']} | "
                     f"{c['tense_ok']}/{c['rows']} | {c['translation_ok']}/{c['rows']} | {c['unique_en']}/{c['rows']} | {c['fails']} |")
    tot = lambda k: sum(c[k] for c in counts.values())  # noqa: E731
    lines.append(f"| **Total** | {total_rows} | {tot('pairs')} | {tot('pairs_complete')}/{tot('pairs')} | "
                 f"{tot('side_pairs_ok')}/{tot('side_pairs')} | {tot('frames_ok')}/{tot('frames')} | "
                 f"{tot('tense_ok')}/{total_rows} | {tot('translation_ok')}/{total_rows} | {tot('unique_en')}/{total_rows} | {len(fails)} |")
    lines += ["", f"Cross-file duplicated English sentences: {len(cross)}", ""]
    by_check = collections.Counter(x[1] for x in fails)
    lines += ["## Failures by check", ""] + [f"- {c}: {by_check.get(c, 0)}" for c in CHECKS] + [""]
    if fails:
        lines += ["## Failure list", "", "| File | Check | pair_id | Detail |", "|---|---|---|---|"]
        lines += [f"| {a} | {b} | {c} | {dd.replace('|', '/')} |" for a, b, c, dd in fails]
    if args.report is None:
        args.report = str(REPORTS / args.version / "validation_report.md")
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4 + len(files) + 3]))
    print(f"\nReport written to {args.report}; {len(fails)} failure(s).")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
