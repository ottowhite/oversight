"""
Defines the `Agent` class, which represents a (chat history, repl state) pair and
defines the central (inference -> execute -> inference -> ...) loop.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, TypedDict, TypeVar

from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam

from agentica import logging
from agentica.logging.loggers.stream_logger import Chunk
from agentica.models import Model

from .responder import (
    EXECUTOR_WARMUP_MESSAGES,
    REPL_EXPLAINER,
    AgentError,
    AgentResult,
    Responder,
)
from .stubs import clean_type_name, emit_stubs

T = TypeVar("T")

MAX_TOOL_USES = 25

NONE_FUTURE = asyncio.Future()
NONE_FUTURE.set_result(None)
NON_FUTURE_FUNCTION = lambda _: NONE_FUTURE


AGENT_LOGS_DIR = Path("logs_agent")

LOG_INITIAL_MESSAGES = False


class InferenceStats(TypedDict):
    input_toks: int | None
    output_toks: int | None
    total_time_s: float
    model: str


ModelSelector = Model | Callable[[str], Awaitable[Model]]


class Agent:
    __model_selector: ModelSelector
    __responder: Responder
    __chat_history: list[ChatCompletionMessageParam]
    __listener: "AgentListener"
    __current_completion_content: str | None
    id: int

    def __init__(
        self,
        model: ModelSelector,
        premise: str,
        listener: "AgentListener",
        agent_id: int,
        chunk_listener: Callable[[], logging.AgentListener] | None = None,
        **init_ns: Any,
    ):
        self.__model_selector = model
        self.__responder = Responder()  # could be a remote object
        self.__responder.extend_ns({"self": self})  # Allows agents to call themselves
        self.__chat_history = []
        self.__listener = listener
        self.__current_completion_content = None
        self.id = agent_id
        self.__chunk_listener = chunk_listener

        premise += f"\n\n{REPL_EXPLAINER}"

        if len(init_ns) > 0:
            self.__responder.extend_ns(init_ns)
            premise += f"\n\n**Your namespace is pre-populated with the following variables:**\n\n{
                '\n\n'.join(
                    self.__responder.get_namespace_definitions(var) for var in init_ns
                )
            }"

        initial_messages = [
            {"role": "system", "content": premise},
            *EXECUTOR_WARMUP_MESSAGES,
        ]
        if LOG_INITIAL_MESSAGES:
            for message in initial_messages:
                self.__listener.message_added(message)
        self.__chat_history.extend(initial_messages)

    def __add_messages(
        self,
        *messages: ChatCompletionMessageParam,
        inference_stats: InferenceStats | None = None,
    ) -> None:
        for message in messages:
            self.__listener.message_added(message, inference_stats)
            self.__chat_history.append(message)

    def call(
        self, agent_output_type: type[T] | Any, user_prompt: str, **agent_inputs: Any
    ) -> Awaitable[T]:
        """
        Invokes the agent with a user prompt and returns the result.

        The agent is prompted to return of the correct type, so specify the return type if you want something specific.

        IF YOU WANT AN AGENT TO CONSTRUCT AN OBJECT, MAKE SURE TO PASS IT THE OBJECT SO IT CAN USE THE CONSTRUCTOR.

        Example:
        ```python
        res = await agent.call(int, "What is 1 + x?", x=5) # kwargs are added as variables in the agents REPL
        assert res == 6
        ```
        """
        # If this agent has a chunk listener, use streaming to populate it gradually
        on_stream: Callable[[str | None], Awaitable[None]] = NON_FUTURE_FUNCTION
        if self.__chunk_listener is not None:
            listener = self.__chunk_listener()
            on_stream = lambda chunk_content: listener.logger.on_chunk(
                Chunk(role="agent", content=chunk_content or "")
            )

        return asyncio.create_task(
            self._call_lazy(agent_output_type, user_prompt, on_stream, **agent_inputs)
        )

    def call_stream(
        self, agent_output_type: type[T] | Any, user_prompt: str, **agent_inputs: Any
    ) -> tuple[Awaitable[T], AsyncIterator[str]]:
        """
        Just like `call`, but also returns an async iterator of the agent's internal textual output.
        """
        content_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def content_iterator() -> AsyncIterator[str]:
            while True:
                content = await content_queue.get()
                if content is None:  # End of stream signal
                    break
                # print(content, end="", flush=True)
                yield content

        task = asyncio.create_task(
            self._call_lazy(
                agent_output_type,
                user_prompt,
                on_stream=content_queue.put,
                **agent_inputs,
            )
        )

        return task, content_iterator()

    async def __create_completion(
        self, model: Model, on_stream: Callable[[str | None], Awaitable[None]]
    ):
        """
        Creates a completion from the model, using streaming only if someone is listening.
        Stores the full content in __current_completion_content and returns inference statistics.
        """
        start_time = time.time()

        full_content = None
        if on_stream is not NON_FUTURE_FUNCTION:
            # Streaming path - someone is listening for incremental updates
            stream = await model.client.chat.completions.create(
                model=model.id,
                messages=self.__chat_history,
                extra_body=model.extra_body,
                stream=True,
            )

            content_parts = []
            input_tokens = None
            output_tokens = None

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    content_delta = chunk.choices[0].delta.content
                    content_parts.append(content_delta)
                    await on_stream(content_delta)

                # Capture usage information from the final chunk
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens
                    output_tokens = chunk.usage.completion_tokens

            full_content = "".join(content_parts)
        else:
            # Batch path - no one is listening, get the whole response at once
            response = await model.client.chat.completions.create(
                model=model.id,
                messages=self.__chat_history,
                extra_body=model.extra_body,
                stream=False,
            )  # listener makes things vibrant, can be swapped out for pure json

            self.__current_completion_content = (
                response.choices[0].message.content or ""
            )
            input_tokens = response.usage.prompt_tokens if response.usage else None
            output_tokens = response.usage.completion_tokens if response.usage else None
            full_content = response.choices[0].message.content or ""

        end_time = time.time()

        self.__add_messages(
            {"role": "assistant", "content": full_content},
            inference_stats={
                "input_toks": input_tokens,
                "output_toks": output_tokens,
                "total_time_s": end_time - start_time,
                "model": model.id,
            },
        )

        return full_content

    async def _call_lazy(
        self,
        agent_output_type: type[T] | Any,
        user_prompt: str,
        on_stream: Callable[[str | None], Awaitable[None]] = NON_FUTURE_FUNCTION,
        **agent_inputs: Any,
    ) -> T:
        self.__listener.call_enter(user_prompt)

        context = {}
        type_name = clean_type_name(agent_output_type, context)
        self.__responder.extend_ns(context)
        user_prompt += f"\n\nWhen you have completed your task or query, return an instance of AgentResult[{type_name}]."

        # Select appropriate model for this task
        model = self.__model_selector
        if not isinstance(model, Model):
            model = await model(user_prompt)

        # Add python variables to that chat
        if len(agent_inputs) > 0:
            stubs, context = emit_stubs(agent_inputs)
            user_prompt += f"\n\nThe following variables have been added to your namespace:\n\n{stubs}"
            self.__responder.extend_ns(agent_inputs)

        self.__add_messages({"role": "user", "content": user_prompt})

        try:
            for _ in range(MAX_TOOL_USES):
                # INFERENCE - use new __create_completion method
                full_content = await self.__create_completion(model, on_stream)

                # EXECUTION
                try:
                    # Create a message object from the content
                    message = ChatCompletionMessage(
                        role="assistant", content=full_content
                    )
                    match await self.__responder.respond(agent_output_type, message):
                        case AgentResult(result=result):
                            self.__listener.call_exit(result)
                            return result  # breaks out of the execution loop
                        case executor_message:
                            assert "content" in executor_message and isinstance(
                                executor_message["content"], str
                            ), "Responder didn't return any content"
                            await on_stream(
                                f"\n<ipython_result>{executor_message['content']}</ipython_result>\n\n"
                            )

                            self.__add_messages(executor_message)
                except AgentError as e:
                    # Tag the error with the agent id
                    raise AgentError(f"Agent {self.id}: {e.reason}")
                finally:
                    # Clear the completion content after processing
                    self.__current_completion_content = None

            # NOTE: Agent IDs are non-deterministic, so this is a potential source of non-determinism and cache misses.
            raise AgentError(
                f"Agent {self.id}: Failed to complete task within {MAX_TOOL_USES} attempts"
            )
        finally:
            # Always signal end of stream if streaming
            await on_stream(None)  # None signals end of stream

    def history(self) -> list[ChatCompletionMessageParam]:
        """
        Returns the chat history of the agent.

        This is often very long, so it usually makes sense to just grab the last few messages:

        ```python
        last_messages = agent.history()[-10:]
        ```
        """
        return self.__chat_history


def find_current_agent() -> "Agent | None":
    """Find the currently executing agent in the call stack."""
    import inspect

    cur_frame = inspect.currentframe()
    call_code = Agent._call_lazy.__code__

    while cur_frame is not None:
        if (
            cur_frame.f_code == call_code
            and "self" in cur_frame.f_locals
            and isinstance(cur_frame.f_locals["self"], Agent)
        ):
            return cur_frame.f_locals["self"]
        cur_frame = cur_frame.f_back

    return None


def make_name(agent_id: int | None) -> str:
    return "User" if agent_id is None else f"Agent {agent_id}"


class AgentListener:
    """Listener that writes agent messages to a file."""

    __file_path: Path
    __on_runtime_log: Callable[[str], None]
    __runtime_id: int
    __agent_id: int
    __parent_agent_id: int | None

    def __init__(
        self,
        agent_id: int,
        runtime_id: int,
        on_runtime_log: Callable[[str], None],
        parent_agent_id: int | None = None,
    ):
        AGENT_LOGS_DIR.mkdir(exist_ok=True)
        self.__file_path = AGENT_LOGS_DIR / f"agent_{agent_id}.log"
        self.__on_runtime_log = on_runtime_log
        self.__runtime_id = runtime_id
        self.__agent_id = agent_id
        self.__parent_agent_id = parent_agent_id

    def message_added(
        self,
        message: ChatCompletionMessageParam,
        inference_stats: InferenceStats | None = None,
    ) -> None:
        """Write a message to the log file in XML format."""
        assert "content" in message, "Message must have content"
        content = str(message["content"])

        attrs: dict[str, Any] = dict(message)
        if inference_stats is not None:
            attrs.update(inference_stats)

        attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items() if k != "content")

        with open(self.__file_path, "a") as f:
            f.write(
                f"<message {attr_str}>\n\t{content.replace('\n', '\n\t')}\n</message>\n"
            )

    def call_enter(self, user_prompt: str) -> None:
        current_name = make_name(self.__agent_id)
        caller_name = make_name(self.__parent_agent_id)

        # Call runtime log callback
        self.__on_runtime_log(f"{caller_name} ►  {current_name}: {user_prompt}")

    def call_exit(self, result: Any) -> None:
        current_name = make_name(self.__agent_id)
        caller_name = make_name(self.__parent_agent_id)

        # Call runtime log callback
        self.__on_runtime_log(f"{caller_name} ◄  {current_name}: {result}")
