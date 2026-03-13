import ast
import textwrap
from typing import cast

from py2many.ast_helpers import create_ast_node, get_id


class PrintBoolRewriter(ast.NodeTransformer):
    def __init__(self, language):
        super().__init__()
        self._language = language

    @staticmethod
    def _do_other_rewrite(node) -> ast.AST:
        ifexpr = cast(
            ast.Expr, create_ast_node("True if True else False", node)
        ).value
        ifexpr = cast(ast.IfExp, ifexpr)
        ifexpr.test = node.args[0]
        ifexpr.lineno = node.lineno
        ifexpr.col_offset = node.col_offset
        ast.fix_missing_locations(ifexpr)
        node.args[0] = ifexpr
        return node

    # Go can't handle IfExpr in print. Handle it differently here
    @staticmethod
    def _do_go_rewrite(node) -> ast.AST:
        if_stmt = create_ast_node(
            textwrap.dedent(
                """\
            if True:
                print('True')
            else:
                print('False')
        """
            ),
            node,
        )
        if_stmt = cast(ast.If, if_stmt)
        if_stmt.test = node.args[0]
        if_stmt.lineno = node.lineno
        if_stmt.col_offset = node.col_offset
        ast.fix_missing_locations(if_stmt)
        return if_stmt

    def visit_Call(self, node):
        if get_id(node.func) == "print":
            if len(node.args) == 1:
                anno = getattr(node.args[0], "annotation", None)
                if get_id(anno) == "bool":
                    if self._language == "go":
                        return self._do_go_rewrite(node)
                    else:
                        return self._do_other_rewrite(node)
        return node

