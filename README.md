runtime-type-checker
====================
![PyPI](https://img.shields.io/pypi/v/runtime-type-checker)
![PyPI - License](https://img.shields.io/pypi/l/runtime-type-checker)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

This package performs type-check at runtime with help of type annotations.

## How to use this package

There are two ways to perform type checks using this package.

I provide a few simple examples here. For a complete overview, have a look at the package's unit tests.

### 1- the `check_type` function

You can check an object against a type or an annotation via the `check_type` function.

The function returns `None` if the check was successful or raises a `TypeError` in case of error.

Note that this function does not check recursively for e.g. the attributes of a class.
```python
from typing import List, Sequence, Optional, Mapping
from dataclasses import dataclass
from runtime_type_checker import check_type


check_type("a", str)  # OK
check_type(["a"], List[str])  # OK
check_type(["a", 1], Sequence[str])  # raises TypeError


@dataclass
class Foo:
    a: int
    b: Optional[Mapping[str, int]] = None


check_type(Foo(1), Foo)  # OK
check_type(Foo(1), int)  # raises TypeError
```

### 2- The check_types decorator

You can also type-check classes upon instance creation and functions or methods upon call through the `check_types`
decorator:
```python
from typing import Optional, Mapping
from dataclasses import dataclass
from runtime_type_checker import check_types

def run_typed(f):
  return check_types(dataclass(f))

@check_types
@dataclass
class Foo:
    a: int
    b: Optional[Mapping[str, int]] = None


Foo(1)              # returns an instance of foo
Foo(0, {"a": "b"})  # raises TypeError


@check_types
def bar(a: bool, **options: str) -> str:
    return options.get("b", "missing") if a else "unknown"

bar(True, b="1")  # returns "1"
bar(True, c=1)    # raises TypeError
```

## Package features and short-comings

### 1- Features
- _simplicity_: there's only one function and one decorator to keep in mind.
- _robustness_: this package relies on the `typing-inspect` for the heavy lifting. This package is maintained by
core contributors to the typing module, which means very little hacks on my side to work with older versions of python.

### 2- Short-comings

- _coverage_: I don't offer coverage for all features of type annotations: for example Protocol, Generators, IO are not
currently supported. Generics are not really well handled.
