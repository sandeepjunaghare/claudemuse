"""Multi-turn example: a persistent session that carries case facts across turns.

`run_conversation` opens one ClaudeSDKClient session, so verified identity, case
facts, and history persist across turns (TR9 / FR6) — turn 2 recalls the exact
order id and amount from turn 1 via the injected case-facts block.

Run from the project root with the shared venv:
    /Users/sandeep/Dropbox/dev/experiments/claudemuse/.venv/bin/python run_conversation_example.py
"""

import asyncio
import sys

sys.path.insert(0, "src")

import config
from agent import build_options
from session import run_conversation

config.load_env()


async def main():
    convo = await run_conversation(
        [
            "Hi, I'm Alice Wong, alice@example.com — what's the status of order O1001?",
            "Thanks — remind me the exact amount and order number.",
        ],
        build_options(),
    )
    for i, turn in enumerate(convo.turns, 1):
        print(f"--- turn {i} ---")
        print("TOOLS:", turn.tool_calls)
        print("REPLY:", turn.final_text)
        print()


if __name__ == "__main__":
    asyncio.run(main())
