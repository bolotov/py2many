import os

from py2many.language import LanguageSettings

from .inference import infer_zig_types
from .rewriters import ZigImplicitConstructor, ZigInferMoveSemantics
from .transpiler import ZigTranspiler


def settings(args, env=os.environ):
    zig_args = {}
    return LanguageSettings(
        transpiler=ZigTranspiler(**zig_args),
        ext=".zig",
        display_name="Zig",
        formatter=["zig", "fmt"],
        # None,
        rewriters=[ZigInferMoveSemantics()],
        transformers=[infer_zig_types],
        post_rewriters=[
            ZigImplicitConstructor(),
        ],
    )
