"""
The main differences between rewriters and transformers
besides their names are that:

- rewriters are expected to be used in multiple languages,
  while transformers are language-specific (well ... kind of)

- rewriters are expected to be used in multiple places in
  the pipeline, while transformers are expected to be used
  in a specific place in the pipeline
  (e.g. after type inference, before code generation, etc.)

- rewriters are expected to be more general and less invasive,
  while transformers are expected to be more specific and
  more invasive (e.g. changing the structure of the AST more
  significantly)

Rewriters are used in pipeline.py (that need to be extracted)
...and in registry.py

Languages are expected to implement too specific to them
rewriters in their own package, but common ones that are
used across languages can be used from here.
"""

# FIXME: Unfortunately rewriters check inside them
#  wherever they should be used or not.
#  HOW IT MUST ME:
#  - rewriters must be listed in language's settings
#    as convenience
#  - language must decide itself how to use rewriters

# FIXME: camel_case, capitalize_first should be
#  extracted elsewhere into ..../utils or into a separate
#  module for case utilities, this would improve their re-use.

from .complex_destructuring import ComplexDestructuringRewriter
from .doc_string_to_comment import DocStringToCommentRewriter
from .f_string_join import FStringJoinRewriter
from .ignored_assign import IgnoredAssignRewriter
from .loop_else import LoopElseRewriter
from .print_bool import PrintBoolRewriter
from .python_main import PythonMainRewriter
from .str_str import StrStrRewriter
from .unpack_scope import UnpackScopeRewriter
from .with_to_block_transformer import WithToBlockTransformer
from .with_to_block_transformer import camel_case, capitalize_first

__all__ = (
    "camel_case",
    "capitalize_first",
    "WithToBlockTransformer",
    "ComplexDestructuringRewriter",
    "DocStringToCommentRewriter",
    "FStringJoinRewriter",
    "IgnoredAssignRewriter",
    "LoopElseRewriter",
    "PrintBoolRewriter",
    "PythonMainRewriter",
    "StrStrRewriter",
    "UnpackScopeRewriter",
)


# LoopElseRewriter - used for ALL but python (in pipeline.py::_transpile)