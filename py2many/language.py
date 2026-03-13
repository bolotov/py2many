import ast
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from .clike import CLikeTranspiler


class Transformer(Protocol):
    """A function that transforms an AST node.
    This allows plug-in passes to mutate the AST pre/post transpilation."""
    def __call__(self, node: ast.AST) -> ast.AST: ...


@dataclass(frozen=True)
class LanguageSettings:
    """
    Fully configured target language backend.

    Interfaces transpilation core with transpilation backends,
    managing code emission, AST transformations, formatting,
    linting, and `project` initialization.

    Example:
        settings = LanguageSettings(
            transpiler=RustTranspiler(),
            ext=".rs",
            display_name="Rust",
            formatter=["rustfmt"],
            create_project=["cargo", "new", "."]
        )
    """


    transpiler: CLikeTranspiler  # FIXME: CLikeTranspiler should not be here
    """The core object responsible for emitting code in the target language."""

    ext: str
    """The file extension for this language (e.g., '.rs', '.cpp')."""

    display_name: str
    """Human-readable name, e.g., 'Rust', 'C++'. Used in logs and CLI output."""

    lang_id: Optional[str] = None
    """
    Internal lowercase ID (e.g., 'rust', 'cpp').
    Used for registry keys and CLI argument matching.
    If None, fallback to display_name.lower().
    """

    formatter: Optional[Tuple[str, ...]] = None
    """Command-line formatter to invoke after emitting code
    (e.g., 'black', 'clang-format')."""

    indent: Optional[str] = None
    """Default indentation unit for this language,
    e.g., '    ' (4 spaces) or '\\t' (tab).
    If None, tools may fall back to 4 spaces.
    """

    rewriters: Tuple[ast.NodeVisitor, ...] = ()
    """AST visitor passes applied before code generation
    (e.g., mutability tagging)."""

    transformers: Tuple[Transformer, ...] = ()
    """Callables that transform AST nodes (used before or after visitors)."""

    post_rewriters: Tuple[ast.NodeVisitor, ...] = ()
    """AST passes applied after main rewriting but
    before rendering (e.g., cleanup)."""

    linter: Optional[Tuple[str, ...]] = None
    """External linter command(s) to invoke for this language, e.g., 'cargo clippy'."""

    create_project: Optional[Tuple[str, ...]] = None
    """Optional shell command to initialize a project structure for the target.
    Example: ('cargo', 'init') for Rust, or ('go', 'mod', 'init') for Go.
    """

    project_subdir: Optional[str] = None
    """Optional path inside the project directory where sources are expected.
    Example: 'src' for Rust.
    """

    ignore_formatter_errors: bool = False
    """If True, formatter failures won't break the transpilation pipeline."""


    def get_indent(self) -> str:
        """Return the indent unit for this language,
        falling back to 4 spaces if unset."""
        return self.indent if self.indent is not None else "    "

    def get_lang_id(self) -> str:
        """Return the language's canonical internal ID."""
        return self.lang_id or self.display_name.lower()

    def __repr__(self) -> str:
        return (
            f"<LanguageSettings for {self.display_name} "
            f"(ext='{self.ext}', id='{self.get_lang_id()}')>"
        )

    def __hash__(self) -> int:
        """ Enables use of LanguageSettings as dictionary keys or set members,
        primarily for caching or registry purposes."""
        fmt = tuple(self.formatter or ())
        lint = tuple(self.linter or ())
        return hash((self.transpiler, fmt, lint))
