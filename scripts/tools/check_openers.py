#!/usr/bin/env python3
"""Check that every translation uses the canonical temporal opener.

The canonical mapping is shared with the full validator. Run from the repository as:
    python3 dataset/tools/check_openers.py --dir dataset/data/v1.1
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
from pathlib import Path

from openers_canon import CANON


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_DATA = ROOT / "data" / "v1.1"


def expected(english_opener: str, lang: str) -> list[str]:
    """Return the one prescribed rendering, including dynamic year openers."""
    year = re.fullmatch(r"In (20\d\d)", english_opener)
    if year:
        value = f"В {year.group(1)} году" if lang == "ru" else f"У {year.group(1)} році"
        return [value]
    pair = CANON.get(english_opener)
    if pair is None:
        return []
    return [pair[0] if lang == "ru" else pair[1]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(DEFAULT_DATA))
    args = parser.parse_args()

    totals: collections.Counter[tuple[str, str]] = collections.Counter()
    failures: collections.Counter[tuple[str, str]] = collections.Counter()
    variants: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(collections.Counter)

    for path in sorted(Path(args.dir).glob("[0-9]*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                english_opener = row["sentence_en"].split(",", 1)[0]
                for lang in ("ru", "uk"):
                    translation = row[lang]
                    if not translation:
                        continue
                    totals[(path.name, lang)] += 1
                    prescribed = expected(english_opener, lang)
                    if not prescribed or not any(translation.startswith(item) for item in prescribed):
                        failures[(path.name, lang)] += 1
                        variants[(english_opener, lang)][" ".join(translation.split()[:3])] += 1

    print(f"{'file':42s} ru_bad/total   uk_bad/total")
    for filename in sorted({key[0] for key in totals}):
        print(
            f"{filename:42s} {failures[(filename, 'ru')]:4d}/{totals[(filename, 'ru')]:5d}   "
            f"{failures[(filename, 'uk')]:4d}/{totals[(filename, 'uk')]:5d}"
        )
    ru_bad = sum(value for key, value in failures.items() if key[1] == "ru")
    uk_bad = sum(value for key, value in failures.items() if key[1] == "uk")
    ru_total = sum(value for key, value in totals.items() if key[1] == "ru")
    uk_total = sum(value for key, value in totals.items() if key[1] == "uk")
    print(f"TOTAL ru {ru_bad}/{ru_total}  uk {uk_bad}/{uk_total}")

    print("\nunexpected openers (English opener, language): variants")
    for key, counts in sorted(variants.items(), key=lambda item: -sum(item[1].values()))[:25]:
        print(f"  {key}: {dict(counts.most_common(4))}")

    bad_count = sum(failures.values())
    status = "FAIL" if bad_count else "OK"
    print(f"\nRESULT: {bad_count} sentence(s) with a non-prescribed opener rendering — {status}")
    return 1 if bad_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
