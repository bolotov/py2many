import ast
import textwrap
from typing import Any, Optional, Union, cast

from py2many.analysis import get_id
from py2many.ast_helpers import create_ast_block, create_ast_node
from py2many.clike import CLikeTranspiler
from py2many.inference import get_inferred_type
from py2many.scope import ScopeList
from py2many.tracer import find_node_by_type


class FStringJoinRewriter(ast.NodeTransformer):
    """
    Rewrites fstrings to str.join calls for languages that don't support them
    """

    def __init__(self, language: str) -> None:
        super().__init__()
        self._language = language

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        if self._language in {"mojo", "python"}:
            # following comment is ancient as python supports f-strings
            # TODO: investigate what it does if target is python
            # FIXME: this code sucks as well, so all to be made normal
            # mojo fstrings will be implemented at some point
            # https://github.com/modularml/mojo/issues/398
            return node

        elements: list[ast.AST] = []

        for value in node.values:
            if isinstance(value, ast.Constant):
                elements.append(value)
            elif isinstance(value, ast.FormattedValue):
                elements.append(
                    ast.Call(
                        func=ast.Name(id="str", ctx=ast.Load()),
                        args=[value.value],
                        keywords=[],
                    )
                )

        join_call = ast.Call(
            func=ast.Attribute(
                value=ast.Constant(value=""),
                attr="join",
                ctx=ast.Load(),
            ),
            args=[ast.List(elts=elements, ctx=ast.Load())],
            keywords=[],
        )

        join_call.lineno = node.lineno
        join_call.col_offset = node.col_offset
        ast.fix_missing_locations(join_call)

        return join_call


