from . import loggers
from .loggers.stream_logger import StreamLogger


class AgentListener:
    logger: StreamLogger

    def __init__(self, logger: StreamLogger):
        self.logger = logger


__all__ = ["loggers", "AgentListener"]
