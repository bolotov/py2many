import ast
from typing import Optional


class DocStringToCommentRewriter(ast.NodeTransformer):
    """
    It shittily rewrites docstrings to comments, since many languages
     don't support docstrings.
     Only rewrites if the node has a docstring, since otherwise there's
     nothing to rewrite.

     Also does not rewrite if the language is one that supports
     docstrings, since in those cases it's better
     to keep them as they are.

     The docstring is stored in a new field on the node called
     docstring_comment, so backends can choose to handle it
     differently if they want to.
    """
    def __init__(self): # FIXME: pipeline.py calls this with "language" parameter which may be stupid
        super().__init__()
        self._docstrings = set()
        self._docstring_parent = {}

    @staticmethod
    def _get_doc_node(node) -> Optional[ast.AST]:
        if not (node.body and isinstance(node.body[0], ast.Expr)):
            return None
        node = node.body[0].value
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node
        return None

    def _visit_documentable(self, node):
        doc_node = self._get_doc_node(node)
        self._docstrings.add(doc_node)
        self._docstring_parent[doc_node] = node
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        return self._visit_documentable(node)

    def visit_ClassDef(self, node):
        return self._visit_documentable(node)

    def visit_Module(self, node):
        return self._visit_documentable(node)

    def visit_Constant(self, node):
        if node in self._docstrings:
            parent = self._docstring_parent[node]
            parent.docstring_comment = ast.Constant(value=node.value)
            return None
        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        if not hasattr(node, "value"):
            return None
        return node

