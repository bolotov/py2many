"""
result.py — A Pythonic Result[T, E] type.

Inspired by Rust's std::result and the `result` package on PyPI
(https://pypi.org/project/result/, MIT licence).  The type hierarchy and
several API ideas are drawn from that prior art; this implementation
diverges in structure (a real base class rather than a TypeAlias union),
in the handling of do-notation, in `with_context`, and in omitting
features that are redundant or belong in a different layer.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from typing import Any, Generic, ParamSpec, TypeVar, final

# ---------------------------------------------------------------------------
# Type variables
# ---------------------------------------------------------------------------

T = TypeVar("T")    # Success value type
U = TypeVar("U")    # Mapped success value type
E = TypeVar("E")    # Error type
F = TypeVar("F")    # Mapped error type
P = ParamSpec("P")  # Parameter spec for decorator helpers
R = TypeVar("R")    # Return type for decorator helpers
TBE = TypeVar("TBE", bound=BaseException)  # Caught exception type


# ---------------------------------------------------------------------------
# Internal sentinel for do-notation short-circuiting
# ---------------------------------------------------------------------------

class _ShortCircuit(Exception):
    """
    Raised inside a ``do()`` generator when an ``Err`` is iterated.

    This is a private implementation detail — it must never escape into
    user code.  ``do()`` catches it unconditionally and converts it back
    to an ``Err`` value.
    """

    def __init__(self, err: Err[Any, Any]) -> None:
        self.err = err


# ---------------------------------------------------------------------------
# Core type
# ---------------------------------------------------------------------------

class Result(Generic[T, E]):
    """
    Algebraic sum type representing either success or failure:

        Result[T, E] = Ok[T] | Err[E]

    Do not instantiate this class directly. Use ``Ok(value)`` or ``Err(error)``.

    Design notes
    ------------
    Subclass structure vs. tagged union
        Rather than a single class with a ``(value, is_ok)`` pair, we use two
        concrete subclasses. This lets ``isinstance`` checks act as exhaustive
        pattern matches that mypy and pyright can narrow through safely.

    Phantom type parameters in ``Ok`` and ``Err``
        ``Ok`` stores only ``value: T`` but declares both ``T`` and ``E`` as
        type parameters (``Ok(Result[T, E])``).  ``Err`` mirrors this — it
        stores only ``error: E`` but also carries ``T``.  The unused parameter
        in each subclass is a *phantom* — it has no runtime representation, but
        its presence means the type checker sees ``Ok(42)`` as ``Ok[int, <free
        E>]`` rather than ``Ok[int, Never]``.  A free TypeVar can be unified
        with a concrete type from context:

            def parse(s: str) -> Result[int, str]:
                return Ok(int(s))   # E unified to str  ✓
                return Err("bad")   # T unified to int  ✓

        The earlier ``Never``-as-phantom approach was neater in theory but
        caused mypy to reject these return statements because invariant
        containers do not allow ``Never → str`` widening at a construction
        site.

    ``assert isinstance(self, Err)`` for narrowing
        After ``if isinstance(self, Ok): return ...`` mypy/pyright do **not**
        automatically narrow ``self`` to ``Err`` in the remaining code —
        ``Result`` is an open class as far as the type checker is concerned,
        so ``self`` remains ``Result[T, E]``, which has no ``.error``.  The
        ``assert`` is the lightweight, zero-overhead-in-CPython way to supply
        that narrowing hint.  Stripped by ``python -O``, which is acceptable:
        the assert is purely for the type checker, not for runtime safety —
        the subclass hierarchy already enforces the invariant.

    ``# type: ignore[return-value]`` in combinators
        Two kinds of unavoidable mismatches appear:

        1. ``return Ok(f(self.value))`` — inferred as ``Ok[U]``
           (i.e. ``Result[U, Never]``), declared return is ``Result[U, E]``.
           Although ``Never ≤ E``, mypy does not coerce free TypeVars this way
           at a construction site.
        2. ``return self`` in the pass-through branch — the declared return
           changes a TypeVar (``T → U``), which mypy cannot verify statically.

        In both cases the runtime behaviour is provably correct.  A targeted
        ``type: ignore[return-value]`` is the honest annotation — preferable
        to a ``cast`` that carries no extra runtime truth.

    ``__bool__``
        Lets ``Result`` values participate naturally in ``if``/``while``/
        ``assert`` without forcing an explicit ``.is_ok()`` call.

    ``__iter__`` and do-notation
        ``__iter__`` enables a generator-comprehension syntax for chaining
        fallible operations without explicit ``.bind()`` calls.  See ``do()``.
    """

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def is_ok(self) -> bool:
        """Return ``True`` if this result is ``Ok``."""
        return isinstance(self, Ok)

    def is_err(self) -> bool:
        """Return ``True`` if this result is ``Err``."""
        return isinstance(self, Err)

    # ------------------------------------------------------------------
    # Unwrapping
    # ------------------------------------------------------------------

    def unwrap(self) -> T:
        """
        Return the contained value.

        Raises:
            Exception: if this is ``Err``.  Prefer ``unwrap_or`` or
                ``unwrap_or_else`` for recoverable paths.
        """
        if isinstance(self, Ok):
            return self.value
        assert isinstance(self, Err)
        raise Exception(f"Unwrapped error: {self.error}")

    def unwrap_err(self) -> E:
        """
        Return the contained error.

        Raises:
            Exception: if this is ``Ok``.
        """
        if isinstance(self, Err):
            return self.error
        raise Exception("Called unwrap_err on Ok value")

    def unwrap_or(self, default: T) -> T:
        """
        Return the contained value, or ``default`` if this is ``Err``.

        The default is eagerly evaluated.  If constructing it is expensive
        or has side effects, use ``unwrap_or_else`` instead.
        """
        if isinstance(self, Ok):
            return self.value
        return default

    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        """
        Return the contained value, or compute a fallback from the error.

        ``f`` is only called when this is ``Err``, making this the lazy
        counterpart to ``unwrap_or``.
        """
        if isinstance(self, Ok):
            return self.value
        assert isinstance(self, Err)
        return f(self.error)

    def expect(self, message: str) -> T:
        """
        Return the contained value, or raise with a custom message if ``Err``.

        Prefer this over bare ``unwrap()`` whenever you have context to offer:

            config = load_config(path).expect(f"failed to load {path}")

        Raises:
            Exception: with ``"{message}: {error!r}"`` if this is ``Err``.
        """
        if isinstance(self, Ok):
            return self.value
        assert isinstance(self, Err)
        raise Exception(f"{message}: {self.error!r}")

    # ------------------------------------------------------------------
    # Functional combinators
    # ------------------------------------------------------------------

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        """
        Transform the success value with ``f``, leaving errors untouched.

        Forms a functor over the success dimension:

            Ok(x).map(f)  == Ok(f(x))
            Err(e).map(f) == Err(e)
        """
        if isinstance(self, Ok):
            return Ok(f(self.value))  # type: ignore[return-value]
        return self  # type: ignore[return-value]

    def map_err(self, f: Callable[[E], F]) -> Result[T, F]:
        """
        Transform the error value with ``f``, leaving successes untouched.

        The mirror image of ``map`` over the error dimension:

            Ok(x).map_err(f)  == Ok(x)
            Err(e).map_err(f) == Err(f(e))
        """
        if isinstance(self, Err):
            return Err(f(self.error))  # type: ignore[return-value]
        return self  # type: ignore[return-value]

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """
        Monadic bind (also known as ``flat_map`` or ``and_then``).

        Apply ``f`` to the success value when ``Ok``, short-circuiting on
        the first ``Err``.  This is the primary tool for chaining fallible
        operations without nested ``if`` checks:

            parse(text).bind(validate).bind(save)

        Laws (with ``ret = Ok``):

            ret(x).bind(f)    == f(x)                              # left identity
            m.bind(ret)       == m                                 # right identity
            m.bind(f).bind(g) == m.bind(lambda x: f(x).bind(g))   # associativity
        """
        if isinstance(self, Ok):
            return f(self.value)
        return self  # type: ignore[return-value]

    def or_else(self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        """
        The error-dimension complement of ``bind``.

        Apply ``f`` to the contained error if ``Err``, allowing recovery or
        error transformation.  If ``Ok``, propagate the value unchanged:

            Ok(x).or_else(f)  == Ok(x)
            Err(e).or_else(f) == f(e)

        Typical use — attempt a fallback or convert the error type:

            read_primary(path).or_else(lambda _: read_fallback(path))
        """
        if isinstance(self, Err):
            return f(self.error)
        return self  # type: ignore[return-value]

    def fold(self, on_ok: Callable[[T], U], on_err: Callable[[E], U]) -> U:
        """
        Collapse both variants into a single value of type ``U``.

        This is the *total eliminator* — it handles every possible state and
        produces a result without any possibility of raising.  Prefer this
        over ``if result.is_ok()`` when you need to produce a value from
        both branches:

            label = result.fold(
                on_ok=lambda v: f"success: {v}",
                on_err=lambda e: f"failure: {e}",
            )
        """
        if isinstance(self, Ok):
            return on_ok(self.value)
        assert isinstance(self, Err)
        return on_err(self.error)

    # ------------------------------------------------------------------
    # Side-effect taps
    # ------------------------------------------------------------------

    def inspect(self, f: Callable[[T], Any]) -> Result[T, E]:
        """
        Call ``f`` with the contained value if ``Ok``, then return ``self``.

        ``f`` is used purely for its side effects (logging, metrics, debugging)
        and its return value is discarded.  The chain is not broken:

            result = (
                parse(raw)
                .inspect(lambda v: logger.debug("parsed: %s", v))
                .bind(validate)
                .inspect(lambda v: logger.debug("validated: %s", v))
            )
        """
        if isinstance(self, Ok):
            f(self.value)
        return self

    def inspect_err(self, f: Callable[[E], Any]) -> Result[T, E]:
        """
        Call ``f`` with the contained error if ``Err``, then return ``self``.

        The mirror image of ``inspect`` over the error dimension — useful for
        logging errors mid-chain without consuming them:

            result = (
                load(path)
                .inspect_err(lambda e: logger.warning("load failed: %s", e))
                .or_else(fallback)
            )
        """
        if isinstance(self, Err):
            assert isinstance(self, Err)
            f(self.error)
        return self

    # ------------------------------------------------------------------
    # Boundary helpers
    # ------------------------------------------------------------------

    def raise_if_err(
            self,
            exc_type: Callable[[E], Exception] = lambda e: Exception(str(e)),
    ) -> T:
        """
        Return the value or raise an exception — bridge to exception-land.

        Useful at I/O or API boundaries where callers expect exceptions
        rather than ``Result`` values.  The default wraps the error in a
        plain ``Exception``; supply ``exc_type`` to raise something more
        specific:

            result.raise_if_err(ValueError)
            result.raise_if_err(lambda e: HTTPError(503, str(e)))
        """
        if isinstance(self, Ok):
            return self.value
        assert isinstance(self, Err)
        raise exc_type(self.error)

    def with_context(self, msg: str) -> Result[T, tuple[str, E]]:
        """
        Attach a context message to the error, leaving successes untouched.

        The error is wrapped in a ``(message, original_error)`` tuple so that
        the original structured error is never discarded — callers can still
        inspect or match on ``e[1]`` after the fact.

        Implemented as ``map_err(lambda e: (msg, e))``, so the
        ``Ok`` path is zero-cost.

        Example::

            result = read_file(path).with_context(f"reading config {path}")
            # Err(("reading config /etc/app.conf", FileNotFoundError(...)))
        """
        return self.map_err(lambda e: (msg, e))

    # ------------------------------------------------------------------
    # Python protocols
    # ------------------------------------------------------------------

    def __bool__(self) -> bool:
        """
        ``Ok``  → ``True``
        ``Err`` → ``False``

        Enables natural use in boolean contexts::

            if result:
                ...  # safe to call result.unwrap()
        """
        return isinstance(self, Ok)

    def __iter__(self) -> Iterator[T]:
        """
        Support for ``do()``-notation via generator comprehension.

        Iterating an ``Ok`` yields its value exactly once.  Iterating an
        ``Err`` raises ``_ShortCircuit`` immediately, which ``do()`` catches
        to abort the generator and return that ``Err``.

        Do not iterate ``Result`` values outside of a ``do()`` block —
        the ``_ShortCircuit`` exception will propagate uncaught.
        See ``do()`` for the intended usage pattern.
        """
        if isinstance(self, Ok):
            yield self.value
            return
        assert isinstance(self, Err)
        raise _ShortCircuit(self)
        # Note: no yield here — the yield in the Ok branch above is sufficient
        # to make Python treat this as a generator function.  The Err branch
        # simply raises, which the generator machinery propagates normally.


# ---------------------------------------------------------------------------
# Concrete variants
# ---------------------------------------------------------------------------

@final
@dataclass(frozen=True, slots=True)
class Ok(Result[T, E]):
    """
    Successful variant of ``Result``, holding a value of type ``T``.

    Both type parameters are present so that ``Ok[int, str]`` is a valid
    annotation and unification works at call sites:

        def parse(s: str) -> Result[int, str]:
            return Ok(int(s))   # Ok[int, <free E>] unifies with Result[int, str] ✓

    The error type ``E`` has no corresponding field — it is a phantom parameter
    that exists only to satisfy the ``Result[T, E]`` base type and allow the
    type checker to infer ``E`` from context.  At runtime ``Ok`` stores only
    ``value``.
    """

    value: T

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@final
@dataclass(frozen=True, slots=True)
class Err(Result[T, E]):
    """
    Failure variant of ``Result``, holding an error of type ``E``.

    Both type parameters are present so that ``Err[int, str]`` is a valid
    annotation and unification works at call sites:

        def parse(s: str) -> Result[int, str]:
            return Err("bad input")   # Err[<free T>, str] unifies with Result[int, str] ✓

    The success type ``T`` has no corresponding field — it is a phantom parameter
    that exists only to satisfy the ``Result[T, E]`` base type and allow the
    type checker to infer ``T`` from context.  At runtime ``Err`` stores only
    ``error``.
    """

    error: E

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# ---------------------------------------------------------------------------
# Do-notation
# ---------------------------------------------------------------------------

def do(gen: Generator[Result[T, E], None, None]) -> Result[T, E]:
    """
    Do-notation: run a generator that yields ``Result`` values, short-circuiting
    on the first ``Err``.

    This is syntactic sugar for a chain of ``.bind()`` calls, using Python's
    generator comprehension syntax to give each intermediate value a name:

        result: Result[float, str] = do(
            Ok(x + y)
            for x in parse_float(a)
            for y in parse_float(b)
        )

    Is exactly equivalent to:

        result = parse_float(a).bind(lambda x:
                 parse_float(b).bind(lambda y:
                 Ok(x + y)))

    How it works
    ------------
    Iterating an ``Ok`` inside the generator yields its value and continues.
    Iterating an ``Err`` raises ``_ShortCircuit``, which unwinds the generator
    and is caught here, returning that ``Err`` as the final result.

    The final expression in the comprehension (``Ok(x + y)`` above) is the
    value ``next(gen)`` returns after all the ``for`` bindings succeed.

    Important: always annotate the call site with the expected return type.
    Without the annotation some type checkers cannot infer ``T`` and ``E``:

        result: Result[int, str] = do(Ok(x) for x in some_result)

    Limitation: only synchronous generators are supported.  For async code,
    compose with ``.bind()`` or ``await`` the individual steps manually.
    """
    try:
        return next(gen)
    except _ShortCircuit as exc:
        err: Err[Any, E] = exc.err  # type: ignore[assignment]
        return err  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Decorator helpers
# ---------------------------------------------------------------------------

def as_result(
        *exceptions: type[TBE],
) -> Callable[[Callable[P, R]], Callable[P, Result[R, TBE]]]:
    """
    Decorator factory that wraps a function so that it returns a ``Result``
    instead of raising.

    Specified exception types are caught and returned as ``Err(exc)``.
    All other exceptions propagate normally — ``as_result`` does not swallow
    unexpected errors.

    Usage::

        @as_result(ValueError, OSError)
        def parse_and_load(path: str) -> Config:
            ...   # may raise ValueError or OSError

        result: Result[Config, ValueError | OSError] = parse_and_load(path)

    At least one exception type must be provided, and every argument must be
    a subclass of ``BaseException``:

        as_result()              # TypeError — no exceptions given
        as_result(int)           # TypeError — int is not an exception

    Raises:
        TypeError: if called with no arguments or with non-exception types.
    """
    if not exceptions or not all(
            isinstance(exc, type) and issubclass(exc, BaseException)
            for exc in exceptions
    ):
        raise TypeError("as_result() requires one or more exception types")

    def decorator(f: Callable[P, R]) -> Callable[P, Result[R, TBE]]:
        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Result[R, TBE]:
            try:
                return Ok(f(*args, **kwargs))  # type: ignore[return-value]
            except exceptions as exc:
                return Err(exc)  # type: ignore[return-value]

        return wrapper

    return decorator


def as_async_result(
        *exceptions: type[TBE],
) -> Callable[[Callable[P, R]], Callable[P, Result[R, TBE]]]:
    """
    Async variant of ``as_result``.

    Wraps a coroutine function so that it returns ``Result`` instead of raising.
    Identical contract to ``as_result`` — see that docstring for full details.

    Usage::

        @as_async_result(aiohttp.ClientError)
        async def fetch(url: str) -> bytes:
            ...

        result: Result[bytes, aiohttp.ClientError] = await fetch(url)
    """
    if not exceptions or not all(
            isinstance(exc, type) and issubclass(exc, BaseException)
            for exc in exceptions
    ):
        raise TypeError("as_async_result() requires one or more exception types")

    def decorator(f: Callable[P, R]) -> Callable[P, Result[R, TBE]]:
        @functools.wraps(f)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Result[R, TBE]:  # type: ignore[misc]
            try:
                return Ok(await f(*args, **kwargs))  # type: ignore[misc, return-value]
            except exceptions as exc:
                return Err(exc)  # type: ignore[return-value]

        return wrapper  # type: ignore[return-value]

    return decorator