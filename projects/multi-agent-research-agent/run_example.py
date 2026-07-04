"""Minimal one-shot example: run a broad research question end-to-end.

Run from the project root with the shared venv:
    /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python run_example.py
"""

import asyncio
import sys

sys.path.insert(0, "src")

import config
from coordinator import run_research

config.load_env()


async def main():
    run = await run_research("What is the impact of AI on creative industries?")
    print("ROUTE:      ", run.route)  # 'fan_out' for this broad question (TR3)
    print("DELEGATED TO:", sorted(run.delegated_subagents))  # e.g. ['doc_analysis', 'web_search']
    print("TOOL CALLS: ", run.tool_calls)
    print("DELEGATION BATCHES     :", run.delegation_batches)  # one Agent call per msg (spike finding)
    print("MAX PARALLEL DELEGATIONS:", run.max_parallel_delegations, "(batching intent — 1 in practice)")
    print("PEAK CONCURRENT TASKS  :", run.peak_concurrent_tasks, "(>=2 ⇒ real fan-out, TR2/FR3)")
    print("OUTCOME:    ", run.subtype)  # 'success' on a clean run
    print("TURNS:      ", run.num_turns, "(backstop is", config.MAX_TURNS_BACKSTOP, ")")
    print("COST (TR10): $", run.total_cost_usd, " | subagent tokens:", run.subagent_total_tokens, sep="")
    print("COVERAGE (TR4):", run.coverage)  # canonical facet -> status; all 4 covered on a clean run
    print("GAPS:       ", run.gaps)  # [] when the topic is fully covered
    print("REFINEMENT ITERATIONS (TR5):", run.refinement_iterations, "(0 = covered on first pass)")
    print("COVERAGE HISTORY:", run.coverage_history)  # coverage map after each turn (progression)
    if run.report is not None:
        # FR5: every parsed claim carries a source (TR8). Should be > 0 and all cited on a broad run.
        print("CLAIMS (FR5):", len(run.report.claims),
              "| all cited:", run.report.all_claims_have_source())
    # TR7: the timed-out source (D004) should be annotated as unavailable, not silently dropped.
    annotated = any(s in run.final_text for s in ("Recording Artists Coalition", "unavailable", "timed out"))
    print("UNAVAILABLE SOURCE ANNOTATED (TR7):", annotated)
    print("REPORT:\n")
    print(run.final_text)


if __name__ == "__main__":
    asyncio.run(main())
