import ast
import textwrap
from typing import Any, Optional, Union, cast

from py2many.analysis import get_id
from py2many.ast_helpers import create_ast_block, create_ast_node
from py2many.clike import CLikeTranspiler
from py2many.inference import get_inferred_type
from py2many.scope import ScopeList
from py2many.tracer import find_node_by_type

class RenameTransformer(ast.NodeTransformer):
    def __init__(self, old_name, new_name):
        super().__init__()
        self._old_name = old_name
        self._new_name = new_name

    def visit_Name(self, node):
        if node.id == self._old_name:
            node.id = self._new_name
        return node

    def visit_FunctionDef(self, node):
        if node.name == self._old_name:
            node.name = self._new_name
        self.generic_visit(node)
        return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == self._old_name:
            node.func.id = self._new_name
        self.generic_visit(node)
        return node

def rename(scope, old_name, new_name):
    tx = RenameTransformer(old_name, new_name)
    tx.visit(scope)