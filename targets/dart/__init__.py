"""
Nim target language backend for py2many.

Defines the `settings()` function that returns a configured LanguageSettings
object used for transpiling Python code to Nim.
"""


import os

from py2many.language import LanguageSettings
from .transpiler import DartIntegerDivRewriter, DartTranspiler

# Regarding <py2many root>/py2many/rewriters/.. in this language
#
# Following rewriters are likely skipped for dart:
# - StrStrRewriter
#
#  Check followiing rewriters for dart:
# - RemoveTypeCommentsRewriter (because of type annotations in dart)
# - DocStringToCommentRewriter (because of docstrings in dart)
# - RemovePassRewriter (because of pass statements in dart)

def settings(args, env=os.environ):
    return LanguageSettings(
        transpiler=DartTranspiler(),
        ext=".dart",
        display_name="Dart",
        formatter=["dart", "format"],
        post_rewriters=[DartIntegerDivRewriter()],
    )

