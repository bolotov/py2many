import ast

# MARK: - Constants & Literals (Modern ast.Constant replacements)

def is_number(node: ast.AST) -> bool:
    """Check if node is a numeric constant (int, float, complex)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float, complex))

def is_string(node: ast.AST) -> bool:
    """Check if node is a string constant."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str)

def is_bytes(node: ast.AST) -> bool:
    """Check if node is a bytes constant."""
    return isinstance(node, ast.Constant) and isinstance(node.value, bytes)

def is_boolean(node: ast.AST) -> bool:
    """Check if node is a boolean constant (True, False)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, bool)

def is_none(node: ast.AST) -> bool:
    """Check if node is a None constant."""
    return isinstance(node, ast.Constant) and node.value is None

def is_ellipsis(node: ast.AST) -> bool:
    """Check if node is an Ellipsis (...) constant."""
    return isinstance(node, ast.Constant) and node.value is Ellipsis

# MARK: - Structural Checks

def is_name(node: ast.AST) -> bool:
    """Check if node is an ast.Name."""
    return isinstance(node, ast.Name)

def is_attribute(node: ast.AST) -> bool:
    """Check if node is an ast.Attribute."""
    return isinstance(node, ast.Attribute)

def is_callable_definition(node: ast.AST) -> bool:
    """Check if node is a function or async function definition."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


# MARK: - Data Extraction Helpers

def get_name_id(node: ast.AST) -> str | None:
    """Return node.id if it is an ast.Name, else None."""
    return node.id if isinstance(node, ast.Name) else None

