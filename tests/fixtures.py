from dataclasses import dataclass
from datetime import date
import sys
from typing import ClassVar, Generic, Union, NewType, List, Optional, Tuple, TypeVar

if sys.version_info >= (3, 8):
    PYTHON_38 = True
    from typing import TypedDict

    class MyTpDict(TypedDict):
        a: str
        b: "MyClass"


else:
    PYTHON_38 = False
    from unittest.mock import MagicMock

    class MyTpDict(MagicMock):
        pass


T_bound = TypeVar("T_bound", bound=Union[date, str])
T_constraint = TypeVar("T_constraint", Union[date, str], Optional[int])


@dataclass
class MyClass:
    t: ClassVar[int] = 1
    a: int = 1
    b: Tuple[str, str] = ("a", "b")
    c: Optional["MyClass"] = None


@dataclass
class MyDerived(MyClass):
    d: int = 0


@dataclass
class MyGeneric(Generic[T_bound]):
    a: T_bound


NewString = NewType("NewString", str)
NewList = NewType("NewList", List[str])


def my_func(a, b: int, c: Optional["MyClass"] = None, *args: str, d: str = "a", **kwargs: float) -> int:
    return 1


def my_decorator(t):
    def wrapped(*args, **kwargs):
        return t(*args, **kwargs)

    return wrapped
