## Overview of Tools and Optional Dependencies



py2many uses a variety of tools for pretty-printing, formatting, type inference, and code quality. Some are language-specific, while others are shared across backends. This document summarizes these tools, their purposes, and how they are used.

### Shared / Core Tools



#### How to Install

Install Python 3.11+, install optional formatters as needed for your target language.
For Kotlin pretty-printing, install **jgo**.
See the README and main.yml for more details.



#### Summary Table

- |Language| -- |Formatter / Prettyprinter|
- C++  -- clang-format	
- Rust  -- rustfmt
- Kotlin -- jgo (prettyprinter)
- Nim -- nimpretty
- Dart -- dartfmt
- Go -- gofmt
- D -- dfmt
- Julia -- juliaformatter



### Type Inference

py2many includes a core type inference engine (inference.py) used by all backends to infer types from Python code. **Typette** and **Z3** are used.

Each backend may extend or override inference logic for language-specific needs (see e.g. inference.py, inference.py).

### AST Rewriters and Transformers

AST rewriters and transformers are used to preprocess and annotate the Python AST before code generation.
These are defined in language.py as part of the LanguageSettings dataclass:
rewriters: AST visitor passes (e.g., mutability tagging)
transformers: Functional AST transformations
post_rewriters: Final AST passes before rendering

### Logging

Logging is used throughout for diagnostics and debugging, with a shared logger (py2many).



### Formatting and Pretty-Printing

Many backends rely on external formatters to ensure the generated code is idiomatic and readable.



#### C++

Formatter: clang-format
Used to format generated C++ code.
Must be installed separately (see README).
Invoked automatically after code generation.



#### Rust

Formatter: rustfmt
Used to format generated Rust code.
Invoked automatically if available.



#### Kotlin

Prettyprinter: jgo (optional dependency)
jgo is used to fetch and run a prettyprinter for Kotlin code.
Optional, but recommended for best results.



#### Nim, Dart, Go, D, Julia
Each language may use its own formatter if available (e.g., nimpretty for Nim, dartfmt for Dart, gofmt for Go, etc.).
These are typically invoked after code generation if installed.
Type Inference (By Language)



#### Rust: inference.py
Extends core inference for Rust-specific types and lifetimes.
Kotlin: inference.py
Handles Kotlin type mapping and inference.



### Nim, Dart, C++

### Each has its own inference logic, often subclassing or extending the core.

Optional and External Dependencies
jgo: For Kotlin pretty-printing.
clang-format: For C++ formatting.
rustfmt: For Rust formatting.
Other formatters: As appropriate for each language.
See the README and main.yml for installation instructions for these tools.



#### Testing and Linting
pytest: Used for running Python unit tests.



#### Language-specific linters

Some backends may invoke linters (e.g., **cargo**, **clippy** for Rust) if configured in LanguageSettings.linter.

