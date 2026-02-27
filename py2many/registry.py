import sys
import pathlib
import importlib
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from py2many.language import LanguageSettings
from py2many.python_transformer import PythonTranspiler, RestoreMainRewriter
from py2many.rewriters import InferredAnnAssignRewriter
from py2many.result import Result

PY2MANY_DIR: pathlib.Path = pathlib.Path(__file__).parent
PROJECT_ROOT: pathlib.Path = PY2MANY_DIR.parent
TARGETS_DIR: pathlib.Path = PROJECT_ROOT / "targets"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SettingsFactory = Callable[[Any, Optional[Dict[str, str]]], LanguageSettings]


def python_settings(
        args: Any, env: Optional[Dict[str, str]] = None
) -> LanguageSettings:
    """
    Build LanguageSettings for Python backend.
    """
    return LanguageSettings(
        PythonTranspiler(args.no_prologue),
        ".py",
        "Python",
        formatter=["black"],
        rewriters=[RestoreMainRewriter()],
        post_rewriters=[InferredAnnAssignRewriter()],
    )


def _discover_targets() -> Result[Dict[str, SettingsFactory], str]:
    """
    Discover language backends inside targets/ directory.

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
        except Exception as e:
            return Result.err(
                f"Failed to import backend '{target_path.name}': {e}"
            )

        if not hasattr(module, "settings"):
            return Result.err(
                f"Backend '{target_path.name}' missing required 'settings' factory"
            )

        settings_factory = getattr(module, "settings")

        if not callable(settings_factory):
            return Result.err(
                f"'settings' in backend '{target_path.name}' is not callable"
            )

        discovered[target_path.name] = settings_factory

    return Result.ok(discovered)


def _build_all_settings() -> Dict[str, SettingsFactory]:
    base: Dict[str, SettingsFactory] = {"python": python_settings}

    discovery = _discover_targets()

    if discovery.is_err():
        raise RuntimeError(discovery.unwrap_err())

    return {**base, **discovery.unwrap()}


ALL_SETTINGS: Dict[str, SettingsFactory] = _build_all_settings()


def get_all_settings(
        args: Any, env: Optional[Dict[str, str]] = None
) -> Dict[str, LanguageSettings]:
    """
    Instantiate all configured backends.
    """
    if env is None:
        import os

        env = os.environ

    return {key: factory(args, env=env) for key, factory in ALL_SETTINGS.items()}