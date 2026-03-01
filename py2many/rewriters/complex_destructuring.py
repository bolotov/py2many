import ast

from py2many.ast_helpers import create_ast_block


class ComplexDestructuringRewriter(ast.NodeTransformer):
    """
    Rewrites complex destructuring assignments (e.g. a, (b, c) = foo())
     into simpler ones that are easier to transpile to C-like languages
    """

    def __init__(self, language):
        super().__init__()
        self._disable = False
        if language in {"cpp", "julia", "d", "dart", "v", "mojo"}:
            self._disable = True
        self._no_underscore = False
        if language in {"nim"}:
            self._no_underscore = True
        self._temp = 0

    def _get_temp(self):
        self._temp += 1
        if self._no_underscore:
            return f"tmp{self._temp}"
        return f"__tmp{self._temp}"

    def visit_Assign(self, node):
        """
        Visits to rewrite complex destructuring assignments (e.g. a, (b, c) = foo())
         into simpler ones that are easier to transpile to C-like languages. Only rewrites if
        """
        if self._disable:
            return node
        target = node.targets[0]
        if isinstance(target, ast.Tuple) and not (isinstance(target.elts[0], ast.Name)):
            temps = []
            orig = [None] * len(target.elts)
            body = [node]
            for i in range(len(target.elts)):
                temps.append(ast.Name(id=self._get_temp(), lineno=node.lineno))
                # The irony!
                target.elts[i], orig[i] = temps[i], target.elts[i]
                body.append(
                    ast.Assign(targets=[orig[i]], value=temps[i], lineno=node.lineno) # FIXME: this
                    # FIXME: ... is wrong as '''class ast.Assign(targets, value, type_comment)'''
                    #  so there is no 'lineno' and doc says that: '''
                    #  type_comment is an optional string with the type annotation as a comment.
                    #  '''
                )
            return create_ast_block(body=body, at_node=node)
        return node


