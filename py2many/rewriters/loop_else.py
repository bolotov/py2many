import ast
from typing import Union


class LoopElseRewriter(ast.NodeTransformer):
    """
    Rewrites Python's `for ... else` and `while ... else`
    into explicit flag-based control flow.

    Python semantics:
        The `else` block executes only if the loop
        completes without encountering `break`.

    Transformation:

        for ...:
            ...
        else:
            body

    becomes:

        _loop_break_0 = False
        for ...:
            ...
            # on break:
            _loop_break_0 = True
        if not _loop_break_0:
            body

    This transformation:
        - preserves semantics
        - supports nested loops
        - generates a unique flag per loop
        - does not rely on external scope metadata
    """

    def __init__(self, language: str) -> None:
        super().__init__()
        self._language: str = language
        self._counter: int = 0

    # ---------------------------------------------------------
    # MARK: Utilities
    # ---------------------------------------------------------

    def _new_flag_name(self) -> str:
        name = f"_loop_break_{self._counter}"
        self._counter += 1
        return name

    @staticmethod
    def _make_flag_assign(name: str, value: bool) -> ast.Assign:
        node = ast.Assign(
            targets=[ast.Name(id=name, ctx=ast.Store())],
            value=ast.Constant(value=value),
        )
        ast.fix_missing_locations(node)
        return node

    # ---------------------------------------------------------
    # MARK: Visitors
    # ---------------------------------------------------------

    def visit_For(self, node: ast.For) -> ast.AST:
        return self._rewrite_loop(node)

    def visit_While(self, node: ast.While) -> ast.AST:
        return self._rewrite_loop(node)

    # ---------------------------------------------------------
    # MARK: Core logic
    # ---------------------------------------------------------

    def _rewrite_loop(
        self, node: Union[ast.For, ast.While]
    ) -> ast.AST:
        self.generic_visit(node)

        if not node.orelse:
            return node

        flag_name = self._new_flag_name()

        # Initialize flag before loop
        init_flag = self._make_flag_assign(flag_name, False)

        # Rewrite breaks inside this loop body only
        node.body = self._rewrite_breaks(node.body, flag_name)

        # Build `if not flag:` wrapper for else
        test = ast.UnaryOp(
            op=ast.Not(),
            operand=ast.Name(id=flag_name, ctx=ast.Load()),
        )

        else_if = ast.If(
            test=test,
            body=node.orelse,
            orelse=[],
        )

        ast.fix_missing_locations(else_if)

        # Remove original orelse
        node.orelse = []

        # Return block:
        # flag = False
        # loop
        # if not flag: ...
        return ast.Module(
            body=[init_flag, node, else_if],
            type_ignores=[],
        )

    def _rewrite_breaks(
        self,
        body: list[ast.stmt],
        flag_name: str,
    ) -> list[ast.stmt]:
        """
        Recursively injects `flag = True` before `break`
        statements inside the loop body.
        """

        new_body: list[ast.stmt] = []

        for stmt in body:
            if isinstance(stmt, ast.Break):
                set_flag = self._make_flag_assign(flag_name, True)
                new_body.append(set_flag)
                new_body.append(stmt)
                continue

            # Recurse into nested blocks but stop at nested loops
            if isinstance(stmt, (ast.If, ast.With, ast.Try)):
                stmt.body = self._rewrite_breaks(stmt.body, flag_name)
                if hasattr(stmt, "orelse"):
                    stmt.orelse = self._rewrite_breaks(stmt.orelse, flag_name)
                new_body.append(stmt)
                continue

            if isinstance(stmt, (ast.For, ast.While)):
                # Do not rewrite nested loops here.
                # They will be handled separately by visitor.
                new_body.append(stmt)
                continue

            new_body.append(stmt)

        return new_body
