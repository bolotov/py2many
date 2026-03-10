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

from py2many.analysis import IGNORED_MODULE_SET, get_id
from py2many.astx import LifeTime
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
        typename: Optional[str],
        default_type: Any,
        localns: Optional[Mapping[str, Any]] = None,
) -> Any:
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
        self._aliases = {} # PROBABLY:  Dict[str, str]
        self._imported_names = {} # PROBABLY:  Dict[str, Any]
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

    def headers(self, meta=None) -> str:
        """Return the necessary headers for the target language as a string."""
        return ""

    def usings(self) -> str:
        """Return the necessary using/import statements for the target language as a string."""
        return ""

    @staticmethod
    def aliases() -> str:
        """Return any type aliases needed for the target language as a string."""
        return ""

    @staticmethod
    def features() -> str:
        """Return any language features needed for the target language as a string."""
        return ""


    @property
    def extension(self):
        """Whether the transpiler is being used in extension mode,
        where it is expected to produce code snippets
        to be embedded in handwritten code, rather than a complete program.
        This can be used to conditionally include or exclude certain code
        constructs or prologue/epilogue code.
        """
        return self._extension

    @staticmethod
    def extension_module() -> str:
        """Return the module name to use for an extension build, if applicable."""
        return ""

    @staticmethod
    def comment(text) -> str:
        """Return a comment string for the target language."""
        return f"/* {text} */"

    @staticmethod
    def comment_block(lines: list[str]) -> str:
        """Emit a block comment."""
        body = "\n".join(lines)
        return f"/*\n{body}\n*/"


    @staticmethod
    def _cast(name: str, to) -> str:
        """Return a string representing a cast of name to the type represented by to in the target language."""
        return f"({to}) {name}"


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
                                    or an extended multi-dimensional slice.
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
        """
        Map a list of annotation strings to target-language types.
        """
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
        The exact format of the combined type string can be customized based on the conventions of the target language.
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
                # ."Subscript" has no attribute "container_type"

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
            raise AstNotImplementedError(str(exc), node) from exc


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

        def is_callable_definition(n: ast.AST) -> bool:
            """
            Identify nodes that represent top-level callable definitions.

            FIX:
            The previous implementation explicitly checked only
            `ast.FunctionDef`. This caused `ast.AsyncFunctionDef`
            (and any future callable node types) to be processed in the
            wrong phase.

            The classification is now centralized in this predicate,
            eliminating duplicated type checks and preventing omissions.
            """
            return isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))

        # ---------------------------------------------------------
        # Phase 1: declarations
        # ---------------------------------------------------------

        for stmt in node.body:
            if not is_callable_definition(stmt):
                result = self.visit(stmt)
                if result:
                    buf.append(result)

        # ---------------------------------------------------------
        # Phase 2: callable definitions
        # ---------------------------------------------------------

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


    def _import(self, name: str):
        """
        Placeholder for the method that handles the actual
        import logic for a module name.

        Args:
            name (str): The name of the module to import.

        Returns:
            str: A string representing the import statement
            for the target language.
        """
        raise NotImplementedError # WAS: ...


    def _import_from(
            self, module_name: str, names: List[str], level: int = 0
    ):
        """
        Placeholder for handling 'from ... import ...' statements.

        Args:
            module_name (str): The module being imported from.
            names (List[str]): The list of names being imported.
            level (int, optional): Relative import level (0 for absolute). Defaults to 0.

        Returns:
            str: A string representing the import statements needed for the target language.
        """
        ...
        #raise NotImplementedError # WAS: ...


    def visit_Import(self, node: ast.Import):
        """
        Visit an import statement node, e.g., `import numpy as np`.

        Args:
            node (ast.Import): The import statement AST node.

        Returns:
            str: A string containing import statements in the target language.
        """
        names = [self.visit(n) for n in node.names]
        imports = [
            self._import(name)
            for name, alias in names
            if name not in self._ignored_module_set
        ]
        for name, asname in names:
            if asname is not None:
                try:
                    imported_name = importlib.import_module(name)
                except ImportError:
                    imported_name = name
                self._imported_names[asname] = imported_name
        return "\n".join(imports)


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

        names = [self.visit(n) for n in node.names] # names would be list[] of .. or set but most likely list of tuples (name, asname)
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


    # def visit_Ellipsis(self, node) -> str: # TODO: Fix to ast.Constant properly. FIXME
    #     """
    #     Visit an ellipsis node ('...').
    #
    #     Args:
    #         node (ast.Ellipsis): The ellipsis AST node.
    #
    #     Returns:
    #         str: A comment indicating unsupported ellipsis in the target language.
    #     """
    #     return self.comment("...")


    def visit_NameConstant(self, node):
        """
        Visit a constant node representing True, False, or None.

        Args:
            node (ast.NameConstant): The AST node representing a constant.

        Returns:
            str: The equivalent constant in the target language.
        """
        if node.value is True:
            return "true"
        elif node.value is False:
            return "false"
        elif node.value is None:
            return "NULL"
        elif node.value is Ellipsis:
            return self.comment("...")  #  ast.Ellipsis is gone:
            # return self.visit_Ellipsis(node) # WARNING: Expected type 'Ellipsis', got 'NameConstant' instead
        else:
            return str(node.value)

    def visit_Constant(self, node: ast.Constant) -> str:
        """
        Visit a constant node (string, number, boolean).

        Args:
            node (ast.Constant): The AST constant node.

        Returns:
            str: The string representation in the target language.
        """
        if isinstance(node.value, str):
            return self.visit_Str(node)  # WARNING: Expected type 'Str', got 'Constant' instead
        elif isinstance(node.value, bytes):
            return self.visit_Bytes(node)  # WARNING: Expected type 'Bytes', got 'Constant' instead
        return str(self.visit_NameConstant(node)) # WARNING: Expected type 'NameConstant', got 'Constant' instead

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

    def visit_Str(self, node) -> str:
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

    def visit_Bytes(self, node) -> str:
        """
        Visit a bytes literal node.

        Args:
            node (ast.Bytes): The AST bytes node.

        Returns:
            str: A string representation of bytes for the target language.
        """
        #bytes_str = node.s
        bytes_str = node.value
        byte_array = ", ".join([hex(c) for c in bytes_str])
        return f"{{{byte_array}}}"

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
                and node.orelse == []
                and hasattr(node, "rewritten")
                and node.rewritten
        )

    #def visit_If(self, node: ast.If, use_parens: bool = True) -> str:
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
        """Visit a continue statement node,
        which represents a continue statement in a loop.
        """
        return "continue;"

    def visit_Break(self, node) -> str:
        """
        Visit a break statement node, which represents a break statement in a loop."""
        return "break;"

    def visit_While(self, node, use_parens=True) -> str:
        """
        Visit a while loop node, which represents a while loop in the code.
        This method handles the translation of while loops,
        including their test conditions and body.
         It also includes special handling for the same block-creating idiom used in visit_If,
        where a while loop with a test condition of True and no else clause is used to create a block of statements.
        In this case, the method will generate a block of code without the while condition, allowing the statements to be executed sequentially.
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
        """
        Visit a comparison node, which represents a comparison
        operation in the code, such as "a < b" or "x == y".
         This method handles the translation of comparison operations,
        including support for chained comparisons like "a < b < c".
         It also includes special handling for the "in" operator,
         which is represented as a comparison in the AST but may
         require different handling in the target language.
         """
        if isinstance(node.ops[0], ast.In):
            return self.visit_In(node)

        left = self.visit(node.left)
        op = self.visit(node.ops[0])
        right = self.visit(node.comparators[0])

        return f"{left} {op} {right}"

    def visit_BoolOp(self, node) -> str:
        """Visit a boolean operation node, which represents a logical
        operation in the code, such as "and" or "or".
        This method handles the translation of boolean operations,
        including support for chaining multiple operations together,
        such as "a and b and c"."""
        op = self.visit(node.op)
        return op.join([self.visit(v) for v in node.values])

    def visit_UnaryOp(self, node) -> str:
        """
        Visit a unary operation node, which represents
        a unary operation in the code, such as "not" or "-x".
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


    def visit_unsupported_body(self, node, name: str, body) -> str:
        """
        Emit a commented representation of a construct that has
        no translation for the current backend.

        The node body is still visited so that nested expressions
        participate in traversal and dependency discovery.
        """
        lines = [f"unsupported construct: {name}"]

        if isinstance(body, list):
            for stmt in body:
                try:
                    rendered = self.visit(stmt)
                except Exception: # WARNING: Too broad exception clause
                    rendered = "<untranslatable>"
                if rendered:
                    lines.append(rendered)

        elif body is not None:
            try:
                rendered = self.visit(body)
            except Exception:  # WARNING: Too broad exception clause
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
        body = [self.visit(t) for t in node.targets]
        return self.visit_unsupported_body(node, "del", body)

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

    def visit_StrEnum(self, node) -> str:
        raise Exception("Unimplemented")

    def visit_IntEnum(self, node) -> str:
        raise Exception("Unimplemented")

    def visit_IntFlag(self, node) -> str:
        raise Exception("Unimplemented")

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
            vargs: List[str],
    ) -> Optional[str]:
        """
        Dispatch a function call to a registered handler.

        Dispatch order:
            1. Direct string dispatch
            2. Small dispatch map
            3. Object-based dispatch
            4. Leaf-name fallback dispatch

        Returns:
            Translated string if handler found.
            None if no handler matches.
        """
        if fname in self._dispatch_map:
            try:
                return self._dispatch_map[fname](self, node, vargs)
            except IndexError:
                return None

        if fname in self._small_dispatch_map:
            if fname in self._small_usings_map:
                self._usings.add(self._small_usings_map[fname])
            try:
                return self._small_dispatch_map[fname](node, vargs)
            except IndexError:
                return None

        func = self._func_for_lookup(fname)

        if func is not None and func in self._func_dispatch_table:
            if func in self._func_usings_map:
                self._usings.add(self._func_usings_map[func])

            handler_func, result_type = self._func_dispatch_table[func]
            setattr(node, "result_type", result_type)

            try:
                return handler_func(self, node, vargs)
            except IndexError:
                return None

        stem, leaf = self._func_name_split(fname)
        if leaf in self._func_dispatch_table:
            handler_func, result_type = self._func_dispatch_table[leaf]
            setattr(node, "result_type", result_type)

            try:
                return stem + handler_func(self, node, vargs)
            except IndexError:
                return None

        return None

    @property
    def main_signature_arg_names(self):
        return self._main_signature_arg_names

