import sys
import pathlib
import importlib
from typing import Any, Callable, Dict, Iterator, Optional, Tuple
from unittest.mock import Mock

from py2many.language import LanguageSettings
from py2many.python_transformer import PythonTranspiler, RestoreMainRewriter
from py2many.rewriters import InferredAnnAssignRewriter

"""
This module constructs ALL_SETTINGS from __init__.py of language backends.
"""

# Now instead of hardcoded modules for target languages uses pathlib which is also bad

FAKE_ARGS = Mock(indent=4)  # TODO: Investigate this more

PY2MANY_DIR = pathlib.Path(__file__).parent
PROJECT_ROOT = PY2MANY_DIR.parent  # project root directory
TARGETS_DIR = PROJECT_ROOT / "targets"

if str(TARGETS_DIR) not in sys.path:
    sys.path.insert(0, str(TARGETS_DIR))


if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def python_settings(args: Any, env: Optional[Dict[str, str]] = None) -> LanguageSettings:
    """
    Create and return a LanguageSettings instance for the Python backend.

    Args:
        args: Parsed command-line arguments or configuration object. MUST have attribute 'no_prologue'.
        env: Optional mapping of environment variables. If None, defaults to os.environ in _get_all_settings.

    Returns:
        LanguageSettings: Configured for Python output.
    """
    return LanguageSettings(
        PythonTranspiler(args.no_prologue),
        ".py",
        "Python",
        formatter=["black"],
        rewriters=[RestoreMainRewriter()],
        post_rewriters=[InferredAnnAssignRewriter()],
    )


# TODO: consider LanguageName type instead of str for use down here
def discover_targets() -> Iterator[Tuple[str, Callable[..., Any]]]:
    """
    Imperative. Dynamically discover and yield available target language backends.

    Yields:
        Tuple[str, Callable[..., Any]]: Pairs of (language_name, settings_factory),
        where settings_factory is a callable that returns a LanguageSettings instance.
    """
    for target_path in TARGETS_DIR.iterdir():
        if target_path.is_dir() and (target_path / "__init__.py").exists():
            try:
                mod = importlib.import_module(f"targets.{target_path.name}")
                if hasattr(mod, "settings"):
                    yield target_path.name, mod.settings
            except ImportError as e:
                print(f"Failed to import {target_path.name}: {e}")


PYTHON_SETTINGS = {"python": python_settings,}

ALL_SETTINGS = PYTHON_SETTINGS | {name: settings for name, settings in discover_targets()}


def _get_all_settings(args: Any, env: Optional[Dict[str, str]] = None)\
        -> Dict[str, LanguageSettings]:
    """
    Build a dictionary mapping language names to their LanguageSettings instances.

    Args:
        args: Parsed command-line arguments or configuration object.
        env: Optional mapping of environment variables. If None, defaults to os.environ.

    Returns:
        Dict[str, LanguageSettings]: Mapping from language name to its settings instance.
    """
    if env is None:
        import os
        env = os.environ
    return {key: func(args, env=env) for key, func in ALL_SETTINGS.items()}
