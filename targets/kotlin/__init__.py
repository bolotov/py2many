from py2many.language import LanguageSettings
from .inference import infer_kotlin_types
from .transpiler import KotlinBitOpRewriter, KotlinPrintRewriter, KotlinTranspiler

# Regarding py2many/rewriters.py in this language:
#
# Following rewriters are likely skipped for dart:
# - StrStrRewriter

def settings() -> LanguageSettings:
    return LanguageSettings(
        transpiler=KotlinTranspiler(),
        ext=".kt",
        display_name="Kotlin",
        formatter=(
            "jgo",
            "--log-level=DEBUG",
            "--add-opens",
            "java.base/java.lang=ALL-UNNAMED",
            "com.pinterest.ktlint:ktlint-cli",
            "--reporter=plain",
            "--format",
        ),
        rewriters=(KotlinBitOpRewriter(),),
        transformers=(infer_kotlin_types,),
        post_rewriters=(KotlinPrintRewriter(),),
        linter=(
            "jgo",
            "--log-level=DEBUG",
            "--add-opens",
            "java.base/java.lang=ALL-UNNAMED",
            "com.pinterest.ktlint:ktlint-cli",
            "--reporter=plain",
        ),
    )
