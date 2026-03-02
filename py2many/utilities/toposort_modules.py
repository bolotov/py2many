import ast
from collections import defaultdict
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Tuple


def module_for_path(path: Path) -> str:
    """Convert file Path to Python dotted module name (without .py extension).
    
    Examples:
        >>> from pathlib import Path
        >>> module_for_path(Path('src/pkg/mod.py'))
        'src.pkg.mod'
        >>> module_for_path(Path('mod.py'))
        'mod'
        >>> module_for_path(Path('/a/b/c.py'))
        '/a/b/c'
    
    Args:
        path: Path to Python source file
        
    Returns:
        Dotted module name (dir1.dir2.mod)
    """
    # strip out .py at the end
    module = ".".join(path.parts)
    return module.rsplit(".", 1)[0]


class ImportDependencyVisitor(ast.NodeVisitor):
    """AST visitor that extracts Python import dependencies between modules.
    
    Only tracks imports from known project modules (filtered by modules set).
    Builds graph where deps[current_module] = set(imported_modules).
    
    Example:
        >>> import ast
        >>> tree = ast.parse("from . import foo\\nimport bar")
        >>> tree.__file__ = "pkg/mod.py"
        >>> visitor = ImportDependencyVisitor({'pkg.foo', 'bar'})
        >>> visitor.visit(tree)
        >>> list(visitor.deps['pkg.mod'])
        ['pkg.foo', 'bar']
    """
    def __init__(self, modules):
        """
        Args:
            modules: Set of known module names to track
        """
        self.deps = defaultdict(set)
        self._modules = modules
        self._current: str = ""

    def visit_Module(self, node):
        """Track current module when entering module node."""
        self._current = module_for_path(Path(node.__file__))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Capture 'from module import ...' dependencies."""
        if node.module and node.module in self._modules:
            self.deps[self._current].add(node.module)
        self.generic_visit(node)

    def visit_Import(self, node):
        """Capture 'import module' dependencies."""
        names = [n.name for n in node.names]
        for n in names:
            if n in self._modules:
                self.deps[self._current].add(n)
        self.generic_visit(node)


def get_dependencies(trees):
    """Extract complete dependency graph from list of Python AST trees.
    
    Ensures every module appears in deps graph (empty set if no deps).
    
    Args:
        trees: List of ast.Module nodes with __file__ attribute set
        
    Returns:
        Dict[module_name, set(dependencies)] - graph where keys depend ON values
        
    Example:
        >>> import ast
        >>> t1 = ast.parse("from foo import x"); t1.__file__ = "a.py"
        >>> t2 = ast.parse("pass"); t2.__file__ = "foo.py" 
        >>> deps = get_dependencies([t1, t2])
        >>> deps['a']
        {'foo'}
        >>> deps['foo']
        set()
    """
    modules = {module_for_path(Path(node.__file__)) for node in trees}
    visitor = ImportDependencyVisitor(modules)
    for t in trees:
        visitor.visit(t)
    for m in modules:
        if m not in visitor.deps:
            visitor.deps[m] = set()
    return visitor.deps


class StableTopologicalSorter(TopologicalSorter):
    """Topological sorter that yields nodes in stable lexicographical order.
    
    Unlike base TopologicalSorter, groups ready nodes and sorts them before yielding.
    Ensures deterministic output for same graph.
    
    Example:
        >>> from graphlib import TopologicalSorter
        >>> graph = {'a': {'b'}, 'c': set()}
        >>> ts = StableTopologicalSorter(graph)
        >>> tuple(ts.static_order())
        ('c', 'b', 'a')
    """
    def static_order(self):
        """Yield nodes in topological order, sorting ready batches lexicographically.
        
        Yields:
            Module names in execution order (dependents after dependencies)
        """
        self.prepare()
        while self.is_active():
            node_group = self.get_ready()
            yield from sorted(node_group)
            self.done(*node_group)


def toposort(trees) -> Tuple:
    """Complete pipeline: extract deps -> toposort -> return ordered trees.
    
    Prerequisites:
        * Each tree must have tree.__file__ set to source file path
        * Graph must be acyclic (raises GraphlibError if circular deps)
    
    Args:
        trees: List of ast.Module nodes with __file__ attributes
        
    Returns:
        Tuple of trees in topological order (independent first, dependents last)
        
    Example:
        >>> import ast
        >>> foo = ast.parse("pass"); foo.__file__ = "foo.py"
        >>> bar = ast.parse("from foo import x"); bar.__file__ = "bar.py"
        >>> result = toposort([foo, bar])
        >>> module_for_path(Path(result[0].__file__))
        'foo'
        >>> module_for_path(Path(result[1].__file__))
        'bar'
    """
    deps = get_dependencies(trees)
    tree_dict = {module_for_path(Path(node.__file__)): node for node in trees}
    ts = StableTopologicalSorter(deps)
    return tuple([tree_dict[t] for t in ts.static_order()])
