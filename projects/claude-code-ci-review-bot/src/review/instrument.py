"""False-positive instrumentation + category quarantine (TR9/FR4).

The feedback loop that protects trust: dismissed findings are tracked *by
``detected_pattern``* (fine-grained evidence), a *per-category* dismissal rate is
computed from them, and a category whose rate crosses a threshold — with enough
samples — is **quarantined** (its findings filtered out) so one noisy category
never poisons the rest. A manual override list quarantines regardless of rate.

Two halves, mirroring ``dedupe.py`` (pure) + ``store.py`` (file I/O):

* **Pure core** (``record_*`` / ``*_rates`` / ``*_quarantined`` /
  ``apply_quarantine``): stdlib-only, deterministic, never raises, never touches
  the CLI/network/filesystem, and unit-tests offline with no credentials. The
  ``record_*`` functions return a NEW store (never mutate the argument), exactly
  like ``severity.apply_canonical_severity``.
* **File store** (``load_store`` / ``save_store``): the read/write + mkdir idiom
  from ``store.py``; a missing store yields the default (never raises). A
  ``path=`` override lets tests point at a tmp file.

Quarantine granularity is the **category** (the lever the user actually pulls —
"disable the noisy category"), tracked by **pattern** (the evidence). The
min-sample guard prevents a rare 100%-dismissed pattern from nuking its whole
category.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

import config
from parse import Finding

#: The empty store shape. A fresh copy is returned each time so callers can
#: never accidentally share/mutate this module-level literal.
_STORE_DEFAULT = {"patterns": {}, "manual_quarantine": []}


def _default_store() -> dict:
    """A fresh deep copy of the empty store shape."""
    return copy.deepcopy(_STORE_DEFAULT)


# --- pure core (offline) -----------------------------------------------------


def record_emitted(store: dict, findings: "list[Finding]") -> dict:
    """Return a NEW store with each finding's ``detected_pattern`` emit-counted.

    For every finding with a non-empty ``detected_pattern``, ensure a
    ``patterns[pattern]`` entry (creating ``{"category":…, "emitted":0,
    "dismissed":0}`` on first sight) and increment ``emitted``. Findings with a
    blank pattern are skipped (nothing to attribute). Pure — never mutates
    ``store``.
    """
    s = copy.deepcopy(store)
    patterns = s.setdefault("patterns", {})
    for f in findings:
        pattern = (f.detected_pattern or "").strip()
        if not pattern:
            continue
        entry = patterns.setdefault(
            pattern,
            {"category": (f.category or "").strip(), "emitted": 0, "dismissed": 0},
        )
        entry["emitted"] += 1
    return s


def record_dismissal(store: dict, pattern: str, category: "str | None" = None) -> dict:
    """Return a NEW store with one dismissal counted against ``pattern``.

    Ensures the ``patterns[pattern]`` entry (setting ``category`` from the arg on
    creation, or leaving an existing one) and increments ``dismissed``. Pure —
    never mutates ``store``. A blank pattern is a no-op (returns the copy
    unchanged).
    """
    s = copy.deepcopy(store)
    pattern = (pattern or "").strip()
    if not pattern:
        return s
    patterns = s.setdefault("patterns", {})
    entry = patterns.setdefault(
        pattern,
        {"category": (category or "").strip(), "emitted": 0, "dismissed": 0},
    )
    if category and not entry.get("category"):
        entry["category"] = category.strip()
    entry["dismissed"] += 1
    return s


def category_sample_sizes(store: dict) -> "dict[str, int]":
    """Σemitted per category (the min-sample denominator/guard input)."""
    sizes: "dict[str, int]" = {}
    for entry in store.get("patterns", {}).values():
        cat = (entry.get("category") or "").strip()
        if not cat:
            continue
        sizes[cat] = sizes.get(cat, 0) + int(entry.get("emitted", 0))
    return sizes


def category_dismissal_rates(store: dict) -> "dict[str, float]":
    """Σdismissed/Σemitted per category. Categories with Σemitted == 0 are
    skipped (no rate, no ZeroDivision)."""
    emitted: "dict[str, int]" = {}
    dismissed: "dict[str, int]" = {}
    for entry in store.get("patterns", {}).values():
        cat = (entry.get("category") or "").strip()
        if not cat:
            continue
        emitted[cat] = emitted.get(cat, 0) + int(entry.get("emitted", 0))
        dismissed[cat] = dismissed.get(cat, 0) + int(entry.get("dismissed", 0))
    return {
        cat: dismissed[cat] / emitted[cat]
        for cat in emitted
        if emitted[cat] > 0
    }


def auto_quarantined(store: dict, *, threshold: float, min_sample: int) -> "list[str]":
    """Sorted categories whose dismissal rate >= ``threshold`` AND Σemitted >=
    ``min_sample`` (the FR4 rate gate + rare-noise guard)."""
    rates = category_dismissal_rates(store)
    sizes = category_sample_sizes(store)
    return sorted(
        cat
        for cat, rate in rates.items()
        if rate >= threshold and sizes.get(cat, 0) >= min_sample
    )


def quarantined_categories(
    store: dict, *, threshold: float, min_sample: int
) -> "list[str]":
    """Sorted union of the auto-quarantined categories and the manual override
    list (``store["manual_quarantine"]``). A manual entry quarantines regardless
    of rate/sample."""
    auto = set(auto_quarantined(store, threshold=threshold, min_sample=min_sample))
    manual = {c.strip() for c in store.get("manual_quarantine", []) if c and c.strip()}
    return sorted(auto | manual)


def apply_quarantine(
    findings: "list[Finding]", quarantined: "list[str]"
) -> "tuple[list[Finding], list[Finding]]":
    """Split ``findings`` into ``(kept, dropped)`` by quarantined category.

    A finding is dropped iff its (stripped) ``category`` is in ``quarantined``.
    Empty ``quarantined`` → ``(all, [])`` — the no-op default path. Pure — never
    mutates the input list. Mirrors ``dedupe.suppress_prior``'s (new, still) shape.
    """
    q = {c.strip() for c in quarantined if c and c.strip()}
    kept: "list[Finding]" = []
    dropped: "list[Finding]" = []
    for f in findings:
        (dropped if (f.category or "").strip() in q else kept).append(f)
    return kept, dropped


# --- file store (mirrors store.py) -------------------------------------------


def load_store(*, path: "Path | None" = None) -> dict:
    """Load the dismissal store; a missing store → the default (never raises).

    ``path`` defaults to ``config.DISMISSED_PATTERNS_STORE`` (the runtime store);
    tests pass a tmp file. Because a missing runtime store is the normal
    first-run / no-dismissals-yet case, an absent file returns the empty default
    — which makes ``quarantined_categories`` empty and the CLI filter a no-op.
    """
    target = Path(path) if path is not None else config.DISMISSED_PATTERNS_STORE
    if not target.exists():
        return _default_store()
    return json.loads(target.read_text(encoding="utf-8"))


def save_store(store: dict, *, path: "Path | None" = None) -> Path:
    """Write ``store`` to ``path`` (default ``config.DISMISSED_PATTERNS_STORE``).

    Creates the parent directory if absent. Returns the written path.
    """
    target = Path(path) if path is not None else config.DISMISSED_PATTERNS_STORE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return target


def main(argv: "list[str] | None" = None) -> int:
    """Thin ops CLI: record a dismissal into the runtime store.

    ``instrument --dismiss <pattern> [--category <c>]`` loads the runtime store,
    records one dismissal against the pattern, saves, and prints the new count.
    """
    parser = argparse.ArgumentParser(
        prog="instrument",
        description="Record a dismissed finding by detected_pattern (TR9/FR4).",
    )
    parser.add_argument("--dismiss", required=True, help="The detected_pattern slug that was dismissed.")
    parser.add_argument("--category", default=None, help="Category for the pattern (used on first sight).")
    args = parser.parse_args(argv)

    store = load_store()
    store = record_dismissal(store, args.dismiss, args.category)
    save_store(store)
    count = store["patterns"][args.dismiss.strip()]["dismissed"]
    print(f"recorded dismissal: {args.dismiss} (dismissed count now {count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
