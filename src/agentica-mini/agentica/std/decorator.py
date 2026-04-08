"""
Standard library functions which users can use instead of
interacting directly with the primitives.
"""

import asyncio
import inspect
from typing import Any, Awaitable, Callable, TypeVar, cast

from ..agent import Agent
from ..runtime import local_runtime
from ..stubs import emit_stubs

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _map_args_to_params(
    sig: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    extra_ns: dict[str, Any] | None = None,
    skip_self: bool = False,
) -> dict[str, Any]:
    """
    Helper function to map positional args and kwargs to parameter names based on function signature.
    """
    param_names = list(sig.parameters.keys())
    if skip_self and param_names and param_names[0] == "self":
        param_names = param_names[1:]  # Skip 'self' parameter

    # Start with extra namespace
    mapped_ns = extra_ns.copy() if extra_ns else {}

    # Map positional args to parameter names
    for i, arg in enumerate(args):
        if i < len(param_names):
            mapped_ns[param_names[i]] = arg

    # Add kwargs that match function parameters
    for k, v in kwargs.items():
        if k in sig.parameters:
            mapped_ns[k] = v

    return mapped_ns


def magic_class(**extra_ns: Any) -> Callable[[type], type]:
    def wrap(target_class: type) -> type:
        """
        Turns a class into a magic class.
        """

        class MagicClass:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                # Get constructor signature to map args to parameter names
                sig = inspect.signature(target_class.__init__)
                constructor_ns = _map_args_to_params(
                    sig, args, kwargs, extra_ns, skip_self=True
                )
                # constructor_ns[target_class.__name__] = target_class

                # Store initialization parameters for lazy agent creation
                self.__system_prompt = f"""
You are an instance of a PYTHON OBJECT with the following signature:

<ipython_stub>
{emit_stubs({target_class.__name__: target_class})[0]}
</ipython_stub>

The user will "call methods" on you in user messages, and you are to respond with what you think the method WOULD return, if it was actually called.

you do not have access to an instance of this class, AND YOU DON'T NEED ONE TO SIMULATE IT, because your job is just to simulate what the methods would return, not call them directly.

Each time a method is called
1. Update internal state (your REPL variables) to reflect the method call. This will involve speculating on what datastructures will be useful.
2. Return (with AgentResult) the value that the method would return. You will have to execute python in order to construct this result.
"""
                self.__constructor_ns = constructor_ns
                self.__agent: Agent | None = None

            async def _get_agent(self) -> Agent:
                """Lazy initialization of the agent."""
                if self.__agent is None:
                    self.__agent = await local_runtime.spawn_agent(
                        self.__system_prompt,
                        **self.__constructor_ns,
                    )
                return self.__agent

            def __getattr__(self, name: str) -> Any:
                # TODO: Check if attr is sync or async, and make a different fake_method for each.

                async def fake_method(*args: Any, **kwargs: Any) -> Any:
                    real_method = getattr(target_class, name)
                    # Get method signature to map args to parameter names
                    sig = inspect.signature(real_method)
                    method_ns = _map_args_to_params(sig, args, kwargs, skip_self=True)

                    agent = await self._get_agent()
                    return await agent.call(
                        real_method.__annotations__["return"]
                        if "return" in real_method.__annotations__
                        else None,
                        f"""
What would the following method return? (bear in mind all previous operations that have been performed on the class)

<method_stub>
{emit_stubs({real_method.__name__: real_method})[0]}
</method_stub>

Return the value that the method would return, the arguments have been added to your namespace.
                        """,
                        **method_ns,
                    )

                return fake_method

        return MagicClass

    return wrap


def magic_fn(**extra_ns: Any) -> Callable[[F], F]:
    """
    Decorator which turns a function into an single-use agent,
    using the function's docstring as the user prompt,
    and type annotations to control what can be passed to the agent.

    Example usage:
    ```python
    @magic_fn()
    async def compare_cvs_swe(cv_a: str, cv_b: str) -> Literal["a is better", "roughly equal", "b is better"]:
        \"""
        Takes two CVs in markdown format, and returns a string indicating which candidate is probably a better software engineer.
        \"""
        ...

    # Read CVs from disk
    cv_a, cv_b = ...

    # Use an LLM to compare CVs
    result = await compare_cvs_swe(cv_a, cv_b)
    ```
    """

    def wrap(fn: F) -> F:
        assert inspect.iscoroutinefunction(fn), (
            "magic can only be used on coroutine functions"
        )

        async def run_agent_lazy(*args: Any, **kwargs: Any) -> Any:
            agent = await local_runtime.spawn_agent()

            # Get function signature to map args to parameter names
            sig = inspect.signature(fn)
            added_ns = _map_args_to_params(sig, args, kwargs, extra_ns)

            return await agent.call(
                sig.return_annotation,
                f"""
You are to behave like the following function:

{emit_stubs({fn.__name__: fn})[0]}

The user has called this function with certain arguments, which have been added to your namespace.

What should the function return for these inputs?
                """,
                **added_ns,
            )

        def run_agent(*args, **kwargs) -> Awaitable[Any]:
            return asyncio.create_task(run_agent_lazy(*args, **kwargs))

        return cast(F, run_agent)

    return wrap
