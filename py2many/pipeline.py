import argparse
import ast
import os
import sys
import tempfile
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
from .analysis import add_imports
from .annotation_transformer import add_annotation_flags
from .context import add_assignment_context, add_list_calls, add_variable_context
from .exceptions import AstErrorBase
from .inference import infer_types, infer_types_typpete
from .language import LanguageSettings
from .mutability_transformer import detect_mutable_vars
from .nesting_transformer import detect_nesting_levels
from .raises_transformer import detect_raises
from .registry import ALL_SETTINGS, get_all_settings
from .scope import add_scope_context
from .version import __version__

from py2many.utilities.logger import setup_logger, LogLevel, NOOP #LOGGING
_log = setup_logger().unwrap_or(NOOP) # LOGGING

PY2MANY_DIR = Path(__file__).parent
ROOT_DIR = PY2MANY_DIR.parent
STDIN = "-"
STDOUT = "-"
CWD = Path.cwd()

FAKE_ARGS = argparse.Namespace(
    indent=4,
    no_prologue=False,
    extension=False,
    suffix="",
    comment_unsupported=False,
    ignore_formatter_errors=False,
    typpete=False,
    version=False,
    project=None,
    llm=False,
    llm_model=None,
)

LANGS = get_all_settings(FAKE_ARGS)






import ast


class ASTValidationError(Exception):
    pass


class ASTValidator(ast.NodeVisitor):

    def visit_Break(self, node):
        if not hasattr(node, "_in_loop"):
            raise ASTValidationError("break outside loop")

    def visit_Return(self, node):
        if not hasattr(node, "_in_function"):
            raise ASTValidationError("return outside function")

    def visit_Assign(self, node):
        for target in node.targets:
            if not isinstance(target, (ast.Name, ast.Attribute, ast.Subscript)):
                raise ASTValidationError(
                    f"invalid assignment target {type(target)}"
                )

    def generic_visit(self, node):
        super().generic_visit(node)


def validate(tree):
    """
    Example of use:

    for transform in pipeline:
    tree = transform.run(tree)
    validate(tree)
    """
    ASTValidator().visit(tree)







def core_transformers(
        tree: ast.AST,
        trees: Sequence[ast.AST],
        args: Optional[argparse.Namespace],
) -> Tuple[ast.AST, Any]:
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


def _transpile(
        filenames: List[Path],
        sources: List[str],
        settings,  # is it "Maybe" LanguageSetings
        args: Optional[argparse.Namespace] = None,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[List[str], List[Path]]:
    """
    Transpile a list of Python translation units into target language.
    :type settings: # FIXME: LanguageSetings - wrong type for some reason here
    """

    transpiler = settings.transpiler
    rewriters: List[Any] = list(settings.rewriters)
    transformers: List[Callable[[ast.AST], None]] = list(settings.transformers)
    post_rewriters: List[Any] = list(settings.post_rewriters)

    tree_list: List[ast.AST] = []
    for filename, source in zip(filenames, sources):
        tree = ast.parse(source)
        setattr(tree, "__file__", filename)
        tree_list.append(tree)

    trees = toposort(tree_list)
    topo_filenames: List[Path] = [
        getattr(t, "__file__") for t in trees  # type: ignore[arg-type]
    ]

    language = transpiler.NAME

    generic_rewriters: List[Any] = [
        ComplexDestructuringRewriter(language),
        PythonMainRewriter(settings.transpiler.main_signature_arg_names),
        FStringJoinRewriter(language),
        DocStringToCommentRewriter(),
        WithToBlockTransformer(language),
        IgnoredAssignRewriter(language),
    ]

    generic_post_rewriters: List[Any] = [
        PrintBoolRewriter(language),
        StrStrRewriter(language),
        UnpackScopeRewriter(language),
    ]

    if settings.ext != ".py":
        generic_post_rewriters.append(LoopElseRewriter(language))

    rewriters = generic_rewriters + rewriters
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
            successful.append(filename)
            outputs[filename] = output
        except Exception as e:
            import traceback

            formatted_lines = traceback.format_exc().splitlines()
            if isinstance(e, AstErrorBase):
                print(f"{filename}:{e.lineno}:{e.col_offset}: {formatted_lines[-1]}")
            else:
                print(f"{filename}: {formatted_lines[-1]}")
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
    add_scope_context(tree)

    for rewriter in rewriters:
        tree = rewriter.visit(tree)

    tree, infer_meta = core_transformers(tree, trees, args)

    for tx in transformers:
        tx(tree)

    for rewriter in post_rewriters:
        tree = rewriter.visit(tree)

    tree, infer_meta = core_transformers(tree, trees, args)

    out: List[str] = []
    code = transpiler.visit(tree) + "\n"
    headers = transpiler.headers(infer_meta)
    features = transpiler.features()

    if features:
        out.append(features)
    if headers:
        out.append(headers)

    usings = transpiler.usings()
    if usings:
        out.append(usings)

    aliases = transpiler.aliases()
    if aliases:
        out.append(aliases)

    out.append(code)

    if transpiler.extension:
        out.append(transpiler.extension_module(tree))

    return "\n".join(out)


@lru_cache(maxsize=100)
def _process_one_data(
        source_data: str,
        filename: Path,
        settings: LanguageSettings,
) -> str:
    """
    Process a single source string and return transpiled output.
    """
    outputs, _ = _transpile([filename], [source_data], settings)
    return outputs[0]


def _create_cmd(
        certain_parts: Sequence[str],
        filename: Path | str,
        **kw: Any,
) -> List[str]:
    """
    Return a command list with filename and other keyword arguments formatted in.
    """
    cmd = [arg.format(filename=filename, **kw) for arg in certain_parts]
    if list(certain_parts) != cmd:
        return cmd
    return [*certain_parts, str(filename)]


def _relative_to_cwd(absolute_path: Path) -> Path:
    """"Return a path relative to the current working directory."""
    return Path(os.path.relpath(absolute_path, CWD))


def _get_output_path(filename: Path, ext: str, out_dir: Path) -> Path:
    if filename.name == STDIN:
        return Path(STDOUT)

    directory = out_dir / filename.parent
    if not directory.is_dir():
        directory.mkdir(parents=True)

    output_path = directory / (filename.stem + ext)

    if ext == ".kt" and output_path.is_absolute():
        output_path = _relative_to_cwd(output_path)

    return output_path


def _process_one(
        settings: LanguageSettings,
        filename: Path,
        out_dir: Path,
        args: argparse.Namespace,
        environment: Optional[Mapping[str, str]],
) -> bool | Tuple[Set[Path], Set[Path]]:
    """Transpile and optionally reformat a single file."""

    suffix = f".{args.suffix}" if args.suffix is not None else settings.ext

    output_path = _get_output_path(
        filename.relative_to(filename.parent), suffix, out_dir
    )

    if filename.name == STDIN:
        output = _process_one_data(sys.stdin.read(), Path("test.py"), settings)

        tmp_name: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                    suffix=settings.ext, delete=False
            ) as f:
                tmp_name = f.name
                f.write(output.encode("utf-8"))

            tmp_path = Path(tmp_name)

            if _format_one(settings, tmp_path, environment):
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
        return _format_one(settings, output_path, environment)

    return True


def _format_one(
        settings: LanguageSettings,
        output_path: Path,
        env: Optional[Mapping[str, str]] = None,
) -> bool:
    try:
        restore_cwd: Optional[Path] = None

        # Kotlin formatter has issues with 'folder above' path, so
        # we change CWD to the output file's directory and run
        # the formatter there, which seems to work fine
        if settings.ext == ".kt" and output_path.parts and output_path.parts[0] == "..":
            restore_cwd = CWD
            os.chdir(output_path.parent)
            output_path = Path(output_path.name)

        cmd = _create_cmd(settings.formatter, filename=output_path)
        proc = run(cmd, env=env, capture_output=True)

        if proc.returncode:
            if settings.ext == ".jl":
                if proc.stderr:
                    print(
                        f"{cmd} (code: {proc.returncode}):\n{proc.stderr}{proc.stdout}"
                    )
                    if b"ERROR: " in proc.stderr:
                        return False
                return True

            print(
                f"Error: {cmd} (code: {proc.returncode}):\n{proc.stderr}{proc.stdout}"
            )

            if restore_cwd:
                os.chdir(restore_cwd)

            return False

        if settings.ext == ".kt":
            if run(cmd, env=env).returncode:
                print(f"Error: Could not reformat: {cmd}")
                if restore_cwd:
                    os.chdir(restore_cwd)
                return False

        if restore_cwd:
            os.chdir(restore_cwd)

    except Exception as e:
        if settings.ignore_formatter_errors:
            return True
        print(f"Error: Could not format: {output_path}")
        print(f"Due to: {e.__class__.__name__} {e}")
        return False

    return True


FileSet = Set[Path]


def _process_many(
        settings: LanguageSettings,
        basedir: Path,
        filenames: Sequence[Path],
        out_dir: Path,
        env: Optional[Mapping[str, str]] = None,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[FileSet, FileSet]:
    """Transpile and reformat many files."""

    settings.transpiler.set_continue_on_unimplemented()

    source_data: List[str] = []
    for filename in filenames:
        with open(basedir / filename) as f:
            source_data.append(f.read())

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

    for output, output_path in zip(outputs, output_paths):
        with open(output_path, "w") as f:
            f.write(output)

    successful_set: Set[Path] = set(successful)
    format_errors: Set[Path] = set()

    if settings.formatter:
        for filename, output_path in zip(filenames, output_paths):
            if filename in successful_set and not _format_one(
                    settings, output_path, env
            ):
                format_errors.add(filename)

    return successful_set, format_errors


def _process_dir(
        settings: LanguageSettings,
        source: Path,
        out_dir: Path,
        project: bool,
        env: Optional[Mapping[str, str]] = None,
        _suppress_exceptions: type[BaseException] = Exception,
) -> Tuple[Set[Path], Set[Path], Set[Path]]:
    print(f"Transpiling whole directory to {out_dir}:")

    if settings.create_project is not None and project:
        cmd = settings.create_project + [f"{out_dir}"]
        proc = run(cmd, env=env, capture_output=True)
        if proc.returncode:
            print(f"Error: running {' '.join(cmd)}: {proc.stderr}")
            return set(), set(), set()
        if settings.project_subdir is not None:
            out_dir = out_dir / settings.project_subdir
    else: # IF NOT "settings.create_project is not None and project" THEN WHAT?
        pass

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
        env=env,
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


def transpile_from_args(args: argparse.Namespace, env: Optional[Mapping[str, str]] = None) -> int:
    """
    Execute the transpilation pipeline using parsed CLI arguments.
    Returns process exit code (0 for success, 1 for failure).
    """
    if getattr(args, "version", False):
        print(__version__)
        return 0

    selected_language = args.lang
    if selected_language not in ALL_SETTINGS:
        raise ValueError(f"Unsupported language: {selected_language}")

    settings_func: Callable[..., LanguageSettings] = ALL_SETTINGS[selected_language]

    if env is None: # FIX ATTEMPT FOR     settings = settings_func(args, env=env)
        env = {}    # FIX ATTEMPT FOR     settings = settings_func(args, env=env)

    settings = settings_func(args, env=env)

    if getattr(args, "comment_unsupported", False) or not getattr(args, "strict", True):
        settings.transpiler.set_continue_on_unimplemented()

    settings.ignore_formatter_errors = getattr(args, "ignore_formatter_errors", False)

    rest = getattr(args, "_rest", [])
    for filename in rest:
        source = Path(filename)
        out_dir = (
            source.parent if args.out_dir is None else Path(args.out_dir)
        )

        if source.is_file() or source.name == STDIN:
            print(f"Writing to: {out_dir}", file=sys.stderr)
            try:
                rv = _process_one(settings, source, out_dir, args, env)
            except Exception as e:
                import traceback
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
            if args.out_dir is None:
                out_dir = source.parent / f"{source.name}-py2many"

            successful, format_errors, failures = _process_dir(
                settings, source, out_dir, getattr(args, "project", True), env=env
            )
            rv = not (failures or format_errors)

        return 0 if rv is True else 1

    return 1  # We return 1 here to indicate failure if no files were processed.
