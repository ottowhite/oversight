"""
Defines the `Executor` class, which is responsible for reading code snippets from
the LLM's messages, executing them, and returning the result to the LLM.

Code execution and prompting should be separate, but
for the sake of speed they're combined in this file.
"""

import re
from pathlib import Path
from textwrap import dedent
from typing import Any, TypeVar, cast

from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam
from typeguard import TypeCheckError, check_type

from .executor import AgentError, AgentResult, Executor

T = TypeVar("T")

SNIPPET_START = "<ipython>"
SNIPPET_END = "</ipython>"
SHOW_DEF_START = "<ipython_show_definition>"
SHOW_DEF_END = "</ipython_show_definition>"
RESPONSE_START = "<ipython_result>"
RESPONSE_END = "</ipython_result>"
RESPONSE_NAME = "code_executor"


def executor_message(content: str) -> ChatCompletionMessageParam:
    return {"role": "user", "name": RESPONSE_NAME, "content": content}


REPL_EXPLAINER = (
    (Path(__file__).parent / "repl_explainer.md")
    .read_text()
    .format(
        SNIPPET_START=SNIPPET_START,
        SNIPPET_END=SNIPPET_END,
        SHOW_DEF_START=SHOW_DEF_START,
        SHOW_DEF_END=SHOW_DEF_END,
        RESPONSE_START=RESPONSE_START,
        RESPONSE_END=RESPONSE_END,
        RESPONSE_NAME=RESPONSE_NAME,
    )
)

EXECUTOR_WARMUP_MESSAGES: list[ChatCompletionMessageParam] = [
    {
        "role": "user",
        "content": "As a warmup, tell me if ~/secret.md contains any numbers.",
    },
    {
        "role": "assistant",
        "content": dedent("""
        <ipython>
        import os
        try:
            content = !cat ~/secret.txt
            has_numbers = any(c.isdigit() for c in content)
            has_numbers
        except Exception as e:
            AgentError(f"Error reading file: {str(e)}")
        </ipython>
        
        Hmm, that doesn't seem to have executed, I wonder why not?
        """),
    },
    {
        "role": "user",
        "name": RESPONSE_NAME,
        "content": "Code executed successfully with no output.",
    },
    {
        "role": "assistant",
        "content": dedent("""
        Ah! A couple of learning points here:
        1. I didn't return an AgentResult, so the executor just showed me the output, instead of handing it back to the user
        2. The executor doesn't run the code until I have finished my message, so I need to send the message back to the user immediately after the code blocks.
        <ipython>has_numbers = any(c.isdigit() for c in content)</ipython>
        <ipython>AgentResult(result=has_numbers)</ipython>
        """),
    },
    {
        "role": "user",
        "name": RESPONSE_NAME,
        "content": "Multiple code blocks in one message is not allowed. **Please send one code block per message.**",
    },
    {
        "role": "assistant",
        "content": dedent("""
        <ipython>
        has_numbers = any(c.isdigit() for c in content)
        AgentResult(result=True)
        </ipython>
        """),
    },
    {
        "role": "user",
        "content": dedent("""
        Thanks, I got that result and it was correct!
        
        A point of feedback: **you didn't have to do that try/except block**.
        Just run it directly, your execution environment will catch errors and show you the result.

        Next: tell me if ~/secret.md contains any names.
        """),
    },
    {
        "role": "assistant",
        "content": dedent("""
        Hmm I have the variable `content` in my namespace already, so I don't have to read the file again.
        I could come up with a regex to detect names, and then return the result, but Python is terrible at natural language processing, so it would make more sense for me to just evaluate the variable and look at the result directly. I am an LLM after all, and perfect for natural language processing!
        <ipython>content</ipython>
        """),
    },
    {
        "role": "user",
        "name": RESPONSE_NAME,
        "content": '"Hello! This is my secret little file for Jeff\'s eyes only."',
    },
    {
        "role": "assistant",
        "content": dedent("""
        Now I've printed the contents of the file. I can see that it contains the word "Jeff" in it.
        <ipython>AgentResult(result=True)</ipython>
        """),
    },
]


class Responder:
    __executor: Executor
    __last_code: str = "iugyftcgvhbjkn"

    def __init__(self):
        self.__executor = Executor()

    def extend_ns(self, agent_inputs: dict[str, Any]):
        """
        Adds variables to the IPython namespace, returns string containing stubs.
        """
        self.__executor.extend_ns(agent_inputs)

    def get_namespace_definitions(self, var_name: str) -> str:
        """
        Get definitions for all variables in the current namespace.
        """
        return self.__executor.show_definition(var_name)

    async def respond(
        self, agent_output_type: type[T], message: ChatCompletionMessage
    ) -> ChatCompletionMessageParam | AgentResult[T]:
        # Extract the python snippet from the message
        content = message.content or ""

        # First, check for show_definition tags
        show_def_pattern = f"{re.escape(SHOW_DEF_START)}(.*?){re.escape(SHOW_DEF_END)}"
        show_def_matches = re.findall(show_def_pattern, content, re.DOTALL)

        if show_def_matches:
            # Handle show_definition tags
            if len(show_def_matches) > 1:
                return executor_message(
                    "Error: multiple show_definition tags found in message. Only one is allowed."
                )

            var_name = show_def_matches[0].strip()
            return executor_message(
                f"{self.__executor.show_definition(var_name)}\n\nIf you have questions about any of the types mentioned in the above defintion, use ipython_show_definition again on that type."
            )

        # Find all code snippets between SNIPPET_START and SNIPPET_END
        pattern = f"{re.escape(SNIPPET_START)}(.*?){re.escape(SNIPPET_END)}"
        matches = re.findall(pattern, content, re.DOTALL)

        # No code snippet found, return a message indicating this
        if not matches:
            return executor_message(
                "No Python code snippet found in the message. Remember to return an AgentResult or AgentError to send a message back to the user."
            )

        # Agent not allowed to execute multiple code snippets per message
        if len(matches) > 1:
            return executor_message(
                "Error: multiple code snippets found in message. Only one is allowed. No code was executed."
            )

        code = matches[0].strip()
        assert isinstance(code, str), "Code must be a string"

        certain = code == self.__last_code

        if not certain:
            # if code.count("\n") > 10:
            #     return executor_message(
            #         dedent("""
            #         That's quite a lot of code! Are you sure the task can't be broken down into smaller chunks and executed seperately so you can inspect the intermediate values?

            #         If you are sure you want to execute this large snippet, run the exact same snippet again, and it will be executed.
            #         """)
            #     )

            if re.search(r"\bdir\s*\(|\bhelp\s*\(", code):
                return executor_message(
                    dedent("""
                    No code was executed.
                    You have access to the `show_definition` function, which is usually more useful than `dir`/`help,
                    if you are confident that you want to use `dir`/`help` instead of `show_definition`, then execute the same snippet again.
                    """)
                )

            pass

        self.__last_code = code

        # Execute the code using the Executor
        output, result = await self.__executor.execute_code(code)

        # Terminal cases: agent has returned a result or errored.
        ret_type_error = None

        # Cast required because pyright interprets .result as None
        match cast(Any, result):
            case AgentResult(result=agent_result):
                try:
                    # Verify the agent returned a value of the correct type
                    agent_result = check_type(agent_result, agent_output_type)

                    return AgentResult(result=agent_result)
                except TypeCheckError:
                    ret_type_error = f"Result type {agent_result} does not match expected type {agent_output_type}"
            case AgentError() as error:
                raise error

        # Build response string
        response = output
        if ret_type_error is not None:
            if response:
                response += "\n\n"
            response += ret_type_error

        # Get rid of memory addresses (they cause non-deterministic output and cache misses)
        response = re.sub(r"0x[0-9a-fA-F]+", "0x...", response)

        # Truncate to last 1000 characters if too long
        MAX_MESSAGE_LENGTH = 4000
        if len(response) > MAX_MESSAGE_LENGTH:
            keep = MAX_MESSAGE_LENGTH // 2
            head, mid, last = response[:keep], response[keep:-keep], response[-keep:]
            response = f"{head}\n\n...{len(mid)} characters omitted...\n\n{last}"

        if not response:
            response = "Code executed successfully with no output."

        return executor_message(response)
