
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

-----

- Maybe migrate Dart from use of sprintf to dart-format and modern string
  interpolation ${} syntax

- Change LanguageSettings 'ext' to be 'extension' but only after merging all backends

- Investigate more about test suite 

- Integrate tests/cases/for_else.py into testsuite *PROPERLY* (add expected)

