"""Minimal one-shot example: resolve a single customer message end-to-end.

Run from the project root with the shared venv:
    /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python run_example.py
"""

import asyncio
import sys

sys.path.insert(0, "src")

import config
from agent import build_options
from loop import run_turn

config.load_env()


async def main():
    run = await run_turn(
        "Hi, I'm Alice Wong (alice@example.com). What's the status of order O1001?",
        build_options(),
    )
    print("TOOLS: ", run.tool_calls)   # e.g. ['get_customer', 'lookup_order']
    print("OUTCOME:", run.subtype)     # 'success' on a clean resolution
    print("REPLY: ", run.final_text)


if __name__ == "__main__":
    asyncio.run(main())
