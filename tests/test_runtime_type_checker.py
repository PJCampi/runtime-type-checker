try:
    from collections.abc import Sequence as Sequence_co, Callable as Callable_co
except ImportError:
    from collections import Sequence as Sequence_co, Callable as Callable_co
from datetime import datetime
from typing import (
    Any,
    Callable,
    ClassVar,
    Collection,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)

try:
    from typing_extensions import Literal
except ImportError:
    from typing_extensions import _Literal as Literal

import pytest

from runtime_type_checker import check_type, check_types
from runtime_type_checker.utils import get_func_type_hints

from .fixtures import (
    T_bound,
    T_constraint,
    MyClass,
    MyDerived,
    NewList,
    NewString,
    my_func,
    MyTpDict,
    MyGeneric,
    MyGenericImpl,
    PYTHON_38,
)

skip_before_3_8 = pytest.mark.skipif(not PYTHON_38, reason="feature exists only in python 3.8")


@pytest.mark.parametrize(
    "type_or_hint, instance, raises",
    [
        pytest.param(Any, None, False, id="any"),
        pytest.param(None, None, False, id="none"),
        pytest.param(type(None), None, False, id="none__type"),
        pytest.param(Optional[int], 1, False, id="optional"),
        pytest.param(Optional[int], None, False, id="optional__none_value"),
        pytest.param(Union[int, str], "a", False, id="union"),
        pytest.param(Union[int, str], 3.1, True, id="union__wrong_val"),
        pytest.param(Union[List[str], Mapping[str, int]], ["a", "b"], False, id="union__nested"),
        pytest.param(Union[List[str], Mapping[str, int]], {"a": "a"}, True, id="union__nested_wrong_item"),
        pytest.param(Tuple, tuple(), False, id="tuple__no_subscription"),
        pytest.param(Tuple, (3,), False, id="tuple__no_subscription"),
        pytest.param(Tuple[int], (3,), False, id="tuple__single_type"),
        pytest.param(Tuple[int], ("a",), True, id="tuple__wrong_type"),
        pytest.param(Tuple[int], (3, 2), True, id="tuple__wrong_length"),
        pytest.param(Tuple[int, str], (3, "a"), False, id="tuple_variadic"),
        pytest.param(Tuple[int, str], (3, 4), True, id="tuple_variadic__wrong_type"),
        pytest.param(Tuple[int, str], (3, "a", "b"), True, id="tuple_variadic__wrong_length"),
        pytest.param(Tuple[int, ...], tuple(), False, id="tuple_ellipsis__empty"),
        pytest.param(Tuple[int, ...], (3, 4, 5), False, id="tuple_ellipsis__values"),
        pytest.param(Tuple[int, ...], (3, "a"), True, id="tuple_ellipsis__wrong_type"),
        pytest.param(Mapping[str, int], {"a": 1}, False, id="mapping__abstract"),
        pytest.param(Dict[str, int], {"a": 1}, False, id="mapping__concrete"),
        pytest.param(Dict, {"a": 1}, False, id="mapping__non_parametrized"),
        pytest.param(Dict, {"a", 1}, True, id="mapping__non_parametrized_wrong_type"),
        pytest.param(dict, {"a": 1}, False, id="mapping__plain"),
        pytest.param(Dict[str, int], {1: 1}, True, id="mapping__wrong_key"),
        pytest.param(Dict[str, int], {"a": "a"}, True, id="mapping__wrong_key"),
        pytest.param(Collection[str], frozenset(["a", "b"]), False, id="collection__abstract"),
        pytest.param(Collection[str], frozenset(), False, id="collection__abstract_no_item"),
        pytest.param(Sequence[str], ("a", "b", "c"), False, id="collection__tuple"),
        pytest.param(Sequence_co, ["a", "b"], False, id="collection__concrete_sequence"),
        pytest.param(List[str], ["a", "b", "c"], False, id="collection__concrete"),
        pytest.param(List[str], {"a", "b"}, True, id="collection__wrong_type"),
        pytest.param(List[str], ["a", 1, "b"], True, id="collection__wrong_item"),
        pytest.param(List[List["MyClass"]], [[MyClass()]], False, id="collection__nested"),
        pytest.param(List, ["a", 1], False, id="collection__non_parametrized"),
        pytest.param(list, ["a", 1], False, id="collection__plain"),
        pytest.param(T_bound, datetime(2020, 1, 1), False, id="type_variable__bound_date"),
        pytest.param(T_bound, "2020__01__01", False, id="type_variable__bound_str"),
        pytest.param(T_bound, 1, True, id="type_variable__bound_int"),
        pytest.param(T_constraint, datetime(2020, 1, 1), False, id="type_variable__constraint_date"),
        pytest.param(T_constraint, None, False, id="type_variable__constraint_none"),
        pytest.param(T_constraint, 1, False, id="type_variable__int"),
        pytest.param(T_constraint, None, False, id="type_variable__none"),
        pytest.param(T_constraint, [1], True, id="type_variable__none"),
        pytest.param("int", 1, False, id="forward_reference__literal"),
        pytest.param("MyClass", MyClass(), False, id="forward_reference__class"),
        pytest.param(NewString, NewString("1"), False, id="new_type"),
        pytest.param(str, NewString("1"), False, id="new_type__string"),
        pytest.param(NewList, NewList(["1"]), False, id="new_type__nested"),
        pytest.param(ClassVar[int], MyClass.t, False, id="ClassVar"),
        pytest.param(Type[int], int, False, id="type"),
        pytest.param(Type[int], 1, True, id="type__wrong_argument"),
        pytest.param(Type["MyClass"], MyClass, False, id="type__forward_ref"),
        pytest.param(Type[Union[List[str], Mapping[str, int]]], list, False, id="type__nested_union"),
        pytest.param(Callable[[int], int], lambda x: 1, False, id="callable"),
        pytest.param(Callable_co, lambda x: 1, False, id="callable__concrete"),
        pytest.param(MyClass, MyClass(2, ("a", "c"), MyClass()), False, id="class"),
        pytest.param(MyDerived, MyDerived(2, d=0), False, id="class__inherited"),
        pytest.param(MyClass, MyDerived(), False, id="class__inherited_from_base"),
        pytest.param(MyClass, 1, True, id="class__wrong_type"),
        pytest.param(MyTpDict, {"a": "a", "b": MyClass()}, False, id="typed_dict", marks=skip_before_3_8),
        pytest.param(
            MyTpDict, {"a": "a", "b": MyClass(), "c": 1}, True, id="typed_dict__extra_key", marks=skip_before_3_8
        ),
        pytest.param(MyTpDict, {"a": "a"}, True, id="typed_dict__too_few_keys", marks=skip_before_3_8),
        pytest.param(MyTpDict, {"a": "a", "b": 2}, True, id="typed_dict__wrong_val_type", marks=skip_before_3_8),
        pytest.param(MyGeneric[str], MyGeneric("a"), False, id="generic"),
        pytest.param(Literal[1, 2, 3], 1, False, id="literal"),
        pytest.param(Literal[1, 2, 3], 4, True, id="literal__wrong_val"),
        pytest.param(Literal[1, 2, 3], "1", True, id="literal__wrong_type"),
    ],
)
def test_type_check(type_or_hint, instance, raises):
    for _ in range(1):
        if raises:
            with pytest.raises(TypeError):
                check_type(instance, type_or_hint)
        else:
            check_type(instance, type_or_hint, is_argument=False)


@pytest.mark.parametrize(
    "func, expected",
    [
        pytest.param(lambda: 1, {"return": Any}, id="empty"),
        pytest.param(
            my_func,
            {
                "a": Any,
                "args": Sequence[str],
                "b": int,
                "c": Optional[MyClass],
                "d": str,
                "kwargs": Mapping[str, float],
                "return": int,
            },
            id="full_function",
        ),
    ],
)
def test_to_type_hints(func, expected):
    assert get_func_type_hints(func) == expected


@pytest.mark.parametrize(
    "kls, args, kwargs, raises",
    [
        pytest.param(MyDerived, tuple(), {}, False, id="no_args"),
        pytest.param(MyDerived, ("a",), {}, True, id="wrong_arg"),
        pytest.param(MyDerived, tuple(), {"c": MyClass(c=MyClass())}, False, id="forward_ref__ok"),
        pytest.param(MyDerived, tuple(), {"c": MyClass(c=MyClass("a")), "d": "str"}, True, id="forward_ref__wrong"),
        pytest.param(MyGeneric, ("1",), {}, False, id="generic"),
        pytest.param(MyGeneric, (1,), {}, True, id="generic__wrong_args"),
        pytest.param(MyGenericImpl, ("1",), {}, False, id="generic_impl"),
        pytest.param(MyGenericImpl, (1,), {}, True, id="generic_impl__wrong_args"),
    ],
)
def test_check_type_with_class(kls, args, kwargs, raises):
    if raises:
        with pytest.raises((TypeError, NotImplementedError)):
            class_with_check = check_types(kls)
            class_with_check(*args, **kwargs)
    else:
        class_with_check = check_types(kls)
        instance = class_with_check(*args, **kwargs)
        assert isinstance(instance, kls)


@pytest.mark.parametrize(
    "func, args, kwargs, raises",
    [
        pytest.param(my_func, ("a", 1, None, "x", "y"), {"n": 1.1}, False, id="all_args"),
        pytest.param(my_func, ("a", 1, MyClass(), 1), {}, True, id="wrong_vararg"),
        pytest.param(my_func, ("a", 1), {"x": 1}, True, id="wrong_kwarg"),
        pytest.param(lambda x: 1, ("a",), {}, False, id="lambda"),
        pytest.param(MyClass().my_method, (1,), {}, False, id="method"),
        pytest.param(MyClass().my_method, ("a",), {}, True, id="method__wrong_arg"),
        pytest.param(MyClass.my_class_method, (1,), {}, False, id="class_method"),
        pytest.param(MyClass.my_class_method, ("a",), {}, True, id="class_method__wrong_arg"),
        pytest.param(MyClass.my_static_method, (1,), {}, False, id="static_method"),
        pytest.param(MyClass.my_static_method, ("a",), {}, True, id="static_method__wrong_arg"),
    ],
)
def test_check_type_with_func(func, args, kwargs, raises):
    func_with_check = check_types(func)
    if raises:
        with pytest.raises(TypeError):
            func_with_check(*args, **kwargs)
    else:
        func_with_check(*args, **kwargs)
