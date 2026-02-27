"""
Kotlin target language backend for py2many.

Defines the `settings()` function that returns a configured LanguageSettings
object used for transpiling Python code to Kotlin.
"""
import os

from py2many.language import LanguageSettings
from .inference import infer_kotlin_types
from .transpiler import KotlinBitOpRewriter, KotlinPrintRewriter, KotlinTranspiler


def settings(args, env=os.environ) -> LanguageSettings:
    return LanguageSettings(
        transpiler=KotlinTranspiler(),
        ext=".kt",
        display_name="Kotlin",
        formatter=[
            "jgo",
            "--log-level=DEBUG",
            "--add-opens",
            "java.base/java.lang=ALL-UNNAMED",
            "com.pinterest.ktlint:ktlint-cli",
            "--reporter=plain",
            "--format",
        ],
        rewriters=[KotlinBitOpRewriter()],
        transformers=[infer_kotlin_types],
        post_rewriters=[KotlinPrintRewriter()],
        linter=[
            "jgo",
            "--log-level=DEBUG",
            "--add-opens",
            "java.base/java.lang=ALL-UNNAMED",
            "com.pinterest.ktlint:ktlint-cli",
            "--reporter=plain",
        ],
    )
