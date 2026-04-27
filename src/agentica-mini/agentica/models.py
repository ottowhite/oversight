import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


@dataclass
class Model:
    id: str
    client: AsyncOpenAI
    extra_body: object | None = None


CLUSTER_QWEN3 = Model(
    id="s3://models/Qwen/Qwen3-235B-A22B-Instruct-2507",
    client=AsyncOpenAI(base_url="http://10.141.3.26:8000/v1", api_key="EMPTY"),
)

GEMINI_FLASH = Model(
    id="google/gemini-2.5-flash",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
)

OPENROUTER_QWEN3 = Model(
    id="qwen/qwen3-235b-a22b-2507",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
)

CEREBRAS_QWEN3 = Model(
    id="qwen/qwen3-235b-a22b-2507",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
    extra_body={"provider": {"order": ["cerebras"], "allow_fallbacks": False}},
)

BASETEN_DEEPSEEK_V3 = Model(
    id="deepseek/deepseek-chat-v3-0324",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
    # extra_body={"provider": {"order": ["baseten"], "allow_fallbacks": False}},
)

AUTO = Model(
    id="openrouter/auto",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
)

OPENAI_O4_MINI = Model(
    id="o4-mini-2025-04-16",
    client=AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or ""),
)

OPENAI_4_1 = Model(
    id="gpt-4.1",
    client=AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or ""),
)

CLAUDE_SONNET_4 = Model(
    id="anthropic/claude-sonnet-4",
    client=AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY") or "",
    ),
)

# CLAUDE_SONNET_4 = Model(
#     id="claude-sonnet-4-20250514",
#     client=AsyncOpenAI(
#         base_url="https://api.anthropic.com/v1", api_key=os.getenv("ANTHROPIC_API_KEY") or ""
#     ),
# )

LOCAL_PLATFORM = Model(
    id="anthropic/claude-sonnet-4",
    client=AsyncOpenAI(
        base_url="http://localhost:8888/sandbox/inference/v1",
        api_key="a62e743d-1dbf-4c94-9b01-39f8112d1f3c",
    ),
)


def openrouter(model: str) -> Model:
    """Shorthand for making a model from an openrouter model slug"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    assert api_key
    return Model(
        id=model,
        client=AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        ),
    )
