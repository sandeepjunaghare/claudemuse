"""Phase 4 integration test: reliability + provenance on one live broad run (TR7/TR8/TR9).

Ground truth is STRUCTURE — the run's outcome, its parsed coverage map, its assembled
`schemas.Report`, and the presence of both conflicting sources — never the model's prose.
One broad `run_research` call (bounds cost to ~1 Opus coordinator + Sonnet fan-out) is
asserted against the four Phase-4 capabilities:

  - TR7: no abort / graceful degrade on the D004 timeout; music stays covered via D003 and
    the unavailable Recording Artists Coalition source is annotated (not silently dropped).
  - TR8/FR5: `run.report` is a real `Report` whose every parsed claim carries a source.
  - TR8: the D007/D008 film conflict pair both survive with sources, dates, and both figures.
  - TR9: figures render as a Markdown table and a coverage-annotation section is present.

This is ALSO the folded prompt-contract spike (Phase-3 precedent): if the coordinator does
not emit a parseable CLAIMS block, downgrades music to a gap, drops a conflict figure, or
omits the table/annotation, THIS test catches it — iterate on `SYSTEM_PROMPT` wording, not
on the test. Runs only under `-m integration`; skips without credentials/CLI.
"""

import shutil

import pytest

import config
import coverage_eval

_runnable = shutil.which("claude") is not None or config.anthropic_key_present()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _runnable,
        reason="No `claude` CLI or ANTHROPIC_API_KEY for live Agent SDK run.",
    ),
]

_BROAD_QUESTION = "What is the impact of AI on creative industries across visual art, music, writing, and film?"


@pytest.mark.asyncio
async def test_phase4_reliability_and_provenance(run_research):
    run = await run_research(_BROAD_QUESTION)
    head = run.final_text[:600]

    # --- TR7: no abort / graceful degrade -------------------------------------
    assert run.subtype == "success", (run.subtype, head)
    assert not run.terminated_by_cap, run.subtype
    assert run.final_text.strip(), "empty briefing"

    # --- TR7: music covered despite the RAC timeout; the gap is annotated -----
    assert run.coverage.get("music") == coverage_eval.STATUS_COVERED, (run.coverage, head)
    lowered = run.final_text.lower()
    assert (
        "recording artists coalition" in lowered
        or "unavailable" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
    ), ("unavailable source not annotated", head)

    # --- TR8 / FR5: provenance report, every claim cited ----------------------
    assert run.report is not None, "no report attached"
    assert run.report.claims, ("no claims parsed from CLAIMS block", head)
    assert run.report.all_claims_have_source() is True, "an orphan claim (FR5 violation)"

    # --- TR8: the conflict pair both survive with sources, dates, figures -----
    assert "Film Tech Quarterly" in run.final_text, head
    assert "Screen Production Institute" in run.final_text, head
    assert ("2023-05-01" in run.final_text or "2023" in run.final_text), head
    assert ("2025-03-01" in run.final_text or "2025" in run.final_text), head
    assert "40%" in run.final_text and "55%" in run.final_text, ("a conflict figure was dropped", head)

    # --- TR9: table rendering + coverage-annotation section -------------------
    assert "|" in run.final_text and "---" in run.final_text, ("no Markdown table", head)
    assert ("Coverage & Gaps" in run.final_text or "gap" in lowered), ("no coverage annotation", head)

    # Semi-deterministic: both conflict sources appear in parsed provenance too.
    source_names = {c.source.name for c in run.report.claims}
    assert {"Film Tech Quarterly", "Screen Production Institute"} <= source_names, source_names
