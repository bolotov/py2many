"""
Transpilation pipeline orchestration for py2many.

This module coordinates parsing, rewriting, transforming, code generation,
formatting, and project-level transpilation operations.

The goal of this revision is **not to redesign the architecture**, but to
stabilize it while preserving the existing behavior.

Key improvements implemented here:

1. Safe transformer execution wrapper
   - Detects invalid transformer return values.
   - Supports both in-place and functional transformers.

2. Optional AST validation hook - 
   - Disabled by default to avoid breaking existing transformers.
   - Can be enabled during debugging.

3. Structural AST hashing for debugging transforms
   - Helps detect unexpected tree mutations.

The execution order and semantics of rewriters, transformers, and
code generation are intentionally preserved.
"""

import argparse
import ast
import hashlib
import os
import sys
import tempfile
import traceback
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from subprocess import run
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from py2many.rewriters import (
    ComplexDestructuringRewriter,
    DocStringToCommentRewriter,
    FStringJoinRewriter,
    IgnoredAssignRewriter,
    LoopElseRewriter,
    PrintBoolRewriter,
    PythonMainRewriter,
    StrStrRewriter,
    UnpackScopeRewriter,
    WithToBlockTransformer,
)

from py2many.utilities.toposort_modules import toposort
from py2many.utilities.logger import setup_logger

from .analysis import add_imports
from py2many.transformers.annotation_transformer import add_annotation_flags
from .context import add_assignment_context, add_list_calls, add_variable_context
from .exceptions import AstErrorBase
from .inference import infer_types, infer_types_typpete
from .language import LanguageSettings
from py2many.transformers.mutability_transformer import detect_mutable_vars
from py2many.transformers.nesting_transformer import detect_nesting_levels
from py2many.transformers.raises_transformer import detect_raises
from .registry import get_all_settings, call_factory
from .scope import add_scope_context
from .__init__ import __version__


_log = setup_logger()

FileSet = Set[Path] # A set of file paths, used to track successful and failed transpilation targets.

PY2MANY_DIR = Path(__file__).parent
ROOT_DIR = PY2MANY_DIR.parent
STDIN = "-"
STDOUT = "-"
CWD = Path.cwd()


DEFAULT_ARGS = {
    "indent": 4,
    "no_prologue": False,
    "extension": False,
    "suffix": "",
    "comment_unsupported": False,
    "ignore_formatter_errors": False,
    "typpete": False,
    "version": False,
    "project": None,
}

# Create default arguments namespace for module-level initialization
_DEFAULT_ARGS_NS = argparse.Namespace(**DEFAULT_ARGS)

# Get language settings factories and instantiate with defaults
_LANGS_FACTORIES = get_all_settings()
LANGS = {lang: call_factory(factory, _DEFAULT_ARGS_NS) 
         for lang, factory in _LANGS_FACTORIES.items()}


# ------------------------------------------------------------------------------
# MARK: AST validation (optional)
# ------------------------------------------------------------------------------

ENABLE_AST_VALIDATION = False


class ASTValidationError(Exception):
    """Raised when structural AST invariants are violated."""


class ASTValidator(ast.NodeVisitor):
    """
    Structural validator for Python AST nodes.

    This validator intentionally performs only minimal checks
    to avoid breaking existing transformations.
    """

    def visit_Assign(self, node):
        for target in node.targets:
            if not isinstance(target, (ast.Name, ast.Attribute, ast.Subscript)):
                raise ASTValidationError(
                    f"Invalid assignment target: {type(target).__name__}"
                )
        self.generic_visit(node)


def validate(tree: ast.AST) -> None:
    """Run structural validation on AST."""
    ASTValidator().visit(tree)


# ------------------------------------------------------------------------------
# MARK: AST debug helpers
# ------------------------------------------------------------------------------

def _ast_hash(tree: ast.AST) -> str:
    """
    Compute a stable structural hash of an AST.

    This is used only for debugging transform stages.
    """
    try:
        dump = ast.dump(tree, include_attributes=False)
    except TypeError:
        dump = ast.dump(tree)
    return hashlib.sha256(dump.encode()).hexdigest()


def _run_transform(tx: Callable[[ast.AST], Any], tree: ast.AST) -> ast.AST:
    """
    Execute a transformer safely.

    Supports both mutation-style and functional transformers.
    """
    name = getattr(tx, "__name__", type(tx).__name__)
    before = _ast_hash(tree)
    result = tx(tree)

    if result is None:
        tree_after = tree
    else:
        if not isinstance(result, ast.AST):
            raise RuntimeError(
                f"Transformer {name} returned invalid object: {type(result)}"
            )
        tree_after = result

    if ENABLE_AST_VALIDATION:
        validate(tree_after)

    after = _ast_hash(tree_after)

    _log.debug(f"transform {name}")
    _log.trace(f"ast hash {before[:8]} -> {after[:8]}")

    return tree_after


# ------------------------------------------------------------------------------
# MARK: Core semantic analysis stage
# ------------------------------------------------------------------------------


def core_transformers(
        tree: ast.AST,
        trees: Sequence[ast.AST],
        args: Optional[argparse.Namespace],
) -> Tuple[ast.AST, Any]:
    """
    Perform core analysis passes shared across languages.
    """

    add_variable_context(tree, trees)
    add_scope_context(tree)
    add_assignment_context(tree)
    add_list_calls(tree)

    detect_mutable_vars(tree)
    detect_nesting_levels(tree)
    detect_raises(tree)

    add_annotation_flags(tree)

    infer_meta = (
        infer_types_typpete(tree) if args and args.typpete else infer_types(tree)
    )

    add_imports(tree)

    return tree, infer_meta


# ------------------------------------------------------------------------------
# MARK: Transpilation
# ------------------------------------------------------------------------------


def _transpile(
        filenames: List[Path],
        sources: List[str],
        settings,
        args: Optional[argparse.Namespace] = None,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[List[str], List[Path]]:
    """
    Transpile multiple Python files to the target language.
    """

    transpiler = settings.transpiler

    rewriters: Tuple[Any] = tuple(settings.rewriters)
    transformers: List[Callable[[ast.AST], None]] = list(settings.transformers)
    post_rewriters: List[Any] = list(settings.post_rewriters)

    tree_list: List[ast.AST] = []

    for filename, source in zip(filenames, sources):
        tree = ast.parse(source)
        setattr(tree, "__file__", filename)
        tree_list.append(tree)

    trees = toposort(tree_list)

    topo_filenames: List[Path] = [
        getattr(t, "__file__") for t in trees
    ]

    language = transpiler.NAME

    generic_rewriters = (
        ComplexDestructuringRewriter(language),
        PythonMainRewriter(settings.transpiler.main_signature_arg_names),
        FStringJoinRewriter(language),
        DocStringToCommentRewriter(),
        WithToBlockTransformer(language),
        IgnoredAssignRewriter(language),
    )

    generic_post_rewriters = [
        PrintBoolRewriter(language),
        StrStrRewriter(language),
        UnpackScopeRewriter(language),
    ]

    if settings.ext != ".py":
        generic_post_rewriters.append(LoopElseRewriter(language))

    rewriters: Tuple[ast.NodeTransformer, ...] = tuple(generic_rewriters) + rewriters
    post_rewriters = generic_post_rewriters + post_rewriters

    outputs: Dict[Path, str] = {}
    successful: List[Path] = []

    for filename, tree in zip(topo_filenames, trees):
        try:
            output = _transpile_one(
                trees,
                tree,
                transpiler,
                rewriters,
                transformers,
                post_rewriters,
                args,
            )

            outputs[filename] = output
            successful.append(filename)

        except Exception as e:
            formatted = traceback.format_exc().splitlines()

            if isinstance(e, AstErrorBase):
                print(f"{filename}:{e.lineno}:{e.col_offset}: {formatted[-1]}")
            else:
                print(f"{filename}: {formatted[-1]}")

            if not _suppress_exceptions or not isinstance(e, _suppress_exceptions):
                raise

            outputs[filename] = "FAILED"

    output_list = [outputs[f] for f in filenames]

    return output_list, successful


def _transpile_one(
        trees: Sequence[ast.AST],
        tree: ast.AST,
        transpiler: Any,
        rewriters: Sequence[Any],
        transformers: Sequence[Callable[[ast.AST], None]],
        post_rewriters: Sequence[Any],
        args: Optional[argparse.Namespace],
) -> str:
    """
    Transpile a single AST tree into target language source code.
    """

    add_scope_context(tree)

    for rewriter in rewriters:
        tree = rewriter.visit(tree)

    tree, infer_meta = core_transformers(tree, trees, args)

    for tx in transformers:
        tree = _run_transform(tx, tree)

    for rewriter in post_rewriters:
        tree = rewriter.visit(tree)

    tree, infer_meta = core_transformers(tree, trees, args)

    code = transpiler.visit(tree) + "\n"

    out: List[str] = []

    features = transpiler.features()
    headers = transpiler.headers(infer_meta)
    usings = transpiler.usings()
    aliases = transpiler.aliases()

    if features:
        out.append(features)

    if headers:
        out.append(headers)

    if usings:
        out.append(usings)

    if aliases:
        out.append(aliases)

    out.append(code)

    if transpiler.extension:
        out.append(transpiler.extension_module(tree))

    return "\n".join(out)


# ------------------------------------------------------------------------------
# MARK: Shared helpers for file processing
# ------------------------------------------------------------------------------


def _read_sources(basedir: Path, filenames: Sequence[Path]) -> List[str]:
    """Read multiple source files."""
    data = []
    for filename in filenames:
        with open(basedir / filename) as f:
            data.append(f.read())
    return data


def _write_outputs(outputs: Sequence[str], paths: Sequence[Path]) -> None:
    """Write generated outputs to files."""
    for output, path in zip(outputs, paths):
        with open(path, "w") as f:
            f.write(output)


# ------------------------------------------------------------------------------
# Formatting
# ------------------------------------------------------------------------------


def _create_cmd(
        certain_parts: Sequence[str],
        filename: Path | str,
        **kw: Any,
) -> List[str]:
    """Construct formatter command."""
    cmd = [arg.format(filename=filename, **kw) for arg in certain_parts]

    if list(certain_parts) != cmd:
        return cmd

    return [*certain_parts, str(filename)]


def _format_one(
        settings: LanguageSettings,
        output_path: Path,
        env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Run external formatter for generated code."""
    try:
        cmd = _create_cmd(settings.formatter, filename=output_path)
        proc = run(cmd, env=env, capture_output=True)

        if proc.returncode:
            print(
                f"Error: {cmd} (code: {proc.returncode}):\n{proc.stderr}{proc.stdout}"
            )
            return False

    except Exception as e:
        if settings.ignore_formatter_errors:
            return True

        print(f"Error: Could not format: {output_path}")
        print(f"Due to: {e.__class__.__name__} {e}")
        return False
    return True


# ------------------------------------------------------------------------------
# MARK: High-level API
# ------------------------------------------------------------------------------

def transpile_from_args(
        args: argparse.Namespace,
) -> int:
    """Entry point used by CLI."""

    if getattr(args, "version", False):
        print(__version__)
        return 0

    language = args.lang

    if language not in get_all_settings():
        raise ValueError(f"Unsupported language: {language}")

    # Get the factory for the requested language and instantiate it with runtime args
    settings_factory = get_all_settings()[language]
    settings = call_factory(settings_factory, args)

    if getattr(args, "comment_unsupported", False) or not getattr(args, "strict", True):
        settings.transpiler.set_continue_on_unimplemented()

    # Update settings immutably using dataclasses.replace()
    settings = replace(
        settings,
        ignore_formatter_errors=getattr(args, "ignore_formatter_errors", False)
    )

    rest = getattr(args, "_rest", [])

    for filename in rest:
        source = Path(filename)
        out_dir = source.parent if args.out_dir is None else Path(args.out_dir)

        if source.is_file() or source.name == STDIN:
            print(f"Writing to: {out_dir}", file=sys.stderr)

            try:
                rv = _process_one(settings, source, out_dir, args) #, env)
            except Exception as e:

                formatted_lines = traceback.format_exc().splitlines()

                if isinstance(e, AstErrorBase):
                    print(
                        f"{source}:{e.lineno}:{e.col_offset}: {formatted_lines[-1]}",
                        file=sys.stderr,
                    )
                else:
                    print(f"{source}: {formatted_lines[-1]}", file=sys.stderr)
                rv = False

        else:
            successful, format_errors, failures = _process_dir(
                settings,
                source,
                out_dir,
                getattr(args, "project", True),
                # env=env,
            )

            rv = not (failures or format_errors)

        return 0 if rv is True else 1

    return 1



# ------------------------------------------------------------------------------
# Output path helpers
# ------------------------------------------------------------------------------

def _relative_to_cwd(absolute_path: Path) -> Path:
    """Return a path relative to the current working directory."""
    return Path(os.path.relpath(absolute_path, CWD))


def _get_output_path(filename: Path, ext: str, out_dir: Path) -> Path:
    """
    Compute the output file path for a transpiled file.
    """

    if filename.name == STDIN:
        return Path(STDOUT)

    directory = out_dir / filename.parent

    if not directory.is_dir():
        directory.mkdir(parents=True)

    output_path = directory / (filename.stem + ext)

    if ext == ".kt" and output_path.is_absolute():
        output_path = _relative_to_cwd(output_path)

    return output_path


# ------------------------------------------------------------------------------
# File processing
# ------------------------------------------------------------------------------

def _process_one(
        settings: LanguageSettings,
        filename: Path,
        out_dir: Path,
        args: argparse.Namespace,
        # environment: Optional[Mapping[str, str]],
) -> bool | Tuple[Set[Path], Set[Path]]:
    """
    Transpile and optionally format a single file.

    Returns:
        True on success
        False on failure
        tuple when stdin mode is used
    """
    suffix = f".{args.suffix}" if args.suffix is not None else settings.ext

    output_path = _get_output_path(
        filename.relative_to(filename.parent),
        suffix,
        out_dir,
    )

    if filename.name == STDIN:
        output = _process_one_data(sys.stdin.read(), Path("test.py"), settings)
        tmp_name: Optional[str] = None

        try:
            with tempfile.NamedTemporaryFile(
                    suffix=settings.ext,
                    delete=False,
            ) as f:
                tmp_name = f.name
                f.write(output.encode("utf-8"))

            tmp_path = Path(tmp_name)

            if _format_one(settings, tmp_path):
                sys.stdout.write(tmp_path.read_text())
            else:
                sys.stderr.write("Formatting failed")

        finally:
            if tmp_name is not None:
                os.remove(tmp_name)

        return {filename}, {filename}

    if filename.resolve() == output_path.resolve() and not args.force:
        print(f"Refusing to overwrite {filename}. Use --force to overwrite")
        return False

    print(f"{filename} ... {output_path}")

    with open(filename) as f:
        source_data = f.read()

    if filename.stem == "__init__" and not source_data:
        print("Detected empty __init__; skipping")
        return True

    outputs, _ = _transpile([filename], [source_data], settings, args)

    with open(output_path, "wb") as f:
        f.write(outputs[0].encode("utf-8"))

    if settings.formatter:
        return _format_one(settings, output_path)

    return True


@lru_cache(maxsize=100)
def _process_one_data(
        source_data: str,
        filename: Path,
        settings: LanguageSettings,
) -> str:
    """
    Transpile a single in-memory Python source string.

    Used by stdin mode.
    """
    outputs, _ = _transpile([filename], [source_data], settings)
    return outputs[0]




def _process_many(
        settings: LanguageSettings,
        basedir: Path,
        filenames: Sequence[Path],
        out_dir: Path,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[FileSet, FileSet]:
    """Transpile and optionally format multiple files."""

    settings.transpiler.set_continue_on_unimplemented()

    source_data = _read_sources(basedir, filenames)

    outputs, successful = _transpile(
        list(filenames),
        source_data,
        settings,
        _suppress_exceptions=_suppress_exceptions,
    )

    output_paths = [
        _get_output_path(filename, settings.ext, out_dir)
        for filename in filenames
    ]

    _write_outputs(outputs, output_paths)

    successful_set: Set[Path] = set(successful)
    format_errors: Set[Path] = set()

    if settings.formatter:

        for filename, output_path in zip(filenames, output_paths):

            if filename in successful_set and not _format_one(
                    settings,
                    output_path,
            ):
                format_errors.add(filename)

    return successful_set, format_errors


# ------------------------------------------------------------------------------
# MARK: Directory processing
# ------------------------------------------------------------------------------

def _process_dir(
        settings: LanguageSettings,
        source: Path,
        out_dir: Path,
        project: bool,
        # env: Optional[Mapping[str, str]] = None,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[Set[Path], Set[Path], Set[Path]]:
    """Transpile an entire directory recursively."""

    print(f"Transpiling whole directory to {out_dir}:")

    if settings.create_project is not None and project:
        cmd = settings.create_project + [f"{out_dir}"]

        proc = run(cmd, capture_output=True)

        if proc.returncode:
            print(f"Error: running {' '.join(cmd)}: {proc.stderr}")
            return set(), set(), set()

        if settings.project_subdir is not None:
            out_dir = out_dir / settings.project_subdir

    input_paths: List[Path] = []

    for path in source.rglob("*.py"):

        if path.parent.name == "__pycache__":
            continue

        relative_path = path.relative_to(source)

        target_dir = (out_dir / relative_path).parent

        os.makedirs(target_dir, exist_ok=True)

        input_paths.append(relative_path)

    successful, format_errors = _process_many(
        settings,
        source,
        input_paths,
        out_dir,
        # env=env,
        _suppress_exceptions=_suppress_exceptions,
    )

    failures = set(input_paths) - successful

    print("\nFinished!")
    print(f"Successful: {len(successful)}")

    if format_errors:
        print(f"Failed to reformat: {len(format_errors)}")

    print(f"Failed to convert: {len(failures)}")
    print()

    return successful, format_errors, failures