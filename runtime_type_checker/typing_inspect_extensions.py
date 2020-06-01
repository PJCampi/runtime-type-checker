try:
    from typing import _type_check
except ImportError as e:
    raise NotImplementedError("runtime-type-checker is incompatible with the version of python used.") from e

from typing_inspect import NEW_TYPING, get_origin, is_classvar, is_generic_type

__all__ = ["is_type", "is_typed_dict", "is_valid_type"]


def is_type(type_or_hint) -> bool:
    """
    returns whether the type or hint is a Type typehint
    """
    if not is_generic_type(type_or_hint):
        return False
    if NEW_TYPING:
        return get_origin(type_or_hint) is type
    else:
        return getattr(type_or_hint, "__extra__", None) is type


def is_typed_dict(type_or_hint) -> bool:
    """
    returns whether the type or hint is a TypedDict
    """
    return issubclass(type_or_hint, dict) and hasattr(type_or_hint, "__annotations__")


def is_valid_type(arg, message: str, is_argument: bool = True):
    """
    exposes the _type_check function from typing module that does basic validations of the type
    """
    if NEW_TYPING:
        return _type_check(arg, message, is_argument)
    if is_classvar(arg) and not is_argument:
        return arg
    return _type_check(arg, message)
