import ast
from typing import Any, Iterable


IGNORED_MODULE_SET = {
    "typing",
    "enum",
    "dataclasses",
    "ctypes",
    "math",
    "__future__",
    "asyncio",
    "sys",
    "os",
    "adt",
    "py2many.result",
    "py2many.smt",
}


def add_imports(node: ast.AST) -> ast.AST:
    """Populate scope.imports with imported symbols."""
    return ImportTransformer().visit(node)


def is_void_function(fun: ast.FunctionDef) -> bool:
    """
    Return True if the function does not return a value.

    A function is considered void if:
    - it contains no `return <value>` statements, and
    - it has no return annotation.
    """
    finder = ReturnFinder()
    finder.visit(fun)
    return not finder.returns and fun.returns is None


def is_global(target: Any) -> bool:
    """
    Return True if target belongs to module-level scope.
    """
    scopes = getattr(target, "scopes", None)
    if not scopes:
        return False
    return isinstance(scopes[-1], ast.Module)


def is_mutable(scopes: Iterable[Any], target: Any) -> bool:
    """
    Return True if target is marked mutable inside a function scope.

    The transformer that detects mutability is responsible for
    attaching `mutable_vars` to FunctionDef nodes.
    """
    for scope in scopes:
        if isinstance(scope, ast.FunctionDef):
            mutable = getattr(scope, "mutable_vars", None)
            if mutable and target in mutable:
                return True
    return False


def is_ellipsis(node: ast.AST) -> bool:
    """
    Return True if node represents an ellipsis literal (`...`).
    """
    return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and node.value.value is ...
    )


class ReturnFinder(ast.NodeVisitor):
    """
    Detect whether a function contains a `return` with a value.
    """

    def __init__(self) -> None:
        self.returns: bool = False

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self.returns = True
        self.generic_visit(node)


class FunctionTransformer(ast.NodeTransformer):
    """
    Track defined functions within scoped nodes.

    Relies on nodes having a `scopes` attribute injected earlier
    by scope analysis.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.defined_functions = []
        scopes = getattr(node, "scopes", None)
        if scopes and len(scopes) >= 2:
            parent_scope = scopes[-2]
            defined = getattr(parent_scope, "defined_functions", None)
            if defined is not None:
                defined.append(node)
        self.generic_visit(node)
        return node

    def _visit_scoped(self, node: ast.AST) -> ast.AST:
        node.defined_functions = []
        self.generic_visit(node)
        return node

    def visit_Module(self, node: ast.Module) -> ast.AST:
        return self._visit_scoped(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return self._visit_scoped(node)

    def visit_For(self, node: ast.For) -> ast.AST:
        return self._visit_scoped(node)

    def visit_If(self, node: ast.If) -> ast.AST:
        return self._visit_scoped(node)

    def visit_With(self, node: ast.With) -> ast.AST:
        return self._visit_scoped(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        scopes = getattr(node, "scopes", None)
        if not scopes:
            return node

        current_scope = scopes[-1]
        defined = getattr(current_scope, "defined_functions", None)
        if defined is None:
            return node

        if node.module not in IGNORED_MODULE_SET:
            for name in node.names:
                defined.append(name)

        return node


class CalledWithTransformer(ast.NodeTransformer):
    """
    Track variables and functions that are used as call arguments.
    """

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        for target in node.targets:
            setattr(target, "called_with", [])
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.called_with = []
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        scopes = getattr(node, "scopes", None)
        if not scopes:
            return self.generic_visit(node)

        for arg in node.args:
            if isinstance(arg, ast.Name):
                scope_manager = scopes
                finder = getattr(scope_manager, "find", None)
                if callable(finder):
                    var = finder(arg.id)
                    if var is not None:
                        called = getattr(var, "called_with", None)
                        if called is not None:
                            called.append(node)
        return self.generic_visit(node)


class AttributeCallTransformer(ast.NodeTransformer):
    """
    Track attribute calls on variables (e.g., x.foo()).
    """

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        for target in node.targets:
            setattr(target, "calls", [])
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        scopes = getattr(node, "scopes", None)
        if (
                scopes
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
        ):
            finder = getattr(scopes, "find", None)
            if callable(finder):
                var = finder(node.func.value.id)
                if var is not None:
                    calls = getattr(var, "calls", None)
                    if calls is not None:
                        calls.append(node)
        return self.generic_visit(node)


class ImportTransformer(ast.NodeTransformer):
    """
    Attach imported symbols to scope.imports.
    """

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        scopes = getattr(node, "scopes", None)
        if not scopes:
            return node

        current_scope = scopes[-1]
        imports = getattr(current_scope, "imports", None)
        if imports is None:
            return node

        for name in node.names:
            name.imported_from = node
            imports.append(name)

        return node

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.imports = []
        self.generic_visit(node)
        return node