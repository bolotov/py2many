# All common Rewriters to be moved here for better structure
# Languages are expected to implement too specific to them 
# rewriters in their own folder
#
# rewriters are used in cli.py (that need to be extracted)
# ...and in registry.py

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

__all__ = [
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
]

