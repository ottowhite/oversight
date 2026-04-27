from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

type Role = Literal["user", "agent", "system"]


@dataclass
class Chunk:
    role: Role
    content: str

    def __str__(self) -> str:
        return self.content


class StreamLogger:
    on_chunk: Callable[[Chunk], Awaitable[None]]

    def __init__(self, on_chunk: Callable[[Chunk], Awaitable[None]]):
        self.on_chunk = on_chunk
