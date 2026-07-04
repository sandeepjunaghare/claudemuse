"""On-demand benchmark: parallel fan-out vs the sequential baseline (TR2/FR3/TR10).

NOT a pytest test — this makes ~2 full Opus+Sonnet research runs (real cost, several
minutes) and a single wall-clock sample is too noisy to gate CI on. The deterministic
parallelism proof lives in the test suite (`peak_concurrent_tasks >= 2`); this script
exists only to put a real speedup NUMBER on the ~15× architecture, on demand.

Both configs share the SAME background=True subagents and differ ONLY in the system
prompt: the parallel prompt fires delegations back-to-back (tasks overlap), the sequential
baseline waits for each subagent before dispatching the next. Run from the project root:

    ../../.venv/bin/python benchmark_parallel.py
"""

import asyncio
import sys
import time

sys.path.insert(0, "src")

import config
from coordinator import build_coordinator_options, build_sequential_coordinator_options
from loop import run_turn

config.load_env()

QUESTION = "What is the impact of AI on creative industries across visual art, music, and film?"


async def _timed(label, options):
    start = time.perf_counter()
    run = await run_turn(QUESTION, options)
    elapsed = time.perf_counter() - start
    print(f"\n----- {label} -----")
    print(f"  wall-clock s          : {elapsed:.1f}")
    print(f"  num_turns             : {run.num_turns}")
    print(f"  delegations           : {len(run.delegations)} {sorted(run.delegated_subagents)}")
    print(f"  max_parallel_delegations: {run.max_parallel_delegations} (batching intent)")
    print(f"  peak_concurrent_tasks : {run.peak_concurrent_tasks} (real overlap)")
    print(f"  subtype               : {run.subtype}")
    print(f"  total_cost_usd        : {run.total_cost_usd}")
    print(f"  subagent_total_tokens : {run.subagent_total_tokens}")
    return elapsed, run


async def main():
    print("Benchmarking parallel vs sequential on a 3-subtopic question (real API calls)...")
    seq_s, _ = await _timed("SEQUENTIAL baseline", build_sequential_coordinator_options())
    par_s, par_run = await _timed("PARALLEL (default)", build_coordinator_options())

    speedup = seq_s / par_s if par_s else float("inf")
    print("\n===== VERDICT =====")
    print(f"  sequential: {seq_s:.1f}s   parallel: {par_s:.1f}s   speedup: {speedup:.2f}x")
    if speedup > 1.0 and par_run.peak_concurrent_tasks >= 2:
        print("  ✅ parallel fan-out is faster AND subagent tasks genuinely overlapped.")
    elif speedup > 1.0:
        print("  ⚠️ parallel was faster but peak_concurrent_tasks < 2 — check background=True steering.")
    else:
        print("  ⚠️ no speedup on this sample (a single noisy API run — re-run to confirm).")


if __name__ == "__main__":
    asyncio.run(main())
