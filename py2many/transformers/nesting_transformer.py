import ast


def detect_nesting_levels(node: ast.AST) -> ast.AST:
    return NestingTransformer().visit(node)


class NestingTransformer(ast.NodeTransformer):
    """
    Some languages are white space sensitive. This transformer
    annotates relevant nodes with the nesting level
    """

    def __init__(self):
        self.level = 0

    def _visit_level(self, node: ast.AST) -> ast.AST:
        """Annotate node with nesting level and visit children"""
        node.level = self.level
        self.level += 1
        self.generic_visit(node)
        self.level -= 1
        return node

    def visit_FunctionDef(self, node: ast.AST) -> ast.AST:
        """Annotate function definitions with nesting level"""
        return self._visit_level(node)

    def visit_ClassDef(self, node: ast.AST) -> ast.AST:
        """
        Annotate class definitions with nesting level.
        This is relevant for languages like Java
        where nested classes are a thing,
        but not for Python where nested classes are not a thing.
        """
        return self._visit_level(node)

    def visit_If(self, node: ast.AST):
        """Annotate if statements with nesting level"""
        return self._visit_level(node)

    def visit_While(self, node: ast.AST):
        """Annotate while statements with nesting level"""
        return self._visit_level(node)

    def visit_For(self, node: ast.AST):
        """Annotate for statements with nesting level"""
        return self._visit_level(node)

    def visit_Assign(self, node: ast.AST):
        """Annotate assignment statements with nesting level"""
        node.level = self.level
        self.generic_visit(node)
        return node
