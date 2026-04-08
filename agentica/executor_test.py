#!/usr/bin/env python3
"""
Tests for the Responder class, particularly the new ipython_show_definition tags.
"""

import asyncio
from typing import Union

from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam

from .responder import AgentResult, Responder


def print_result(
    result: Union[ChatCompletionMessageParam, AgentResult], test_name: str
):
    """Helper function to print test results safely."""
    print(f"{test_name}:")
    if isinstance(result, dict) and "content" in result:
        print(result["content"])
    elif isinstance(result, AgentResult):
        print(f"AgentResult: {result.result}")
    else:
        print(f"Unexpected result type: {type(result)}")
    print()


async def test_show_definition_tags():
    """Test the new show_definition tag functionality."""
    executor = Responder()

    # Set up some test variables
    executor.extend_ns(
        {"test_var": 42, "test_str": "hello world", "test_list": [1, 2, 3]}
    )

    print("Testing ipython_show_definition tags...")
    print("=" * 50)

    # Test 1: Show single variable
    message1 = ChatCompletionMessage(
        role="assistant",
        content="<ipython_show_definition>test_var</ipython_show_definition>",
    )

    result1 = await executor.respond(str, message1)
    print_result(result1, "Test 1 - Single variable")

    # Test 2: Show all variables (empty tag)
    message2 = ChatCompletionMessage(
        role="assistant", content="<ipython_show_definition></ipython_show_definition>"
    )

    result2 = await executor.respond(str, message2)
    print_result(result2, "Test 2 - All variables")

    # Test 3: Non-existent variable
    message3 = ChatCompletionMessage(
        role="assistant",
        content="<ipython_show_definition>nonexistent</ipython_show_definition>",
    )

    result3 = await executor.respond(str, message3)
    print_result(result3, "Test 3 - Non-existent variable")

    # Test 4: Multiple variables (should fail)
    message4 = ChatCompletionMessage(
        role="assistant",
        content="<ipython_show_definition>test_var, test_str</ipython_show_definition>",
    )

    result4 = await executor.respond(str, message4)
    print_result(result4, "Test 4 - Multiple variables (should error)")

    # Test 5: Multiple show_definition tags (should fail)
    message5 = ChatCompletionMessage(
        role="assistant",
        content="<ipython_show_definition>test_var</ipython_show_definition><ipython_show_definition>test_str</ipython_show_definition>",
    )

    result5 = await executor.respond(str, message5)
    print_result(result5, "Test 5 - Multiple show_definition tags (should error)")

    # Test 6: Regular ipython code still works
    message6 = ChatCompletionMessage(
        role="assistant", content="<ipython>x = 100\nprint(f'x is {x}')</ipython>"
    )

    result6 = await executor.respond(str, message6)
    print_result(result6, "Test 6 - Regular ipython code")

    # Test 7: Show the new variable we just created
    message7 = ChatCompletionMessage(
        role="assistant", content="<ipython_show_definition>x</ipython_show_definition>"
    )

    result7 = await executor.respond(str, message7)
    print_result(result7, "Test 7 - Show newly created variable")


async def test_backward_compatibility():
    """Test that regular ipython tags still work as before."""
    executor = Responder()

    print("Testing backward compatibility...")
    print("=" * 50)

    # Test regular code execution
    message = ChatCompletionMessage(
        role="assistant",
        content="<ipython>result = 2 + 3\nAgentResult(result=result)</ipython>",
    )

    result = await executor.respond(int, message)
    print_result(result, "Backward compatibility test")


if __name__ == "__main__":

    async def main():
        await test_show_definition_tags()
        await test_backward_compatibility()
        print("All tests completed!")

    asyncio.run(main())
