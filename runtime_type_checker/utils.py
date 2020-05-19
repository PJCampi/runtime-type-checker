from inspect import signature
from types import FunctionType
from typing import Any, Callable, get_type_hints, Mapping, Sequence

__all__ = ["type_repr", "get_func_type_hints"]


def type_repr(type_or_hint) -> str:
    """
    Returns representation of a type. This function was taken verbatim from the typing module.
    """
    if isinstance(type_or_hint, type):
        if type_or_hint.__module__ == "builtins":
            return type_or_hint.__qualname__
        return f"{type_or_hint.__module__}.{type_or_hint.__qualname__}"
    if type_or_hint is ...:
        return "..."
    if isinstance(type_or_hint, FunctionType):
        return type_or_hint.__name__
    return repr(type_or_hint)


def get_func_type_hints(func: Callable[..., Any]) -> Mapping[str, Any]:
    """
    returns a mapping of argument name & "return" (for return value) to type annotation.
    Defaults to Any if no annotation is provided.
    """
    results = {}
    type_hints = get_type_hints(func)
    func_sig = signature(func)
    for name, param in func_sig.parameters.items():
        type_hint = type_hints.get(name, param.annotation)
        annotation = Any if type_hint is param.empty else type_hint
        if param.kind is param.VAR_KEYWORD:
            results[name] = Mapping[str, annotation]
        elif param.kind is param.VAR_POSITIONAL:
            results[name] = Sequence[annotation]
        else:
            results[name] = annotation

    type_hint = type_hints.get("return", func_sig.return_annotation)
    annotation = Any if type_hint is func_sig.empty else type_hint
    results["return"] = annotation
    return results
