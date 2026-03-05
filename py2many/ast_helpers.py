import ast
from typing import cast

from py2many.astx import ASTxIf


def get_id(var: ast.AST) -> str | None:
    """
    Return the identifier represented by an AST node, if it has one.

    This function extracts identifier-like names from common declaration
    and reference nodes. For literal nodes (``ast.Constant``), it returns
    the string representation of the literal value.

    Supported node kinds:
        - ast.alias
        - ast.Name
        - ast.arg
        - ast.FunctionDef
        - ast.ClassDef
        - ast.Attribute (recursively resolved)
        - ast.Constant (stringified value)

    Parameters
    ----------
    var:
        The AST node to inspect.

    Returns
    -------
    str | None
        The extracted identifier or literal representation, or None
        if the node does not represent an identifier-like value.
    """

    if isinstance(var, ast.alias):
        return var.name

    if isinstance(var, ast.Name):
        return var.id

    if isinstance(var, ast.arg):
        return var.arg

    if isinstance(var, ast.FunctionDef):
        return var.name

    if isinstance(var, ast.ClassDef):
        return var.name

    if isinstance(var, ast.Attribute):
        base = get_id(var.value)
        if base is None:
            return None
        return f"{base}.{var.attr}"

    if isinstance(var, ast.Constant):
        value = var.value
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    return None


def create_ast_node(code: str, at_node: ast.AST | None = None) -> ast.AST:
    """
    Parse a single statement from source code and return its AST node.

    If ``at_node`` is provided, the returned node inherits its
    ``lineno`` and ``col_offset``. This is useful when synthesizing
    nodes during transformations while preserving source location.

    Args:
        code: A string containing a single Python statement.
        at_node: An optional AST node to copy location information from.

    Returns:
        The parsed AST node, potentially with updated location metadata.
    """
    module = ast.parse(code)
    new_node = module.body[0]

    if at_node is not None:
        new_node.lineno = at_node.lineno
        new_node.col_offset = at_node.col_offset

    return new_node


def create_ast_block(body, at_node=None) -> ASTxIf:
    """
    Create a synthetic block node containing the provided statements.

    The block is represented as:

        if True:
            <body>

    This allows grouping statements in contexts where a block node
    is required syntactically.

    The returned node is marked with ``rewritten = True`` to signal
    that it was introduced during transformation.

    Args:
        body: A list of AST nodes to include in the block body.
        at_node: Optional node whose line number should be copied.

    Returns:
        An ``ast.If`` node (typed as ``ASTxIf``) containing the body.
    """
    block = cast(
        ASTxIf,
        ast.If(
            test=ast.Constant(
                value=True
            ),
            body=body,
            orelse=[]
        )
    )

    block.rewritten = True  # transformation marker

    if at_node:
        block.lineno = at_node.lineno
    ast.fix_missing_locations(block)
    return block
