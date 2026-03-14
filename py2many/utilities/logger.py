"""
logger.py — Small functional logger wrapper.

Tries loguru first; silently falls back to stdlib if unavailable — so it
always produces a working logger with no extra caller effort.

The module exposes a minimal callable Logger abstraction so logging
can be used in functional pipelines without binding to a concrete
logging implementation.
"""

import logging
import sys
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import IO, Callable

# ---------------------------------------------------------------------------
# Optional loguru backend
# ---------------------------------------------------------------------------

try:
    from loguru import logger as _loguru
    _HAS_LOGURU = True
except ImportError:
    _loguru = None
    _HAS_LOGURU = False


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class LogLevel(Enum):
    """Type-safe logging levels using stdlib integer values."""
    DEBUG    = logging.DEBUG
    INFO     = logging.INFO
    WARNING  = logging.WARNING
    ERROR    = logging.ERROR
    CRITICAL = logging.CRITICAL


@dataclass(frozen=True)
class LoggerConfig:
    """
    Immutable configuration for logger creation.

    By default stdout receives DEBUG/INFO and stderr receives
    WARNING and above.

    Custom streams can be supplied for testing or file logging.
    """

    level: LogLevel = LogLevel.INFO
    name: str = "app"
    prefer_loguru: bool = True
    disabled: bool = False

    out_sink: IO[str] | None = None
    err_sink: IO[str] | None = None

    loguru_format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan> - <level>{message}</level>"
    )


class Logger:
    """
    Thin wrapper around a logging backend.

    Supports:

        logger(level, message)
        logger.exception(message, exc)

    Instances are callable so they can be passed as simple
    logging functions.
    """

    __slots__ = ("_log_fn", "_exc_fn", "backend")

    def __init__(
            self,
            log_fn: Callable[[LogLevel, str], None],
            exc_fn: Callable[[str, BaseException], None],
            backend: str,
    ) -> None:
        self._log_fn = log_fn
        self._exc_fn = exc_fn
        self.backend = backend

    def trace(self, msg: str):
        self(LogLevel.DEBUG, msg)

    def debug(self, msg: str):
        self(LogLevel.DEBUG, msg)

    def info(self, msg: str):
        self(LogLevel.INFO, msg)

    def warn(self, msg: str):
        self(LogLevel.WARNING, msg)

    def error(self, msg: str):
        self(LogLevel.ERROR, msg)

    def critical(self, msg: str):
        self(LogLevel.CRITICAL, msg)

    warning = warn


    def __call__(self, level: LogLevel, message: str) -> None:
        """Log a message at the given level."""
        self._log_fn(level, message)

    def exception(self, message: str, exc: BaseException) -> None:
        """Log message together with traceback."""
        self._exc_fn(message, exc)

    def at(self, level: LogLevel) -> Callable[[str], None]:
        """
        Return a function bound to a log level.

        Useful for functional pipelines.
        """
        return lambda message: self(level, message)

    def with_level(self, level: LogLevel) -> "Logger":
        """
        Return a new Logger filtering messages below `level`.
        """

        def _emit(lvl: LogLevel, msg: str) -> None:
            if lvl.value >= level.value:
                self(lvl, msg)

        def _emit_exc(msg: str, exc: BaseException) -> None:
            if LogLevel.ERROR.value >= level.value:
                self.exception(msg, exc)

        return Logger(_emit, _emit_exc, self.backend)

    def __repr__(self) -> str:
        return f"Logger(backend={self.backend!r})"


# ---------------------------------------------------------------------------
# No-op logger
# ---------------------------------------------------------------------------

NOOP = Logger(
    log_fn=lambda _lvl, _msg: None,
    exc_fn=lambda _msg, _exc: None,
    backend="noop",
)


# ---------------------------------------------------------------------------
# stdlib backend
# ---------------------------------------------------------------------------

def _make_stdlib(config: LoggerConfig) -> Logger:

    out = config.out_sink or sys.stdout
    err = config.err_sink or sys.stderr

    std = logging.getLogger(config.name)

    if std.hasHandlers():
        std.handlers.clear()

    std.setLevel(config.level.value)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    )

    out_handler = logging.StreamHandler(out)
    out_handler.setLevel(logging.DEBUG)
    out_handler.addFilter(lambda r: r.levelno < logging.WARNING)
    out_handler.setFormatter(fmt)

    err_handler = logging.StreamHandler(err)
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(fmt)

    std.addHandler(out_handler)
    std.addHandler(err_handler)

    std.propagate = False

    def _emit(level: LogLevel, message: str) -> None:
        std.log(level.value, message)

    def _emit_exc(message: str, error: BaseException) -> None:
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        std.error("%s\n%s", message, tb)

    return Logger(_emit, _emit_exc, "stdlib")


# ---------------------------------------------------------------------------
# loguru backend
# ---------------------------------------------------------------------------

def _make_loguru(config: LoggerConfig) -> Logger:

    out = config.out_sink or sys.stdout

    assert _loguru is not None

    _loguru.remove()

    _loguru.add(
        out,
        format=config.loguru_format,
        level=config.level.name,
        colorize=(out is sys.stdout),
    )

    def _emit(level: LogLevel, message: str) -> None:
        _loguru.log(level.name, message)

    def _emit_exc(message: str, error: BaseException) -> None:
        _loguru.opt(exception=error).error(message)

    return Logger(_emit, _emit_exc, "loguru")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logger(config: LoggerConfig = LoggerConfig()) -> Logger:
    """
    Create and return a configured Logger.

    loguru is used if available and preferred,
    otherwise the standard logging module is used.
    """

    if config.disabled:
        return NOOP

    if config.prefer_loguru and _HAS_LOGURU:
        return _make_loguru(config)

    return _make_stdlib(config)


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    log = setup_logger(LoggerConfig(level=LogLevel.DEBUG))

    log(LogLevel.INFO, "Application started")
    log(LogLevel.DEBUG, "Debug details")

    try:
        1 / 0
    except ZeroDivisionError as err:
        log.exception("Startup error", err)

    print("Backend:", log.backend)