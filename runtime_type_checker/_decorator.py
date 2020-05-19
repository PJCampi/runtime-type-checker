from functools import wraps
from inspect import isclass, signature, unwrap

from ._checker import check_type
from .utils import get_func_type_hints

__all__ = ["check_types"]


def check_types(class_or_func):
    """
    Use this decorator to check the type(s) of a class or a function:
    - in case of a class, any instance of the class will be type-checked
    - in case of a function, arguments and return values will
    """

    if isclass(class_or_func):

        @wraps(class_or_func)
        def wrapped(*args, **kwargs):
            instance = class_or_func(*args, **kwargs)
            check_type(instance, class_or_func)
            return instance

    else:
        func = unwrap(class_or_func, stop=lambda f: hasattr(f, "__code__"))
        func_signature = signature(func)
        func_type_hints = get_func_type_hints(func)

        @wraps(class_or_func)
        def wrapped(*args, **kwargs):
            bound_sig = func_signature.bind(*args, **kwargs)
            for name, val in bound_sig.arguments.items():
                try:
                    check_type(val, func_type_hints[name])
                except TypeError as e:
                    raise TypeError(
                        f"Argument: '{name}' of : '{class_or_func}' with value: '{val}' has wrong type."
                    ) from e
            return_value = class_or_func(*args, **kwargs)
            try:
                check_type(return_value, func_type_hints["return"])
            except TypeError as e:
                raise TypeError(
                    f"Return value of : '{class_or_func}' with value: '{return_value}' has wrong type."
                ) from e
            else:
                return return_value

    return wrapped
