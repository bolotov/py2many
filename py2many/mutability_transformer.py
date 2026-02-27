"""
Detect variables that are mutated inside functions and mark them as mutable.
This is used to determine which variables need to be passed by reference in
languages like C++.
"""
import ast
from typing import Dict, List, Optional

from py2many.analysis import get_id


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
        self._usage_count: Dict[str, int] = {}
        self._in_lvalue: bool = False

    # ---------------------------------------------------------
    # MARK: - Helpers
    # ---------------------------------------------------------

    def _increment(self, name: Optional[str]) -> None:
        if not name:
            return
        self._usage_count[name] = self._usage_count.get(name, 0) + 1

    def _enter_function(self) -> None:
        self._usage_count = {}

    def _leave_function(self, node: ast.FunctionDef) -> None:
        mutable: List[str] = [
            name for name, count in self._usage_count.items() if count > 1
        ]
        node.mutable_vars = mutable  # preserved existing external contract

    # ---------------------------------------------------------
    # MARK: - Visitors
    # ---------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self._enter_function()
        self.generic_visit(node)
        self._leave_function(node)
        return node

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
        if fname and hasattr(node, "scopes"):
            try:
                fndef = node.scopes.find(fname)
            except Exception:
                fndef = None

            if fndef and hasattr(fndef, "args") and hasattr(fndef, "mutable_vars"):
                for fnarg, arg_node in zip(fndef.args.args, node.args):
                    if fnarg.arg in getattr(fndef, "mutable_vars", []):
                        if isinstance(arg_node, ast.Name):
                            self._increment(get_id(arg_node))

        self.generic_visit(node)
        return node