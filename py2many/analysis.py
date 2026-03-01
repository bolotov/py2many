import ast

from .ast_helpers import get_id

# FIXME: I believe that whatever following line wants to achieve - it can be achieved better and in more functional way
get_id  # quiten pyflakes; this should when code is updated to use ast_helpers

IGNORED_MODULE_SET = {
    "typing",
    "enum",
    "dataclasses",
    "ctypes",
    "math",
    "__future__",
    "asyncio",
    "sys",
    "os",
    "adt",
    "py2many.result",
    "py2many.smt",
}


def add_imports(node) -> bool:
    """Provide context of imports Module"""
    return ImportTransformer().visit(node)


def is_void_function(fun) -> bool:
    """
    Checks if a function has a return statement with a value

    :param fun: The AST node representing the function to check
    :return: True if the function has a return statement with a value, False otherwise  
    """
    finder = ReturnFinder()
    finder.visit(fun)
    return not (finder.returns or fun.returns is not None)


def is_global(target) -> bool:
    """
    Checks if the target is defined in the global scope (i.e., module level)

    :param target: The AST node representing the variable or function to check
    :return: True if the target is defined in the global scope, False otherwise
    """
    return isinstance(target.scopes[-1], ast.Module)


def is_mutable(scopes, target) -> bool:
    """
    Checks if the target is mutable
    (i.e., defined in a function scope and assigned to within that scope)

    #  IT SEEMS LIKE IT WILL ALWAYS GO 'false', look **WARNING** in a body of a function
    #  From ast module docs:
    #
    # class ast.FunctionDef(name, args, body, decorator_list, returns, type_comment, type_params)¶
    # A function definition.
    #
    # name is a raw string of the function name.
    # args is an arguments node.
    # body is the list of nodes inside the function.
    # decorator_list is the list of decorators to be applied, stored outermost first (i.e. the first in the list will be applied last).
    # returns is the return annotation.
    # type_params is a list of type parameters.
    # type_comment
    # type_comment is an optional string with the type annotation as a comment.
    """
    for scope in scopes:
        if isinstance(scope, ast.FunctionDef):
            if target in scope.mutable_vars: # WARNING: "FunctionDef" has no attribute "mutable_vars"
                return True
    return False


def is_ellipsis(node) -> bool:
    """
    Checks if the node is an ellipsis literal (i.e., ...).
    This is used to identify function bodies that are not implemented yet.

    :param node: The AST node to check
    :return: True if the node is an ellipsis literal (i.e., ...), False otherwise
    """
    return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and node.value.value is ...
    )


class ReturnFinder(ast.NodeVisitor): # FIXME: I am not sure wherever I have fixed that or not
    def __init__(self):
        self.returns = False


    def visit_Return(self, node) -> bool:
        """Checks if a return statement has a value"""
        if node.value is not None:
            self.returns = True
        else:
            self.generic_visit(node)  # continue searching for return statements with values
        return self.returns  # Return True if a return statement with a value is found, otherwise False
#       ^
#       Do we need this instead (why?):
#       def visit_Return(self, node):
#           if node.value is not None:
#               self.returns = True
#           self.generic_visit(node)

class FunctionTransformer(ast.NodeTransformer):
    """
    Tracks defined functions in scope
    """

    def visit_FunctionDef(self, node):
        """
        Visits a function definition node and adds it to the list of defined functions in the current scope.

        Parameters:
            node AST node representing a function definition

        Returns:
            AST node with updated defined functions in scope
        """
        node.defined_functions = []
        node.scopes[-2].defined_functions.append(node) # WARNING: Unresolved attribute reference 'scopes' for class 'FunctionDef'
        self.generic_visit(node)
        return node

    def _visit_Scoped(self, node):
        """
        Visits a scoped block node and initializes the list of defined functions in that scope.

        :param node AST node representing a scoped block (e.g., module, class, for loop, if statement, with statement):
        :return AST node with updated defined functions in scope:
        """
        node.defined_functions = []
        self.generic_visit(node)
        return node

    # FIXME: methods below have wird issues that I do not understand, fix and **EXPLAIN**

    def visit_Module(self, node):
        return self._visit_Scoped(node) # WARNING: Type 'Module' doesn't have expected attribute 'defined_functions'

    def visit_ClassDef(self, node):
        return self._visit_Scoped(node) # WARNING: Type 'ClassDef' doesn't have expected attribute 'defined_functions'

    def visit_For(self, node):
        return self._visit_Scoped(node) # WARNING: Type 'For' doesn't have expected attribute 'defined_functions'

    def visit_If(self, node):
        return self._visit_Scoped(node) # WARNING: Type 'If' doesn't have expected attribute 'defined_functions'

    def visit_With(self, node):
        return self._visit_Scoped(node) # WARNING: Type 'With' doesn't have expected attribute 'defined_functions'

    def visit_ImportFrom(self, node):
        for name in node.names:
            if node.module not in IGNORED_MODULE_SET:
                # FIXME: does line below attempts to set unexisting properyt? What should happen instead? any functional ways?
                node.scopes[-1].defined_functions.append(name) # WARNING: Unresolved attribute reference 'scopes' for class 'ImportFrom'
        return node


class CalledWithTransformer(ast.NodeTransformer):
    """
    Tracks whether variables or functions get
    used as arguments of other functions
    """

    def visit_Assign(self, node):
        for target in node.targets:
            target.called_with = []
        return node

    def visit_FunctionDef(self, node):
        node.called_with = []
        self.generic_visit(node)
        return node

    def visit_Call(self, node):
        for arg in node.args:
            if isinstance(arg, ast.Name):
                var = node.scopes.find(arg.id) # WARNING: Unresolved attribute reference 'scopes' for class 'Call'
                var.called_with.append(node)
        self.generic_visit(node)
        return node


class AttributeCallTransformer(ast.NodeTransformer):
    """Tracks attribute function calls on variables"""

    def visit_Assign(self, node):
        """

        :param node:
        :return:
        """
        for target in node.targets:
            target.calls = []
        return node

    def visit_Call(self, node):
        """

        :param node:
        :return:
        """
        if isinstance(node.func, ast.Attribute):
            # WARNING (regarding *NEXT* line): Unresolved attribute reference 'id' for class 'expr'
            var = node.scopes.find(node.func.value.id) # WARNING: Unresolved attribute reference 'scopes' for class 'Call'
            var.calls.append(node)
        return node


class ImportTransformer(ast.NodeTransformer):
    """
    Adds imports to scope blocks, so that we can track which
    variables are imported from which modules
    """

    def visit_ImportFrom(self, node):
        """
        Visits an import statement and adds the imported names to the list of imports in the current scope.

        :param node:
        :return:
        """
        for name in node.names:
            name.imported_from = node
            scope = name.scopes[-1] # WARNING: Unresolved attribute reference 'scopes' for class 'alias'
            if hasattr(scope, "imports"):
                scope.imports.append(name)
        return node

    def visit_Module(self, node):
        """
        Initializes the list of imports in the module scope and
        visits the module body.
    
        Parameter:
            node AST node representing the module

        Returns
            AST node with updated imports in module scope
        """
        node.imports = []
        self.generic_visit(node)
        return node
