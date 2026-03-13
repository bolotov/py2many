import os
from pathlib import Path


import py2many
from py2many.language import LanguageSettings

from .inference import infer_go_types
from .transpiler import (
    GoIfExpRewriter,
    GoMethodCallRewriter,
    GoNoneCompareRewriter,
    GoPropagateTypeAnnotation,
    GoTranspiler,
    GoVisibilityRewriter,
)

PY2MANY_DIR = Path(py2many.__file__).parent
ROOT_DIR = PY2MANY_DIR.parent


def settings(args, env=os.environ):
    config_filename = "revive.toml"
    cwd = Path.cwd()

    if os.path.exists(cwd / config_filename):
        revive_config = cwd / config_filename
    elif os.path.exists(ROOT_DIR / config_filename):
        revive_config = ROOT_DIR / config_filename
    else:
        revive_config = None

    linter_to_use = ("revive", "--config", str(revive_config),) if revive_config else ("revive",)

    return LanguageSettings(
        transpiler=GoTranspiler(),
        ext=".go",
        display_name="Go",
        formatter=("gofmt", "-w",),
        rewriters=(
            GoNoneCompareRewriter(),
            GoVisibilityRewriter(),
            GoIfExpRewriter(),
        ),
        transformers=(infer_go_types,),
        post_rewriters=(GoMethodCallRewriter(), GoPropagateTypeAnnotation(),),
        linter=linter_to_use,
    )
