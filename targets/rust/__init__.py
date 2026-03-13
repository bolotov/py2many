import os
from functools import partial
from py2many.language import LanguageSettings
from .inference import infer_rust_types
from .transpiler import (
    RustLoopIndexRewriter,
    RustNoneCompareRewriter,
    RustStringJoinRewriter,
    RustTranspiler,
)


def settings(args, env=os.environ) -> LanguageSettings:
    return LanguageSettings(
        transpiler=RustTranspiler(args.extension, args.no_prologue),
        ext=".rs",
        display_name="Rust",
        formatter=(
            "rustfmt",
            "--edition=2021",
        ),
        rewriters=(RustNoneCompareRewriter(),),
        transformers=(partial(infer_rust_types, extension=args.extension), ),
        post_rewriters=(
            RustLoopIndexRewriter(),
            RustStringJoinRewriter(),
        ),
        linter=(
            "../../scripts/rust-runner.sh",
            "lint",
        ),
    )
