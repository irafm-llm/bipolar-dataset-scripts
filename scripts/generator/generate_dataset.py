#!/usr/bin/env python3
"""Reproducible, API-based generator for the MIRROR-EN-UA-RU dataset.

Replaces the interactive ChatGPT session used for version 1.0 with a scripted
pipeline that talks to an LLM through the OpenRouter API (OpenAI-compatible
chat-completions endpoint; any model available on OpenRouter can be used).
The user only has to provide an API key (environment variable
OPENROUTER_API_KEY or --api-key).

Pipeline per category (see prompts/*.txt for the exact prompts)
  1. entities   the model proposes role nouns for the category (or an existing
                entity_inventory.csv is reused with --entities inventory);
                proposals are filtered by rule (singular role nouns, no names,
                no nationality/place words, no gender-marked roles)
  2. templates  the model returns scenario templates as JSON: positive and
                negative frames in past/present/future with the slots {TIME},
                {SIDE_ADJ}, {ENTITY}; every template is checked (slot
                structure, 'will' only in the future frame, tense variants
                identical apart from the verb group, no coordinated/relative
                verb left in the present tense in past/future frames
                (screen_tense.py), forbidden words, length, pos != neg,
                scenario not seen before in ANY category, exactly or by
                token-set Jaccard >= 0.9) and rejected templates are replaced
                in further rounds until --n-templates valid, distinct scenarios
                exist
  3. expansion  performed IN CODE, not by the model: entity type and temporal
                openers are assigned deterministically (seeded RNG, balanced
                over the opener sets) and the 2 sides x 2 sentiments x
                3 timeframes = 12 rows are written
  4. translate  (optional, --translate) the six Ukrainian-side sentences of a
                template are translated in one request; the Russian-side
                sentences are derived by controlled substitution of the
                nationality adjective; every translation is checked (nationality
                adjective, no Latin letter, year kept, prescribed rendering of the
                temporal opener from check_openers.py, ru != uk)
  5. validate   validate_dataset.py and check_duplicates.py are run on the
                output directory

Every API call is cached (<out>/generator_cache/<sha256 of request>.json) so that an
interrupted run resumes without repeating calls, and logged to
generation_log.jsonl (model, parameters, usage, cost, latency). A
run_manifest.json records model id, seed, temperature, command line, versions
and token totals. Decoding is deterministic as far as the provider allows
(temperature 0, seed; OpenRouter forwards `seed` to providers that support it).
Entity/opener assignment uses one RNG per category seeded from --seed and the
category id, so a run restricted with --categories reproduces the assignment
of the full run.

Usage
  export OPENROUTER_API_KEY=sk-or-...
  python3 generator/generate_dataset.py --out ../../data/v2 --model openai/gpt-5.4 --seed 42 --translate
  python3 generator/generate_dataset.py --out /tmp/test --categories 01,13 --n-templates 10 --mock       # offline test
  python3 generator/generate_dataset.py --out /tmp/repro --from-templates ../../data/v1/templates.csv    # re-expand existing templates, no API
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # dataset code root
DEFAULT_DATA = next((p for p in (ROOT / "data" / "v1.1", ROOT.parent.parent / "data" / "v1") if p.exists()), ROOT / "data" / "v1.1")
sys.path.insert(0, str(HERE.parent / "tools"))
import check_openers as _openers  # noqa: E402  prescribed RU/UK renderings of the temporal openers
import screen_tense as _tense  # noqa: E402  deterministic screen for a second verb left in the present tense

GEN = HERE
CFG = json.loads((GEN / "generator_config.json").read_text(encoding="utf-8"))


def resolve_openers(cfg: dict, reference_year: int | None = None) -> dict:
    """Openers with '{Y+k}' / '{Y-k}' placeholders are resolved against the reference year of the dataset
    (config 'reference_year', overridable with --reference-year) so that year openers do not age into the
    wrong timeframe; the year used is recorded in the run manifest."""
    y = int(reference_year or cfg.get("reference_year") or datetime.now(timezone.utc).year)
    def sub(o: str) -> str:
        return re.sub(r"\{Y([+-]\d+)?\}", lambda m: str(y + int(m.group(1) or 0)), o)
    return {tf: [sub(o) for o in ops] for tf, ops in cfg["openers"].items()}


OPENERS = resolve_openers(CFG)
PROMPTS = {p.stem: p.read_text(encoding="utf-8") for p in (GEN / "prompts").glob("*.txt")}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GENERATOR_OUTPUT = re.compile(r"^(\d+-[a-z_]+\.csv|entity_inventory\.csv|templates(_generated)?\.csv|templates_summary\.md|"
                              r"run_manifest\.json|generation_log\.jsonl|validation_report\.md|duplicates_(report\.md|near\.csv)|opener_check\.txt)$")
FIELDS = ["pair_id", "category", "entity_type", "timeframe", "side", "sentiment", "sentence_en", "ru", "uk"]
TF = ["Past", "Present", "Future"]
SLOT_PREFIX = "{TIME} the {SIDE_ADJ} {ENTITY} "
FORBIDDEN = re.compile(CFG["forbidden_in_frames_regex"], re.I)
ENT_FORBIDDEN = re.compile(CFG["entity_filter"]["forbidden_regex"], re.I)
RU_ADJ, UK_ADJ, LATIN = re.compile(r"украинск", re.I), re.compile(r"українськ", re.I), re.compile(r"[A-Za-z]")
NEAR_DUP_JACCARD = 0.9
MIN_WORDS, MAX_WORDS = 9, 34  # prompt asks for 10-30; one word of tolerance below, four above
MAX_VERB_DIFFS = 3  # tokens that may differ between the tense variants of a frame (main verb + coordinated verbs)
PLURAL_FINAL_OK = {"press", "affairs", "operations", "relations", "services", "resources", "communications", "logistics",
                   "statistics", "ethics", "customs", "records", "standards", "rights", "analytics"}


# --------------------------------------------------------------------------- #
# LLM backends
# --------------------------------------------------------------------------- #
class TruncatedResponse(RuntimeError):
    """The model hit max_tokens or did not finish normally; the answer is not cached."""


class CostLimitExceeded(RuntimeError):
    """--max-cost-usd reached; the run stops (cached calls are free and still served)."""


class OpenRouterBackend:
    """Minimal OpenRouter client (stdlib only) with caching, retries and logging."""

    def __init__(self, model: str, api_key: str, temperature: float, seed: int, cache_dir: Path,
                 log_path: Path, max_tokens: int = 16000, referer: str = "https://github.com/irafm-llm/bipolar",
                 reasoning: str = "auto", max_cost_usd: float | None = None):
        self.model, self.api_key, self.temperature, self.seed = model, api_key, temperature, seed
        self.max_cost_usd = max_cost_usd
        self._inflight = 0
        self._max_call_cost = 0.0
        self.reasoning = reasoning
        self._lock = threading.Lock()
        self._json_mode_ok = True
        self.cache_dir, self.log_path, self.max_tokens, self.referer = cache_dir, log_path, max_tokens, referer
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider_models: set = set()  # exact model ids reported by the provider
        self.usage = Counter()          # tokens/cost of calls made in this run
        self.usage_cached = Counter()   # tokens/cost of calls answered from the cache (earlier runs)

    STAGE_MAX_TOKENS = {"entities": 2000, "translate": 4000}  # templates: self.max_tokens (batch of 20 needs ~8k)

    def _check_cost_limit(self) -> None:
        """Hard cap on paid spending. Called under self._lock, after the cache branch (cached calls are
        free and always served). In-flight parallel calls are reserved at the highest call cost observed
        so far, so with --workers N the cap can be exceeded by at most N-1 first calls before any usage
        is known, and by at most one reserved-underestimate afterwards."""
        if self.max_cost_usd is None:
            return
        projected = self.usage["cost_usd"] + self._inflight * self._max_call_cost
        if projected >= self.max_cost_usd:
            raise CostLimitExceeded(
                f"cost limit {self.max_cost_usd} USD reached ({self.usage['cost_usd']:.4f} USD recorded, "
                f"{self._inflight} call(s) in flight); cached calls are still served")

    def chat(self, system: str, user: str, stage: str, category: str, json_object: bool = True) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": min(self.max_tokens, self.STAGE_MAX_TOKENS.get(stage, self.max_tokens)),
            "usage": {"include": True},
        }
        if json_object and self._json_mode_ok:
            body["response_format"] = {"type": "json_object"}
        if self.reasoning == "off":
            body["reasoning"] = {"enabled": False}
        key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cache = self.cache_dir / f"{key}.json"
        if cache.exists():
            rec = json.loads(cache.read_text(encoding="utf-8"))
            self._log(rec | {"cached": True})
            with self._lock:
                self._add_usage(self.usage_cached, rec.get("usage") or {})
                if rec.get("provider_model"):
                    self.provider_models.add(str(rec["provider_model"]))
            return rec["content"]
        with self._lock:
            self._check_cost_limit()
            self._inflight += 1
        try:
            return self._chat_uncached(body, key, cache, stage, category, json_object)
        finally:
            with self._lock:
                self._inflight -= 1

    def _chat_uncached(self, body: dict, key: str, cache: Path, stage: str, category: str, json_object: bool) -> str:
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        req = urllib.request.Request(
            OPENROUTER_URL, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "HTTP-Referer": self.referer, "X-Title": "MIRROR-EN-UA-RU generator"})
        delay = 5.0
        for attempt in range(6):
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    data = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:300]
                if e.code == 400 and "response_format" in body and "response_format" in msg.lower():
                    # provider does not support JSON mode: drop it for the rest of the run and retry once
                    print("    provider rejects response_format=json_object; continuing without it", file=sys.stderr)
                    self._json_mode_ok = False
                    return self.chat(system, user, stage, category, json_object)
                if e.code in (408, 409, 429, 500, 502, 503, 504) and attempt < 5:
                    print(f"    HTTP {e.code}, retry in {delay:.0f}s: {msg}", file=sys.stderr)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(f"OpenRouter HTTP {e.code}: {msg}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 5:
                    print(f"    network error, retry in {delay:.0f}s: {e}", file=sys.stderr)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error']}")
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason")
        usage = data.get("usage", {}) or {}
        # billed cost is recorded FIRST, so truncated/malformed (but paid) responses count toward --max-cost-usd
        with self._lock:
            self._add_usage(self.usage, usage)
            self._max_call_cost = max(self._max_call_cost, float(usage.get("cost", 0) or 0))
            if data.get("model"):
                self.provider_models.add(str(data["model"]))
        if finish != "stop":
            raise TruncatedResponse(f"response did not finish normally (finish_reason={finish!r}, {int(usage.get('completion_tokens', 0) or 0)} "
                                    f"completion tokens, {stage}/{category}); not cached — increase --max-tokens or reduce --batch")
        if json_object:
            try:
                parse_json(content)
            except json.JSONDecodeError as e:
                raise TruncatedResponse(f"response is not a JSON object ({stage}/{category}); not cached: {e.msg}") from e
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "stage": stage, "category": category,
               "model": self.model, "provider_model": data.get("model"), "response_id": data.get("id"),
               "temperature": self.temperature, "seed": self.seed, "prompt_sha256": key,
               "latency_s": round(time.time() - t0, 2), "usage": usage, "content": content,
               "finish_reason": finish}
        write_atomic(cache, json.dumps(rec, ensure_ascii=False, indent=1))
        self._log(rec | {"cached": False})
        return content

    @staticmethod
    def _add_usage(counter: Counter, usage: dict) -> None:
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            counter[k] += int(usage.get(k, 0) or 0)
        counter["reasoning_tokens"] += int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0)
        counter["cost_usd"] += float(usage.get("cost", 0) or 0)
        counter["calls"] += 1

    def _log(self, rec: dict) -> None:
        with self._lock, self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in rec.items() if k != "content"}, ensure_ascii=False) + "\n")


class MockBackend:
    """Offline backend for tests: answers from an existing release (templates.csv,
    entity_inventory.csv, category CSVs with translations). It exercises the
    whole pipeline (prompt building, JSON parsing, validation, retries) without
    network access. Deliberately injects a few defective items to test the
    rejection logic. Translations are pseudo-Cyrillic placeholders, not real
    Russian/Ukrainian."""

    def __init__(self, release_dir: Path):
        self.release = release_dir
        self.usage = Counter()
        with (release_dir / "templates.csv").open(encoding="utf-8") as fh:
            self.templates = list(csv.DictReader(fh))
        self.inv = defaultdict(list)
        with (release_dir / "entity_inventory.csv").open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                self.inv[r["category"]].append(r["entity"])
        self.served: Counter = Counter()
        self.tr: dict[str, tuple[str, str]] = {}

    def chat(self, system: str, user: str, stage: str, category: str, json_object: bool = True) -> str:
        if stage == "entities":
            ents = self.inv[category][:60] + ["Vladimir Putin", "Ukrainian soldier", "woman"]  # filtered out
            return json.dumps({"entity_types": ents})
        if stage == "templates":
            n = int(re.search(r"Produce (\d+) NEW", user).group(1))
            pool = [t for t in self.templates if t["category"] == category]
            start = self.served[category]
            out = []
            for t in pool[start:start + n]:
                out.append({"scenario": t["scenario_id"], "entity_types": [t["entity_type"]],
                            "pos": {k: t[f"pos_{k}"] for k in ("past", "present", "future")},
                            "neg": {k: t[f"neg_{k}"] for k in ("past", "present", "future")}})
            self.served[category] += n
            if start == 0 and out:  # inject defects: a frame mentioning a country and a wrong prefix
                bad = json.loads(json.dumps(out[0]))
                bad["pos"]["past"] = bad["pos"]["past"].replace("{ENTITY}", "{ENTITY} from Ukraine")
                out.append(bad)
                tense = json.loads(json.dumps(out[0]))  # second verb left in the present tense (the v1.0 defect)
                for k in ("past", "present", "future"):
                    tense["pos"][k] = tense["pos"][k].rstrip(".") + " and urges an inquiry."
                tense["scenario"] += " (tense defect)"
                out.append(tense)
                out.append({"scenario": "broken", "entity_types": ["mayor"],
                            "pos": {"past": "The mayor did X.", "present": "x", "future": "x"},
                            "neg": {"past": "x", "present": "x", "future": "x"}})
            return json.dumps({"templates": out})
        if stage == "translate":
            # pseudo-translations: deterministic Cyrillic rendering that satisfies the
            # automated checks (nationality adjective, year, Cyrillic only, ru != uk)
            sents = re.findall(r"^\d+\. (.+)$", user.split("Sentences:", 1)[1], re.M)
            ru_map = str.maketrans("abcdefghijklmnopqrstuvwxyz", "абцдефгхийклмнопкрстувшхыз")
            uk_map = str.maketrans("abcdefghijklmnopqrstuvwxyz", "абцдефгхійклмнопкрстувшхиз")
            items = []
            for i, s in enumerate(sents, 1):
                op, body = s.split(",", 1)
                body = body.replace("Ukrainian ", "").lower()
                ru_op = (_openers.expected(op.strip(), "ru") or [op])[0]
                uk_op = (_openers.expected(op.strip(), "uk") or [op])[0]
                items.append({"id": i, "ru": ru_op + " украинский " + body.translate(ru_map),
                              "uk": uk_op + " український " + body.translate(uk_map)})
            return json.dumps({"items": items}, ensure_ascii=False)
        raise ValueError(stage)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def fill(template: str, **kw) -> str:
    """Substitute {name} placeholders for the given keys only (prompts contain literal braces)."""
    for k, v in kw.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def read_dotenv_key() -> str | None:
    """Read ROUTER= or OPENROUTER_API_KEY= from .env (repo root, script dir or cwd) without exporting it."""
    for d in (ROOT.parent.parent, ROOT, HERE, Path.cwd()):  # repository root, code root, generator dir, cwd
        f = d / ".env"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if "=" in line and line.split("=", 1)[0].strip() in ("ROUTER", "OPENROUTER_API_KEY"):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return None


def parse_json(text: str) -> dict:
    """Extract the JSON object from a model answer; raises json.JSONDecodeError when there is none
    (or the top level is not an object), so that callers need a single except clause."""
    text = re.sub(r"```(?:json)?", "", text or "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        raise json.JSONDecodeError("no JSON object in response", text, 0)
    obj = json.loads(text[start:end])
    if not isinstance(obj, dict):
        raise json.JSONDecodeError("top-level JSON is not an object", text, 0)
    return obj


def filter_entity(e: str) -> str | None:
    e = re.sub(r"\s+", " ", str(e)).strip().strip(".,;:")
    if not e or len(e.split()) > CFG["entity_filter"]["max_words"] or ENT_FORBIDDEN.search(e):
        return None
    allowed = CFG["entity_filter"]["allowed_capitalised"]
    allowed_tokens = {t for a in allowed for t in a.split()}
    words = e.split()

    def _ok_cap(w: str) -> bool:  # "UN", "Red", and hyphenated forms such as "UN-appointed", "EU-funded"
        return w in allowed_tokens or (w.split("-", 1)[0] in allowed_tokens and w.split("-", 1)[-1].islower())

    if len(words[0]) > 1 and words[0].isupper() and not _ok_cap(words[0]):
        return None  # unknown abbreviation / organisation ("NATO liaison")
    if words[0][0].isupper() and not _ok_cap(words[0]) and (len(words) == 1 or words[1][0].islower()):
        words[0] = words[0].lower()  # sentence-case label ("President", "Defense minister"), not a name
        e = " ".join(words)
    for w in words:
        if w[0].isupper() and not _ok_cap(w):
            return None  # proper name ("Vladimir Putin", "Security Council")
    if e.endswith("s") and not e.endswith(("ss", "us", "ics")) and e.split()[-1] not in PLURAL_FINAL_OK:
        return None  # plural
    return e


def mask(frame: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s{}]", " ", frame.lower())).strip()


def seed_verb_lexicon(release_dir: Path) -> None:
    """Extend the tense screen's verb lexicon with the frames of an existing release (templates.csv), if present."""
    p = release_dir / "templates.csv"
    if not p.exists():
        return
    fut, allf = [], []
    with p.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for k in ("pos", "neg"):
                fut.append(r[f"{k}_future"])
                allf += [r[f"{k}_past"], r[f"{k}_present"], r[f"{k}_future"]]
    _tense.build_verb_lexicon(fut, allf)


kept_present_verb = _tense.kept_present_verb  # single implementation, shared with tools/screen_tense.py


def _verb_like(pres_tok: str, other_tok: str) -> bool:
    """True if the two tokens can be forms of one verb: the present token is a 3sg form (-s/-es/-ies, or an
    irregular such as has/is/does) and the other token shares its stem, ends in -ed, or is in the verb lexicon."""
    p, o = pres_tok.lower(), other_tok.lower()
    irregular = {"has": {"had", "have"}, "is": {"was", "be"}, "does": {"did", "do"}, "goes": {"went", "go"},
                 "says": {"said", "say"}, "keeps": {"kept", "keep"}, "leaves": {"left", "leave"}, "holds": {"held", "hold"},
                 "sends": {"sent", "send"}, "builds": {"built", "build"}, "leads": {"led", "lead"}, "makes": {"made", "make"},
                 "takes": {"took", "take"}, "gives": {"gave", "give"}, "meets": {"met", "meet"}, "seeks": {"sought", "seek"},
                 "brings": {"brought", "bring"}, "fights": {"fought", "fight"}, "sets": {"set"}, "puts": {"put"}, "cuts": {"cut"},
                 "hits": {"hit"}, "lets": {"let"}, "shuts": {"shut"}, "spreads": {"spread"}, "withdraws": {"withdrew", "withdraw"},
                 "forbids": {"forbade", "forbid"}, "upholds": {"upheld", "uphold"}, "withholds": {"withheld", "withhold"},
                 "sells": {"sold", "sell"}, "tells": {"told", "tell"}, "pays": {"paid", "pay"}, "loses": {"lost", "lose"},
                 "wins": {"won", "win"}, "feeds": {"fed", "feed"}, "flees": {"fled", "flee"}, "shoots": {"shot", "shoot"},
                 "stands": {"stood", "stand"}, "understands": {"understood", "understand"}, "breaks": {"broke", "break"},
                 "speaks": {"spoke", "speak"}, "drives": {"drove", "drive"}, "rises": {"rose", "rise"}, "deals": {"dealt", "deal"},
                 "lays": {"laid", "lay"}, "steals": {"stole", "steal"}, "freezes": {"froze", "freeze"}, "hides": {"hid", "hide"}}
    if p in irregular and o in irregular[p]:
        return True
    if not p.endswith("s"):
        # base form in the present after a plural subject ('measures that block' / 'blocked')
        return o in (p + "ed", p + "d", p[:-1] + "ied" if p.endswith("y") else "", p + p[-1] + "ed")
    stems = set(_tense.stem_of_3sg(p))
    if o in stems or o.rstrip("e") in {x.rstrip("e") for x in stems}:
        return True  # base form
    if o.endswith("ed") or o.endswith("ied"):
        base = {o[:-2], o[:-1], o[:-3] + "y" if o.endswith("ied") else o}
        if base & stems or any(x.rstrip("e") in {b.rstrip("e") for b in base} for x in stems):
            return True
        if len(o) > 5 and o[-3] == o[-4] and o[:-3] in stems:
            return True  # stopped -> stop
    return False


def _strip_aux(toks: list[str]) -> list[str]:
    """Drop the tense auxiliaries of the main verb group ('will', 'did/does/do' in negations) from the frame head."""
    out = list(toks)
    while out and out[0].lower() in ("will", "did", "does", "do"):
        out.pop(0)
    return out


def _frame_tokens(frame: str) -> list[str]:
    """Tokens of a frame after the slot prefix (the part the model wrote)."""
    return _tense.tokens(frame[len(SLOT_PREFIX):])


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


class SeenScenarios:
    """Scenario frames accepted so far in ALL categories: exact signature and near-duplicate (Jaccard) lookup."""

    def __init__(self) -> None:
        self.sigs: set = set()
        self.tokens: list[tuple[frozenset, str]] = []  # (token set of the masked past frames, label)

    @staticmethod
    def signature(frames: dict) -> tuple:
        return tuple(mask(frames[(s, tf)]) for s in ("pos", "neg") for tf in ("past", "present", "future"))

    @staticmethod
    def tokset(frames: dict) -> frozenset:
        return frozenset(mask(frames[("pos", "past")]).split()) | frozenset("neg:" + w for w in mask(frames[("neg", "past")]).split())

    def near(self, frames: dict) -> str | None:
        ts = self.tokset(frames)
        for other, label in self.tokens:
            if _jaccard(ts, other) >= NEAR_DUP_JACCARD:
                return label
        return None

    def add(self, frames: dict, label: str) -> None:
        self.sigs.add(self.signature(frames))
        self.tokens.append((self.tokset(frames), label))


def main_verb(frame_future: str) -> str:
    """Base form of the main verb of a frame, taken from the future variant ('{ENTITY} will [not] VERB ...')."""
    toks = _strip_aux(_frame_tokens(frame_future))
    while toks and toks[0].lower() in ("not", "never", "no", "longer"):
        toks.pop(0)
    return toks[0].lower() if toks else ""


def verbs_equivalent(v1: str, v2: str, category: str | None) -> bool:
    """Same main verb, or a pair listed as equivalent for the category in generator_config.json
    ('verb_equivalents', e.g. warn/threaten for Threaten: 'two verbs of the same event type')."""
    if v1 == v2:
        return True
    table = CFG.get("verb_equivalents", {})
    pairs = table.get(category or "", []) + table.get("*", [])
    return any({v1, v2} <= set(p) for p in pairs)


def check_template(t: dict, seen_scenarios: "SeenScenarios", category: str | None = None) -> str | None:
    """Return a rejection reason or None."""
    try:
        frames = {(s, tf): t[s][tf] for s in ("pos", "neg") for tf in ("past", "present", "future")}
    except (KeyError, TypeError):
        return "missing frames"
    for (s, tf), f in frames.items():
        if not isinstance(f, str) or not f.startswith(SLOT_PREFIX):
            return f"{s}/{tf}: frame does not start with '{SLOT_PREFIX}'"
        if f.count("{TIME}") != 1 or f.count("{SIDE_ADJ}") != 1 or f.count("{ENTITY}") != 1:
            return f"{s}/{tf}: slot count"
        if FORBIDDEN.search(f):
            return f"{s}/{tf}: forbidden word '{FORBIDDEN.search(f).group()}'"
        n = len(f.split())
        if not (MIN_WORDS <= n <= MAX_WORDS) or not f.rstrip().endswith("."):
            return f"{s}/{tf}: length/punctuation ({n} words)"
        if '"' in f:
            return f"{s}/{tf}: double quotes"
    for s in ("pos", "neg"):
        if "{ENTITY} will " not in frames[(s, "future")]:
            return f"{s}/future: missing 'will'"
        if "{ENTITY} will " in frames[(s, "past")] or "{ENTITY} will " in frames[(s, "present")]:
            return f"{s}: 'will' in past/present"
        if len({frames[(s, tf)] for tf in ("past", "present", "future")}) != 3:
            return f"{s}: tense variants identical"
        # tense variants must be word-for-word identical apart from the verb group
        past, pres, fut = (_strip_aux(_frame_tokens(frames[(s, tf)])) for tf in ("past", "present", "future"))
        if not (len(past) == len(pres) == len(fut)):
            return f"{s}: tense variants differ in length"
        for name, other in (("past", past), ("future", fut)):
            diffs = [(a, b) for a, b in zip(pres, other) if a.lower() != b.lower()]
            if len(diffs) > MAX_VERB_DIFFS:
                return f"{s}: {name} variant differs from present in {len(diffs)} tokens"
            for a, b in diffs:  # every differing token must be a verb form (present 3sg vs. past/base form)
                if not _verb_like(a, b):
                    return f"{s}: {name} variant differs from present in a non-verb token ('{a}' vs '{b}')"
        # a coordinated/relative-clause verb left in the present tense in past/future frames (v1.0 defect)
        _tense.build_verb_lexicon([frames[(s, "future")]], [frames[(s, tf)] for tf in ("past", "present", "future")])
        left = kept_present_verb(pres, past, fut)
        if left:
            return f"{s}: present-tense verb kept in past/future ('{left}')"
    if mask(frames[("pos", "past")]) == mask(frames[("neg", "past")]):
        return "pos == neg"
    vp, vn = main_verb(frames[("pos", "future")]), main_verb(frames[("neg", "future")])
    if not verbs_equivalent(vp, vn, category):
        return f"pos/neg main verbs differ ('{vp}' vs '{vn}'; add to verb_equivalents if intended)"
    if SeenScenarios.signature(frames) in seen_scenarios.sigs:
        return "duplicate scenario"
    near = seen_scenarios.near(frames)
    if near:
        return f"near-duplicate scenario (Jaccard >= {NEAR_DUP_JACCARD}) of '{near}'"
    return None


def derive_ru_side(text: str, lang: str) -> str:
    if lang == "ru":
        out = re.sub(r"украинск", "российск", text)
        out = re.sub(r"Украинск", "Российск", out)
        out = re.sub(r"Украин(ы|е)", "России", out)
        return out.replace("Украину", "Россию").replace("Украиной", "Россией").replace("Украина", "Россия")
    out = re.sub(r"українськ", "російськ", text)
    out = re.sub(r"Українськ", "Російськ", out)
    out = re.sub(r"Україн(и|і)", "Росії", out)
    return out.replace("Україну", "Росію").replace("Україною", "Росією").replace("Україна", "Росія")


def check_translation(en: str, ru: str, uk: str) -> str | None:
    en_opener = en.split(",", 1)[0].strip()
    for lang, v, adj in (("ru", ru, RU_ADJ), ("uk", uk, UK_ADJ)):
        if not isinstance(v, str) or not v.strip():
            return f"{lang} empty"
        if not adj.search(v):
            return f"{lang} nationality adjective missing"
        if LATIN.search(v):
            return f"{lang} Latin residue"
        m = re.match(r"^In (20\d\d),", en)
        if m and m.group(1) not in v:
            return f"{lang} year missing"
        expected = _openers.expected(en_opener, lang)
        if expected and not any(v.lstrip().startswith(x) for x in expected):
            return f"{lang} opener not rendered as prescribed ({en_opener!r} -> {'/'.join(expected)})"
    return "ru == uk" if ru == uk else None


# --------------------------------------------------------------------------- #
# generation stages
# --------------------------------------------------------------------------- #
def stage_entities(backend, cat: dict, mode: str, inventory: dict, n: int) -> list[str]:
    if mode == "inventory":
        ents = inventory.get(cat["label"], [])
        if not ents:
            raise SystemExit(f"no inventory entries for {cat['label']}")
        return ents
    user = fill(PROMPTS["entities"], label=cat["label"], definition=cat["definition"], n=n,
                seed=", ".join(CFG["seed_entities"]))
    proposed: list = []
    for attempt in range(3):
        try:
            raw = backend.chat(PROMPTS["system"], user + ("\n\n(attempt %d)" % attempt if attempt else ""), "entities", cat["label"])
            proposed = parse_json(raw).get("entity_types", [])
            if isinstance(proposed, list) and proposed:
                break
        except (TruncatedResponse, json.JSONDecodeError) as e:
            print(f"    entity proposal failed: {e}", file=sys.stderr)
    else:
        raise RuntimeError(f"no usable entity proposal for {cat['label']} after 3 attempts")
    ents: list[str] = []
    for e in CFG["seed_entities"] + list(proposed):
        f = filter_entity(e)
        if f and f not in ents:
            ents.append(f)
    print(f"  entities: {len(proposed)} proposed, {len(ents)} kept")
    return ents


def stage_templates(backend, cat: dict, entities: list[str], n_templates: int, batch: int,
                    seen: "SeenScenarios", stats: Counter) -> list[dict]:
    accepted: list[dict] = []
    used_labels: list[str] = []
    last_rejections: Counter = Counter()
    rounds, max_rounds = 0, CFG["max_rounds_factor"] * (n_templates // batch + 1)
    ent_set = set(entities)
    while len(accepted) < n_templates and rounds < max_rounds:
        rounds += 1
        n = min(batch, n_templates - len(accepted))
        feedback = ""
        if last_rejections:
            feedback = ("Templates of your previous batch were REJECTED for these reasons (count: reason); avoid them:\n" +
                        "\n".join(f"  {c}: {r}" for r, c in last_rejections.most_common(8)))
        user = fill(PROMPTS["templates"], label=cat["label"], cameo=cat["cameo"], definition=cat["definition"],
                    entities=", ".join(entities), n=n, used="; ".join(used_labels[-250:]) or "none", feedback=feedback)
        last_rejections = Counter()
        try:
            raw = backend.chat(PROMPTS["system"], user + f"\n\n(round {rounds})" * (rounds > 1), "templates", cat["label"])
            items = parse_json(raw).get("templates", [])
        except TruncatedResponse as e:
            print(f"    {e}", file=sys.stderr)
            stats["truncated_response"] += 1
            continue
        except json.JSONDecodeError:
            stats["bad_json"] += 1
            continue
        if not isinstance(items, list):
            stats["bad_json"] += 1
            continue
        for t in items:
            if not isinstance(t, dict):
                stats["rejected: not an object"] += 1
                continue
            reason = check_template(t, seen, cat["label"])
            if reason:
                stats[f"rejected: {reason.split(':')[-1].strip()[:40]}"] += 1
                last_rejections[reason.split(":")[-1].strip()[:120]] += 1
                continue
            admissible = [e for e in (t.get("entity_types") or []) if e in ent_set]
            if not admissible:
                stats["rejected: no admissible entity"] += 1
                continue
            frames = {(s, tf): t[s][tf] for s in ("pos", "neg") for tf in ("past", "present", "future")}
            seen.add(frames, f"{cat['label']}: {str(t.get('scenario', ''))[:60]}")
            used_labels.append(str(t.get("scenario", ""))[:60])
            t["_admissible"] = admissible
            accepted.append(t)
            if len(accepted) == n_templates:
                break
        print(f"  templates: round {rounds}: {len(accepted)}/{n_templates} accepted")
    if len(accepted) < n_templates:
        print(f"  WARNING: only {len(accepted)} templates after {rounds} rounds", file=sys.stderr)
        stats["incomplete categories"] += 1
    return accepted


def assign_and_expand(cat: dict, templates: list[dict], rng: random.Random, entity_counts: Counter) -> tuple[list[dict], list[dict]]:
    """Assign entity types and openers deterministically and expand to 12 rows per template."""
    openers = {tf: list(OPENERS[tf]) for tf in TF}
    cycles = {tf: [] for tf in TF}

    def next_opener(tf: str) -> str:  # balanced: shuffle a full cycle, then pop
        if not cycles[tf]:
            cycles[tf] = openers[tf][:]
            rng.shuffle(cycles[tf])
        return cycles[tf].pop()

    rows, trows = [], []
    for i, t in enumerate(templates, 1):
        pid = f"{cat['prefix']}_{i:03d}"
        adm = t["_admissible"]
        ent = min(adm, key=lambda e: (entity_counts[(cat["label"], e)], adm.index(e)))  # least used admissible type
        entity_counts[(cat["label"], ent)] += 1
        op = {tf: t.get("_openers", {}).get(tf) or next_opener(tf) for tf in TF}
        trow = {"file": f"{cat['id']}-{cat['slug']}.csv", "category": cat["label"], "pair_id": pid, "entity_type": ent,
                "scenario": str(t.get("scenario", ""))}
        for s in ("pos", "neg"):
            for tf in TF:
                trow[f"{s}_{tf.lower()}"] = t[s][tf.lower()]
        for tf in TF:
            trow[f"opener_{tf.lower()}"] = op[tf]
        trows.append(trow)
        for tf in TF:
            for side in ("ua", "ru"):
                for s in ("pos", "neg"):
                    sent = t[s][tf.lower()].replace("{TIME}", op[tf]).replace("{SIDE_ADJ}", CFG["side_adj"][side]).replace("{ENTITY}", ent)
                    rows.append({"pair_id": pid, "category": cat["label"], "entity_type": ent, "timeframe": tf,
                                 "side": side, "sentiment": s, "sentence_en": sent, "ru": "", "uk": ""})
    return rows, trows


def opener_hints(sents: list[str]) -> str:
    """Prescribed RU/UK renderings of the temporal openers occurring in the batch (one line per opener)."""
    lines = []
    for op in dict.fromkeys(s.split(",", 1)[0].strip() for s in sents):
        ru, uk = _openers.expected(op, "ru"), _openers.expected(op, "uk")
        if ru and uk:
            lines.append(f'  "{op}," -> ru: «{ru[0]}» | uk: «{uk[0]}»')
    return "\n".join(lines) or "  (none)"


def repair_opener(en: str, v: str, lang: str) -> str:
    """Replace a non-prescribed rendering of the temporal opener by the prescribed one: everything before the
    nationality adjective is the opener part of the translation (the actor phrase follows it directly)."""
    expected = _openers.expected(en.split(",", 1)[0].strip(), lang)
    adj = RU_ADJ if lang == "ru" else UK_ADJ
    m = adj.search(v)
    if not expected or not m or any(v.lstrip().startswith(x) for x in expected):
        return v
    return expected[0] + " " + v[m.start():]


def _translate_one(backend, cat: dict, pid: str, grp: list[dict]) -> tuple[str, list[dict] | None, list[str]]:
    if getattr(backend, "cost_exhausted", False):
        return pid, None, ["translation skipped: cost limit reached"]
    ua = [r for r in grp if r["side"] == "ua"]
    sents = [r["sentence_en"] for r in ua]
    notes = []
    for attempt in range(3):
        user = fill(PROMPTS["translate"], sentences="\n".join(f"{i + 1}. {s}" for i, s in enumerate(sents)),
                    opener_hints=opener_hints(sents))
        try:
            raw = backend.chat(PROMPTS["system"], user + ("\n\n(attempt %d)" % attempt if attempt else ""), "translate", cat["label"])
            items = parse_json(raw).get("items", [])
        except (json.JSONDecodeError, TruncatedResponse) as e:
            notes.append(f"translation retry: {type(e).__name__}")
            continue
        except CostLimitExceeded as e:
            notes.append(f"translation stopped: {e}")
            backend.cost_exhausted = True
            return pid, None, notes
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
            notes.append(f"translation error ({type(e).__name__}): {e}")
            continue
        by_id: dict[int, dict] = {}
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and str(it.get("id", "")).strip().isdigit():
                by_id[int(str(it["id"]).strip())] = it
        cand = [by_id.get(i) for i in range(1, len(sents) + 1)]
        errs = ["missing id"] if any(it is None for it in cand) else \
            [check_translation(s, it.get("ru"), it.get("uk")) for s, it in zip(sents, cand)]
        if any(errs) and all("opener" in e for e in errs if e) and not any(it is None for it in cand):
            # only the opener rendering is wrong: repair it deterministically (as fix_openers.py did for v1.1)
            for s_en, it in zip(sents, cand):
                it["ru"], it["uk"] = repair_opener(s_en, it["ru"], "ru"), repair_opener(s_en, it["uk"], "uk")
            errs = [check_translation(s_en, it.get("ru"), it.get("uk")) for s_en, it in zip(sents, cand)]
            if not any(errs):
                notes.append("translation opener repaired deterministically")
                return pid, cand, notes
        if not any(errs):
            return pid, cand, notes
        notes.append(f"translation retry: {next(e for e in errs if e)}")
    return pid, None, notes


def stage_translate(backend, cat: dict, rows: list[dict], stats: Counter, workers: int = 1) -> None:
    from concurrent.futures import ThreadPoolExecutor
    by_pid: dict[str, list[dict]] = OrderedDict()
    for r in rows:
        by_pid.setdefault(r["pair_id"], []).append(r)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for pid, items, notes in ex.map(lambda kv: _translate_one(backend, cat, kv[0], kv[1]), by_pid.items()):
            for n in notes:
                stats[n] += 1
            done += 1
            grp = by_pid[pid]
            if items is None:
                stats["translation FAILED templates"] += 1
                print(f"  translation failed for {pid}", file=sys.stderr)
                continue
            ua = [r for r in grp if r["side"] == "ua"]
            lookup = {(r["timeframe"], r["sentiment"]): it for r, it in zip(ua, items)}
            for r in grp:
                it = lookup[(r["timeframe"], r["sentiment"])]
                if r["side"] == "ua":
                    r["ru"], r["uk"] = it["ru"].strip(), it["uk"].strip()
                else:
                    r["ru"], r["uk"] = derive_ru_side(it["ru"].strip(), "ru"), derive_ru_side(it["uk"].strip(), "uk")
            if done % 20 == 0 or done == len(by_pid):
                print(f"  translated {done}/{len(by_pid)} templates")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_state() -> dict:
    """Commit and dirty flag of the code repository (empty if not a git checkout)."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(ROOT)], cwd=HERE, capture_output=True, text=True, timeout=10)
        if commit.returncode != 0:
            return {}
        return {"git_commit": commit.stdout.strip(), "git_dirty": bool(dirty.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return {}


def write_atomic(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory and rename, so that a crash never leaves a truncated file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_csv_atomic(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    write_atomic(path, buf.getvalue())


def redact_argv(argv: list[str]) -> str:
    """Command line for the manifest with the API key removed."""
    out, skip = [], False
    for a in argv:
        if skip:
            out.append("<redacted>")
            skip = False
        elif a == "--api-key":
            out.append(a)
            skip = True
        elif a.startswith("--api-key="):
            out.append("--api-key=<redacted>")
        else:
            out.append(a)
    return " ".join(out)


def load_templates_csv(path: Path) -> dict[str, list[dict]]:
    """Read an existing templates.csv (release or previous run) into the internal template format."""
    out: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        t = {"scenario": r.get("scenario_id") or r.get("scenario", ""), "_admissible": [r["entity_type"]],
             "_openers": {tf: (r[f"opener_{tf.lower()}"].rstrip(",") + ",") for tf in TF},
             "pos": {k: r[f"pos_{k}"] for k in ("past", "present", "future")},
             "neg": {k: r[f"neg_{k}"] for k in ("past", "present", "future")}}
        out[r["category"]].append(t)
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output directory (release layout)")
    ap.add_argument("--model", default="openai/gpt-5.4", help="OpenRouter model id (see https://openrouter.ai/models)")
    ap.add_argument("--api-key", default=None, help="default: $OPENROUTER_API_KEY, else ROUTER/OPENROUTER_API_KEY from a .env file in the repo root or cwd")
    ap.add_argument("--seed", type=int, default=42, help="seed for the model (where supported) and for entity/opener assignment")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--n-templates", type=int, default=100)
    ap.add_argument("--batch", type=int, default=CFG["templates_per_call"], help="templates requested per API call")
    ap.add_argument("--categories", help="comma-separated category ids or slugs (default: all 22)")
    ap.add_argument("--entities", choices=["propose", "inventory"], default="propose")
    ap.add_argument("--entity-inventory", default=str(DEFAULT_DATA / "entity_inventory.csv"))
    ap.add_argument("--n-entities", type=int, default=60, help="entity types to request per category (propose mode)")
    ap.add_argument("--translate", action="store_true", help="also produce ru/uk columns")
    ap.add_argument("--workers", type=int, default=4, help="parallel API requests in the translation stage")
    ap.add_argument("--reasoning", choices=["auto", "off"], default="off",
                    help="off = ask OpenRouter to disable model reasoning tokens (cheaper/faster; default); auto = provider default")
    ap.add_argument("--from-templates", help="re-expand an existing templates.csv instead of calling the model (no API)")
    ap.add_argument("--mock", action="store_true", help="offline backend replaying data/v1 (for tests)")
    ap.add_argument("--mock-release", default=str(DEFAULT_DATA),
                    help="existing release used by --mock and as verb lexicon for the tense screen")
    ap.add_argument("--max-tokens", type=int, default=16000, help="completion token limit per request (entity stage 2,000, translation 4,000)")
    ap.add_argument("--max-cost-usd", type=float, default=None, help="stop the run when the cost reported by OpenRouter for this run exceeds this amount")
    ap.add_argument("--reference-year", type=int, default=None, help="year the '{Y±k}' openers are resolved against (default: generator_config.json reference_year)")
    ap.add_argument("--resume", action="store_true", help="allow a non-empty output directory (reuse its generator_cache; category files are rewritten)")
    ap.add_argument("--force", action="store_true", help="delete the generator-owned files of a non-empty output directory (category CSVs, inventory, templates, reports, manifest, log; never the cache) and start over")
    ap.add_argument("--allow-incomplete", action="store_true", help="exit 0 even if templates are missing, translations failed or the release checks fail (exploratory runs)")
    ap.add_argument("--english-only", action="store_true", help="English-only run: translation checks (C7, opener check) are skipped and the run is marked 'exploratory'")
    ap.add_argument("--release", default=None, help="with --from-templates: copy the ru/uk columns of this released directory (same pair_id/timeframe/side/sentiment) so that the reproduction passes all gates")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stale = sorted(p.name for p in out.iterdir() if p.name != "generator_cache" and not p.name.startswith("."))
    if stale and not (args.resume or args.force):
        raise SystemExit(f"output directory {out} is not empty ({', '.join(stale[:5])}{', …' if len(stale) > 5 else ''}); "
                         "use --resume to reuse its cache or --force to overwrite, or choose a new directory")
    if stale and args.force:
        owned = [n for n in stale if GENERATOR_OUTPUT.match(n)]
        foreign = [n for n in stale if not GENERATOR_OUTPUT.match(n)]
        if foreign:
            raise SystemExit(f"--force refuses to touch files the generator did not write: {', '.join(foreign[:5])}")
        for n in owned:
            (out / n).unlink()
        print(f"--force: removed {len(owned)} previous output file(s)")
    global OPENERS
    OPENERS = resolve_openers(CFG, args.reference_year)
    reference_year = int(args.reference_year or CFG.get("reference_year") or datetime.now(timezone.utc).year)
    problems: list[str] = []  # reasons for a non-zero exit
    cats = CFG["categories"]
    if args.categories:
        sel = {c.strip() for c in args.categories.split(",")}
        cats = [c for c in cats if c["id"] in sel or c["slug"] in sel or f"{c['id']}-{c['slug']}" in sel]
        if not cats:
            raise SystemExit("no categories matched")
    t_start = time.time()

    if args.from_templates:
        backend = None
        pre = load_templates_csv(Path(args.from_templates))
    elif args.mock:
        backend = MockBackend(Path(args.mock_release))
        pre = None
    else:
        args.api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY") or read_dotenv_key()
        if not args.api_key:
            raise SystemExit("no API key: set OPENROUTER_API_KEY, put ROUTER=... into .env, or use --mock / --from-templates")
        backend = OpenRouterBackend(args.model, args.api_key, args.temperature, args.seed,
                                    out / "generator_cache", out / "generation_log.jsonl", max_tokens=args.max_tokens,
                                    reasoning=args.reasoning, max_cost_usd=args.max_cost_usd)
        pre = None

    inventory: dict[str, list[str]] = defaultdict(list)
    if args.entities == "inventory":
        with Path(args.entity_inventory).open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                inventory[r["category"]].append(r["entity"])

    all_templates, stats, entity_counts = [], Counter(), Counter()
    seen_en: set = set()
    seen = SeenScenarios()  # shared by all categories: no scenario reuse across files
    seed_verb_lexicon(Path(args.mock_release))  # verb lexicon for the tense screen from the existing release
    aborted = None
    for cat in cats:
      try:
        print(f"[{cat['id']}-{cat['slug']}]")
        rng = random.Random(f"{args.seed}:{cat['id']}-{cat['slug']}")  # per category: a --categories subset reproduces the full run
        if pre is not None:
            templates = pre.get(cat["label"], [])
            if not templates:
                print("  no templates in file, skipped")
                continue
        else:
            try:
                entities = stage_entities(backend, cat, args.entities, inventory, args.n_entities)
                templates = stage_templates(backend, cat, entities, args.n_templates, args.batch, seen, stats)
            except CostLimitExceeded as e:
                problems.append(str(e))
                print(f"  {e}", file=sys.stderr)
                break
            except RuntimeError as e:
                problems.append(f"{cat['id']}-{cat['slug']}: {e}")
                print(f"  {e}", file=sys.stderr)
                continue
            if len(templates) < args.n_templates:
                problems.append(f"{cat['id']}-{cat['slug']}: {len(templates)}/{args.n_templates} templates")
        rows, trows = assign_and_expand(cat, templates, rng, entity_counts)
        if args.from_templates and args.release:
            rel = Path(args.release) / f"{cat['id']}-{cat['slug']}.csv"
            if rel.exists():
                with rel.open(encoding="utf-8") as fh:
                    lookup = {(r["pair_id"], r["timeframe"], r["side"], r["sentiment"]): (r["ru"], r["uk"]) for r in csv.DictReader(fh)}
                for r in rows:
                    r["ru"], r["uk"] = lookup.get((r["pair_id"], r["timeframe"], r["side"], r["sentiment"]), ("", ""))
                missing = sum(1 for r in rows if not r["ru"])
                if missing:
                    problems.append(f"{cat['id']}-{cat['slug']}: {missing} rows without a released translation")
            else:
                problems.append(f"{cat['id']}-{cat['slug']}: no released file in {args.release}")
        dup = [r["sentence_en"] for r in rows if r["sentence_en"] in seen_en]
        if dup:  # cannot happen after the global scenario check unless two categories share a frame verbatim
            stats["cross-file duplicate sentences"] += len(dup)
            print(f"  WARNING: {len(dup)} sentences duplicate an earlier file, e.g. {dup[0][:80]!r}", file=sys.stderr)
        seen_en.update(r["sentence_en"] for r in rows)
        if args.translate and backend is not None:
            failed_before = stats["translation FAILED templates"]
            stage_translate(backend, cat, rows, stats, args.workers)
            if stats["translation FAILED templates"] > failed_before:
                problems.append(f"{cat['id']}-{cat['slug']}: {stats['translation FAILED templates'] - failed_before} template(s) without translation")
        write_csv_atomic(out / f"{cat['id']}-{cat['slug']}.csv", FIELDS, rows)
        all_templates += trows
        print(f"  wrote {len(rows)} rows, {len(trows)} templates")
        if getattr(backend, "cost_exhausted", False):
            problems.append("run stopped: cost limit reached during translation")
            break
      except Exception as e:  # noqa: BLE001 - the manifest (status=failed) must be written whatever happens
        import traceback
        traceback.print_exc()
        aborted = f"{cat['id']}-{cat['slug']}: run aborted by {type(e).__name__}: {e}"
        problems.append(aborted)
        break

    # inventory + templates
    inv_rows, seen_inv = [], set()
    for t in all_templates:
        k = (t["category"], t["entity_type"])
        if k not in seen_inv:
            seen_inv.add(k)
            inv_rows.append({"category": k[0], "entity": k[1]})
    write_csv_atomic(out / "entity_inventory.csv", ["category", "entity"], inv_rows)
    if all_templates:
        write_csv_atomic(out / "templates_generated.csv", list(all_templates[0].keys()), all_templates)

    print("\nstats:", dict(stats))
    if backend is not None and backend.usage:
        print("usage:", dict(backend.usage))
    check_results: dict = {}

    if not args.no_validate:
        tools = HERE.parent / "tools"
        expected = ",".join(f"{c['id']}-{c['slug']}.csv" for c in cats)
        validate_cmd = [str(tools / "validate_dataset.py"), "--dir", str(out), "--report", str(out / "validation_report.md"),
                        "--n-templates", str(args.n_templates), "--files", expected, "--reference-year", str(reference_year)]
        if args.english_only:
            validate_cmd.append("--english-only")
        checks = [
            ("validate_dataset.py", validate_cmd),
            ("extract_templates.py", [str(tools / "extract_templates.py"), "--dir", str(out), "--out", str(out / "templates.csv")]),
            ("check_duplicates.py", [str(tools / "check_duplicates.py"), "--dir", str(out), "--out", str(out)]),
        ]
        with_translations = args.translate or (args.from_templates and args.release)
        if with_translations and not args.english_only:
            checks.append(("check_openers.py", [str(tools / "check_openers.py"), "--dir", str(out)]))
        for name, cmd in checks:
            print(f"\nrunning {name} ...")
            r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
            print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
            check_results[name] = r.returncode
            if name == "check_openers.py":
                write_atomic(out / "opener_check.txt", r.stdout)
            if r.returncode != 0:
                if name == "validate_dataset.py" and not with_translations and not args.english_only:
                    print("(translation checks C7 fail when no translations are produced: use --translate, --release <dir> or --english-only)")
                problems.append(f"{name} exit {r.returncode}")
    status = "failed" if problems else ("exploratory" if (args.english_only or args.no_validate) else "passed")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "command": redact_argv(sys.argv),
        "backend": "from-templates" if args.from_templates else ("mock" if args.mock else "openrouter"),
        "model": None if (args.from_templates or args.mock) else args.model,
        "temperature": args.temperature, "seed": args.seed, "n_templates": args.n_templates, "batch": args.batch, "max_tokens": args.max_tokens,
        "entities_mode": args.entities, "translate": args.translate, "reasoning": args.reasoning, "workers": args.workers, "categories": [c["id"] + "-" + c["slug"] for c in cats],
        "reference_year": reference_year, "openers": OPENERS,
        "python": sys.version.split()[0], "generator_config_sha256": hashlib.sha256((GEN / "generator_config.json").read_bytes()).hexdigest(),
        "prompts_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in PROMPTS.items()},
        "generator_sha256": sha256_file(Path(__file__)), **git_state(),
        "inputs_sha256": {k: sha256_file(Path(v)) for k, v in (("from_templates", args.from_templates),
                                                              ("entity_inventory", args.entity_inventory if args.entities == "inventory" else None),
                                                              ("mock_release_templates", str(Path(args.mock_release) / "templates.csv") if args.mock else None))
                          if v and Path(v).exists()},
        "provider_models": sorted(getattr(backend, "provider_models", [])),
        "outputs_sha256": {p.name: sha256_file(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != "run_manifest.json" and GENERATOR_OUTPUT.match(p.name)},
        "status": status, "problems": problems, "checks": check_results,
        "usage": dict(backend.usage) if backend is not None else {},
        "usage_cached": dict(getattr(backend, "usage_cached", {})) if backend is not None else {}, "stats": dict(stats),
        "duration_s": round(time.time() - t_start, 1),
    }
    write_atomic(out / "run_manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
    if problems:
        print("\nPROBLEMS:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        if not args.allow_incomplete:
            print("exit 1 (use --allow-incomplete for exploratory runs); run_manifest.json status = failed", file=sys.stderr)
            return 1
    print(f"\nstatus: {status}" + (" — complete run, all release checks passed" if status == "passed" else
                                    " (problems ignored: --allow-incomplete)" if problems else " (translation checks skipped)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
