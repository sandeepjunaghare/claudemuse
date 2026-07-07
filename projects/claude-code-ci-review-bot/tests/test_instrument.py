"""Offline tests for false-positive instrumentation + quarantine (TR9/FR4).

Hand-authored ``Finding`` lists + a tmp store path; no CLI, no network. The
``apply_quarantine`` test is the FR4 headline: quarantining one category filters
exactly its findings while every other category still emits.
"""

import config
import instrument
from parse import Finding, Location


def _f(file, line, pattern, category):
    return Finding(
        location=Location(file, line),
        issue="x",
        severity="high",
        suggested_fix="fix",
        detected_pattern=pattern,
        category=category,
    )


def _seed_shape() -> dict:
    """The seed store shape, constructed in-code (independent of the fixture)."""
    return {
        "patterns": {
            "none-deref": {"category": "correctness", "emitted": 12, "dismissed": 0},
            "speculative-perf": {"category": "performance", "emitted": 8, "dismissed": 6},
            "style-nit": {"category": "maintainability", "emitted": 10, "dismissed": 7},
            "rare-guess": {"category": "security", "emitted": 2, "dismissed": 2},
        },
        "manual_quarantine": [],
    }


# --- store I/O ---------------------------------------------------------------


def test_load_missing_store_returns_default(tmp_path):
    store = instrument.load_store(path=tmp_path / "nope.json")
    assert store == {"patterns": {}, "manual_quarantine": []}


def test_save_then_load_round_trip(tmp_path):
    store = _seed_shape()
    path = tmp_path / "s.json"
    written = instrument.save_store(store, path=path)
    assert written == path
    assert instrument.load_store(path=path) == store


def test_save_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "s.json"
    instrument.save_store({"patterns": {}, "manual_quarantine": []}, path=path)
    assert path.exists()


# --- record_* (increment + no-mutation) --------------------------------------


def test_record_emitted_creates_and_increments():
    store = instrument._default_store()
    findings = [
        _f("a.py", 1, "none-deref", "correctness"),
        _f("b.py", 2, "none-deref", "correctness"),
        _f("c.py", 3, "style-nit", "maintainability"),
    ]
    out = instrument.record_emitted(store, findings)
    assert out["patterns"]["none-deref"] == {"category": "correctness", "emitted": 2, "dismissed": 0}
    assert out["patterns"]["style-nit"]["emitted"] == 1
    # input untouched (pure)
    assert store == {"patterns": {}, "manual_quarantine": []}


def test_record_emitted_skips_blank_pattern():
    out = instrument.record_emitted(instrument._default_store(), [_f("a.py", 1, "", "correctness")])
    assert out["patterns"] == {}


def test_record_dismissal_increments_and_does_not_mutate():
    store = _seed_shape()
    before = store["patterns"]["speculative-perf"]["dismissed"]
    out = instrument.record_dismissal(store, "speculative-perf")
    assert out["patterns"]["speculative-perf"]["dismissed"] == before + 1
    assert store["patterns"]["speculative-perf"]["dismissed"] == before  # unchanged


def test_record_dismissal_creates_entry_with_category():
    out = instrument.record_dismissal(instrument._default_store(), "new-pat", category="security")
    assert out["patterns"]["new-pat"] == {"category": "security", "emitted": 0, "dismissed": 1}


def test_record_dismissal_blank_pattern_is_noop():
    store = _seed_shape()
    out = instrument.record_dismissal(store, "  ")
    assert out == store


# --- rates + sample sizes ----------------------------------------------------


def test_category_dismissal_rates_on_seed_shape():
    rates = instrument.category_dismissal_rates(_seed_shape())
    assert rates["correctness"] == 0.0
    assert rates["performance"] == 0.75
    assert round(rates["maintainability"], 3) == 0.7
    assert rates["security"] == 1.0


def test_rates_skip_zero_emitted_no_zero_division():
    store = {"patterns": {"p": {"category": "correctness", "emitted": 0, "dismissed": 0}}, "manual_quarantine": []}
    assert instrument.category_dismissal_rates(store) == {}  # no ZeroDivision


def test_category_sample_sizes():
    sizes = instrument.category_sample_sizes(_seed_shape())
    assert sizes == {"correctness": 12, "performance": 8, "maintainability": 10, "security": 2}


# --- quarantine (the FR4 gate) -----------------------------------------------


def test_auto_quarantined_threshold_and_min_sample_gate():
    """FR4 min-sample gate: performance (0.75) + maintainability (0.70) quarantine;
    security (1.0 but only 2 emitted) is protected by min-sample; correctness clean."""
    out = instrument.auto_quarantined(_seed_shape(), threshold=0.5, min_sample=3)
    assert out == ["maintainability", "performance"]


def test_manual_quarantine_forces_category_regardless_of_rate():
    store = _seed_shape()
    store["manual_quarantine"] = ["security"]  # min-sample would exclude it
    out = instrument.quarantined_categories(store, threshold=0.5, min_sample=3)
    assert out == ["maintainability", "performance", "security"]


def test_apply_quarantine_filters_exactly_the_quarantined_categories():
    """FR4 headline: quarantining two categories keeps the other two emitting."""
    findings = [
        _f("a.py", 1, "none-deref", "correctness"),
        _f("b.py", 2, "speculative-perf", "performance"),
        _f("c.py", 3, "style-nit", "maintainability"),
        _f("d.py", 4, "rare-guess", "security"),
    ]
    original = list(findings)
    kept, dropped = instrument.apply_quarantine(findings, ["performance", "maintainability"])
    assert {f.category for f in kept} == {"correctness", "security"}
    assert {f.category for f in dropped} == {"performance", "maintainability"}
    assert findings == original  # input list unchanged (pure)


def test_apply_quarantine_empty_is_noop():
    findings = [_f("a.py", 1, "none-deref", "correctness")]
    kept, dropped = instrument.apply_quarantine(findings, [])
    assert kept == findings and dropped == []


# --- seed regression-lock ----------------------------------------------------


def test_committed_seed_matches_the_quarantine_story():
    """Regression-lock the committed fixture against the documented demo story."""
    seed = instrument.load_store(path=config.DISMISSED_PATTERNS_SEED)
    assert instrument.auto_quarantined(
        seed,
        threshold=config.QUARANTINE_RATE_THRESHOLD,
        min_sample=config.QUARANTINE_MIN_SAMPLE,
    ) == ["maintainability", "performance"]
