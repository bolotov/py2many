import ast
from typing import List, TypeVar

from py2many.astx import ASTxBlock


T = TypeVar("T", bound=ast.AST)


class UnpackScopeRewriter(ast.NodeTransformer):
    """
    Flatten synthetic block containers (ASTxBlock).

    Removes ASTxBlock nodes by inlining their body into
    the surrounding statement body.
    """

    def __init__(self, language: object) -> None:
        super().__init__()
        self._language = language

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _flatten_body(self, body: List[ast.stmt]) -> List[ast.stmt]:
        """
        Inline ASTxBlock statements into the surrounding body.
        """
        flattened: List[ast.stmt] = []

        for stmt in body:
            if isinstance(stmt, ASTxBlock):
                flattened.extend(self._flatten_body(stmt.body))
            else:
                flattened.append(stmt)

        return flattened

    def _rewrite_compound(self, node: T) -> T:
        """
        Rewrite compound statement nodes while preserving type.
        """
        self.generic_visit(node)

        if hasattr(node, "body"):
            node.body = self._flatten_body(node.body)  # type: ignore[attr-defined]

        if hasattr(node, "orelse"):
            node.orelse = self._flatten_body(node.orelse)  # type: ignore[attr-defined]

        return node

    # ------------------------------------------------------------------
    # Visitors
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._rewrite_compound(node)

    def visit_For(self, node: ast.For) -> ast.For:
        return self._rewrite_compound(node)

    def visit_If(self, node: ast.If) -> ast.If:
        return self._rewrite_compound(node)

    def visit_With(self, node: ast.With) -> ast.With:
        return self._rewrite_compound(node)

    def visit_While(self, node: ast.While) -> ast.While:
        return self._rewrite_compound(node)