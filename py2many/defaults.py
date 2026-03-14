from dataclasses import dataclass

DEFAULTS = {
    "indent": 4,
    "no_prologue": False,
    "extension": False,
    "suffix": "",
    "comment_unsupported": False,
    "ignore_formatter_errors": False,
    "typpete": False,
    "version": False,
    "project": None,
}


@dataclass(frozen=True)
class Defaults:
    ident: int = 4
    no_prologue: bool = False
    extension: bool = False
    suffix: str = ""
    comment_unsupported: bool = False
    ignore_formatter_errors: bool = False
    typpete: bool = False
    version: bool = False
    project: bool = False