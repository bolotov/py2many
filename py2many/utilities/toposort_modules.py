import ast
from collections import defaultdict
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any, Tuple, Dict, FrozenSet, Generator


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
    Builds graph where deps[current_module] = frozenset(imported_modules).

    Example:
        >>> import ast
        >>> tree = ast.parse("from . import foo\\nimport bar")
        >>> tree.__file__ = "pkg/mod.py"
        >>> visitor = ImportDependencyVisitor({'pkg.foo', 'bar'})
        >>> visitor.visit(tree)
        >>> visitor.deps['pkg.mod']
        frozenset({'pkg.foo', 'bar'})
    """
    def __init__(self, project_modules: FrozenSet[str]):
        """
        Args:
            project_modules: Frozen set of known module names to track (immutable)
        """
        self.deps: Dict[str, FrozenSet[str]] = {}
        self._project_modules = project_modules
        self._current: str = ""
        self._pending_deps: Dict[str, set[str]] = defaultdict(set)

    def visit_Module(self, node):
        """Track current module when entering module node."""
        self._current = module_for_path(Path(node.__file__))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Capture 'from module import ...' dependencies."""
        if node.module and node.module in self._project_modules:
            self._pending_deps[self._current].add(node.module)
        self.generic_visit(node)

    def visit_Import(self, node):
        """Capture 'import module' dependencies."""
        for alias in node.names:
            if alias.name in self._project_modules:
                self._pending_deps[self._current].add(alias.name)
        self.generic_visit(node)
    
    def finalize(self) -> Dict[str, FrozenSet[str]]:
        """Convert mutable deps to immutable frozensets for all modules."""
        # Ensure all project modules are in the deps dict
        result = {}
        for module in self._project_modules:
            result[module] = frozenset(self._pending_deps.get(module, set()))
        return result


def get_dependencies(trees: Tuple[ast.AST, ...]) -> Dict[str, FrozenSet[str]]:
    """Extract complete dependency graph from list of Python AST trees.

    Ensures every project module appears in deps graph (empty frozenset if no deps).
    Only includes modules from the trees being transpiled - ignores sys.modules.

    Args:
        trees: List of ast.Module nodes with __file__ attribute set

    Returns:
        Dict[module_name, frozenset(dependencies)] - immutable graph 
        where keys depend ON values. Only includes project modules.

    Example:
        >>> import ast
        >>> t1 = ast.parse("from foo import x"); t1.__file__ = "a.py"
        >>> t2 = ast.parse("pass"); t2.__file__ = "foo.py"
        >>> deps = get_dependencies((t1, t2))
        >>> deps['a']
        frozenset({'foo'})
        >>> deps['foo']
        frozenset()
    """
    # Extract module names from trees - only track these modules
    project_modules = frozenset(module_for_path(Path(node.__file__)) for node in trees)
    
    # Visit AST trees to find dependencies
    visitor = ImportDependencyVisitor(project_modules)
    for tree in trees:
        visitor.visit(tree)
    
    # Return immutable dependency graph for only project modules
    return visitor.finalize()


class StableTopologicalSorter(TopologicalSorter[str]):
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

    def static_order(self) -> Generator[str]:
        """Yield nodes in topological order, sorting ready batches lexicographically.
        
        Yields:
            Module names in execution order (dependents after dependencies)
        """
        self.prepare()
        while self.is_active():
            node_group = self.get_ready()
            yield from sorted(node_group)
            self.done(*node_group)


def toposort(trees: Tuple[ast.AST, ...]) -> Tuple[ast.AST, ...]:
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
    tree_dict = {
        module_for_path(Path(node.__file__)):node for node in trees
    }
    ts = StableTopologicalSorter(deps)
    return tuple(tree_dict[t] for t in ts.static_order())
