import ast
import importlib
import io  # noqa: F401
import logging
import math  # noqa: F401
import os  # noqa: F401
import random  # noqa: F401
import sys
import time  # noqa: F401
from ctypes import c_int16 as i16
from ctypes import c_int32 as i32
from ctypes import c_int64 as i64
# Fixed width ints and aliases
from ctypes import c_int8 as i8
from ctypes import c_uint16 as u16
from ctypes import c_uint32 as u32
from ctypes import c_uint64 as u64
from ctypes import c_uint8 as u8
from typing import (  # noqa: F401
    Any,
    Callable,
    Dict,
    List,
    Optional,
    OrderedDict,
    Tuple,
    Union,
    Mapping,
    Type,
)

from py2many.analysis import IGNORED_MODULE_SET
from py2many.ast_helpers import *
from py2many.astx import LifeTime
from py2many.ast_predicates import is_callable_definition
from py2many.exceptions import (
    AstCouldNotInfer,
    AstEmptyNodeFound,
    AstNotImplementedError,
    AstTypeNotSupported,
    TypeNotSupported,
)

# from py2many.result import Result  # noqa: F401

ilong = i64
ulong = u64
isize = i64
usize = u64
c_int8 = i8
c_int16 = i16
c_int32 = i32
c_int64 = i64
c_uint8 = u8
c_uint16 = u16
c_uint32 = u32
c_uint64 = u64

symbols = {
    ast.Eq: "==",
    ast.Is: "==",
    ast.NotEq: "!=",
    ast.Mult: "*",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Div: "/",
    ast.FloorDiv: "/",
    ast.Mod: "%",
    ast.Lt: "<",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.LtE: "<=",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.BitXor: "^",
    ast.BitOr: "|",
    ast.BitAnd: "&",
    ast.Not: "!",
    ast.IsNot: "!=",
    ast.USub: "-",
    ast.And: "&&",
    ast.Or: "||",
    ast.In: "in",
}


_AUTO = "auto"
_AUTO_INVOKED = "auto()"

logger = logging.getLogger("py2many")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)



def class_for_typename(
        typename: Optional[list[str]| str],
        default_type,
        localns: Optional[Mapping[str, Any]] = None,
) -> Optional[Union[str, object]]:
    """
    Resolve a type annotation string into a Python object.

    The function attempts to evaluate `typename` in the current global
    namespace combined with `localns`. If resolution fails, `default_type`
    is returned.

    Special cases:
        - "super" and "super(...)" are ignored and return None.
        - Bound methods are converted to their defining class.

    This function does not guarantee returning a `type`. It may return:
        - a class
        - a function
        - a module attribute
        - `default_type`
        - None (for unsupported constructs like `super`)
    """
    if typename is None:
        return None

    if typename == "super" or typename.startswith("super()"):
        return None

    try:
        resolved = eval(typename, globals(), localns)

        if hasattr(resolved, "__self__") and not isinstance(
                resolved.__self__, type(sys)
        ):
            return getattr(resolved.__self__.__class__, resolved.__name__)

        if not isinstance(resolved, (type, type(open), type(class_for_typename))):
            return resolved.__class__

        return resolved

    except (NameError, SyntaxError, AttributeError, TypeError) as exc:
        logger.debug("Could not evaluate typename '%s': %s", typename, exc)
        return default_type



def c_symbol(node: ast.AST) -> str:
    """
    Map a Python AST operator node to its C-like symbol representation.

    Raises:
        KeyError if operator is not registered in `symbols`.
    """
    return symbols[type(node)]


class CLikeTranspiler(ast.NodeVisitor):
    """Base transpiler for C-like languages (e.g., C, C++, Java, Rust).

        Provides common logic for handling imports, type annotations, and basic
        constructs while allowing language-specific customization through overrides.
        Handles the common AST rewriter idiom where `if True:` blocks are used to
        group statements.

        Attributes:
            NAME (str): The identifier for the target language.
            builtin_constants (frozenset): Set of supported boolean/null constants.
            _type_map (Dict[Any, str]): Mapping of Python types to target types.
            _container_type_map (Dict[str, str]): Mapping for generic containers.
    """

    NAME: str

    builtin_constants = frozenset(["True", "False"])
    _default_type = _AUTO
    _type_map: Dict[Any, str] = {}
    _container_type_map: Dict[str, str] = {}


    def __init__(self):
        """Initializes the transpiler state.

        Note:
            This method is also called by `._reset()` to clear internal
            buffers and state between translation passes.
        """
        self._headers = set()
        self._usings = set()
        self._aliases = {}
        self._imported_names = {}
        self._features = set()
        self._statement_separator = ";" # separators **besides** newline
        self._main_signature_arg_names = []
        self._extension = False
        self._ignored_module_set = IGNORED_MODULE_SET.copy()
        self._module = None
        self._dispatch_map = {}
        self._small_dispatch_map = {}
        self._small_usings_map = {}
        self._func_dispatch_table = {}
        self._func_usings_map = {}
        self._attr_dispatch_table = {}
        self._keywords = {}
        self._throw_on_unimplemented = True


    def _reset(self):
        """Resets the internal state of the transpiler to its default values.

        This method clears all accumulated metadata (headers, usings, aliases,
        features) to prevent state leakage when the same instance is used to
        transpile multiple files. It achieves this by re-invoking `__init__`.

        Note:
            Certain configuration flags, such as `_extension`, `_no_prologue`,
            and `_throw_on_unimplemented`, are preserved across the reset.

        See Also:
            `visit_Module`: This method is automatically called at the start
            of every module visit to ensure a clean slate.
        """
        # Save some settings
        extension = self._extension
        throw_on_unimplemented = self._throw_on_unimplemented
        no_prologue = getattr(self, "_no_prologue", False)

        self.__init__()

        # Re-apply settings
        self._no_prologue = no_prologue
        self._extension = extension
        self._throw_on_unimplemented = throw_on_unimplemented

    # MARK: Placeholders for language-specific overrides

    @property
    def aliases(self) -> str: return ""
    """Return any type aliases needed for the target language as a string."""

    def headers(self, meta=None) -> str: return ""
    """Return the necessary headers for the target language as a string."""

    def usings(self) -> str: return ""
    """Return the necessary using/import statements for the target language as a string."""



    def _import(self, name: str): ...
    """
    Placeholder for the method that handles the actual
    import logic for a module name.

    Args:
    name (str): The name of the module to import.

    Returns:
    str: A string representing the import statement
    for the target language.
    """


    @property
    def main_signature_arg_names(self):
        return self._main_signature_arg_names

    @property
    def features(self) -> str: return ""
    """Return any language features needed for the target language as a string."""

    def extension(self) -> bool: return self._extension
    """Whether the transpiler is being used in **extension mode**"""

    @property
    def extension_module(self) -> str: return ""
    """Return the module name to use for an extension build, if applicable."""

    @staticmethod
    def comment(text) -> str: return f"/* {text} */"
    """Return a comment string for the target language."""

    @staticmethod
    def comment_block(lines: list[str]) -> str:
        """Emit a block comment."""
        return f"/*\n" + f"'\n'.join(lines)" + f"\n*/"

    @staticmethod
    def _cast(name: str, to) -> str: return f"({to}) {name}"
    """Return a string representing a cast of name to the type represented by to in the target language."""

    @staticmethod
    def _slice_value(node: ast.Subscript) -> ast.AST:
        """
        Return the slice or index component of a Subscript node (Python 3.14+).

        In Python 3.14, the Subscript.slice field directly holds the slice or index node.
        All literals (numbers, strings, booleans, None, Ellipsis) are now ast.Constant.

        Args:
            node (ast.Subscript): The AST Subscript node to extract the slice from.

        Returns:
            ast.AST: The slice or index node.

        Raises:
            AstNotImplementedError: If the slice is an advanced slice (start:stop:step)
                                    or an extended multidimensional slice.
        """
        slice_node = node.slice

        # Advanced slicing is not supported
        if isinstance(slice_node, ast.Slice):
            raise AstNotImplementedError(
                "Advanced slicing (start:stop:step) not supported", node
            )
        if isinstance(slice_node, ast.Tuple):  # WAS: ast.ExtSlice
            raise AstNotImplementedError(
                "Extended multi-dimensional slices not supported", node
            )

        # Everything else (ast.Constant, ast.Name, or other simple node) is valid
        return slice_node


    @classmethod
    def _map_type(
            cls,
            typename: Optional[str],
            lifetime: LifeTime = LifeTime.UNKNOWN,
    ) -> str:
        """
        Map a Python annotation string to a target-language type string.

        If no mapping exists, returns the original typename or default type.
        """
        if typename is None:
            return cls._default_type

        if isinstance(typename, list):
            raise NotImplementedError(f"{typename} not supported in this context")

        resolved = class_for_typename(typename, cls._default_type)
        mapped = cls._type_map.get(resolved, typename)

        if mapped == typename:
            logger.debug(
                "[%s] No type mapping for '%s', using fallback.",
                cls.__name__,
                typename,
            )

        return mapped


    @classmethod
    def _map_types(cls, typenames: List[str]) -> List[str]:
        """Map a list of annotation strings to target-language types."""
        return [cls._map_type(name) for name in typenames]


    @classmethod
    def _map_container_type(cls, typename: str) -> str:
        """
        Map a container type name (e.g. List, Dict) to its
        target-language representation.
        """
        return cls._container_type_map.get(typename, cls._default_type)


    @classmethod
    def _combine_value_index(cls, value_type, index_type) -> str:
        """
        Combine a value type and an index type into a single string representation for container types.
        For example, if we have a value type of "List" and an index type of "int",
        this method might return "List<int>" for a language like C++ or "Vec<i32>" for Rust.
        """
        return f"{value_type}<{index_type}>"


    @classmethod
    def _visit_container_type(cls, typename: Tuple) -> str:
        """Handle the mapping of container types based on their value and index types."""
        value_type, index_type = typename
        if isinstance(index_type, List):
            index_contains_default = "Any" in index_type
            if not index_contains_default:
                if any(t is None for t in index_type):
                    raise TypeNotSupported(typename)
                index_type = ", ".join(index_type)
        else:
            index_contains_default = index_type == "Any"
        # Avoid types like HashMap<_, foo>. Prefer default_type instead
        if index_contains_default or value_type == cls._default_type:
            return cls._default_type
        return cls._combine_value_index(value_type, index_type)


    @classmethod
    def _typename_from_type_node(
            cls,
            node: ast.AST,
    ) -> Union[List[str], str, None]:

        match node:

            case ast.Name():  # Simple name
                return cls._map_type(
                    get_id(node),
                    getattr(node, "lifetime", LifeTime.UNKNOWN),
                )

            # --------------------------
            # Literal type reference
            # Only string-like values are valid type names
            # --------------------------
            case ast.Constant(value=val):
                if val is None:
                    return None

                if isinstance(val, bytes):
                    return val.decode("utf-8")

                if isinstance(val, (str, int, float, bool)):
                    return str(val)

                # complex, Ellipsis, unsupported → ignore
                return None

            case ast.ClassDef(): # Class definition reference
                return get_id(node)

            case ast.Tuple(elts=elements): # Tuple type: (A, B) # Must produce List[str]
                result: List[str] = []
                for e in elements:
                    t = cls._typename_from_type_node(e)
                    if isinstance(t, str):
                        result.append(t)
                    # ignore None and nested lists (invalid for tuple element)
                return result if result else None

            case ast.Attribute():  # Qualified attribute: typing.List
                node_id = get_id(node)
                if not node_id:
                    return None

                if node_id.startswith("typing."):
                    return node_id.split(".", 1)[1]

                return node_id

            case ast.Subscript():  #  List[int], Dict[str, int]
                slice_value = cls._slice_value(node)

                value_type = cls._typename_from_type_node(node.value)
                index_type = cls._typename_from_type_node(slice_value)

                # Container must be simple string
                if not isinstance(value_type, str):
                    return None

                value_type = cls._map_container_type(value_type)

                node.container_type = (value_type, index_type) # FIXME: UGLY_AST_MODDING

                return cls._combine_value_index(value_type, index_type)

            case _: # Fallback
                return cls._default_type

    @classmethod
    def _generic_typename_from_type_node(
            cls,
            node: ast.AST
    ) -> Union[List, str, None]:
        """
        Extract a generic type name from a type annotation node in
        the AST without doing any target-specific mapping.
        """

        match node:

            case ast.Name():  # Simple type name
                return get_id(node)

            case ast.Constant(value=val):  # Literal type reference
                return val  # Can be str, int, float, bool, etc.

            case ast.ClassDef():  # Class definition
                return get_id(node)

            case ast.Tuple(elts=elements):  # Tuple type (A, B)
                result: List = []
                for e in elements:
                    t = cls._generic_typename_from_type_node(e)
                    if t is not None:
                        result.append(t)
                return result if result else None

            case ast.Attribute():  # Qualified attribute: typing.List
                node_id = get_id(node)
                if node_id is not None and node_id.startswith("typing."):
                    return node_id.split(".", 1)[1]
                return node_id

            case ast.Subscript():  # List[int], Dict[str, int]
                slice_value = cls._slice_value(node)

                value_type = cls._generic_typename_from_type_node(node.value)
                index_type = cls._generic_typename_from_type_node(slice_value)

                # Attach container info (generic)
                node.generic_container_type = (value_type, index_type)

                return f"{value_type}[{index_type}]"

            case _:  # Fallback
                return cls._default_type

    @classmethod
    def _typename_from_annotation(cls, node, attr="annotation") -> str:
        default_type = cls._default_type
        typename = default_type
        if hasattr(node, attr):
            type_node = getattr(node, attr)
            typename = cls._typename_from_type_node(type_node)
            if isinstance(type_node, ast.Subscript):
                node.container_type = type_node.container_type
                try:
                    return cls._visit_container_type(type_node.container_type)
                except TypeNotSupported as e:
                    raise AstTypeNotSupported(str(e), node)
            if typename is None:
                raise AstCouldNotInfer(type_node, node)
        return typename


    @classmethod
    def _generic_typename_from_annotation(
            cls, node, attr="annotation"
    ) -> Optional[str]:
        """
        Unlike the one above, this doesn't do any target specific mapping.
        """
        typename = None
        if hasattr(node, attr):
            type_node = getattr(node, attr)
            ret = cls._generic_typename_from_type_node(type_node)
            if isinstance(type_node, ast.Subscript):
                node.generic_container_type = type_node.generic_container_type
            return ret
        return typename


    def visit(self, node: ast.AST) -> str:
        """
        Visit an AST node and return its target-language representation.

        Raises:
            AstEmptyNodeFound
            AstNotImplementedError
        """
        if node is None:
            raise AstEmptyNodeFound

        if type(node) in symbols:
            return c_symbol(node)

        try:
            return super().visit(node)
        except AstNotImplementedError:
            raise
        except Exception as exc:
            raise AstNotImplementedError(
                msg=str(exc),
                node=node
            ) from exc


    def visit_Pass(self, node) -> str:
        """Visit a pass statement node, which represents a no-op in the code."""
        return self.comment("pass")


    def visit_Module(self, node) -> str:
        """Visit a module node and emit the top-level translation unit.

        The module is emitted in two conceptual stages:
        1. Top-level declarations (imports, classes, constants, etc.)
        2. Callable definitions (functions, async functions)

        This ordering ensures that declarations appear before functions
        in generated C-like targets.
        """

        buf = []

        # Phase 1: declarations
        for stmt in node.body:
            if not is_callable_definition(stmt):
                result = self.visit(stmt)
                if result:
                    buf.append(result)

        # Phase 2: callable definitions
        for stmt in node.body:
            if is_callable_definition(stmt):
                result = self.visit(stmt)
                if result:
                    buf.append(result)

        return "\n".join(buf)


    def visit_alias(self, node: ast.alias) -> Tuple[str, Optional[str]]:
        """
        Visit an import alias node.

        Args:
            node (ast.alias): The alias node representing a module import,
                e.g., `import numpy as np`.

        Returns:
            Tuple[str, Optional[str]]: A tuple of the original module name
                and the alias (or None if no alias is used).
        """
        return node.name, node.asname




    def _import_from(
            self, module_name: str, names: List[str], level: int = 0
    ): ...
    """
    Placeholder for handling 'from ... import ...' statements.

    Args:
        module_name (str): The module being imported from.
        names (List[str]): The list of names being imported.
        level (int, optional): Relative import level (0 for absolute). Defaults to 0.

    Returns:
        str: A string representing the import statements needed for the target language.
    """


    def visit_Import(self, node: ast.Import) -> str:
        """
        Visit an import statement node, e.g., `import numpy as np`.

        Args:
            node (ast.Import): The import statement AST node.

        Returns:
            str: A string containing import statements in the target language.
        """
        def process(a):
            """Process an import alias node."""
            if a.name in self._ignored_module_set: return ""
            if a.asname:
                try: v = importlib.import_module(a.name)
                except ImportError: v = a.name
                self._imported_names[a.asname] = v
            return self._import(a.name)

        return "\n".join(filter(None, (process(a) for a in node.names)))


    def visit_ImportFrom(self, node: ast.ImportFrom): # not only str?
        """
        Visit a from-import statement node, e.g., `from math import sqrt`.

        Args:
            node (ast.ImportFrom): The from-import AST node.

        Returns:
            str: A string containing import statements in the target language.
        """
        if node.module in self._ignored_module_set:
            return ""

        imported_name = node.module
        imported_module = None
        if node.module:
            try:
                imported_module = importlib.import_module(node.module)
            except ImportError:
                pass
        else:
            imported_name = "."

        names = [self.visit(n) for n in node.names] # names would be list[] of ... or set but most likely list of tuples (name, asname)
        for name, asname in names:
            asname = asname if asname is not None else name
            if imported_module:
                self._imported_names[asname] = getattr(imported_module, name, None)
            else:
                self._imported_names[asname] = (imported_name, name)
        names_list = [n for n, _ in names]
        return self._import_from(imported_name, names_list, node.level)


    def visit_Name(self, node: ast.Name) -> str:
        """
        Visit a name node representing an identifier.

        Args:
            node (ast.Name): The AST name node.

        Returns:
            str: The identifier, possibly converted for the target language.
        """
        if node.id in self.builtin_constants:
            return node.id.lower()
        return node.id

    def visit_Constant(self, node: ast.Constant) -> str:
        value = node.value

        match value:

            case bool():
                return self.render_bool(value)

            case None:
                return self.render_none()

            case int():
                return self.render_int(value)

            case float():
                return self.render_float(value)

            case complex():
                return self.render_complex(value)

            case str():
                return self.render_string(value)

            case bytes():
                return self.render_bytes(value)

            case type(Ellipsis):
                return self.render_ellipsis()

            case _:
                raise AstNotImplementedError(
                    msg=f"Unsupported constant type: {type(value).__name__}",
                    node=node
                ) # msg, node <-- correct parameters


    # MARK: - Render hooks - to be overridden in target

    @staticmethod
    def render_bool(value: bool) -> str: return "true" if value else "false"

    @staticmethod
    def render_none() -> str: return "nullptr"

    @staticmethod
    def render_int(value: int) -> str:
        if value > 2147483647:
            return f"{value}LL"
        return str(value)

    @staticmethod
    def render_float(value: float) -> str:
        s = str(value)
        return s if "." in s or "e" in s.lower() else f"{s}.0"

    @staticmethod
    def render_complex(value: complex) -> str:
        return f"std::complex<double>({value.real}, {value.imag})"

    def render_string(self, value: str) -> str:
        return self._escape_string(value)

    def render_bytes(self, value: bytes) -> str:
        return self._escape_bytes(value)

    def render_ellipsis(self) -> str:
        return self.comment("...")



    @staticmethod
    def _escape_bytes(node) -> str:
        """Renders bytes as a C-style escaped hex string.

        Args:
            node (ast.Node): ast node for raw byte sequence.

        Returns:
            str: A C-style string literal (e.g., '"\\x41\\x42"').
        """
        # Uses a generator to hex-escape every single byte

        bytes_str = node.value

        body = "".join(f"\\x{b:02x}" for b in bytes_str)
        return f'"{body}"'



    @staticmethod
    def _escape_string(node) -> str:
        """
        Visit a string literal node.

        Args:
            node (ast.Str): The AST string node.

        Returns:
            str: Properly escaped string for the target language.
        """
        node_str = node.value
        node_str = node_str.replace('"', '\\"')
        node_str = node_str.replace("\n", "\\n")
        node_str = node_str.replace("\r", "\\r")
        node_str = node_str.replace("\t", "\\t")
        return f'"{node_str}"'



    def visit_Expr(self, node: ast.Expr) -> str:
        """
        Visit an expression node representing a standalone expression.

        Args:
            node (ast.Expr): The AST expression node.

        Returns:
            str: The expression as a string in the target language.
        """
        s = self.visit(node.value)
        if isinstance(node.value, ast.Constant) and node.value.value is Ellipsis:
            return s
        if not s:
            return ""
        s = s.strip()
        if not s.endswith(self._statement_separator):
            s += self._statement_separator
        return "" if s == self._statement_separator else s




    def visit_arguments(self, node) -> Tuple[List[str], List[str]]:
        """
        Visit function argument nodes.

        Args:
            node (ast.arguments): The AST arguments node.

        Returns:
            Tuple[List[str], List[str]]: Two lists:
                - List of type names for each argument (or default type).
                - List of argument names for the function signature.
        """
        args = [self.visit(arg) for arg in node.args]
        if not args:
            return [], []
        typenames, args = map(list, zip(*args))
        return typenames, args

    def visit_Return(self, node) -> str:
        """
        Visit a return statement node, which represents a return statement in a function.
        """
        if node.value:
            return f"return {self.visit(node.value)};"
        return "return;"

    def _make_block(self, node):
        """
        Create a block of code from the body of
        an if statement that is being used as a block.

        This is used to handle the idiom where
        an if statement with a test condition of
        True and no else clause is used to create a block of statements.
        """
        buf = ["({"]
        buf.extend([self.visit(child) for child in node.body])
        buf.append("})")
        return "\n".join(buf)

    @staticmethod
    def is_block(node):
        """
        if True: s1; s2  should be transpiled into ({s1; s2;})
        such that the value of the expression is s2

        This idiom is used by rewriters to transform a single
        ast Node s0 into multiple statements s1, s2
        """
        return (
                isinstance(node.test, ast.Constant)
                and node.test.value == True
                and node.orelse == [] # no else clause which would break the block semantics
                and hasattr(node, "rewritten") # rewriter sets this attribute to indicate the node has been transformed into a block
                and node.rewritten
        )

    def visit_If(self, node, use_parens=True) -> str:
        """
        Translates an `if` statement into target C-like source code.

        Handles standard conditionals and the 'if True:' block idiom. If the
        node represents a block-only idiom (no `else`, test is `True`), it
        unwraps the body directly.

        Args:
            node: The AST `if` statement node to visit.
            use_parens: Whether to wrap the condition in parentheses (e.g., for C/Java).

        Returns:
            The formatted code string for the conditional block.
        """
        buf = []
        make_block = self.is_block(node)
        if make_block:
            return self._make_block(node)
        else:
            if use_parens:
                buf.append(f"if({self.visit(node.test)}) {{")
            else:
                buf.append(f"if {self.visit(node.test)} {{")
        body = [self.visit(child) for child in node.body]
        body = [b for b in body if b is not None]
        buf.extend(body)

        orelse = [self.visit(child) for child in node.orelse]
        if orelse:
            buf.append("} else {")
            buf.extend(orelse)
            buf.append("}")
        else:
            buf.append("}")
        return "\n".join(buf)

    def visit_Continue(self, node) -> str:
        """Translate an ``ast.Continue`` node.

        Args:
            node (ast.Continue):
                The ``continue`` statement node.

        Returns:
            str:
                The target-language representation of the statement.
        """
        return "continue;"

    def visit_Break(self, node) -> str:
        """Translate an ``ast.Break`` node.

        Args:
            node (ast.Break):
                The ``break`` statement node.

        Returns:
            str:
                The target-language representation of the statement.
        """
        return "break;"

    def visit_While(self, node, use_parens=True) -> str:
        """Translate an ``ast.While`` node into a C-style loop.

        Generates a ``while`` loop with the translated condition and body.

        Args:
            node (ast.While):
                The ``while`` loop AST node.
            use_parens (bool):
                Whether to wrap the condition expression in parentheses.

        Returns:
            str:
                A string representing the translated loop, including the loop
                body enclosed in braces.

        Notes:
            Each statement in the loop body is visited recursively using
            ``self.visit``.
        """
        buf = []
        if use_parens:
            buf.append(f"while ({self.visit(node.test)}) {{")
        else:
            buf.append(f"while {self.visit(node.test)} {{")
        buf.extend([self.visit(n) for n in node.body])
        buf.append("}")
        return "\n".join(buf)


    def visit_Compare(self, node) -> str:
        """Translate an ``ast.Compare`` node into a comparison expression.

        Supports simple binary comparisons (e.g., ``a < b``). If the comparison
        operator is ``in``, translation is delegated to ``visit_In``.

        Args:
            node (ast.Compare):
                The comparison expression node.

        Returns:
            str:
                A string representing the translated comparison expression.

        Notes:
            Only the first comparison operator and comparator are currently
            emitted. Python chained comparisons (e.g., ``a < b < c``) are not
            fully expanded.
        """
        if isinstance(node.ops[0], ast.In):
            return self.visit_In(node)

        left = self.visit(node.left)
        op = self.visit(node.ops[0])
        right = self.visit(node.comparators[0])

        return f"{left} {op} {right}"


    def visit_BoolOp(self, node) -> str:
        """Translate an ``ast.BoolOp`` node into a logical expression.

        Handles logical operations such as ``and`` and ``or`` by joining the
        translated operands using the target-language operator.

        Args:
            node (ast.BoolOp):
                The boolean operation node.

        Returns:
            str:
                A string representing the logical expression.

        Notes:
            All operand expressions are recursively translated using
            ``self.visit`` and joined using the operator returned by
            ``visit(node.op)``.
        """
        op = self.visit(node.op)
        return op.join([self.visit(v) for v in node.values])

    def visit_UnaryOp(self, node) -> str:
        """Translate an ``ast.UnaryOp`` node into a unary expression.

        Handles unary operations such as logical negation (``not``) or
        arithmetic negation (``-x``).

        Args:
            node (ast.UnaryOp):
                The unary operation node.

        Returns:
            str:
                A string representing the translated unary expression in the
                form ``operator(operand)``.
        """
        return f"{self.visit(node.op)}({self.visit(node.operand)})"

    def _visit_AssignOne(self, node, target): ...
    """
    Handle the translation of a single assignment target in an assignment statement.
    This method is called for each target in an assignment statement,
    allowing for support of multiple assignment targets like "a = b = c"
    """

    def visit_Assign(self, node) -> str:
        """
        Visit an assignment statement node, which represents an assignment
        operation in the code, such as "a = 5" or "x, y = 1, 2".
        """

        return "\n".join(
            [self._visit_AssignOne(node, target) for target in node.targets]
        )

    def visit_AugAssign(self, node) -> str:
        """
        Visit an augmented assignment statement node,
        which represents an operation like "a += 1" or "x *= 2".

        This method handles the translation
        of augmented assignment operations,
        including the target of the assignment,
        the operator, and the value being assigned.
        """
        target = self.visit(node.target)
        op = self.visit(node.op)
        val = self.visit(node.value)
        return f"{target} {op}= {val};"

    def visit_AnnAssign(self, node) -> Tuple[str, str, Optional[str]]:
        """
        Visit an annotated assignment statement node,
        which represents an assignment with
        a type annotation, such as "x: int = 5".

        This method handles the translation of annotated assignment statements,
        including the target of the assignment, the type annotation, and the value being assigned.
        It also includes special handling for cases where the type annotation is a Callable,
        which may require a default type to be used in the target language.
        """
        target = self.visit(node.target)
        if (
                hasattr(node.target, "annotation")
                and isinstance(node.target.annotation, ast.Subscript)
                and get_id(node.target.annotation.value) == "Callable"
        ):
            type_str = self._default_type
        else:
            type_str = self._typename_from_annotation(node)
        val = self.visit(node.value) if node.value is not None else None
        return target, type_str, val

    def set_continue_on_unimplemented(self):
        """
        Set the flag to throw an error when
        an unimplemented feature is encountered.
        """
        self._throw_on_unimplemented = False


    # MARK : - Misc. unsupported



    def generic_visit(self, node: ast.AST | None) -> str:
        """
        Safe visitor wrapper.

        Guarantees that every AST node is traversed even if:
            - a specific visitor is missing
            - a visitor raises an exception
            - a backend does not support the node

        This prevents the historical py2many issue where
        ~15% of AST shapes silently skipped traversal.

        Returns
        -------
        str
            Rendered representation of the node, or an empty string
            if rendering failed but traversal succeeded.
        """
        if node is None:
            return ""

        method = getattr(self, f"visit_{node.__class__.__name__}", None)

        try:
            if method:
                return method(node)
        except Exception:
            # Continue traversal even if rendering fails
            pass

        # Fallback traversal: visit child nodes
        for child in ast.iter_child_nodes(node):
            self.visit(child)

        return ""


    def visit_unsupported(self, node, name) -> str:
        """
        Handle the translation of an unsupported feature in the code.
        """
        if self._throw_on_unimplemented:
            raise AstNotImplementedError(f"{name} not implemented", node)
        else:
            return self.comment(
                f"{name} unimplemented on line {node.lineno}:{node.col_offset}"
            )


    def visit_unsupported_body(self, node: ast.AST, name: str, body) -> str:
        """Emit a commented representation of an unsupported construct.

        Even though the construct cannot be translated, all nested nodes are
        still visited to ensure that dependency discovery, symbol tracking,
        and imports/usings are still correctly identified.

        Args:
            node (ast.AST): The unsupported AST node.
            name (str): Human-readable name of the construct.
            body (Union[ast.AST, list[ast.AST], None]): Body of the construct
            to be traversed.

        Returns:
            str: A comment block describing the unsupported construct.
        """
        lines = [f"unsupported construct: {name}"]

        for stmt in iter_body(body):
            try:
                rendered = self.visit(stmt)
            except Exception:
                rendered = "<untranslatable>"

            if rendered:
                lines.append(rendered)

        lines.append("end unsupported")

        return self.comment_block(lines)


    def visit_NamedExpr(self, node) -> str:
        """
        Assignment expressions are not lowered for C-like targets.
        """
        target = self.visit(node.target)
        return self.visit_unsupported_body(node, f"named expr {target}", node.value)

    def visit_Delete(self, node) -> str:
        """
        Python's 'del' statement has no direct equivalent.
        """
        return self.visit_unsupported_body(node, "del", node.targets)

    def visit_Starred(self, node) -> str:
        """
        Visit a starred expression node,
        which represents the use of the * operator
        in function calls or assignments.
        """
        return self.visit_unsupported_body(node, "starred", node.value)

    def visit_Await(self, node) -> str:
        """
        Await expressions require coroutine support which is not implemented.
        """
        return self.visit_unsupported_body(node, "await", node.value)

    def visit_AsyncFor(self, node) -> str:
        """Async iteration is not supported."""
        target = self.visit(node.target)
        iterator = self.visit(node.iter)

        return self.visit_unsupported_body(
            node, f"async for {target} in {iterator}", node.body
        )

    def visit_AsyncWith(self, node) -> str:
        """Async context managers are not supported."""
        items = [self.visit(i) for i in node.items]
        return self.visit_unsupported_body(node, f"async with {items}", node.body)

    def visit_YieldFrom(self, node) -> str:
        """Generator delegation is not supported."""
        return self.visit_unsupported_body(node, "yield from", node.value)

    def visit_AsyncFunctionDef(self, node) -> str:
        """
        Visit an asynchronous function definition node.

        Async functions are lowered to normal functions for C-like targets
        since the transpiler does not implement coroutine semantics.
        """
        # FIX: treat async functions the same as normal functions
        # instead of marking them unsupported.
        return self.visit_FunctionDef(node)

    def visit_Nonlocal(self, node) -> str:
        """
        Visit a nonlocal statement node, which represents
        the use of the nonlocal keyword for declaring that
        a variable is not local to the current function but is also not global.
        """
        return self.visit_unsupported_body(node, "nonlocal", node.names)

    def visit_DictComp(self, node) -> str:
        """Visit a dictionary comprehension node, which represents the use of dictionary comprehensions in Python, such as "{k: v for k, v in iterable}". This method handles the translation of dictionary comprehensions, including the key and value expressions and the generators that define the iteration. It delegates to the visit_unsupported_body method to handle the translation of the dictionary comprehension, allowing for a consistent way to represent these constructs in the target language, even if they do not have a direct equivalent."""
        key = self.visit(node.key)
        value = self.visit(node.value)
        return self.visit_unsupported_body(
            node, f"dict comprehension ({key}, {value})", node.generators
        )


    # MARK: - Generators, comprehensions

    def visit_GeneratorExp(self, node) -> str:
        """Generator expressions like ``(x for x in iterable)``."""
        body = [node.elt] + node.generators
        return self.visit_unsupported_body(node, "generator expression", body)

    def visit_ListComp(self, node) -> str:
        """List comprehension such as ``[x for x in iterable]``."""
        return self.visit_GeneratorExp(node)  # by default, they are the same

    def visit_SetComp(self, node) -> str:
        """Set comprehension node, such as "{x for x in iterable}"."""
        return self.visit_GeneratorExp(node)  # by default, they are the same


    # MARK: - Class definition handling

    def visit_ClassDef(self, node):
        """
        Visit a class definition node.
        This method handles the translation of class definitions
        """
        bases = [get_id(base) for base in node.bases]
        if set(bases) == {"Enum", "str"}:
            return self.visit_StrEnum(node)
        if len(bases) != 1:
            return None
        if not bases[0] in {"Enum", "IntEnum", "IntFlag"}:
            return None
        if bases == ["IntEnum"] or bases == ["Enum"]:
            return self.visit_IntEnum(node)
        if bases == ["IntFlag"]:
            return self.visit_IntFlag(node)
        return None

    def visit_StrEnum(self, node): ...

    def visit_IntEnum(self, node): ...

    def visit_IntFlag(self, node): ...

    def visit_IfExp(self, node) -> str:
        """
        Visit a conditional expression node,
        which represents a ternary conditional expression in the code,
        such as "x if condition else y".
        """
        body = self.visit(node.body)
        orelse = self.visit(node.orelse)
        test = self.visit(node.test)
        return f"({test}? ({{ {body}; }}) : ({{ {orelse}; }}))"

    def visit_ExceptHandler(self, node) -> str:
        """
        Visit an except handler node, which
        represents an except clause in a try-except block.
        """
        return self.visit_unsupported_body(node, "except handler", node.body)


    def visit_Try(self, node, finallybody=None) -> str:
        """
        Exception handling is not implemented for C-like targets.
        """
        lines = [self.visit_unsupported_body(node, "try", node.body)]
        for each_handler in node.handlers:
            lines.append(self.visit(each_handler))
        if finallybody:
            lines.append(self.visit_unsupported_body(node, "finally", finallybody))
        return "\n".join(lines)

    def visit_Raise(self, node) -> str:
        """
        Translate a raise statement.

        Most C-like targets do not implement Python exception semantics.
        The construct is therefore emitted as an unsupported block while
        still visiting the exception expression.
        """

        if node.exc is not None:
            return self.visit_unsupported_body(node, "raise", node.exc)

        return self.visit_unsupported(node, "raise")


    # MARK: - _* methods

    def _func_for_lookup(self, fname: str) -> Optional[Any]:
        """
        Resolve a function name into an actual object using imported names.

        Returns:
            Resolved callable object if hashable.
            None if resolution fails.
        """
        func = class_for_typename(fname, None, self._imported_names)
        if func is None:
            return None

        try:
            hash(func)
        except TypeError:
            logger.debug("%s is not hashable", func)
            return None

        return func

    @staticmethod
    def _func_name_split(fname: str) -> Tuple[str, str]:
        """
        Split a dotted function name into (stem, leaf).

        Example:
            "math.sqrt" -> ("math.", "sqrt")
            "print" -> ("", "print")
        """
        parts = fname.rsplit(".", maxsplit=1)
        if len(parts) == 2:
            return parts[0] + ".", parts[1]
        return "", parts[0]


    def _dispatch(
            self,
            node: ast.Call,
            fname: str,
            vargs: list[str],
    ) -> str | None:
        """
        Dispatch a function call to a registered handler.

        Dispatch order:
            1. Exact name
            2. Small dispatch map
            3. Object-based dispatch
            4. Leaf fallback

        Args:
            node (ast.Call): The function call AST node being processed.
            fname (str): The name of the function to dispatch.
            vargs (list[str]): List of already-rendered string arguments.

        Returns:
            str | None: The translated function call string if a handler was
                matched; otherwise, None.
        """

        def safe_call(handler, use_self=True):
            try:
                if use_self:
                    return handler(self, node, vargs)
                return handler(node, vargs)
            except IndexError:
                return None

        # 1. direct dispatch
        handler = self._dispatch_map.get(fname)
        if handler:
            return safe_call(handler)

        # 2. small dispatch
        handler = self._small_dispatch_map.get(fname)
        if handler:
            using = self._small_usings_map.get(fname)
            if using:
                self._usings.add(using)
            return safe_call(handler, use_self=False)

        # 3. object dispatch
        func = self._func_for_lookup(fname)
        if func is not None:
            entry = self._func_dispatch_table.get(func)
            if entry:
                handler, result_type = entry

                if func in self._func_usings_map:
                    self._usings.add(self._func_usings_map[func])

                node.result_type = result_type
                return safe_call(handler)

        # 4. leaf fallback
        stem, leaf = self._func_name_split(fname)

        entry = self._func_dispatch_table.get(leaf)
        if entry:
            handler, result_type = entry
            node.result_type = result_type

            result = safe_call(handler)
            return f"{stem}{result}" if result is not None else None

        return None


