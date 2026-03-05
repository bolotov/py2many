import ast
from collections.abc import Iterable
from contextlib import contextmanager

from py2many.analysis import get_id


def add_scope_context(node):
    """Provide to scope context to all nodes"""
    return ScopeTransformer().visit(node)


class ScopeMixin:
    """
    Adds a scope property with the current scope (function, module)
    a node is part of.
    """

    scopes : list[ast.AST] = []

    @contextmanager
    def enter_scope(self, node): # -> Iterable[None]:
        """Context manager for entering a new scope."""
        if self._is_scopable_node(node):
            self.scopes.append(node)
            yield
            self.scopes.pop()
        else:
            yield

    @property
    def scope(self):
        try:
            return self.scopes[-1]
        except IndexError:
            return None

    @staticmethod
    def _is_scopable_node(node): # FIXME: IMPORTANT: KEEP OLD NAME IN A COMMENT | IMPORTANT: FIND A BETTER NAME TO NOT TRIGGER SPELLCHECKER
        scopes = [
            ast.Module,
            ast.ClassDef,
            ast.FunctionDef,
            ast.Lambda,
            ast.For,
            ast.If,
            ast.With,
        ]
        return len([s for s in scopes if isinstance(node, s)]) > 0


class ScopeList(list):
    """
    Wraps around list of scopes and provides find method for finding
    the definition of a variable
    """

    def find(self, lookup):
        """Find definition of variable lookup."""

        def find_definition(scope, var_attr="vars"):
            for var in getattr(scope, var_attr):
                if get_id(var) == lookup:
                    return var
            return None

        for scope in reversed(self):
            defn = None
            if not defn and hasattr(scope, "vars"): # TODO: convert into match-case pattern matching OR something better
                defn = find_definition(scope, "vars")
            if not defn and hasattr(scope, "body_vars"):
                defn = find_definition(scope, "body_vars")
            if not defn and hasattr(scope, "orelse_vars"):
                defn = find_definition(scope, "orelse_vars")
            if not defn and hasattr(scope, "body"):
                # special case lambda functions here. Their body is not a list
                if isinstance(scope.body, Iterable):
                    defn = find_definition(scope, "body")
                else:
                    return None
            if defn:
                return defn
        return None

    def find_import(self, lookup):  # pragma: no cover
        """
        Find definition of an import.

        Currently unused.
        """
        for one_scope in reversed(self):
            if hasattr(one_scope, "imports"):
                for imp in one_scope.imports:
                    if imp.name == lookup:
                        return imp
        return None # <-- is it safe?

    @property
    def parent_scopes(self):
        scopes = list(self)
        scopes.pop()
        return ScopeList(scopes)

class ScopeTransformer(ast.NodeTransformer, ScopeMixin):
    """Adds a scope attribute to each AST node.

    This transformer traverses the AST and attaches a `ScopeList` to each node,
    representing the lexical scope (e.g., Module, Function, For loop) the
    node belongs to.

    Attributes:
        scopes: Inherited from ScopeMixin, tracks the current nesting level.
    """

    def visit(self, node: ast.AST):
        """Visits a node and attaches the current scope list.

        Args:
            node: The AST node to process.

        Returns:
            The visited node, potentially transformed.
        """
        with self.enter_scope(node): # WARNING: Parameter 'node' unfilled
        # with self.enter_scope(node): #
            # Note: Attaching custom attributes to AST nodes is valid in Python
            node.scopes = ScopeList(self.scopes)  # type: ignore
            return super().visit(node)