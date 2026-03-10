import ast

from py2many.ast_helpers import create_ast_block, get_id
from py2many.inference import get_inferred_type


class InferredAnnAssignRewriter(ast.NodeTransformer):
    """
    Rewrites Assign nodes with annotated targets to AnnAssign, so they can be
     properly transpiled to C-like languages that require type annotations on
     all variables. Only rewrites if the annotation is different from anyi
     previous annotation
     on the same variable, to avoid unnecessary noise in the output.
    Does not rewrite if the target is a subscript, since those are usually
     mutations rather than new variable definitions.
    Does not rewrite if the annotation is a class definition, since those
    are usually forward references that can't be rewritten to an annotation
    without a lot of extra work. In those cases, the class definition should
    be rewritten to a type alias in a separate pass, and then this rewriter
    can rewrite the annotation properly.
    Also assumes that all targets in a multi-target assignment have the same
    annotation, which is usually the case since it's uncommon to have
    different annotations in a multi-target assignment, and it's not worth
    the extra complexity to handle that case.
    If there are different annotations, it will just use the annotation of the
    first target, which is usually the most common case.
    """

    def visit_Assign(self, node):
        target = node.targets[0]  # Assumes all targets have same annotation
        if isinstance(target, ast.Subscript):
            return node
        annotation = getattr(target, "annotation", False)
        if not annotation:
            return node

        if isinstance(annotation, ast.ClassDef):
            annotation = ast.Name(id=get_id(annotation))

        col_offset = getattr(node, "col_offset", None)

        assigns = []
        for assign_target in node.targets:
            definition = node.scopes.parent_scopes.find(get_id(assign_target))
            if definition is None:
                definition = node.scopes.find(get_id(assign_target))
            if definition is not assign_target:
                previous_type = get_inferred_type(definition)
                if get_id(previous_type) == get_id(annotation):
                    if len(node.targets) == 1:
                        return node
                    else:
                        new_node = ast.Assign(
                            targets=[assign_target],
                            value=node.value,
                            lineno=node.lineno,
                            col_offset=col_offset,
                        )
                        assigns.append(new_node)
                        continue
            new_node = ast.AnnAssign(
                target=assign_target, # This field exists!
                value=node.value, # This field exists!
                lineno=node.lineno,  # AnnAssign has no 'lineno' <- it must be passed differently OR must be created
                col_offset=col_offset, # AnnAssign has no 'col_offset' <- it must be passed differently OR must be created
                simple=True, # This field exists!
                annotation=annotation, # This field exists!
            )
            assigns.append(new_node)

        if len(assigns) == 1:
            return assigns[0]

        return create_ast_block(body=assigns, at_node=node)


