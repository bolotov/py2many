import ast
from typing import cast, Callable, Any, Set, Optional, Union
from py2many.astx import ASTxIf


def iter_body(body):
    """Yield AST nodes from a body that may be node | list[node] | None."""
    if body is None:
        return ()
    if isinstance(body, list):
        return body
    return (body,)


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
        return f"{base}.{func.attr}" if base else func.attr

    return None


def mark_assigned(target, assign_node, scope):
    """
    Attach assignment metadata to a variable node.
    """
    if isinstance(target, ast.Name):
        target.assigned_from = assign_node

        if not hasattr(scope, "vars"):
            scope.vars = []

        scope.vars.append(target)



def get_id(var: ast.AST) -> str | None: # IMPORTANT: this is USED IN MANY PLACES!!
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


"""
# MAYBE better version
def get_id(var: ast.AST) -> str | None:
    match var:
        # Вузли з атрибутом .name або .id
        case ast.alias(name=n) | ast.FunctionDef(name=n) | ast.ClassDef(name=n):
            return n
        case ast.Name(id=name_id):
            return name_id
        case ast.arg(arg=arg_name):
            return arg_name
            
        # Атрибути (obj.attr) та Індексація (list[int])
        case ast.Attribute(value=val, attr=attr):
            base = get_id(val)
            return f"{base}.{attr}" if base else None
        case ast.Subscript(value=val, slice=slc):
            base = get_id(val)
            index = get_id(slc)
            return f"{base}[{index}]" if base and index else base

        # Union Types (int | str) — це BinOp з оператором BitOr
        case ast.BinOp(left=left, op=ast.BitOr(), right=right):
            l_id, r_id = get_id(left), get_id(right)
            return f"{l_id} | {r_id}" if l_id and r_id else None

        # Кортежі для складних анотацій (dict[str, int])
        case ast.Tuple(elts=elements):
            items = [get_id(e) for e in elements]
            return ", ".join(filter(None, items)) if items else None
            
        # Константи та None
        case ast.Constant(value=val):
            match val:
                case bytes(): return val.decode("utf-8")
                case None: return "None"
                case _: return str(val)
            
        case _:
            return None
"""



# IMPORTANT: get_ann_repr MAYBE implements MORE than  get_id


def get_ann_repr(
        node: Any,
        parse_func: Optional[Callable[[str], str]] = None,
        default: Any = None,
        sep: tuple[str, str] = ("[", "]"),
        _seen: Optional[Set[int]] = None
) -> Union[str, Any]:
    """Returns a string representation of an AST node suitable for type annotations.

    This function recursively processes AST nodes to create human-readable strings.
    It supports modern Python features like Union types (PEP 604), f-strings,
    decorators, and handles potential infinite recursion using an identity set.

    Args:
        node: The AST node or object to represent.
        parse_func: An optional function to post-process the resulting string.
        default: The value to return if the node cannot be represented.
        sep: A tuple of (open, close) characters used for subscript representations.
        _seen: Internal set of node object IDs to prevent infinite recursion.

    Returns:
        str: A representation of the node, or the `default` value.
    """
    if _seen is None:
        _seen = set()

    # Recursion guard using object identity
    node_id = id(node)
    if node_id in _seen:
        return default
    _seen.add(node_id)

    def finalize(result: str | None) -> Union[str, Any]:
        """Applies parse_func and handles None or empty results."""
        if not result:
            return default
        return parse_func(result) if parse_func else result

    # Recursive helper lambda
    repr_node = lambda n, d=default: get_ann_repr(n, parse_func, d, sep, _seen)

    open_s, close_s = sep

    match node:
        case None:
            return default

        case str():
            return finalize(node)

        # 1. Names and Identifiers (The most common case)
        case ast.Name(id=name_id) | ast.alias(name=name_id) | ast.arg(arg=name_id):
            return finalize(name_id)

        # 2. Definitions (Functions/Classes) with Decorators and Type Comments
        case ast.FunctionDef(name=n, decorator_list=decs) | \
             ast.AsyncFunctionDef(name=n, decorator_list=decs) | \
             ast.ClassDef(name=n, decorator_list=decs):

            output = n
            if decs:
                dec_parts = []
                for d in decs:
                    r = repr_node(d, "")
                    if r:
                        dec_parts.append(f"@{r}")
                if dec_parts:
                    output = f"{' '.join(dec_parts)} {output}"

            # Support for PEP 484 type comments
            t_comment = getattr(node, "type_comment", None)
            if t_comment:
                return f"{output} # type: {t_comment}"

            return finalize(output)

        # 3. F-strings (JoinedStr)
        case ast.JoinedStr(values=vals):
            parts = []
            for v in vals:
                r = repr_node(v, "")
                if r is not None:
                    parts.append(str(r))
            return finalize("".join(parts))

        case ast.FormattedValue(value=inner_val):
            return repr_node(inner_val)

        # 4. Call expressions (Formatted as arguments.func_name)
        case ast.Call(func=call_func, args=call_args, keywords=kws):
            fn_name = repr_node(call_func)
            params = []

            for a in call_args:
                prefix = "*" if isinstance(a, ast.Starred) else ""
                params.append(prefix + str(repr_node(a, "")))

            for kw in kws:
                val = repr_node(kw.value)
                if kw.arg:
                    params.append(f"{kw.arg}={val}")
                else:
                    params.append(f"**{val}")

            if params:
                return ".".join(params) + "." + str(fn_name)
            return fn_name

        # 5. Attributes (obj.attr)
        case ast.Attribute(value=attr_val, attr=attr_name):
            base = repr_node(attr_val)
            return f"{base}.{attr_name}" if base else attr_name

        # 6. Subscripts (Generics like List[int])
        case ast.Subscript(value=sub_val, slice=sub_slice):
            container = repr_node(sub_val)
            content = repr_node(sub_slice)
            if container and content:
                return f"{container}{open_s}{content}{close_s}"
            return container or default

        # 7. Union Types (int | str)
        case ast.BinOp(left=left_node, op=ast.BitOr(), right=right_node):
            l_repr = repr_node(left_node)
            r_repr = repr_node(right_node)
            return f"{l_repr} | {r_repr}"

        # 8. Collections (Tuples and Lists)
        case ast.Tuple(elts=elements) | ast.List(elts=elements):
            items = []
            for e in elements:
                r = repr_node(e)
                if r:
                    items.append(r)
            return ", ".join(items)

        # 9. Constants (Literals)
        case ast.Constant(value=const_val):
            match const_val:
                case bytes():
                    try:
                        return finalize(const_val.decode("utf-8"))
                    except UnicodeDecodeError:
                        return finalize(repr(const_val))
                case None:
                    return finalize("None")
                case _:
                    return finalize(str(const_val))

        # 10. Generic Fallback
        case ast.AST():
            try:
                return finalize(ast.unparse(node))
            except (AttributeError, ValueError, TypeError):
                return default

        case _:
            return default



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
