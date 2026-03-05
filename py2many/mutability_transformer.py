"""
Detect variables that are mutated inside functions and mark them as mutable.
This is used to determine which variables need to be passed by reference in
languages like C++.
"""
import ast
from typing import Dict, List, Optional

from py2many.analysis import get_id
from py2many.utilities.logger import setup_logger, NOOP, LogLevel

log = setup_logger().unwrap_or(NOOP)


def detect_mutable_vars(node: ast.AST) -> ast.AST:
    return MutabilityTransformer().visit(node)


class MutabilityTransformer(ast.NodeTransformer):
    """
    Detect variables that are written to more than once inside a function.
    A variable is considered mutable if assigned multiple times or mutated
    through list operations.
    """

    def __init__(self) -> None:
        super().__init__()

        # FIX: nested functions previously corrupted analysis state because
        # _usage_count was overwritten when entering an inner function.
        # A stack is required so each function has an independent environment.
        self._usage_stack: List[Dict[str, int]] = []

        self._in_lvalue: bool = False

    # ---------------------------------------------------------
    # MARK: - Helpers
    # ---------------------------------------------------------

    def _increment(self, name: Optional[str]) -> None:
        if not name or not self._usage_stack:
            return

        # FIX: use the top frame of the stack instead of a shared dictionary
        usage = self._usage_stack[-1]
        usage[name] = usage.get(name, 0) + 1

    def _enter_function(self) -> None:
        # FIX: push a new scope frame instead of resetting global state
        self._usage_stack.append({})

    def _leave_function(self, node: ast.AST) -> None:
        # FIX: pop the correct function frame
        usage = self._usage_stack.pop()

        mutable: List[str] = [
            name for name, count in usage.items() if count > 1
        ]

        # preserved existing external contract
        node.mutable_vars = mutable

    # ---------------------------------------------------------
    # MARK: - Visitors
    # ---------------------------------------------------------

    def _visit_function(self, node: ast.AST) -> ast.AST:
        """
        Shared handler for FunctionDef and AsyncFunctionDef.

        FIX: AsyncFunctionDef previously had no mutability analysis which
        caused downstream AttributeError when mutable_vars was expected.
        """
        self._enter_function()
        self.generic_visit(node)
        self._leave_function(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._visit_function(node)

    # FIX: async functions must be analyzed the same way as normal functions
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._visit_function(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        for target in node.targets:
            self._visit_assignment_target(target)
        self.visit(node.value)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        self._visit_assignment_target(node.target)
        if node.value:
            self.visit(node.value)
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:
        self._visit_assignment_target(node.target)
        self.visit(node.value)
        return node

    def _visit_assignment_target(self, target: ast.AST) -> None:
        previous = self._in_lvalue
        self._in_lvalue = True

        # FIX: tuple/list unpacking targets were previously ignored,
        # resulting in missed mutations such as:  a, b = foo()
        if isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self.visit(elt)
        else:
            self.visit(target)

        self._in_lvalue = previous

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if self._in_lvalue:
            self._increment(get_id(node))
        return node


    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Track list mutations like x.append(...)
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in {"append", "extend", "insert", "remove", "pop"}:
                value = node.func.value
                if isinstance(value, ast.Name):
                    self._increment(get_id(value))

        # Track passing mutable args to functions that mutate them
        fname = get_id(node.func)

        # Defensive guard: scope analysis may not have run yet
        scopes = getattr(node, "scopes", None)

        if fname and scopes:
            try:
                fndef = scopes.find(fname)

            # EXPECTED structural failures
            except (AttributeError, TypeError):
                # AttributeError → scopes object missing expected API
                # TypeError → scopes is not a ScopeList-like object
                log(LogLevel.WARNING, f"Invalid scope object while resolving '{fname}'")
                fndef = None

            # Lookup failure inside ScopeList
            except KeyError:
                fndef = None

            # True unexpected failure (pipeline corruption)
            except Exception as exc:  # pragma: no cover
                log.exception(
                    f"Unexpected scope lookup failure for '{fname}'",
                    exc
                )
                fndef = None
        else:
            fndef = None

        if fndef and hasattr(fndef, "args") and hasattr(fndef, "mutable_vars"):
            for fnarg, arg_node in zip(fndef.args.args, node.args):
                if fnarg.arg in getattr(fndef, "mutable_vars", []):
                    if isinstance(arg_node, ast.Name):
                        self._increment(get_id(arg_node))

        self.generic_visit(node)
        return node