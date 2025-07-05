from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, TypeVar, Union, final, overload

T = TypeVar("T")  # success type
U = TypeVar("U")  # new success type for mapping
E = TypeVar("E")  # error type
F = TypeVar("F")  # new error type


@final
class Result(Generic[T, E]):
    """
    A functional Result type representing either a success (Ok) or failure (Err).
    Inspired by Rust, Haskell, and other FP languages. Avoids exceptions,
    encourages safe composition, and integrates with type checkers.
    """

    def __init__(self, ok: Optional[T] = None, err: Optional[E] = None):
        if (ok is None) == (err is None):  # either both are set or both are None
            raise ValueError("Result must contain exactly one of ok or err.")
        self._ok = ok
        self._err = err

    @classmethod
    def ok(cls, value: T) -> Result[T, E]:
        return cls(ok=value)

    @classmethod
    def err(cls, error: E) -> Result[T, E]:
        return cls(err=error)

    def is_ok(self) -> bool:
        return self._err is None

    def is_err(self) -> bool:
        return self._ok is None

    def unwrap(self) -> T:
        if self.is_ok():
            return self._ok  # type: ignore
        raise Exception(f"Unwrapped error: {self._err}")

    def unwrap_or(self, default: T) -> T:
        return self._ok if self.is_ok() else default  # type: ignore

    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        return self._ok if self.is_ok() else f(self._err)  # type: ignore

    def unwrap_err(self) -> E:
        if self.is_err():
            return self._err  # type: ignore
        raise Exception("Called unwrap_err on Ok result")

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        return Result.ok(f(self._ok)) if self.is_ok() else Result.err(self._err)  # type: ignore

    def map_err(self, f: Callable[[E], F]) -> Result[T, F]:
        return Result.ok(self._ok) if self.is_ok() else Result.err(f(self._err))  # type: ignore

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return f(self._ok) if self.is_ok() else Result.err(self._err)  # type: ignore

    def fold(self, on_ok: Callable[[T], U], on_err: Callable[[E], U]) -> U:
        return on_ok(self._ok) if self.is_ok() else on_err(self._err)  # type: ignore

    def raise_if_err(self, exc_type: Callable[[E], Exception] = lambda e: Exception(str(e))) -> T:
        if self.is_err():
            raise exc_type(self._err)
        return self._ok  # type: ignore

    def to_dict(self) -> dict:
        return {"ok": self._ok} if self.is_ok() else {"err": self._err}

    def with_context(self, msg: str) -> Result[T, str]:
        if self.is_ok():
            return self
        return Result.err(f"{msg}: {self._err}")

    def __repr__(self) -> str:
        return f"Ok({self._ok})" if self.is_ok() else f"Err({self._err})"

    def __bool__(self) -> bool:
        return self.is_ok()


# Type aliases for clearer intent
Ok = Result.ok
Err = Result.err

# Optional-style wrapper (not tied to error values)
Option = Union[T, None]


