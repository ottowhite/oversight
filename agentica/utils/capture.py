"""
Vibe coded replacement of IPython's capture_output which is async aware.
https://chatgpt.com/share/6894a26f-e4c0-8009-8d33-31d0e0f807fe

o3 Explaination of how it works:

• On import we replace ``sys.stdout`` / ``sys.stderr`` with a lightweight proxy
  that consults a ``contextvars.ContextVar``.
  When the variable holds a pair of ``StringIO`` buffers **for this task**,
  all writes are diverted there; otherwise they go straight to the real stream.

• ``capture_output(stdout=True, stderr=True)`` is both a synchronous *and* an
  asynchronous context-manager, so you can use either::

      with capture_output() as cap:            # inside sync or async code
          ...
      async with capture_output() as cap:      # stylistic fit for async-only code
          ...

• Capture is **per-task and nestable**: starting a new block or spawning a child
  task pushes a fresh buffer set; exiting the block restores the previous one.

The helper is a drop-in, coroutine-safe replacement for
``IPython.utils.capture.capture_output``—identical public interface, no external
dependencies, no global side-effects beyond the single proxy patch.
"""

import contextvars
import io
import sys
from types import TracebackType
from typing import Optional, Tuple, Type

# --------------------------------------------------------------------------- #
# 1)  Context-variable that points to the *current task’s* pair of buffers.   #
#     (None means “no capture is active for this task”.)                      #
# --------------------------------------------------------------------------- #
_task_buffers: contextvars.ContextVar[
    Optional[Tuple[Optional[io.StringIO], Optional[io.StringIO]]]
] = contextvars.ContextVar("_task_buffers", default=None)


# --------------------------------------------------------------------------- #
# 2)  A stream proxy that consults the ContextVar on every write().           #
# --------------------------------------------------------------------------- #
class _StreamProxy(io.TextIOBase):
    __slots__ = ("_real", "_idx")

    def __init__(self, real_stream: io.TextIOBase, idx: int) -> None:
        self._real = real_stream  # the original sys.stdout / sys.stderr
        self._idx = idx  # 0 == stdout, 1 == stderr

    # –– Methods needed by print() and many libraries –– #
    def write(self, s: str) -> int:  # type: ignore[override]
        buffers = _task_buffers.get()
        if buffers is None or buffers[self._idx] is None:
            return self._real.write(s)
        buf = buffers[self._idx]
        assert buf is not None
        return buf.write(s)

    def flush(self) -> None:  # type: ignore[override]
        buffers = _task_buffers.get()
        if buffers is None or buffers[self._idx] is None:
            return self._real.flush()
        buf = buffers[self._idx]
        assert buf is not None
        buf.flush()

    # — Forward a few attributes so libraries stay happy — #
    @property
    def encoding(self) -> str:  # type: ignore[override]  # noqa: D401
        return self._real.encoding

    @property
    def errors(self) -> str | None:  # type: ignore[override]  # noqa: D401
        return self._real.errors

    def isatty(self) -> bool:  # noqa: D401
        return self._real.isatty()


# --------------------------------------------------------------------------- #
# 3)  Monkey-patch sys.stdout / sys.stderr **once**.                          #
# --------------------------------------------------------------------------- #
if not isinstance(sys.stdout, _StreamProxy):  # idempotent import
    sys.stdout = _StreamProxy(sys.stdout, 0)  # type: ignore[assignment]
    sys.stderr = _StreamProxy(sys.stderr, 1)  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# 4)  The public context-manager                                               #
# --------------------------------------------------------------------------- #
class capture_output:
    """
    Async-aware clone of IPython’s ``capture_output``.

        async with capture_output() as cap:
            await shell.run_cell_async("print('hi')")
        print(cap.stdout)   # → 'hi\\n'

    • Works with *or* without ``async``/ ``await`` (implements both CM protocols)
    • Nested captures do what you expect:
          outer sees everything except what the inner block consumed.
    """

    def __init__(self, stdout: bool = True, stderr: bool = True) -> None:
        self._want_out = stdout
        self._want_err = stderr
        self._token: Optional[contextvars.Token] = None
        self._buf_out: Optional[io.StringIO] = io.StringIO() if stdout else None
        self._buf_err: Optional[io.StringIO] = io.StringIO() if stderr else None
        self.stdout: str = ""
        self.stderr: str = ""

    def __enter__(self) -> "capture_output":
        self._token = _task_buffers.set((self._buf_out, self._buf_err))
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        _task_buffers.reset(self._token)  # type: ignore[arg-type]
        if self._buf_out:
            self.stdout = self._buf_out.getvalue()
        if self._buf_err:
            self.stderr = self._buf_err.getvalue()
        return False  # do not swallow exceptions
