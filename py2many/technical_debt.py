# All here is unfortunate necessary temporary EVIL
# TODO: add logging when necessary

import ast



def getattr_by_name(source: ast.AST, key: str | None) -> str | None:
    """
    Retrieve the specified attribute from an AST node.

    Parameters:
    source (ast.AST): The AST node from which to retrieve the attribute.
    key (str): The name of the attribute to retrieve.

    Returns:
    The value of the requested attribute, or None if it does not exist.

    Example:
    >>> line = "x = 5"
    >>> tree_1 = ast.parse(line)
    >>> some_node = tree_1.body[0]  # Access the first node (Assign)
    >>> getattr_by_name(some_node, 'targets')
    [<_ast.Name object at ...>]
    >>> getattr_by_name(some_node, 'value')
    <_ast.Constant object at ...>
    >>> getattr_by_name(some_node, 'nonexistent_attr')
    Warning: 'nonexistent_attr' attribute does not exist on the given AST node.
    >>> getattr_by_name(some_node, None)  # Passing None as key
    >>> None
    """
    if key is None:
        return None  # Return None if no key is provided

    try:
        return getattr(source, key)  # Return the attribute value
    except AttributeError:
        print(f"\033[93mWarning: '{key}' attribute does not exist on the given AST node.\033[0m")
        return None  # Return None if the attribute does not exist

