import ast

from py2many.analysis import get_id
from py2many.inference import get_inferred_type


class StrStrRewriter(ast.NodeTransformer):
    """
    Rewrites 'a' in 'b' to a.contains(b) for languages that support it,
    since it's more efficient and idiomatic than using find or index methods.

    Only rewrites if:
        the left operand is a string literal
              and
        the right operand is a string literal,

    ... since in those cases it's usually more efficient and idiomatic
    to use the contains method.
    In other cases, it's better to keep the original code,
    since it may be more efficient or more readable depending on the context.

    By only rewriting when both operands are string literals, we can
    keep the output code cleaner and more readable, while still making it
    compatible with languages that support the contains method.
    """
    def __init__(self, language):
        super().__init__()
        self._language = language

    def visit_Compare(self, node):
        if self._language in {"d", "dart", "kotlin", "nim", "python"}:
            return node

        if isinstance(node.ops[0], ast.In):
            left = node.left
            right = node.comparators[0]
            left_type = get_id(get_inferred_type(left))
            right_type = get_id(get_inferred_type(right))
            if left_type == "str" and right_type == "str":
                if self._language == "julia":
                    ret = ast.parse("findfirst(a, b) != Nothing").body[0].value
                    ret.left.args[0] = left
                    ret.left.args[1] = right
                elif self._language == "go":
                    # To be rewritten to strings.Contains via plugins
                    ret = ast.parse("StringsContains(a, b)").body[0].value
                    ret.args[0] = right
                    ret.args[1] = left
                elif self._language == "cpp":
                    ret = ast.parse("a.find(b) != string.npos").body[0].value
                    ret.left.func.value = right
                    ret.left.args[0] = left
                else:
                    # rust and c++23
                    ret = ast.parse("a.contains(b)").body[0].value
                    ret.func.value = right
                    ret.args[0] = left
                ret.lineno = node.lineno
                ast.fix_missing_locations(ret)
                return ret

        return node


