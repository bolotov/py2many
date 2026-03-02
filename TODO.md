#### Issue with rewriters

Right now many rewriters:

* Mutate node fields
* Reuse node.value references
* Sometimes return same node
* Sometimes return new nodes
That is dangerous and bad.

Better if Rewriters would:
* Return original node unchanged
* Return a NEW node
* Never mutate siblings

-----


- Make a "type/class" 'language' and backend would be requered to
  have itself described using it in code of targets/backends in __init__i
  regarding which rewriters does it need and how it needs them or to have
  own rewriters with own stuf or with customized standard rewriters

- Make each language to have:
   * its own transformer configuration.
   * its own rewriter configuration.

- Language specific transformers and rewrites inside language **target**s
  **and** possibility to use/inherit common transformers and rewriters
  that are **reusable**, **composable**, **inheritable**
  ... or a functional way to have type of language to be inherited from 
  a template but defined in a **target** language folder

#### In other words:

- Refactor rewriters to be language-agnostic
- Move language filtering to registry
- Turn pipeline into declarative transformation chain
- Introduce compiler phase separation:

    - AST normalization
    - semantic lowering
    - backend lowering

-----

#### Design improvements

Ogranise language data for better both way transformation

Creation of 'syntax'

Better **organisation**. Put into sepparate folder/module/package (depending what would bebetter):

- python shims
- "transformers"





---



- js2py as front (ast producer) for py2many. Problems and solutions:
  - Js2Py wraps everything in a pyjs object to preserve JS behavior
     (like null vs undefined).
  - a small AST Walker (using ast.NodeTransformer) that would replace
    for example ``pyjs.lib.Number(5)`` with simply ``5``.
    This could make the code transformation much cleaner.
  - Truth-ines solver for js.

- Maybe migrate Dart from use of sprintf to dart-format and modern string
  interpolation ${} syntax

- Change LanguageSettings 'ext' to be 'extension' but only after merging all backends

- Investigate more about test suite 

- Integrate tests/cases/for_else.py into testsuite *PROPERLY* (add expected)

