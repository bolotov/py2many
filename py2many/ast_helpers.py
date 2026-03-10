import ast
from typing import cast

from py2many.astx import ASTxIf


def iter_body(body):
    """Yield AST nodes from a body that may be node | list[node] | None."""
    if body is None:
        return []

    if isinstance(body, list):
        return body

    return [body]


def safe_attr(node, name, default=None):
    """Read an attribute from an AST node without raising."""
    return getattr(node, name, default)


def is_name(node):
    """Return True if node is ast.Name."""
    return isinstance(node, ast.Name)


def is_attribute(node):
    """Return True if node is ast.Attribute."""
    return isinstance(node, ast.Attribute)


def get_name_id(node):
    """Return identifier if node is ast.Name, else None."""
    return node.id if isinstance(node, ast.Name) else None


def get_call_name(node):
    if not isinstance(node, ast.Call):
        return None

    func = node.func

    if isinstance(func, ast.Name):
        return func.id

    if isinstance(func, ast.Attribute):
        base = get_id(func.value)
        if base:
            return f"{base}.{func.attr}"

    return None


def mark_assigned(target: ast.AST, assign_node: ast.AST, scope: ast.AST) -> None:
    """
    Register assignment metadata for a variable inside a scope.
    """
    if not isinstance(target, ast.Name):
        return

    target.assigned_from = assign_node

    if not hasattr(scope, "vars"):
        scope.vars = set()

    scope.vars.add(target)



def get_id(node: ast.AST | None) -> str | None: # IMPORTANT: this is USED IN MANY PLACES!!
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

    Args:
        The AST node to inspect.

    Returns:
        (str | None): The extracted identifier or literal representation,
         or None if the node does not represent an identifier-like value.
    """



    """
    Extract identifier name from common AST nodes.
    """

    if not isinstance(node, ast.AST):
        return None

    match node:

        case ast.alias(name=name):
            return name

        case ast.Name(id=name):
            return name

        case ast.arg(arg=name):
            return name

        case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
            return name

        case ast.ClassDef(name=name):
            return name

        case ast.Attribute(value=value, attr=attr):
            base = get_id(value)
            return f"{base}.{attr}" if base else attr

        case _:
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
