"""
Backend registry and dynamic target discovery.
"""

import argparse
import functools
import importlib
import inspect
import logging
import pkgutil
from collections.abc import Callable, Mapping
from typing import Any

import targets
from py2many.defaults import DEFAULTS
from py2many.language import LanguageSettings
from py2many.rewriters.inferred_ann_assign import InferredAnnAssignRewriter
from py2many.transformers.python_transformer import PythonTranspiler, RestoreMainRewriter

log = logging.getLogger(__name__)

SettingsFactory = Callable[[Any, Mapping[str, str] | None], LanguageSettings]

def python_settings(args: argparse.Namespace | None) -> LanguageSettings:
    # FIXME: TODO: extract into <root>/targets/python/__init__.py
    return LanguageSettings(
        transpiler=PythonTranspiler(args.no_prologue),
        ext=",py",
        display_name="Python",
        formatter=("black",),
        rewriters=(RestoreMainRewriter(),),
        post_rewriters=(InferredAnnAssignRewriter(),),
    )


def _discover_targets() -> dict[str, SettingsFactory]:
    discovered: dict[str, SettingsFactory] = {}

    for module in pkgutil.iter_modules(targets.__path__):
        name = module.name
        modname = f"targets.{name}"

        try:
            module_obj = importlib.import_module(modname)
            factory = getattr(module_obj, "settings")
        except Exception as exc:
            log.warning("Skipping backend '%s': %s", name, exc)
            continue

        if callable(factory):
            discovered[name] = factory
        else:
            print(f"Skipping backend '{name}': 'settings' not callable")

    return discovered


def call_factory(factory: SettingsFactory, args: argparse.Namespace | None) -> LanguageSettings:
    """Call a settings factory, handling both factories that accept args and those that don't.
    
    Public utility function for instantiating language settings from factory functions.
    """
    sig = inspect.signature(factory)
    if len(sig.parameters) > 0:
        return factory(args)
    else:
        return factory()


@functools.cache
def _get_all_factories_cached(defaults_frozen: frozenset[tuple[str, str]]) -> dict[str, SettingsFactory]:
    """Internal cached function that returns factories bound to default settings.
    
    Returns factory functions that will use default settings when called.
    This avoids issues with non-hashable Namespace objects by caching only with
    hashable default dicts at module initialization time.
    """
    # Convert frozenset back to dict, then to Namespace for factory creation
    defaults_dict : dict[str, Any] = dict(defaults_frozen)
    defaults_ns = argparse.Namespace(**defaults_dict)
    
 
    
    # Return the raw factories (not instantiated), but some may be wrapped
    # to use defaults if they need them
    return { "python": python_settings, **_discover_targets(), }
    


def get_all_settings(args: argparse.Namespace | None = None) -> dict[str, SettingsFactory]:
    """Get all language settings factories.
    
    Returns a dict of factory functions that can be called to instantiate language settings.
    
    Args:
        args: Optional argparse.Namespace. If None, factories will use default settings.
              Currently only used for validation; actual instantiation happens when
              factories are called.
    
    Returns:
        Dict mapping language names to SettingsFactory callables.
        Each factory can be called with args to get a LanguageSettings instance.
        
    Notes:
        - Module-level initialization (args=None) uses @functools.cache for performance
        - Backend discovery is cached to avoid expensive module imports
        - Each factory function returns a LanguageSettings instance when called
    """
    # Use cached factory discovery
    # The defaults_frozen parameter ensures we cache the expensive _discover_targets() call
    defaults_frozen = frozenset(DEFAULTS.items())
    
    return _get_all_factories_cached(defaults_frozen)