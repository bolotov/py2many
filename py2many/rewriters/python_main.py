import ast
from typing import cast

from py2many.ast_helpers import create_ast_node
from .rename_transformer import RenameTransformer


def rename(scope, old_name, new_name):
    tx = RenameTransformer(old_name, new_name)
    tx.visit(scope)


class PythonMainRewriter(ast.NodeTransformer):
    def __init__(self, main_signature_arg_names):
        self.main_signature_arg_names = set(main_signature_arg_names)
        super().__init__()

    def visit_If(self, node):
        is_main = (
                isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                and isinstance(node.test.ops[0], ast.Eq)
                and isinstance(node.test.comparators[0], ast.Constant)
                and node.test.comparators[0].value == "__main__"
        )
        if is_main:
            if hasattr(node, "scopes") and len(node.scopes) > 1:
                rename(node.scopes[-2], "main", "main_func")
            # ast.parse produces a Module object that needs to be destructured
            if self.main_signature_arg_names == {"argc", "argv"}:
                ret = cast(
                    ast.FunctionDef,
                    create_ast_node(
                        "def main(argc: int, argv: List[str]) -> int: True", node
                    ),
                )
            elif self.main_signature_arg_names == {"argv"}:
                ret = create_ast_node("def main(argv: List[str]): True", node)
            else:
                ret = create_ast_node("def main(): True")
            ret = ret
            ret.lineno = node.lineno
            ret.body = node.body
            # So backends know to handle argc, argv etc
            ret.python_main = True
            return ret
        return node


