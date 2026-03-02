import ast

from py2many.ast_helpers import get_id


def get_ann_repr(node, parse_func=None, default=None, sep=None) -> str:
    """
    Returns a string representation of the node suitable for type annotations,
    handling various AST node types such as
    Name, Call, Attribute, Constant, Subscript, Tuple, and List.
    If the node cannot be represented, it returns the provided default value.

    :param node: The AST node to represent
    :param parse_func: An optional function to parse the node's value
    (e.g., to handle type annotations)

    :param default: The default value to return if the node cannot be
    represented

    :param sep: An optional tuple of (open, close) separators to use
    for subscript representations (e.g., for generics)

    :return: A string representation of the node, or the default value
    if it cannot be represented
    """
    if sep is None:
        sep = ["[", "]"]

    if node is None:
        return default

    if isinstance(node, str):
        if parse_func:
            return parse_func(node)
        return node
    elif isinstance(node, ast.Name):
        id = get_id(node)
        if parse_func:
            return parse_func(id)
        return id
    elif isinstance(node, ast.Call):
        func = get_ann_repr(node.func, parse_func, default, sep)
        args = []
        for arg in node.args:
            args.append(get_ann_repr(arg, parse_func, default, sep))
        return f"{'.'.join(args)}.{func}"
    elif isinstance(node, ast.Attribute):
        return f"{get_ann_repr(node.value, parse_func, default, sep)}.{get_ann_repr(node.attr, parse_func, default, sep)}"
    elif isinstance(node, ast.Constant):
        if parse_func:
            return parse_func(node.value)
        return f"{node.value}"
    elif isinstance(node, ast.Subscript):
        id = get_ann_repr(node.value, parse_func, default, sep)
        slice_val = get_ann_repr(node.slice, parse_func, default, sep)
        if sep:
            return f"{id}{sep[0]}{slice_val}{sep[1]}"
        return f"{id}[{slice_val}]"
    elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        elts = list(map(lambda x: get_ann_repr(x, parse_func, default, sep), node.elts))
        return ", ".join(elts)
    elif ann := ast.unparse(node):
        # Not in expected cases
        if parse_func and (parsed_ann := parse_func(ann)):
            return parsed_ann
        return ann

    return default
