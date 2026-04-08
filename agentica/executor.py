"""
Defines the `Executor` class, which is responsible for pure code execution
in an IPython environment. This class handles only the execution aspect,
without any knowledge of chat messages or response formatting.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

from agentica.stubs import emit_stubs

from .utils.capture import capture_output


class AgentError(Exception):
    """Exception that the agent should raise when it cannot complete a task."""

    reason: str

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class AgentResult[T]:
    result: T


class Executor:
    """Pure code execution engine using IPython."""

    __ipython: InteractiveShell

    # Variables required to field "follow up" show defintion calls
    __required_context: dict[str, Any]

    def __init__(self):
        self.__ipython = InteractiveShell()
        self.__ipython.autoawait = True  # Enables top-level await
        self.__ipython.colors = "nocolor"  # Disables terminal colors

        self.__required_context = {}

        self.extend_ns(
            {
                "AgentResult": AgentResult,
                "AgentError": AgentError,
            }
        )

    def extend_ns(self, variables: dict[str, Any]) -> None:
        """Add variables to the execution namespace."""
        self.__required_context.update(variables)
        self.__ipython.user_ns.update(variables)

    async def execute_code(self, code: str) -> tuple[str, Any]:
        """Execute Python code and return (output, result).

        Args:
            code: Python code string to execute

        Returns:
            tuple[str, Any]: (combined stdout/stderr output, return value)

        Raises:
            AgentError: If the code explicitly raised an AgentError
        """
        result = None

        try:
            with capture_output() as captured:
                # Execute the code using IPython with timeout
                exec_result = await asyncio.wait_for(
                    self.__ipython.run_cell_async(code), timeout=100.0
                )
                result = exec_result.result

            # Combine stdout and stderr
            output_parts = []
            if captured.stdout:
                output_parts.append(captured.stdout.strip())
            if captured.stderr:
                output_parts.append(captured.stderr.strip())

            combined_output = "\n".join(output_parts)

            return combined_output, result
        except asyncio.TimeoutError:
            return "Execution timed out after 10s", None

    def show_definition(self, var_name: str) -> str:
        """
        Handle show_definition tags by parsing variable name and showing its definition.
        Only allows a single variable name, or empty to show all variables.
        """
        var_name = var_name.strip()

        # If empty, show all variables
        if not var_name:
            display, context = emit_stubs(self.__required_context)
            self.__required_context.update(context)
            return display if display else "No variables defined."

        # Check for multiple variables (comma-separated)
        if not var_name.isidentifier():
            return "Error: only exact variable names are allowed in show_definition tags, not arbitrary expressions."

        # Check if variable exists in namespace
        var_value = None
        if var_name in self.__required_context:
            var_value = self.__required_context[var_name]
        elif var_name in self.__ipython.user_ns:
            var_value = self.__ipython.user_ns[var_name]
        else:
            return f"Variable not found: {var_name}"

        # Show the single variable
        display, context = emit_stubs({var_name: var_value})
        self.__required_context.update(context)

        return f"As well as the default python builtins, the following variables are defined:\n\n{display}"
