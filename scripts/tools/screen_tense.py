#!/usr/bin/env python3
"""Deterministic screen for the 'second verb keeps the present tense' defect.

The detector kept_present_verb() is shared with the generator (single implementation).

For every template (pair_id) the positive and negative frames of the three
timeframes are compared word by word. In a correct template the Past and Future
frames differ from the Present frame only in the main verb group. A present-tense
verb that survives unchanged in the Past or Future frame *after* a coordinator
("and", "but", "while", "then") or a relative pronoun ("that", "which", "who")
is the defect found by the annotators, e.g.
  Past:   "... investigated evidence but manipulates conclusions"
  Future: "... will accuse a unit of looting and urges an inquiry"
  Past:   "... conducted a patrol that harasses residents"

Method: tokenise the Present frame; for every token that looks like a 3rd-person
present verb (ends in -s/-es, not a plural noun heuristically: preceded by
and/but/while/then/that/which/who, or by a noun phrase head followed by
that/which/who within the clause) check whether the identical token occurs at
the same relative position in the Past and Future frames. If it does, the
template is a candidate. Candidates are listed with the three frames for manual
confirmation; no data are changed.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # dataset code root (src/v1 in the workspace, dataset/ on GitHub)
DEFAULT_DATA = next((p for p in (ROOT / "data" / "v1.1", ROOT.parent.parent / "data" / "v1") if p.exists()), ROOT / "data" / "v1.1")  # data/v1.1 inside the repository, else the workspace layout; or pass --dir
REPORTS = ROOT / "reports"


TRIGGERS = {"and", "but", "while", "then", "that", "which", "who", "yet", "or"}
SPEECH = {"said", "says", "say", "stated", "states", "state", "claimed", "claims", "claim", "announced", "announces",
          "announce", "declared", "declares", "declare", "warned", "warns", "warn", "insisted", "insists", "insist",
          "argued", "argues", "argue", "noted", "notes", "note", "added", "adds", "add", "admitted", "admits", "admit",
          "denied", "denies", "deny", "confirmed", "confirms", "confirm", "promised", "promises", "promise",
          "stressed", "stresses", "stress", "demanded", "demands", "demand", "acknowledged", "acknowledges",
          "acknowledge", "reported", "reports", "report", "explained", "explains", "explain", "asserted", "asserts",
          "assert", "emphasized", "emphasizes", "emphasize", "suggested", "suggests", "suggest"}
VERB_STEMS: set[str] = {"use", "make", "take", "give", "put", "keep", "leave", "set", "hold", "bring", "cause", "create",
                        "lead", "allow", "force", "block", "hit", "cut", "let", "get", "run", "send", "seek", "show",
                        "tell", "pay", "buy", "sell", "see", "go", "come", "do", "have", "meet", "win", "lose", "hurt"}


_LEX = Path(__file__).resolve().parent / "verb_lexicon.txt"
if _LEX.exists():  # stems derived from the v1.1 release, so the screen works without the release data
    VERB_STEMS.update(l.strip() for l in _LEX.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))


def tokens(s: str) -> list[str]:
    return re.findall(r"[A-Za-z'{}_-]+", s)


VERBAL_SUFFIX = re.compile(r"(izes|ises|ifies|ates)$")


def looks_verbal(w: str) -> bool:
    """Lexicon membership, or a clearly verbal derivational suffix (covers novel verbs such as
    'mischaracterizes' that no release or run has used before)."""
    return any(st in VERB_STEMS for st in stem_of_3sg(w)) or bool(VERBAL_SUFFIX.search(w.lower()) and len(w) > 6)


def stem_of_3sg(w: str) -> list[str]:
    """Possible base forms of a 3rd-person-singular present verb."""
    w = w.lower()
    out = []
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    if w.endswith("es"):
        out.append(w[:-2])
    if w.endswith("s"):
        out.append(w[:-1])
    return out


def build_verb_lexicon(frames_future: list[str], all_frames: list[str]) -> None:
    """Verb stems = words after 'will' in future frames + stems of -ed/-ied/-ing forms anywhere."""
    for f in frames_future:
        toks = [t.lower() for t in tokens(f)]
        for i, t in enumerate(toks[:-1]):
            if t == "will":
                VERB_STEMS.add(toks[i + 1])
                # coordinated bare verbs share the auxiliary: "will accuse X and demand Y"
                for j in range(i + 2, len(toks) - 1):
                    if toks[j] in ("and", "but", "or", "then") and toks[j + 1] not in ("the", "a", "an"):
                        VERB_STEMS.add(toks[j + 1])
    for f in all_frames:
        for t in (x.lower() for x in tokens(f)):
            if t.endswith("ied") and len(t) > 4:
                VERB_STEMS.add(t[:-3] + "y")
            elif t.endswith("ed") and len(t) > 4:
                VERB_STEMS.add(t[:-2])          # harass-ed, destroy-ed
                VERB_STEMS.add(t[:-1])          # manipulate-d, urge-d
                if len(t) > 5 and t[-3] == t[-4]:
                    VERB_STEMS.add(t[:-3])      # stopp-ed -> stop
            elif t.endswith("ing") and len(t) > 5:
                VERB_STEMS.add(t[:-3])          # harass-ing
                VERB_STEMS.add(t[:-3] + "e")    # manipulat-ing -> manipulate


def present_verbs(pres_toks: list[str]) -> list[tuple[int, str]]:
    """Indices of tokens that are 3sg present verbs (by lexicon) introduced by a coordinator/relative
    pronoun and not inside a that-clause governed by a speech verb."""
    out = []
    low = [t.lower() for t in pres_toks]
    for i, w in enumerate(low):
        if not w.endswith("s") or w.endswith("ss") or len(w) < 4:
            continue
        if not looks_verbal(w):
            continue
        window = low[max(0, i - 3):i]
        if not any(x in TRIGGERS for x in window):
            continue
        # reported speech: a speech verb followed by "that" anywhere before -> content clause, legitimate present
        if any(low[j] in SPEECH and j + 1 < len(low) and low[j + 1] == "that" for j in range(0, i)):
            continue
        out.append((i, pres_toks[i]))
    return out


def kept_present_verb(pres: list[str], past: list[str], fut: list[str]) -> str | None:
    """The single shared detector (used by this screen and by generator/generate_dataset.py): a 3sg present
    verb after a coordinator/relative pronoun that survives unchanged in the past frame (or, for a coordinated
    verb, in the past or future frame). Noun coordinations ('lawsuits and arrests') are skipped; inside a reported
    content clause ('says that the plan which allows ...') a relative-clause verb may stay in the present, but a
    coordinated verb after the clause belongs to the actor ('said that ... and urges') and must be conjugated.
    After a relative pronoun the present is normal English in the future frame ('will carry out an attack that
    hits'), so only the past frame is checked there."""
    low = [w.lower() for w in pres]
    for i, w in enumerate(low):
        if i == 0 or not w.endswith("s") or w.endswith("ss") or len(w) < 4 or low[i - 1] not in TRIGGERS:
            continue
        if low[i - 1] in ("and", "or") and i >= 2 and low[i - 2].endswith("s"):
            continue  # plural-noun coordination
        if not looks_verbal(w):
            continue
        coordinated = low[i - 1] in ("and", "but", "or", "then", "yet", "while")
        if not coordinated and any(low[j] in SPEECH and low[j + 1] == "that" for j in range(0, i - 1)):
            continue
        kept_in = (past, fut) if coordinated else (past,)
        if any(pres[i] in fr for fr in kept_in):
            return pres[i]
    return None


def main() -> int:
    d = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATA)
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else REPORTS / "v1.1" / "tense_screen.csv")
    hits = []
    n_templates = 0
    files = sorted(d.glob("[0-9]*.csv"))
    fut_frames, all_frames = [], []
    for p in files:
        with p.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            if r["side"] == "ua":
                all_frames.append(r["sentence_en"])
                if r["timeframe"] == "Future":
                    fut_frames.append(r["sentence_en"])
    build_verb_lexicon(fut_frames, all_frames)
    for p in files:
        with p.open(encoding="utf-8") as fh:
            recs = list(csv.DictReader(fh))
        by: dict[str, dict] = {}
        for r in recs:
            if r["side"] != "ua":
                continue
            by.setdefault(r["pair_id"], {})[(r["sentiment"], r["timeframe"])] = r["sentence_en"]
        for pid, fr in by.items():
            n_templates += 1
            for st in ("pos", "neg"):
                pres = tokens(fr[(st, "Present")].split(",", 1)[-1])
                past = tokens(fr[(st, "Past")].split(",", 1)[-1])
                fut = tokens(fr[(st, "Future")].split(",", 1)[-1])
                hit = kept_present_verb(pres, past, fut)
                found = [hit] if hit else []
                if found:
                    hits.append({"file": p.name, "pair_id": pid, "sentiment": st, "suspect_tokens": ";".join(found),
                                 "past": fr[(st, "Past")], "present": fr[(st, "Present")], "future": fr[(st, "Future")]})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(hits[0].keys()) if hits else ["file"])
        w.writeheader()
        w.writerows(hits)
    tpl = {(h["file"], h["pair_id"]) for h in hits}
    print(f"templates screened: {n_templates}; candidate frames: {len(hits)}; candidate templates: {len(tpl)}")
    byfile = {}
    for f, pid in tpl:
        byfile[f] = byfile.get(f, 0) + 1
    for f, n in sorted(byfile.items()):
        print(f"  {f}: {n}")
    print(f"written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
