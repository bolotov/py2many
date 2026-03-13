"""
Backend registry and dynamic target discovery.
"""

import functools
import importlib
import logging
import pkgutil
from collections.abc import Callable, Mapping
from typing import Any

import targets
from py2many.language import LanguageSettings
from py2many.rewriters.inferred_ann_assign import InferredAnnAssignRewriter
from py2many.transformers.python_transformer import PythonTranspiler, RestoreMainRewriter

log = logging.getLogger(__name__)

SettingsFactory = Callable[[Any, Mapping[str, str] | None], LanguageSettings]

def python_settings(args) -> LanguageSettings:
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


@functools.cache
def get_all_settings(args ) -> dict[str, LanguageSettings]:

    ALL_SETTINGS = {
        "python": python_settings,
        **_discover_targets(), # Here
    }

    return { name: factory(args) for name, factory in ALL_SETTINGS.items() }