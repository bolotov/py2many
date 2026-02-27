"""
Nim target language backend for py2many.

Defines the `settings()` function that returns a configured LanguageSettings
object used for transpiling Python code to Nim.
"""


import os

from sympy.integrals.manualintegrate import rewriter

from py2many.language import LanguageSettings

from .inference import infer_nim_types
from .transpiler import NimNoneCompareRewriter, NimTranspiler


def settings(args, env=os.environ):
    nim_args = {}
    nimpretty_args = []
    if args.indent is not None:
        nim_args["indent"] = args.indent
        nimpretty_args.append(f"--indent:{args.indent}")
    return LanguageSettings(
        transpiler=NimTranspiler(**nim_args),
        ext=".nim",
        display_name="Nim",
        formatter=["nimpretty", *nimpretty_args],
        # None,  # <--- IMPORTANT: IDK, the fuck is that, something is 'None'
        rewriters=[NimNoneCompareRewriter()],
        transformers=[infer_nim_types],
    )
