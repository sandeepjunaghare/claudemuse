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
    print("DELEGATED TO:", sorted(run.delegated_subagents))  # e.g. ['doc_analysis', 'web_search']
    print("TOOL CALLS: ", run.tool_calls)
    print("OUTCOME:    ", run.subtype)  # 'success' on a clean run
    print("TURNS:      ", run.num_turns, "(backstop is", config.MAX_TURNS_BACKSTOP, "- TR10 groundwork)")
    print("REPORT:\n")
    print(run.final_text)


if __name__ == "__main__":
    asyncio.run(main())
