import ast
from typing import Optional

from .analysis import get_id


def detect_raises(node: ast.AST) -> ast.AST:
    return RaisesTransformer().visit(node)


class RaisesTransformer(ast.NodeTransformer):
    """
    Annotate FunctionDef nodes with a boolean attribute `raises`.
    A function is marked as raising if it:
      - contains an `assert`
      - calls another function already marked as raising
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Initialize attribute for stability
        node.raises = False
        self.generic_visit(node)
        return node

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        self._mark_parent_raises(node)
        return self.generic_visit(node)


    @staticmethod
    def _nearest_function(node: ast.AST) -> Optional[ast.FunctionDef]:
        """Find nearest enclosing FunctionDef, if any."""
        scopes = getattr(node, "scopes", None)
        if not scopes:
            return None

        for scope in scopes:
            if isinstance(scope, ast.FunctionDef):
                return scope
        return None

    def _mark_parent_raises(self, node: ast.AST) -> None:
        """Mark nearest enclosing function as raising."""
        fndef = self._nearest_function(node)
        if fndef is not None:
            fndef.raises = True

    def visit_Assert(self, node: ast.Assert) -> ast.AST:
        """Assert statements indicate the function can raise."""
        self._mark_parent_raises(node)
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Calls to functions marked as raising indicate the caller can raise."""
        scopes = getattr(node, "scopes", None)
        if not scopes:
            return self.generic_visit(node)

        # Extract function name safely
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = get_id(node.func)

        if func_name:
            finder = getattr(scopes, "find", None)
            if callable(finder):
                callee = finder(func_name)
                if callee is not None and getattr(callee, "raises", False):
                    self._mark_parent_raises(node)

        return self.generic_visit(node)