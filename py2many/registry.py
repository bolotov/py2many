"""
Backend registry and dynamic target discovery.

This module is responsible for:

- Discovering language backends located in `targets/`
- Validating that each backend exposes a proper `settings` factory
- Building a mapping of language names → LanguageSettings factories
- Instantiating LanguageSettings objects on demand

This module intentionally performs dynamic imports to allow
external backends to register themselves without modifying
core py2many code.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import sys
from typing import Any, Callable, Dict, Mapping, Optional

from py2many.language import LanguageSettings
from py2many.python_transformer import PythonTranspiler, RestoreMainRewriter
from py2many.result import Result
from py2many.rewriters.inferred_ann_assign import InferredAnnAssignRewriter


# ---------------------------------------------------------------------------
# MARK: Paths
# ---------------------------------------------------------------------------

PY2MANY_DIR: pathlib.Path = pathlib.Path(__file__).parent
PROJECT_ROOT: pathlib.Path = PY2MANY_DIR.parent
TARGETS_DIR: pathlib.Path = PROJECT_ROOT / "targets"

# Ensure project root is importable for dynamic backend discovery.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# MARK: Types
# ---------------------------------------------------------------------------

SettingsFactory = Callable[
    [Any, Optional[Mapping[str, str]]],
    LanguageSettings,
]


# ---------------------------------------------------------------------------
# MARK: Built-in Python backend
# ---------------------------------------------------------------------------

def python_settings(
        args: Any,
        env: Optional[Mapping[str, str]] = None,
) -> LanguageSettings:
    """
    Build LanguageSettings for the built-in Python backend.

    NOTE:
        This should eventually be moved into targets/python/
        to unify backend discovery logic.
    """
    return LanguageSettings(
        transpiler=PythonTranspiler(args.no_prologue),
        ext=',py',
        # extension=".py",  # NOTE: now it's "ext" and not "extension"
        display_name="Python",
        formatter=["black"],
        rewriters=[RestoreMainRewriter()],
        post_rewriters=[InferredAnnAssignRewriter()],
    )


# ---------------------------------------------------------------------------
# Backend discovery
# ---------------------------------------------------------------------------

def _discover_targets() -> Result[Dict[str, SettingsFactory], str]:
    """
    Discover language backends inside the `targets/` directory.

    Each backend must:
        - Be a directory
        - Contain an `__init__.py`
        - Expose a callable `settings(args, env)` factory

    Returns:
        Result.ok(mapping) on success
        Result.err(error_message) on failure
    """
    discovered: Dict[str, SettingsFactory] = {}

    for target_path in TARGETS_DIR.iterdir():
        if not target_path.is_dir():
            continue

        init_file = target_path / "__init__.py"
        if not init_file.exists():
            continue

        module_name = f"targets.{target_path.name}"

        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            return Result.err(
                f"Failed to import backend '{target_path.name}': {exc}"
            )

        settings_factory = getattr(module, "settings", None)

        if settings_factory is None:
            return Result.err(
                f"Backend '{target_path.name}' missing required "
                f"'settings(args, env)' factory"
            )

        if not callable(settings_factory):
            return Result.err(
                f"'settings' in backend '{target_path.name}' is not callable"
            )

        # We trust the type at runtime but cast for static typing.
        discovered[target_path.name] = settings_factory  # type: ignore[assignment]

    return Result.ok(discovered)


def _build_all_settings() -> Dict[str, SettingsFactory]:
    """
    Build mapping of all available backends → their settings factories.

    Raises:
        RuntimeError: If backend discovery fails.
    """
    base: Dict[str, SettingsFactory] = {
        "python": python_settings,
    }

    discovery = _discover_targets()

    if discovery.is_err():
        raise RuntimeError(discovery.unwrap_err())

    return {**base, **discovery.unwrap()}


# ---------------------------------------------------------------------------
# Registry (factories only)
# ---------------------------------------------------------------------------

# Factories are built once at import time.
# Individual LanguageSettings are instantiated lazily via get_all_settings().
ALL_SETTINGS: Dict[str, SettingsFactory] = _build_all_settings()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_settings(
        args: Any,
        env: Optional[Mapping[str, str]] = None,
) -> Dict[str, LanguageSettings]:
    """
    Instantiate all discovered backends.

    Args:
        args:
            CLI argument namespace (typically argparse.Namespace).

        env:
            Optional environment mapping.
            Defaults to os.environ.

    Returns:
        Mapping of language name → instantiated LanguageSettings.
    """
    if env is None:
        env = os.environ

    return {
        name: factory(args, env)
        for name, factory in ALL_SETTINGS.items()
    }