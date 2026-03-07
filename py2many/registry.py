"""
Backend registry and dynamic target discovery.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable, Mapping
from typing import Any

import targets
from py2many.language import LanguageSettings
from py2many.python_transformer import PythonTranspiler, RestoreMainRewriter
from py2many.rewriters.inferred_ann_assign import InferredAnnAssignRewriter

SettingsFactory = Callable[[Any, Mapping[str, str] | None], LanguageSettings]

log = logging.getLogger(__name__)

def python_settings(args: Any, env: Mapping[str, str] | None = None) -> LanguageSettings:
    return LanguageSettings(
        transpiler=PythonTranspiler(args.no_prologue),
        ext=",py",
        display_name="Python",
        formatter=["black"],
        rewriters=[RestoreMainRewriter()],
        post_rewriters=[InferredAnnAssignRewriter()],
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
            # print(f"Skipping backend '{name}': {exc}")
            continue

        if callable(factory):
            discovered[name] = factory
        else:
            print(f"Skipping backend '{name}': 'settings' not callable")

    return discovered


ALL_SETTINGS: dict[str, SettingsFactory] = {
    "python": python_settings,
    **_discover_targets(),
}


import os
from collections.abc import Mapping


def get_all_settings(
        args: Any,
        env: Mapping[str, str] | None = None,
) -> dict[str, LanguageSettings]:

    if env is None:
        env = os.environ

    return {
        name: factory(args, env)
        for name, factory in ALL_SETTINGS.items()
    }