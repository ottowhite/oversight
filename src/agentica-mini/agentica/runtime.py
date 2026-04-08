"""
Defines the `Runtime` class, which is responsible for spawning agents.
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Callable, Literal

from dotenv import load_dotenv

from agentica import logging
from agentica.cache import RequestCache, local_cache

from . import models
from .agent import Agent, AgentListener, find_current_agent
from .models import Model, openrouter

load_dotenv()


# Terminal color constants
COLORS = [
    "\033[95m",  # Magenta/Pink
    "\033[94m",  # Blue
    "\033[91m",  # Red
    "\033[92m",  # Green
    "\033[93m",  # Yellow
    "\033[96m",  # Cyan
    "\033[90m",  # Dark Gray
    "\033[35m",  # Purple
    "\033[36m",  # Teal
    "\033[33m",  # Orange/Brown
    "\033[31m",  # Dark Red
]
RESET = "\033[0m"
GREY = "\033[90m"

# Global list to track names and their assigned colors
_name_registry: list[str] = []

DEFAULT_PREMISE = """
You are a helpful assistant which answers user queries and solves tasks from the user.

In solving these tasks you will typically run a series of python snippets, which is the primary way you interact with the world and your user.
"""

# Toggle for terminal coloring in agent output
RUNTIME_LOGS_TO_STDOUT = True

RUNTIME_LOGS_DIR = Path("logs_runtime")


def _get_color_for_name(name: str) -> str:
    """Get the appropriate color for a name based on its position in the registry."""
    if name not in _name_registry:
        _name_registry.append(name)

    name_index = _name_registry.index(name)
    color_index = name_index % len(COLORS)
    return COLORS[color_index]


def _colorize_names(text: str) -> str:
    """Apply colors to User and Agent names in the text using regex."""

    def replace_name(match):
        name = match.group(0)
        color = _get_color_for_name(name)
        return f"{color}{name}{RESET}"

    # Regex to match "User" or "Agent X" (where X is a number)
    pattern = r"(?:User|Agent \d+)\b"
    return re.sub(pattern, replace_name, text)


class RuntimeListener:
    """Listener that writes runtime messages to a file."""

    __file_path: Path
    __runtime_id: int
    __log_queue: asyncio.Queue[str]
    __listening: bool
    print_logs: bool

    def __init__(self, runtime_id: int):
        RUNTIME_LOGS_DIR.mkdir(exist_ok=True)
        self.__file_path = RUNTIME_LOGS_DIR / f"runtime_{runtime_id}.log"
        self.__runtime_id = runtime_id
        self.__listening = False
        self.__log_queue = asyncio.Queue()
        self.print_logs = RUNTIME_LOGS_TO_STDOUT

    async def __ensure_listening(self):
        """Ensure the log listening task is started."""
        if not self.__listening:
            self.__listening = True
            asyncio.create_task(self.__listen_logs())

    async def __listen_logs(self) -> None:
        """Listen for log messages and process them."""
        while True:
            log_line = await self.__log_queue.get()

            # Also print to stdout if colors are enabled (for terminal output)
            if self.print_logs:
                print(_colorize_names(log_line))

            # Remove all ansi escape codes
            log_line = re.sub(r"\x1b\[[0-9;]*[mK]", "", log_line)

            # Write to file
            with open(self.__file_path, "a") as f:
                f.write(f"{log_line}\n")

    async def agent_spawned(self, agent_id: int) -> AgentListener:
        """Create and return an AgentListener for a newly spawned agent."""
        await self.__ensure_listening()

        # Log the agent spawn with full path to its log file
        agent_log_file = Path("logs_agent") / f"agent_{agent_id}.log"
        spawn_message = f"{GREY}Spawned{RESET} Agent {agent_id} {GREY}({agent_log_file.absolute()}){RESET}"
        self.__log_queue.put_nowait(spawn_message)

        # Try to detect if we're currently executing inside an agent
        parent_agent = find_current_agent()
        parent_agent_id = parent_agent and parent_agent.id

        return AgentListener(
            agent_id, self.__runtime_id, self.__log_queue.put_nowait, parent_agent_id
        )


class AgentRuntime:
    id: int

    __default_model: Model
    __agent_counter: int
    __agent_logs_dir: Path

    def __init__(self, default_model: Model, cache: RequestCache | None = None):
        self.__cache = cache
        self.__default_model = default_model
        self.__agent_logs_dir = Path("logs_agent")

        # Ensure logs directory exists
        self.__agent_logs_dir.mkdir(exist_ok=True)

        # Ensure runtime logs directory exists
        RUNTIME_LOGS_DIR.mkdir(exist_ok=True)

        # Assign runtime ID based on existing runtime logs
        self.id = self._get_next_runtime_id()

        # Create listener with runtime ID and log creation
        self.__listener = RuntimeListener(self.id)

        # Initialize agent counter to highest existing agent number + 1
        self.__agent_counter = self._get_highest_agent_number()

    def _get_next_runtime_id(self) -> int:
        """Scan the runtime logs directory for existing runtime files and return the next runtime ID."""
        highest_number = 0
        runtime_pattern = re.compile(r"^runtime_(\d+)\.log$")

        for log_file in RUNTIME_LOGS_DIR.glob("runtime_*.log"):
            match = runtime_pattern.match(log_file.name)
            if match:
                runtime_number = int(match.group(1))
                highest_number = max(highest_number, runtime_number)

        return highest_number + 1

    def _get_highest_agent_number(self) -> int:
        """Scan the logs directory for existing agent files and return the highest agent number."""
        highest_number = 0
        agent_pattern = re.compile(r"^agent_(\d+)\.log$")

        for log_file in self.__agent_logs_dir.glob("agent_*.log"):
            match = agent_pattern.match(log_file.name)
            if match:
                agent_number = int(match.group(1))
                highest_number = max(highest_number, agent_number)

        return highest_number

    async def spawn_agent(
        self,
        premise: str = DEFAULT_PREMISE,
        model: Model | Literal["auto"] = "auto",
        chunk_listener: Callable[[], logging.AgentListener] | None = None,
        **init_ns: Any,
    ) -> Agent:
        """
        Makes a new agent with a continuous conversation history and a REPL.

        The default system_prompt and model are usually sufficient for the task,
        only override them if they are failing.

        The init_ns are variables that are available to the agent, pass anything
        you want the agent to have access to in via these kwargs.

        Example:
        ```python
        agent = runtime.spawn_agent(
            foo=lambda x: x + 42
        )
        result = await agent.call(int, "Does foo return when you pass it 0?", int)
        assert result == 42
        ```

        Agents get stupider the longer their context window gets, so if a task
        doesn't require context from the previous calls, **SPAWN A NEW AGENT**.

        Spawning an agent is cheap, so don't be afraid to do it.
        """
        # Create a unique log file for this agent
        self.__agent_counter += 1
        agent_id = self.__agent_counter

        listener = await self.__listener.agent_spawned(agent_id)

        selected_model = self.__default_model if model == "auto" else model

        if self.__cache is not None:
            self.__cache.hook_openai(selected_model.client)
        return Agent(
            selected_model, premise, listener, agent_id, chunk_listener, **init_ns
        )

    async def __auto_select_model(self, user_prompt: str) -> Model:
        selector_agent = await self.spawn_agent(
            """You are an LLM selector. You pick the appropriate model for a given task.
            
            Model selection guidance:
            - For the most complex tasks, like long-horizon tasks involving the orchestration of many sub agents, use sonnet-4
            - For medium complexity tasks, like writing/reading code, use gpt-4.1
            - For simple tasks, like quick calculations or listeners, use Qwen3""",
            model=models.CLUSTER_QWEN3,
            sonnet_4=models.CLAUDE_SONNET_4,
            gpt_4_1=models.OPENAI_4_1,
            qwen3=models.CLUSTER_QWEN3,
        )

        return await selector_agent.call(
            Model,
            f"""What would be the best model to deal with the following user query:
            
            ```
            {user_prompt}
            ```""",
        )

    def print_logs(self, enabled: bool) -> None:
        self.__listener.print_logs = enabled


# Gets keys from env variables, usually a .env
local_runtime = AgentRuntime(models.CLAUDE_SONNET_4, local_cache)

type ModelStrings = Literal[
    "openai:gpt-3.5-turbo",
    "openai:gpt-4o",
    "openai:gpt-4.1",
    "openai:gpt-5",
    "anthropic:claude-sonnet-4",
    "anthropic:claude-opus-4.1",
    "anthropic:claude-sonnet-4.5",
]


async def spawn(
    premise: str | None = None,
    scope: dict[str, Any] | None = None,
    *,
    # system: str | None = None,
    # mcp: str | None = None,
    # mode: Literal["code"] = "code",
    model: str = "openai:gpt-4.1",  # default to copy main-agentica, but sonnet-4.5 is reccomended as performs better
    listener: Callable[[], logging.AgentListener] | None = None,
    # max_tokens: int = 2048,
    # _logging: bool = False,
    # _call_depth: int = 0,
) -> Agent:
    model_obj = openrouter(model.replace(":", "/"))

    scope = scope or {}

    return await local_runtime.spawn_agent(
        premise=premise or DEFAULT_PREMISE,
        model=model_obj,
        chunk_listener=listener,
        **scope,
    )
