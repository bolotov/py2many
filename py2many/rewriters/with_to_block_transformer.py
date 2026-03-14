import ast

from py2many.ast_helpers import create_ast_block


class WithToBlockTransformer(ast.NodeTransformer):
    """
    Rewrites **with** statements to blocks, since many languages
    don't have a with statement.

    Only rewrites if the with statement has an optional_vars,
    since otherwise it's just a try-finally block that can be easily
    transpiled to C-like languages without rewriting.

    Also adds a hint to UnpackScopeRewriter below to not unpack
    the new scope, since with statements usually introduce
    a new scope that shouldn't be unpacked.

    Does not rewrite if the language is one that does support
    with statements, since in those cases it's better to keep
    them as they are.

    Also does not rewrite if the with statement has no optional_vars,
    since those are usually just try-finally blocks that can be
    easily transpiled to C-like languages without rewriting.

    If we wanted to rewrite all with statements, we would have to
    introduce a new variable for the context manager in the case
    where there are no optional_vars, and then call __enter__ and
    __exit__ manually, which would be a lot more work and would
    make the output code much more verbose and less readable.

    By only rewriting with statements that have optional_vars,
    we can keep the output code cleaner and more readable, while
    still making it compatible with languages that don't support
    **with** statements.
    """

    def __init__(self, language):
        super().__init__()
        self._no_underscore = False
        if language in {"nim"}:
            self._no_underscore = True
        self._temp = 0

    def _get_temp(self):
        self._temp += 1
        if self._no_underscore:
            return f"tmp{self._temp}"
        return f"__tmp{self._temp}"

    def visit_With(self, node):
        self.generic_visit(node)
        stmts = []
        for i in node.items:
            if i.optional_vars:
                target = i.optional_vars
            else:
                target = ast.Name(
                    id=self._get_temp(),
                    lineno=node.lineno
                )
            stmt = ast.Assign(
                targets=[target],
                value=i.context_expr,
                lineno=node.lineno
            )
            stmts.append(stmt)
        node.body = stmts + node.body
        ret = create_ast_block(body=node.body, at_node=node)
        # IMPORTANT: unpack false is a hint to UnpackScopeRewriter to leave the new scope alone
        ret.unpack = False
        return ret


# def capitalize_first(name):
#     first_letter = name[0].upper()
#     remainder = list(name)
#     remainder.remove(name[0])
#     remainder = "".join(remainder)
#     return first_letter + remainder

def capitalize_first(name: str) -> str:
    first_letter = name[0].upper()
    remainder = name[1:]
    return first_letter + remainder


def camel_case(name: str) -> str:
    if (
            "_" not in name
            or
            (name.startswith("__") and name.endswith("__"))
    ):
        return name
    else:
        return "".join(capitalize_first(part) if
                       part else
                       "" for part in name.split("_"))
