"""
C++ target language backend for py2many.

Defines the `settings()` function that returns a configured LanguageSettings
object used for transpiling Python code to C++.
"""

import os
import sys
import pathlib
from itertools import chain
from typing import List

from py2many.language import LanguageSettings
from py2many.process_helpers import find_executable
from .transpiler import CppListComparisonRewriter, CppTranspiler

# Constants for Conan include detection
USER_HOME = os.path.expanduser("~")
CONAN_ROOTS = [f"{USER_HOME}/.conan/", f"{USER_HOME}/.conan2/"]
REQUIRED_INCLUDE_FILES = [
    "catch2/catch_test_macros.hpp",
    "cppitertools/range.hpp",
]


def _conan_include_dirs() -> List[str]:
    """Search Conan cache for known includes and extract their parent dirs."""
    include_dirs = []
    for hpp_filename in REQUIRED_INCLUDE_FILES:
        for root in CONAN_ROOTS:
            for path in pathlib.Path(root).rglob(hpp_filename):
                include_dirs.append(str(path.parent.parent))
    return include_dirs


def _conan_include_args() -> List[str]:
    """Convert Conan include dirs into -I flags for compiler."""
    return list(chain(*[["-I", dir] for dir in _conan_include_dirs()]))


def settings(args, env=os.environ) -> LanguageSettings:
    """
    Configure C++ backend with formatter, rewriters, linter, etc.

    Args:
        args: Parsed CLI args, must have .extension and .no_prologue
        env: Environment mapping for $CXX, $CLANG_FORMAT_STYLE, $CXXFLAGS

    Returns:
        LanguageSettings configured for C++ code generation.
    """
    # Select compiler
    cxx = env.get("CXX")
    default_cxx = ["clang++", "g++-11", "g++"]
    if cxx and not find_executable(cxx):
        print(f"Warning: CXX={cxx} not found")
        cxx = None
    if not cxx:
        for exe in default_cxx:
            if find_executable(exe):
                cxx = exe
                break
        else:
            cxx = default_cxx[0]

    # Construct C++ compiler flags
    cxx_flags = env.get("CXXFLAGS", "-std=c++17 -Wall -Werror").split()
    cxx_flags = _conan_include_args() + cxx_flags
    if cxx.startswith("clang++") and sys.platform != "win32":
        cxx_flags += ["-stdlib=libc++"]

    # Construct formatter
    clang_style = env.get("CLANG_FORMAT_STYLE")
    clang_format_cmd = ["clang-format", "-i"]
    if clang_style:
        clang_format_cmd.insert(1, f"-style={clang_style}")

    return LanguageSettings(
        transpiler=CppTranspiler(args.extension, args.no_prologue),
        ext=".cpp",
        display_name="C++",
        lang_id="cpp",  # ensures consistent key in registry
        formatter=clang_format_cmd,
        rewriters=[
            #   CLikeRewriter(),  # general structural normalization
            CppListComparisonRewriter(),  # language-specific
        ],
        post_rewriters=[],
        linter=[cxx] + cxx_flags,
        project_subdir="src",
        indent="    ",  # default to 4 spaces
    )
