import ast

from py2many.clike import CLikeTranspiler


class UnpackScopeRewriter(ast.NodeTransformer):
    """ Rewrites nested blocks (e.g. if, for, with) to a single block, since some
    languages don't support nested blocks. Only rewrites if there are nested blocks,
    since otherwise there's nothing to rewrite.
     Also does not rewrite if the language supports nested blocks, since in those
     cases it's better to keep the original nested blocks, which are more readable
     and maintain the original structure of the code.
     The new block is created by unpacking the body of the nested blocks into
     a single block, and the original nested blocks are removed.
     This is done recursively until there are no more nested blocks.
     A hint is added to the new block to not unpack it again, since it's already
     been unpacked.
    """
    def __init__(self, language):
        super().__init__()
        self._language = language

    def _visit_body(self, body):
        unpacked = []
        for s in body:
            do_unpack = getattr(s, "unpack", True)
            if isinstance(s, ast.If) and CLikeTranspiler.is_block(s) and do_unpack:
                unpacked.extend(self._visit_body(s.body))
            else:
                unpacked.append(s)
        return unpacked

    def _visit_assign_node_body(self, node):
        node.body = self._visit_body(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        return self._visit_assign_node_body(node)

    def visit_For(self, node: ast.For) -> ast.For:
        return self._visit_assign_node_body(node)

    def visit_If(self, node: ast.If) -> ast.If:
        return self._visit_assign_node_body(node)

    def visit_With(self, node: ast.With) -> ast.With:
        return self._visit_assign_node_body(node)

    def visit_While(self, node: ast.With) -> ast.With:
        return self._visit_assign_node_body(node)


