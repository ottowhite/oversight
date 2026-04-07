from __future__ import annotations

import logging
import itertools
from typing import Iterator, TypeVar
from collections.abc import Iterable

T = TypeVar("T")


def get_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    return logging.getLogger(__name__)


def chunked_iterable(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk
