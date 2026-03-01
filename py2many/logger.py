"""
logger.py — Functional logger returning Result[Logger, str].

Tries loguru first; silently falls back to stdlib if unavailable — so it
always produces a working logger with no extra caller effort.  Result is
returned so callers that *want* to know which backend was chosen can inspect
it, while callers that don't can just call .unwrap_or(NOOP).
"""

from __future__ import annotations

import logging
import sys
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import IO, Callable

from py2many.result import Ok, Result

try:
    from loguru import logger as _loguru
    _HAS_LOGURU = True
except ImportError:
    # _loguru is intentionally undefined when loguru is absent.
    # _make_loguru() is only called when _HAS_LOGURU is True,
    # so the name is always defined at the point of use.
    _HAS_LOGURU = False


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class LogLevel(Enum):
    """Type-safe logging levels with stdlib int values."""
    DEBUG    = logging.DEBUG
    INFO     = logging.INFO
    WARNING  = logging.WARNING
    ERROR    = logging.ERROR
    CRITICAL = logging.CRITICAL


@dataclass(frozen=True)
class LoggerConfig:
    """
    Immutable configuration for logger creation.

    Output sinks
    ------------
    By default ``out_sink`` receives DEBUG/INFO and ``err_sink`` receives
    WARNING and above, mirroring the conventional stdout/stderr split.
    Supply any ``TextIO``-compatible object (open file, ``StringIO``, …)
    to redirect output — useful for file logging, test capture, etc.:

        LoggerConfig(out_sink=open("app.log", "a"), err_sink=open("app.log", "a"))

    When both sinks point to the same stream all levels go there in order.
    ``None`` means use the process-level ``sys.stdout`` / ``sys.stderr``
    (looked up at call time, so redirection via ``contextlib.redirect_stdout``
    works as expected).
    """
    level:         LogLevel       = LogLevel.INFO
    name:          str            = "app"
    prefer_loguru: bool           = True
    disabled:      bool           = False
    out_sink:      IO[str] | None = None   # stdout by default
    err_sink:      IO[str] | None = None   # stderr by default
    loguru_format: str            = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan> - <level>{message}</level>"
    )


class Logger:
    """
    Thin wrapper around a log backend exposing two operations:

        logger(level, message)              — regular message
        logger.exception(message, exc)      — message + full traceback

    Callable as ``logger(level, msg)`` so existing ``LogFunc``-typed
    callsites continue to work without changes.

    Construct via ``setup_logger()``, not directly.
    """

    __slots__ = ("_log_fn", "_exc_fn", "backend")

    def __init__(
            self,
            log_fn:  Callable[[LogLevel, str], None],
            exc_fn:  Callable[[str, BaseException], None],
            backend: str,
    ) -> None:
        object.__setattr__(self, "_log_fn",  log_fn)
        object.__setattr__(self, "_exc_fn",  exc_fn)
        object.__setattr__(self, "backend",  backend)

    def __call__(self, level: LogLevel, message: str) -> None:
        """Log a plain message at the given level."""
        self._log_fn(level, message)            # type: ignore[attr-defined]

    def exception(self, message: str, exc: BaseException) -> None:
        """
        Log ``message`` together with a formatted traceback of ``exc``.

        With loguru: renders the beautiful coloured exception panel.
        With stdlib: appends the plain ``traceback.format_exception`` output.
        """
        self._exc_fn(message, exc)              # type: ignore[attr-defined]

    def at(self, level: LogLevel) -> Callable[[str], None]:
        """
        Return a ``Callable[[str], None]`` bound to ``level``.

        Eliminates lambda noise when composing with Result chains:

            result = (
                parse(raw)
                .inspect(log.at(LogLevel.DEBUG))
                .bind(validate)
                .inspect_err(log.at(LogLevel.WARNING))
            )
        """
        return lambda message: self(level, message)

    def with_level(self, level: LogLevel) -> Logger:
        """
        Return a new ``Logger`` that filters messages below ``level``.

        Does not reconstruct the backend — wraps ``self`` with a threshold
        check.  Purely functional: ``self`` is unchanged and both loggers
        can coexist:

            log     = setup_logger().unwrap_or(NOOP)
            verbose = log.with_level(LogLevel.DEBUG)
            quiet   = log.with_level(LogLevel.ERROR)

        ``exception()`` is always treated as ERROR level for filtering
        purposes — it is never suppressed below that.
        """
        def _emit(lvl: LogLevel, message: str) -> None:
            if lvl.value >= level.value:
                self(lvl, message)

        def _emit_exc(message: str, error: BaseException) -> None:
            if LogLevel.ERROR.value >= level.value:
                self.exception(message, error)

        return Logger(log_fn=_emit, exc_fn=_emit_exc, backend=self.backend)

    def __repr__(self) -> str:
        return f"Logger(backend={self.backend!r})"


# A Logger that silently discards everything — safe default / disabled state.
NOOP: Logger = Logger(
    log_fn=lambda _level, _msg: None,
    exc_fn=lambda _msg, _exc: None,
    backend="noop",
)


# ---------------------------------------------------------------------------
# Private backend builders
# ---------------------------------------------------------------------------

def _make_stdlib(config: LoggerConfig) -> Logger:
    out = config.out_sink or sys.stdout
    err = config.err_sink or sys.stderr

    std = logging.getLogger(config.name)
    if std.hasHandlers():
        std.handlers.clear()
    std.setLevel(config.level.value)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s")

    out_h = logging.StreamHandler(out)
    out_h.setLevel(logging.DEBUG)
    out_h.addFilter(lambda r: r.levelno < logging.WARNING)
    out_h.setFormatter(fmt)

    err_h = logging.StreamHandler(err)
    err_h.setLevel(logging.WARNING)
    err_h.setFormatter(fmt)

    std.addHandler(out_h)
    std.addHandler(err_h)
    std.propagate = False

    def _emit(level: LogLevel, message: str) -> None:
        std.log(level.value, message)

    def _emit_exc(message: str, error: BaseException) -> None:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        std.error("%s\n%s", message, tb)

    return Logger(log_fn=_emit, exc_fn=_emit_exc, backend="stdlib")


def _make_loguru(config: LoggerConfig) -> Logger:
    out = config.out_sink or sys.stdout

    _loguru.remove()                            # type: ignore[name-defined]
    _loguru.add(                                # type: ignore[name-defined]
        out,
        format=config.loguru_format,
        level=config.level.value,
        colorize=(out is sys.stdout),           # colour only for real stdout
    )

    def _emit(level: LogLevel, message: str) -> None:
        _loguru.log(level.name, message)        # type: ignore[name-defined]

    def _emit_exc(message: str, error: BaseException) -> None:
        _loguru.opt(exception=error).error(message)  # type: ignore[name-defined]

    return Logger(log_fn=_emit, exc_fn=_emit_exc, backend="loguru")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logger(config: LoggerConfig = LoggerConfig()) -> Result[Logger, str]:
    """
    Return a configured ``Logger`` wrapped in ``Result``.

    ``prefer_loguru=True`` (the default): tries loguru, silently falls back
    to stdlib if loguru is not installed:

        log = setup_logger().unwrap_or(NOOP)
        log(LogLevel.INFO, "hello")
        log.exception("something broke", exc)

    Inspect which backend was chosen via ``logger.backend``:

        setup_logger()
            .inspect(lambda lg: print(f"using {lg.backend}"))
            .unwrap_or(NOOP)

    Redirect output to a file:

        cfg = LoggerConfig(
            out_sink=open("app.log", "a"),
            err_sink=open("app.log", "a"),
        )
        log = setup_logger(cfg).unwrap_or(NOOP)
    """
    if config.disabled:
        return Ok(NOOP)

    if config.prefer_loguru and _HAS_LOGURU:
        return Ok(_make_loguru(config))

    return Ok(_make_stdlib(config))


# ---------------------------------------------------------------------------
# Usage examples
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- Default: loguru if available, stdlib otherwise ---
    log = setup_logger().unwrap_or(NOOP)
    log(LogLevel.INFO,  "Application started.")
    log(LogLevel.DEBUG, "Detail (only shown if level=DEBUG).")

    # --- See which backend is active ---
    setup_logger(LoggerConfig(level=LogLevel.DEBUG)) \
        .inspect(lambda lg: lg(LogLevel.DEBUG, f"Backend: {lg.backend}")) \
        .unwrap_or(NOOP)

    # --- Exception rendering ---
    try:
        1 / 0
    except ZeroDivisionError as caught:
        log.exception("Caught an error during startup", caught)

    # --- Force stdlib ---
    stdlib_log = setup_logger(LoggerConfig(prefer_loguru=False)).unwrap_or(NOOP)
    stdlib_log(LogLevel.WARNING, "Running without loguru.")

    # --- Redirect to file ---
    with open("/tmp/app.log", "a") as logfile:
        file_log = setup_logger(
            LoggerConfig(out_sink=logfile, err_sink=logfile, prefer_loguru=False)
        ).unwrap_or(NOOP)
        file_log(LogLevel.INFO, "This goes to the file.")

    # --- Disabled ---
    silent = setup_logger(LoggerConfig(disabled=True)).unwrap_or(NOOP)
    silent(LogLevel.CRITICAL, "This goes nowhere.")

    # --- Result chain with .at() ---
    (
        setup_logger(LoggerConfig(level=LogLevel.DEBUG))
        .inspect(lambda lg: lg(LogLevel.INFO, "Logger ready."))
        .inspect_err(lambda err: print(f"[fatal] {err}", file=sys.stderr))
    )