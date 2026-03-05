#!/usr/bin/env python3
import argparse
import os.path
import sys
from typing import Optional, Sequence

from py2many.pipeline import LANGS, transpile_from_args

try:
    project_root = os.path.dirname(__file__)
    sys.path.insert(0, project_root)
except Exception: # better exception or couple, maybe use result here?
    project_root = None # ERROR: Incompatible types in assignment (expression has type "None", variable has type "str")
    # ^ which "None" is that usual one or which one?


def parse_args(arguments: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for py2many CLI.
    Returns an argparse.Namespace with all CLI options.
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-l",
        "--lang",
        choices=LANGS.keys(),
        required=True,
        metavar="LANG",
        help="Target language to transpile to.",
    )

    parser.add_argument(
        "--out_dir",
        default=None
    )
    parser.add_argument(
        "-i",
        "--indent",
        type=int,
        default=None,
        help="Indentation to use in languages that use it",

    )
    parser.add_argument(
        "--comment-unsupported",
        default=False,
        action="store_true",
        help="Skip over unsupported constructs and generate some code",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        default=True,
        action="store_false",
    )
    parser.add_argument(
        "--ignore-formatter-errors",
        dest="ignore_formatter_errors",
        default=False,
        action="store_true",
        help="Ignore formatter error if its not installed",
    )
    parser.add_argument(
        "--extension",
        action="store_true",
        default=False,
        help="Build a python extension",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Alternate suffix to use instead of the default one for the language",
    )
    parser.add_argument(
        "--no-prologue",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="When output and input are the same file, force overwriting",
    )
    parser.add_argument(
        "--typpete",
        action="store_true",
        default=False,
        help="Use typpete for inference",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        default=False,
        help="Display version number",

    )
    parser.add_argument(
        "--project",
        default=True
    )

    parsed_args, rest = parser.parse_known_args(args=arguments)
    parsed_args._rest = rest  # Attach rest for downstream use
    return parsed_args


def main():
    args = parse_args()
    sys.exit(transpile_from_args(args))
    # Parse CLI arguments and run the transpilation pipeline