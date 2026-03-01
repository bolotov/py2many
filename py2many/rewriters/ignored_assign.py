import ast

from py2many.analysis import get_id
from py2many.ast_helpers import create_ast_block


class IgnoredAssignRewriter(ast.NodeTransformer):
    """ Rewrites destructuring assignments with ignored variables
     (e.g. a, _, c = foo()) into separate assignments for the non-ignored
      variables, since some languages don't support ignored variables
       in destructuring assignments. Only rewrites if there are ignored
       variables in the destructuring assignment, since otherwise
        there's nothing to rewrite.
     Also does not rewrite if the language supports ignored variables in
     destructuring assignments, since in those cases it's better to keep
     the original destructuring assignment, which is more concise and readable.
    """
    def __init__(self, language):
        super().__init__()
        self._language = language
        self._disable = language in {"nim", "v"}
        self._unpack = language in {"cpp", "d", "dart", "go", "rust"}

    def _visit_assign_unpack_all(self, node):
        keep_ignored = self._language == "go"
        body = []
        target = node.targets[0]
        for i in range(len(target.elts)):
            elt = target.elts[i]
            if isinstance(elt, ast.Name):
                name = get_id(elt)
                if name == "_" and not keep_ignored:
                    body.append(ast.Expr(value=node.value.elts[i]))
                    body[-1].unused = True
                    continue
            body.append(ast.Assign(targets=[target.elts[i]], value=node.value.elts[i]))
        return create_ast_block(body=body, at_node=node)

    def visit_Assign(self, node):
        if self._disable:
            return node

        target = node.targets[0]
        if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
            names = [get_id(elt) for elt in target.elts if isinstance(elt, ast.Name)]
            has_ignored = "_" in names
            if self._unpack and has_ignored:
                return self._visit_assign_unpack_all(node)
            if not has_ignored:
                return node

            body = [node]
            to_eval = []
            for i in range(len(target.elts)):
                if names[i] == "_":
                    del target.elts[i]
                    to_eval.append(node.value.elts[i])
                    del node.value.elts[i]
            # TODO: Evaluation order - we may have to split the tuple assignment to get
            #  it right. For now, keep it simple
            body = [ast.Expr(value=e) for e in to_eval] + body
            return create_ast_block(body=body, at_node=node)
        return node


