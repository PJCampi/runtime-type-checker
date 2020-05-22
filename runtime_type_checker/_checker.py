"""Main module."""
from collections.abc import Collection, Iterable, Mapping
from contextlib import suppress
from inspect import isclass
from functools import lru_cache
from typing import (
    Any,
    get_type_hints,
    Union,
    _type_check as _base_type_check,
)

from typing_inspect import (
    get_bound,
    is_callable_type,
    is_classvar,
    is_forward_ref,
    is_generic_type,
    is_literal_type,
    is_new_type,
    is_tuple_type,
    is_typevar,
    is_union_type,
    get_args,
    get_constraints,
    get_origin,
    NEW_TYPING,
)

from .utils import evaluate_forward_reference, type_repr

__all__ = [
    "check_type",
]

USE_CACHING = False
if USE_CACHING:
    _base_type_check = lru_cache(maxsize=4096)(_base_type_check)
    get_type_hints = lru_cache(maxsize=4096)(get_type_hints)
    evaluate_forward_reference = lru_cache(maxsize=512)(evaluate_forward_reference)


def check_type(instance, type_or_hint, *, is_argument: bool = True) -> None:
    _check_instance_or_type(instance, type_or_hint, instance_check=True, is_argument=is_argument)


def _check_instance_or_type(
    instance_or_type, type_or_hint, *, instance_check: bool = True, is_argument: bool = True
) -> None:
    # This ensures the validity of the type passed (see typing documentation for info)
    type_or_hint = _type_check(type_or_hint, "Invalid type.", is_argument)

    # NOTE: Any always validate correctly
    if type_or_hint is Any:
        return

    if _is_type(type_or_hint):
        return _check_type(instance_or_type, type_or_hint)

    if is_literal_type(type_or_hint):
        return _check_literal_type(instance_or_type, type_or_hint)

    if is_generic_type(type_or_hint):
        origin = get_origin(type_or_hint)
        if issubclass(origin, Mapping):
            return _check_mapping(instance_or_type, type_or_hint, instance_check=instance_check)
        if issubclass(origin, Collection):
            return _check_collection(instance_or_type, type_or_hint, instance_check=instance_check)
        if issubclass(origin, Iterable):
            raise NotImplementedError("It is currently not possible to cater for iterable that exhaust.")

        try:
            return _check_concrete_type(instance_or_type, origin, instance_check=instance_check)
        except TypeError:
            raise
        except Exception as e:
            raise NotImplementedError(
                f"I could not check: '{instance_or_type}' with generic type hint: '{type_or_hint}'"
            ) from e

    if is_tuple_type(type_or_hint):
        return _check_tuple(instance_or_type, type_or_hint, instance_check=instance_check)

    if is_callable_type(type_or_hint):
        return _check_callable(instance_or_type, type_or_hint)

    if isclass(type_or_hint):
        if _is_typed_dict(type_or_hint):
            return _check_typed_dict(instance_or_type, type_or_hint, instance_check=instance_check)
        return _check_concrete_type(instance_or_type, type_or_hint, instance_check=instance_check)

    if is_union_type(type_or_hint):
        return _check_union(instance_or_type, type_or_hint, instance_check=instance_check)

    if is_typevar(type_or_hint):
        return _check_type_var(instance_or_type, type_or_hint, instance_check=instance_check)

    if is_new_type(type_or_hint):
        return _check_new_type(instance_or_type, type_or_hint, instance_check=instance_check)

    if is_forward_ref(type_or_hint):
        _check_forward_reference(instance_or_type, type_or_hint, instance_check=instance_check)
        return

    if is_classvar(type_or_hint):
        return _check_class_var(instance_or_type, type_or_hint, instance_check=instance_check)

    raise NotImplementedError(f"I could not check: '{instance_or_type}' with type or hint: '{type_or_hint}'")


def _check_callable(instance, callable_type) -> None:
    if not callable(instance):
        raise TypeError(f"Callable type: {type_repr(callable_type)} expects a callable. '{instance}' isn't.")
    # Note: we need to beef up the validation by comparing the arguments of the callable with typehints
    # from the instance


def _check_class_var(instance_or_type, class_var, *, instance_check: bool = True) -> None:
    var_type = get_args(class_var, evaluate=True)[0]
    _check_instance_or_type(instance_or_type, var_type, instance_check=instance_check)


def _check_collection(instance_or_type, collection_type, *, instance_check: bool = True) -> None:
    origin = get_origin(collection_type)
    _check_concrete_type(instance_or_type, origin, instance_check=instance_check)

    if instance_check:
        item_type = (get_args(collection_type, evaluate=True) or (Any,))[0]
        for item in instance_or_type:
            try:
                _check_instance_or_type(item, item_type, instance_check=True)
            except TypeError as e:
                raise TypeError(f"Item: '{item}' of collection: '{instance_or_type}' has wrong type.") from e


def _check_concrete_type(instance_or_type, concrete_type, *, instance_check: bool = True) -> None:
    if not (isinstance if instance_check else issubclass)(instance_or_type, concrete_type):
        raise TypeError(
            f"Type: '{_get_type_repr(instance_or_type, instance_check)}' is not consistent with "
            f"expected type: '{_get_type_repr(concrete_type, False)}'."
        )

    if instance_check:
        type_hints = get_type_hints(concrete_type)
        for name, hint in type_hints.items():
            val = getattr(instance_or_type, name)
            try:
                _check_instance_or_type(val, hint, instance_check=True, is_argument=False)
            except TypeError as e:
                raise TypeError(
                    f"Attribute: '{name}' of instance: '{instance_or_type}' with value: '{val}' has wrong type."
                ) from e


def _check_forward_reference(instance_or_type, forward_reference, *, instance_check: bool = True) -> None:
    forward_type = _get_forward_type(instance_or_type, forward_reference)
    _check_instance_or_type(instance_or_type, forward_type, instance_check=instance_check)


def _check_literal_type(instance_or_type, literal_type) -> None:
    literals = get_args(literal_type, evaluate=True)
    if instance_or_type not in literals:
        raise TypeError(f"Value: {instance_or_type} is not in the list of literals: {literals}.")


def _check_mapping(instance_or_type, mapping_type, *, instance_check: bool = True) -> None:
    origin = get_origin(mapping_type)
    _check_concrete_type(instance_or_type, origin, instance_check=instance_check)

    if instance_check:
        key_type, value_type = get_args(mapping_type, evaluate=True) or (Any, Any)
        for key, val in instance_or_type.items():
            try:
                _check_instance_or_type(key, key_type, instance_check=True)
            except TypeError as e:
                raise TypeError(f"Key: '{key}' of mapping: '{instance_or_type}' has wrong type.") from e

            try:
                _check_instance_or_type(val, value_type, instance_check=True)
            except TypeError as e:
                raise TypeError(f"Value: '{val}' of mapping: '{instance_or_type}' has wrong type.") from e


def _check_new_type(instance_or_type, type_, *, instance_check: bool = True) -> None:
    super_type = getattr(type_, "__supertype__", None)
    if super_type is None:
        raise TypeError(f"No supertype for NewType: {type_}. This is not allowed.")
    return _check_instance_or_type(instance_or_type, super_type, instance_check=instance_check)


def _check_tuple(instance_or_type, tuple_type, *, instance_check: bool = True) -> None:
    _check_concrete_type(instance_or_type, tuple, instance_check=instance_check)

    if instance_check:
        args = get_args(tuple_type, evaluate=True)
        len_instance, len_args = len(instance_or_type), len(args)
        if not len_args:
            if len_instance > 1:
                raise TypeError(
                    f"'Tuple' expects a tuple of len: 1. " f"Tuple: '{instance_or_type}' has len: {len_instance}."
                )
            return

        if len_args == 2 and args[1] is Ellipsis:
            _check_collection(instance_or_type, tuple_type, instance_check=True)
            return

        if len_instance != len_args:
            raise TypeError(
                f"'{tuple_type}' expects a tuple of len: {len_args}. "
                f"Tuple: '{instance_or_type}' has len: {len_instance}."
            )

        for i, (item, item_type) in enumerate(zip(instance_or_type, args)):
            try:
                _check_instance_or_type(item, item_type, instance_check=True)
            except TypeError as e:
                raise TypeError(f"Item: {i} of tuple: '{instance_or_type}' with value: '{item}' has wrong type.") from e


def _check_type(actual_type, expected_type) -> None:
    type_type = get_args(expected_type, evaluate=True)[0]
    _check_instance_or_type(actual_type, type_type, instance_check=False)


def _check_typed_dict(instance_or_type, typed_dict, *, instance_check: bool = True) -> None:
    _check_concrete_type(instance_or_type, dict, instance_check=instance_check)

    if instance_check:

        typed_dict_hints = get_type_hints(typed_dict)
        instance_keys, typed_dict_keys = instance_or_type.keys(), typed_dict_hints.keys()

        unknown_keys = instance_keys - typed_dict_keys
        if unknown_keys:
            raise TypeError(
                f"Keys: '{list(unknown_keys)}' of dict: {instance_or_type} are not part of typed dict: '{typed_dict}'."
            )

        if getattr(typed_dict, "__total__", True):
            missing_keys = typed_dict_keys - instance_keys
            if missing_keys:
                raise TypeError(
                    f"Keys: '{list(missing_keys)}' of typed dict: '{typed_dict}' are not set in '{instance_or_type}'."
                )

        for name, hint in typed_dict_hints.items():
            val = instance_or_type[name]
            try:
                _check_instance_or_type(val, hint, instance_check=True)
            except TypeError as e:
                raise TypeError(
                    f"Key: '{name}' of TypedDict: '{instance_or_type}' with value: '{val}' has wrong type."
                ) from e


def _check_type_var(instance_or_type, type_var, *, instance_check: bool = True) -> None:
    bound_type = get_bound(type_var)
    if bound_type:
        return _check_instance_or_type(instance_or_type, bound_type, instance_check=instance_check)
    constraints = get_constraints(type_var)
    if constraints:
        return _check_instance_or_type(instance_or_type, Union.__getitem__(constraints), instance_check=instance_check)


def _check_union(instance_or_type, union_type, *, instance_check: bool = True) -> None:
    union_types = get_args(union_type, evaluate=True)
    for type_ in union_types:
        with suppress(TypeError):
            return _check_instance_or_type(instance_or_type, type_, instance_check=instance_check)
    raise TypeError(
        f"{'Instance of' if instance_check else 'Type'}: '{instance_or_type}' does not belong to: {union_type!r}."
    )


def _get_forward_type(instance_or_type, forward_reference):
    if not forward_reference.__forward_evaluated__:
        return evaluate_forward_reference(forward_reference, getattr(instance_or_type, "__module__", None))
    return forward_reference.__forward_value__


def _get_type_repr(instance_or_type, is_instance: bool = True) -> str:
    type_ = type(instance_or_type) if is_instance else instance_or_type
    return type_repr(type_)


def _is_type(type_or_hint) -> bool:
    if not is_generic_type(type_or_hint):
        return False
    if NEW_TYPING:
        return get_origin(type_or_hint) is type
    else:
        return getattr(type_or_hint, "__extra__", None) is type


def _is_typed_dict(type_or_hint) -> bool:
    return issubclass(type_or_hint, dict) and hasattr(type_or_hint, "__annotations__")


def _type_check(arg, message: str, is_argument: bool = True):
    if NEW_TYPING:
        return _base_type_check(arg, message, is_argument)
    if is_classvar(arg) and not is_argument:
        return arg
    return _base_type_check(arg, message)
