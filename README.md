# py2many: Python to other languages transpiler

![Build](https://github.com/py2many/py2many/actions/workflows/fast.yaml/badge.svg)![License](https://img.shields.io/github/license/adsharma/py2many?color=brightgreen)

## Why

Python is popular, easy to program in, but *if written naively* has poor runtime
performance. We can fix that by transpiling a subset of the language into
a more performant, statically typed language.

A second benefit is security. Writing security sensitive code in a low level language
like C is error prone and could lead to privilege escalation.

Specialized languages exist to address this use case, you may also want to
look at [wuffs](https://github.com/google/wuffs).

py2many can be a more general purpose solution to the problem
where you can verify the source via unit tests before you transpile.

A third potential use case is to accelerate python code by transpiling
it into an [extension](https://github.com/adsharma/py2many/issues/62)

Swift and Kotlin dominate the mobile app development workflow. However, there is
no one solution that works well for lower level libraries where there is desire
to share code between platforms. Kotlin Mobile Multiplatform (KMM) is a player
in this place, but it hasn't really caught on. py2many provides an alternative.

Lastly, it's a great educational tool to learn a new language by implementing
a backend for your favorite language.

## Status

Rust is the language where the focus of development has been.

C++14 is historically the first language to be supported.
C++17 is now required for some features.

Preliminary support exists for Julia, Kotlin, Nim, Go, Dart, V, and D.

py2many can also emit Python 3 code that includes inferred type annotations,
and revisions to the syntax intended to simplify parsing of the code.

## History and Acknowledgments

Based on Julian Konchunas' [pyrs](http://github.com/konchunas/pyrs).

Based on Lukas Martinelli [Py14](https://github.com/lukasmartinelli/py14)
and [Py14/python-3](https://github.com/ProgVal/py14/tree/python-3) branch by Valentin Lorentz.

## Example

Original Python code:

```python
def fib(i: int) -> int:
    if i == 0 or i == 1:
        return 1
    return fib(i - 1) + fib(i - 2)
```

Transpiled Rust code:

```rust
fn fib(i: i32) -> i32 {
    if i == 0 || i == 1 {
        return 1;
    }
    return (fib((i - 1)) + fib((i - 2)));
}
```

Transpiled code for other languages:

https://github.com/adsharma/py2many/tree/main/tests/expected (fib*)

## Trying it out

Requirements:

- Python 3.11+ (may work or not on older versions)

Optional dependencies:

- [jgo](https://github.com/scijava/jgo.git) - gets & runs prettyprinter for kotlin

Local installation:

```sh
pip3 install --user  # installs to $HOME/.local
```

OR

```sh
sudo pip3 install  # installs systemwide
```

Add the py2many script to your $PATH and run:

Transpiling:

```sh
py2many --lang=cpp tests/cases/fib.py
py2many --lang=rust tests/cases/fib.py
py2many --lang=julia tests/cases/fib.py
py2many --lang=kotlin tests/cases/fib.py
py2many --lang=nim tests/cases/fib.py
py2many --lang=dart tests/cases/fib.py
py2many --lang=go tests/cases/fib.py
py2many --lang=dlang tests/cases/fib.py
```

Compiling:

```sh
clang tests/expected/fib.cpp
./scripts/rust-runner.sh run tests/expected/fib.rs
...
dmd -run tests/cases/fib.d
```

Many of the transpilers rely on a language specific formatter to parse the output and reformat it.
Typically this is the most prominent formatter for the language, such as `rustfmt` for Rust.

Most of the transpilers also rely on external libraries to provide bridges from
Python constructs to the target language.

The steps to install these external libraries can be found in `.github/workflows/main.yml`.

# Contributing

See [CONTRIBUTING.md](https://github.com/adsharma/py2many/blob/main/CONTRIBUTING.md)
for how to test your changes and contribute to this project.
