import asyncio, sys
sys.path.insert(0, "src")
import config; config.load_env()
from agent import build_options
from session import run_conversation

async def main():
    options = build_options()
    history = []
    print("Customer-support agent. Type 'quit' to exit.")
    while True:
        msg = input("you> ").strip()
        if msg.lower() in {"quit", "exit"}:
            break
        history.append(msg)
        convo = await run_conversation(history, options)   # replays full history
        print("agent>", convo.turns[-1].final_text)

asyncio.run(main())