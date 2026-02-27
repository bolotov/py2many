"""
Nim target language backend for py2many.

Defines the `settings()` function that returns a configured LanguageSettings
object used for transpiling Python code to Nim.
"""


import os

from py2many.language import LanguageSettings
from .transpiler import DartIntegerDivRewriter, DartTranspiler


def settings(args, env=os.environ):
    return LanguageSettings(
        transpiler=DartTranspiler(),
        ext=".dart",
        display_name="Dart",
        formatter=["dart", "format"],
        post_rewriters=[DartIntegerDivRewriter()],
    )
