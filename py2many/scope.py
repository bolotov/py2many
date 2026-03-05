import ast
from contextlib import contextmanager

from py2many.analysis import get_id


# All AST node types that introduce lexical scopes.
# FIX: Explicit central definition ensures consistent scope detection
# across the entire module and avoids duplicated isinstance logic.
_SCOPE_TYPES = (
    ast.Module,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)


def add_scope_context(node):
    """Provide to scope context to all nodes"""
    return ScopeTransformer().visit(node)


class ScopeMixin:
    """
    Adds a scope property with the current scope (function, module)
    a node is part of.
    """

    def __init__(self):
        # FIX:
        # Scope stack must be instance-local and must never be shared.
        # Using a plain list is correct because the transformer instance
        # is single-use per traversal.
        self.scopes = []

    @contextmanager
    def enter_scope(self, node):
        """Context manager for entering a new scope."""

        # Only push nodes that actually introduce scopes.
        if isinstance(node, _SCOPE_TYPES):
            self.scopes.append(node)
            try:
                yield
            finally:
                # FIX:
                # Ensure the stack is restored even if an exception occurs
                # during subtree traversal.
                self.scopes.pop()
        else:
            yield

    @property
    def scope(self):
        # Return current scope or None when traversal has not yet entered one.
        return self.scopes[-1] if self.scopes else None


class ScopeList(list):
    """
    Wraps around list of scopes and provides find method for finding
    the definition of a variable
    """

    @staticmethod
    def _lookup(scope, attr, name):
        # FIX:
        # getattr default prevents AttributeError when analysis passes
        # have not attached attributes like vars/body_vars/orelse_vars.
        for var in getattr(scope, attr, ()):
            if get_id(var) == name:
                return var
        return None

    def find(self, lookup):
        """Find definition of variable lookup."""

        # Attributes expected from earlier analysis passes.
        attrs = ("vars", "body_vars", "orelse_vars")

        for scope in reversed(self):

            # Search synthetic attributes added by analysis passes.
            for attr in attrs:
                if hasattr(scope, attr):
                    result = self._lookup(scope, attr, lookup)
                    if result:
                        return result

            # Fallback: search body nodes.
            # Needed for constructs like lambdas whose body may contain
            # definitions directly.
            if hasattr(scope, "body") and isinstance(scope.body, list):
                result = self._lookup(scope, "body", lookup)
                if result:
                    return result

        return None

    @property
    def parent_scopes(self):
        # FIX:
        # Returning an empty ScopeList ensures type consistency.
        # Returning [] previously would break callers expecting ScopeList.
        if len(self) <= 1:
            return ScopeList()
        return ScopeList(self[:-1])


class ScopeTransformer(ast.NodeTransformer, ScopeMixin):
    """Adds a scope attribute to each AST node.

    This transformer traverses the AST and attaches a `ScopeList` to each node,
    representing the lexical scope (e.g., Module, Function, For loop) the
    node belongs to.

    Attributes:
        scopes: Inherited from ScopeMixin, tracks the current nesting level.
    """

    def __init__(self):
        ast.NodeTransformer.__init__(self)
        ScopeMixin.__init__(self)

    def visit(self, node):

        # FIX:
        # The scope list attached to nodes must be a *snapshot*
        # of the current scope stack. Using ScopeList(self.scopes)
        # directly would expose the mutable internal stack.
        with self.enter_scope(node):
            node.scopes = ScopeList(list(self.scopes))
            return super().visit(node)