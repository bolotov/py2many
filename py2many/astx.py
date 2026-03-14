"""
Extended AST node dataclasses with extra metadata.

Defines extended AST node dataclasses that inherit from the standard `ast`
module's node classes.

These extended classes include additional fields for metadata that can
be used during the AST transformation and code generation processes.

The extra metadata includes information about variable lifetimes, whether
a class is a dataclass, mutable variables in functions, and more.

This allows for better and more informed transformations and optimizations
when converting Python code to other languages.
"""

import ast
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple


class LifeTime(IntEnum):
    UNKNOWN = 0
    STATIC = 1


class ASTxBlock(ast.stmt):
    """
    Synthetic block node used as an internal container
    for multiple statements.

    This node does not exist in Python syntax.
    It is used purely inside the transpilation pipeline.
    """

    _fields = ("body",)

    def __init__(self, body: List[ast.stmt]) -> None:
        super().__init__()
        self.body = body
        self.synthetic = True


@dataclass
class ASTxName(ast.Name):
    lifetime: LifeTime = LifeTime.UNKNOWN
    assigned_from: Optional["ASTx"] = None


@dataclass
class ASTxClassDef(ast.ClassDef):
    is_dataclass: bool = False


@dataclass
class ASTxFunctionDef(ast.FunctionDef):
    mutable_vars: List["ASTx"] = field(default_factory=list)
    python_main: bool = False


@dataclass
class ASTxModule(ast.Module):
    __file__: Optional[str] = None


@dataclass
class ASTxSubscript(ast.Subscript):
    container_type: Optional[Tuple[str, str]] = None
    generic_container_type: Optional[Tuple[str, str]] = None


@dataclass
class ASTxIf(ast.If):
    unpack: bool = False


@dataclass
class ASTx(ast.AST):
    annotation: ASTxName
    rewritten: bool = False
    lhs: bool = False
    scopes: List["ASTx"] = field(default_factory=list)
    id: Optional[str] = None
