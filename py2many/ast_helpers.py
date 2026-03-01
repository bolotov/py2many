import ast
from typing import cast

from py2many.astx import ASTxIf


def get_id(var) -> str | None:
    """
    Returns the identifier of an AST node, if it has one.
    Handles various AST node types such as
    alias, Name, arg, FunctionDef, ClassDef, and Attribute.

    If the node does not have an identifier, it returns None.
    
    Args:
        var: The AST node to extract the identifier from

    Returns:
        The identifier of the node, or None if the node
        does not have an identifier
    """

    if isinstance(var, ast.alias):
        return var.name
    elif isinstance(var, ast.Name):
        return var.id
    elif isinstance(var, ast.arg):
        return var.arg
    elif isinstance(var, ast.FunctionDef):
        return var.name
    elif isinstance(var, ast.ClassDef):
        return var.name
    elif isinstance(var, ast.Attribute):
        value_id = get_id(var.value)
        return f"{value_id}.{var.attr}"
    elif isinstance(var, ast.Constant):
        return str(var.value)
    elif isinstance(var, ast.Str):
        return var.s
    elif isinstance(var, ast.Num):
        return str(var.n)
    elif isinstance(var, ast.Bytes):
        return var.s.decode('utf-8')
    else:
        # print(f"warning: {var}"") # TODO: add logging/reporting
        return None

#----- This WAS here -------
#     if isinstance(var, ast.alias):
#         return var.name
#     elif isinstance(var, ast.Name):
#         return var.id
#     elif isinstance(var, ast.arg):
#         return var.arg
#     elif isinstance(var, ast.FunctionDef):
#         return var.name
#     elif isinstance(var, ast.ClassDef):
#         return var.name
#     elif isinstance(var, ast.Attribute):
#         value_id = get_id(var.value)
#         return f"{value_id}.{var.attr}"
##     elif isinstance(var, ast.Str): # Gone in 3.14 use ast.Constant
##         return var.s
##     elif isinstance(var, ast.Num): # Gone in 3.14 use ast.Constant
##         return str(var.n)
##     elif isinstance(var, ast.Bytes): # Gone in 3.14 use ast.Constant
##         return var.s.decode('utf-8')
#     else:
#         # print(f"warning: {var}"") # TODO: add logging/reporting
#         return None


def create_ast_node(code, at_node=None) -> ast.AST:
    """
    Returns an AST node created from the provided code string.
    If at_node is provided, the new node's line number and column offset
    will be set to match at_node.
    
    :param code:
    :param at_node:
    :return:
    """
    new_node = ast.parse(code).body[0]
    if at_node:
        new_node.lineno = at_node.lineno
        new_node.col_offset = at_node.col_offset
    return new_node


def create_ast_block(body, at_node=None) -> ASTxIf:
    """
    Returns an AST node representing a block of code with the provided body.
    The block is created as an if statement with a constant true condition,
    allowing it to be used as a container for the body statements.
    If at_node is provided, the new block's line number will be set to
    match at_node.
    
    :param body:
    :param at_node:
    :return:
    """
    block = cast(
        ASTxIf,
        ast.If(test=ast.Constant(value=True),body=body, orelse=[])
    )
    block.rewritten = True  # noqa
    if at_node:
        block.lineno = at_node.lineno
    ast.fix_missing_locations(block)
    return block
