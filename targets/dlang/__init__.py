import os

from py2many.language import LanguageSettings

from .transpiler import DIntegerDivRewriter, DTranspiler


def settings(args, env=os.environ):
    dfmt_args = ["--inplace", "--brace_style=otbs"]
    if args.indent is not None:
        dfmt_args.append(f"--indent_size={args.indent}")
    else:
        dfmt_args.append("--indent_size=2")
    return LanguageSettings(
        transpiler=DTranspiler(),
        ext=".d",
        display_name="D",
        formatter=[
            "dub",
            "run",
            "--yes",
            "dfmt",
            "--",
            *dfmt_args,
        ],
        post_rewriters=[DIntegerDivRewriter()],
    )
