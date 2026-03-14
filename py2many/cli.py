#!/usr/bin/env python3
import argparse
import os.path
import sys
from typing import Optional, Sequence

from py2many.pipeline import LANGS, transpile_from_args

try:
    project_root = os.path.dirname(__file__)
    sys.path.insert(0, project_root)
except Exception as exc:
    print(f"Error determining project root: {exc}")
    project_root = None


def parse_args(arguments: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-l", "--lang",
        type=str,
        choices=LANGS.keys(),
        required=True,
        metavar="LANG",
        help="Target language to transpile to.",
    )

    parser.add_argument(
        "--out_dir",
        type=str,
        default=None,
        help="Output directory for transpiled files. Defaults to same directory as input.",
    )

    parser.add_argument(
        "-i", "--indent",
        type=int,
        default=None,
        help="Indentation to use in languages that use it",
    )

    parser.add_argument(
        "--comment-unsupported",
        action="store_true",
        default=False,
        help="Skip over unsupported constructs and generate some code",
    )

    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        default=True,
        help="Don't raise an error on unsupported constructs, just comment them out",
    )

    parser.add_argument(
        "--ignore-formatter-errors",
        action="store_true",
        default=False,
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
        type=str,
        default=None,
        help="Alternate suffix to use instead of the default one for the language",
    )

    parser.add_argument(
        "--no-prologue",
        action="store_true",
        default=False,
        help="Don't include the default prologue in the output code (e.g. imports, helper functions, etc.)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="When output and input are the same file, force overwriting",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        default=False,
        help="Display version number",
    )

    parser.add_argument(
        "--project",
        action="store_true",
        default=True,
        help="Enable project mode"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity: -v for DEBUG, -vv for TRACE",
    )

    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="Suppress non-essential output; only show errors",
    )
#    return parser.parse_args(arguments)

    parsed_args, rest = parser.parse_known_args(args=arguments)
    parsed_args._rest = rest  # Attach rest for downstream use
    return parsed_args


def main():
    args = parse_args()
    sys.exit(transpile_from_args(args))