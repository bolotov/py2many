"""
AST helper utilities for py2many.

This module provides small utility functions used throughout
the transpilation pipeline for:

- Extracting identifiers from AST nodes
- Creating AST nodes from source strings
- Creating synthetic block containers
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Dict, Mapping, Optional, cast

from py2many.astx import ASTxIf, ASTxBlock

# ---------------------------------------------------------------------------
# Identifier Extraction
# ---------------------------------------------------------------------------

# Type alias for clarity
IdExtractor = Callable[[ast.AST], Optional[str]]


def _extract_attribute(node: ast.Attribute) -> Optional[str]:
    """Extract dotted name from Attribute node recursively."""
    base = get_id(node.value)
    if base is None:
        return None
    return f"{base}.{node.attr}"


def _extract_constant(node: ast.Constant) -> Optional[str]:
    """Extract identifier from Constant node."""
    if isinstance(node.value, bytes):
        return node.value.decode("utf-8")
    return str(node.value)


# Dispatch table for AST node types → identifier extraction logic.
_ID_EXTRACTORS: Mapping[type, IdExtractor] = {
    ast.alias: operator.attrgetter("name"),
    ast.Name: operator.attrgetter("id"),
    ast.arg: operator.attrgetter("arg"),
    ast.FunctionDef: operator.attrgetter("name"),
    ast.ClassDef: operator.attrgetter("name"),
    ast.Attribute: _extract_attribute,
    ast.Constant: _extract_constant,
    # Legacy nodes (safe fallback for older Python versions)
    ast.Str: operator.attrgetter("s"),      # pragma: no cover
    ast.Num: lambda n: str(n.n),            # pragma: no cover
    ast.Bytes: lambda b: b.s.decode("utf-8"),  # pragma: no cover
}


def get_id(var: Any) -> Optional[str]:
    """
    Extract an identifier-like string from an AST node.

    Supported node types:
        - alias
        - Name
        - arg
        - FunctionDef
        - ClassDef
        - Attribute (recursively dotted)
        - Constant (converted to string)

    Returns:
        A string representation of the identifier,
        or None if the node has no identifier semantics.

    This function is intentionally conservative.
    Unknown node types return None.
    """
    if not isinstance(var, ast.AST):
        return None

    extractor = _ID_EXTRACTORS.get(type(var))
    if extractor is None:
        return None

    return extractor(var)


# ---------------------------------------------------------------------------
# AST Creation Helpers
# ---------------------------------------------------------------------------

def create_ast_node(code: str, at_node: Optional[ast.AST] = None) -> ast.AST:
    """
    Create an AST node from a single-statement code string.

    Args:
        code:
            Python source code containing exactly one statement.

        at_node:
            Optional node whose location (lineno, col_offset)
            should be copied to the new node.

    Returns:
        The parsed AST node.

    Raises:
        ValueError:
            If the code does not produce exactly one statement.
    """
    module = ast.parse(code)

    if len(module.body) != 1:
        raise ValueError("create_ast_node expects exactly one statement")

    new_node = module.body[0]

    if at_node is not None:
        new_node.lineno = getattr(at_node, "lineno", 0)
        new_node.col_offset = getattr(at_node, "col_offset", 0)

    return new_node


def create_ast_block(
        body: list[ast.stmt],
        at_node: Optional[ast.AST] = None,
) -> ASTxBlock:
    """
    Create a synthetic block container node.

    This replaces the old `if True:` hack.

    This is used to inject multiple statements where the AST
    expects a single statement node.


    Args:
        body:
            List of AST statements to include inside the block.

        at_node:
            Optional node whose location should be copied.

    Returns:
        An ASTxBlock
    """
    block = ASTxBlock(body)

    if at_node is not None:
        block.lineno = getattr(at_node, "lineno", 0)
        block.col_offset = getattr(at_node, "col_offset", 0)

    ast.fix_missing_locations(block)
    return block