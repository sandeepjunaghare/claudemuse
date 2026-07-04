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
    print("REPORT:\n")
    print(run.final_text)


if __name__ == "__main__":
    asyncio.run(main())
