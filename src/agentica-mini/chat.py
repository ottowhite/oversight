"""
Example output:

➜  ~/repos/situ/prototypes/simple-situ git:(charlie/simple-situ) ✗ uv run python -m chat
Send empty message to end the chat.
User: Hello!
Agent: Hello! I'm ready to assist you.
User: What is the time?
Agent: 2025-08-06 12:35:29
User: What is the 32nd power of 3?
Agent: 1853020188851841
User:
➜  ~/repos/situ/prototypes/simple-situ git:(charlie/simple-situ) ✗
"""

import asyncio

import dotenv

from agentica import AgentError, local_runtime, spawn
from agentica.logging import AgentListener
from agentica.logging.loggers.stream_logger import StreamLogger

dotenv.load_dotenv()

RED = "\033[91m"
GREEN = "\033[92m"
PURPLE = "\033[95m"
RESET = "\033[0m"
GREY = "\033[90m"

# Spawn a sub agent, and get it to work out the 32nd power of 3


async def chat():
    print("Send empty message to end the chat.")

    local_runtime.print_logs(False)

    # Stream intermediate "thinking" to console
    async def on_chunk(chunk):
        print(chunk, end="", flush=True)

    listener = AgentListener(StreamLogger(on_chunk=on_chunk))

    agent = await spawn(
        # model="google/gemini-3-pro-preview",
        # model="anthropic/claude-opus-4.5",
        # model="x-ai/grok-4.1-fast",
        scope={"spawn_agent": local_runtime.spawn_agent},
        listener=lambda: listener,
    )

    while user_input := input(f"\n{PURPLE}User{RESET}: "):
        try:
            # Invoke agent against user prompt
            print(GREY)
            result = await agent.call(str, user_input)
            print(RESET)

            # Print final result
            print(f"\n{GREEN}Agent{RESET}: {result}")

        except AgentError as agent_error:
            print(f"\n{RED}AgentError: {agent_error.reason}{RESET}")

    print("\nExiting...")


if __name__ == "__main__":
    asyncio.run(chat())
