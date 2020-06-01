from abc import ABCMeta, abstractmethod
from collections.abc import Mapping as MappingCol, Collection
from contextlib import suppress
from functools import lru_cache, wraps
from inspect import isclass, isfunction, ismethod, signature, unwrap
from typing import Any, Callable, Iterable, Mapping, Tuple, Union, get_type_hints

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
)

from .typing_inspect_extensions import is_valid_type, is_type, is_typed_dict
from .utils import evaluate_forward_reference, get_func_type_hints, type_repr

__all__ = ["check_type", "check_types", "TypeChecker", "USE_CACHING"]

USE_CACHING = True
if USE_CACHING:
    is_valid_type = lru_cache(maxsize=4096)(is_valid_type)
    get_type_hints = lru_cache(maxsize=4096)(get_type_hints)
    evaluate_forward_reference = lru_cache(maxsize=512)(evaluate_forward_reference)
    cache_decorator = lru_cache(maxsize=4096)
else:

    def cache_decorator(f):
        return f


def check_type(instance, type_or_hint, *, is_argument: bool = True) -> None:
    type_checker = TypeChecker.get(type_or_hint, is_argument=is_argument)
    return type_checker.check_type(instance)


def check_types(class_or_func):
    """
    Use this decorator to check the type(s) of a class or a function:
    - in case of a class, any instance of the class will be type-checked
    - in case of a function, arguments and return values will
    """
    if isclass(class_or_func):
        attribute_hints = get_type_hints(class_or_func)
        attribute_checkers = {name: TypeChecker.get(hint) for name, hint in attribute_hints.items()}

        @wraps(class_or_func)
        def wrapped(*args, **kwargs):
            instance = class_or_func(*args, **kwargs)
            for attr_name, checker in attribute_checkers.items():
                val = getattr(instance, attr_name)
                try:
                    checker.check_type(val)
                except TypeError as e:
                    raise TypeError(
                        f"Attribute: '{attr_name}' of instance: '{instance}' with value: '{val}' has wrong type."
                    ) from e
            return instance

    elif isfunction(class_or_func) or ismethod(class_or_func):
        func = unwrap(class_or_func, stop=lambda f: hasattr(f, "__code__"))
        func_signature = signature(func)
        func_type_hints = dict(get_func_type_hints(func))

        # CONSIDER: this does not take well in account TypeVars: you could end up with a return value with a different
        # type as argument, even though they have the same TypeVar.
        return_checker = TypeChecker.get(func_type_hints.pop("return"))
        argument_checkers = {name: TypeChecker.get(hint, is_argument=True) for name, hint in func_type_hints.items()}

        @wraps(class_or_func)
        def wrapped(*args, **kwargs):
            bound_sig = func_signature.bind(*args, **kwargs)
            for name, val in bound_sig.arguments.items():
                try:
                    argument_checkers[name].check_type(val)
                except TypeError as e:
                    raise TypeError(
                        f"Argument: '{name}' of : '{class_or_func}' with value: '{val}' has wrong type."
                    ) from e
            return_value = class_or_func(*args, **kwargs)
            try:
                return_checker.check_type(return_value)
            except TypeError as e:
                raise TypeError(
                    f"Return value of : '{class_or_func}' with value: '{return_value}' has wrong type."
                ) from e
            else:
                return return_value

    else:
        raise NotImplementedError(f"'check_types' is not implemented for: {class_or_func}")

    return wrapped


class TypeChecker(metaclass=ABCMeta):
    def __init__(self, type_):
        self._type = type_
        self._type_repr = type_repr(type_)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self._type_repr})"

    @classmethod
    @cache_decorator
    def get(cls, type_or_hint, *, is_argument: bool = False) -> "TypeChecker":
        # This ensures the validity of the type passed (see typing documentation for info)
        type_or_hint = is_valid_type(type_or_hint, "Invalid type.", is_argument)

        if type_or_hint is Any:
            return AnyTypeChecker()

        if is_type(type_or_hint):
            return TypeTypeChecker.make(type_or_hint, is_argument)

        if is_literal_type(type_or_hint):
            return LiteralTypeChecker.make(type_or_hint, is_argument)

        if is_generic_type(type_or_hint):
            origin = get_origin(type_or_hint)
            if issubclass(origin, MappingCol):
                return MappingTypeChecker.make(type_or_hint, is_argument)

            if issubclass(origin, Collection):
                return CollectionTypeChecker.make(type_or_hint, is_argument)

            # CONSIDER: how to cater for exhaustible generators?
            if issubclass(origin, Iterable):
                raise NotImplementedError("No type-checker is setup for iterables that exhaust.")

            return GenericTypeChecker.make(type_or_hint, is_argument)

        if is_tuple_type(type_or_hint):
            return TupleTypeChecker.make(type_or_hint, is_argument)

        if is_callable_type(type_or_hint):
            return CallableTypeChecker.make(type_or_hint, is_argument)

        if isclass(type_or_hint):
            if is_typed_dict(type_or_hint):
                return TypedDictChecker.make(type_or_hint, is_argument)
            return ConcreteTypeChecker.make(type_or_hint, is_argument)

        if is_union_type(type_or_hint):
            return UnionTypeChecker.make(type_or_hint, is_argument)

        if is_typevar(type_or_hint):
            bound_type = get_bound(type_or_hint)
            if bound_type:
                return cls.get(bound_type)
            constraints = get_constraints(type_or_hint)
            if constraints:
                union_type_checkers = tuple(cls.get(type_) for type_ in constraints)
                return UnionTypeChecker(Union.__getitem__(constraints), union_type_checkers)
            else:
                return AnyTypeChecker()

        if is_new_type(type_or_hint):
            super_type = getattr(type_or_hint, "__supertype__", None)
            if super_type is None:
                raise TypeError(f"No supertype for NewType: {type_or_hint}. This is not allowed.")
            return cls.get(super_type)

        if is_forward_ref(type_or_hint):
            return ForwardTypeChecker.make(type_or_hint, is_argument=is_argument)

        if is_classvar(type_or_hint):
            var_type = get_args(type_or_hint, evaluate=True)[0]
            return cls.get(var_type)

        raise NotImplementedError(f"No {TypeChecker.__qualname__} is available for type or hint: '{type_or_hint}'")

    @classmethod
    @abstractmethod
    def make(cls, type_or_hint, is_argument: bool) -> "TypeChecker":
        raise NotImplementedError()

    @property
    def type(self):
        return self._type

    @abstractmethod
    def check_subclass(self, type_) -> None:
        raise NotImplementedError(f"{type(self).__qualname__} does not implement 'check_subclass'.")

    @abstractmethod
    def check_type(self, instance) -> None:
        raise NotImplementedError(f"{type(self).__qualname__} does not implement 'check_type'.")


class AnyTypeChecker(TypeChecker):
    def __init__(self):
        super().__init__(Any)

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "AnyTypeChecker":
        return cls()

    def check_subclass(self, type_) -> None:
        pass

    def check_type(self, instance) -> None:
        pass


class CallableTypeChecker(TypeChecker):
    def __init__(self, callable_type):
        super().__init__(callable_type)

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "CallableTypeChecker":
        return cls(type_or_hint)

    def check_subclass(self, type_) -> None:
        super().check_subclass(type_)

    def check_type(self, instance) -> None:
        # CONSIDER: beef this check up so it's possible to check the arguments and return types
        if not callable(instance):
            raise TypeError(f"Callable type: {self._type_repr} expects a callable. '{instance}' isn't.")


class CollectionTypeChecker(TypeChecker):
    def __init__(self, collection_type, collection_checker: TypeChecker, item_checker: TypeChecker):
        super().__init__(collection_type)
        self._collection_checker = collection_checker
        self._item_checker = item_checker

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "CollectionTypeChecker":
        origin = get_origin(type_or_hint)
        origin_type_checker = ConcreteTypeChecker(origin)
        item_type = (get_args(type_or_hint, evaluate=True) or (Any,))[0]
        return cls(type_or_hint, origin_type_checker, cls.get(item_type))

    def check_subclass(self, type_) -> None:
        self._collection_checker.check_subclass(type_)

    def check_type(self, instance) -> None:
        self._collection_checker.check_type(instance)
        for item in instance:
            try:
                self._item_checker.check_type(item)
            except TypeError as e:
                raise TypeError(f"Item: '{item}' of collection: '{instance}' has wrong type.") from e


class ConcreteTypeChecker(TypeChecker):
    def __init__(self, concrete_type):
        super().__init__(concrete_type)

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "ConcreteTypeChecker":
        return cls(type_or_hint)

    def check_subclass(self, type_) -> None:
        if not issubclass(type_, self._type):
            raise TypeError(f"Type: '{type_repr(type_)}' is not consistent with expected type: '{self._type_repr}'.")

    def check_type(self, instance) -> None:
        if not isinstance(instance, self._type):
            raise TypeError(
                f"Type: '{type_repr(type(instance))}' is not consistent with expected type: '{self._type_repr}'."
            )


class ForwardTypeChecker(TypeChecker):
    def __init__(self, forward_ref, is_argument: bool):
        super().__init__(forward_ref)
        self._is_argument = is_argument
        self._forward_type_checker = None

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "ForwardTypeChecker":
        return cls(type_or_hint, is_argument)

    def check_subclass(self, type_) -> None:
        return self._get_forward_type_checker(type_).check_subclass(type_)

    def check_type(self, instance) -> None:
        return self._get_forward_type_checker(instance).check_type(instance)

    def _get_forward_type_checker(self, instance_or_type) -> TypeChecker:
        if not self._forward_type_checker:
            if self._type.__forward_evaluated__:
                forward_type = self._type.__forward_value__
            else:
                forward_type = evaluate_forward_reference(self._type, getattr(instance_or_type, "__module__", None))
            self._forward_type_checker = self.get(forward_type, is_argument=self._is_argument)
        return self._forward_type_checker


class LiteralTypeChecker(TypeChecker):
    def __init__(self, literal_type, literal_values):
        super().__init__(literal_type)
        self._literal_values = literal_values

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "LiteralTypeChecker":
        literals_values = get_args(type_or_hint, evaluate=True)
        return cls(type_or_hint, literals_values)

    def check_subclass(self, type_) -> None:
        return super().check_subclass(type_)

    def check_type(self, instance) -> None:
        if instance not in self._literal_values:
            raise TypeError(f"Value: {instance} is not in the list of literals: {self._literal_values}.")


class MappingTypeChecker(TypeChecker):
    def __init__(
        self, mapping_type, mapping_checker: TypeChecker, key_checker: TypeChecker, value_checker: TypeChecker
    ):
        super().__init__(mapping_type)
        self._mapping_checker = mapping_checker
        self._key_checker = key_checker
        self._value_checker = value_checker

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "MappingTypeChecker":
        origin = get_origin(type_or_hint)
        origin_type_checker = ConcreteTypeChecker(origin)
        key_type, value_type = get_args(type_or_hint, evaluate=True) or (Any, Any)
        return cls(type_or_hint, origin_type_checker, cls.get(key_type), cls.get(value_type),)

    def check_subclass(self, type_) -> None:
        self._mapping_checker.check_subclass(type_)

    def check_type(self, instance) -> None:
        self._mapping_checker.check_type(instance)
        for key, val in instance.items():
            try:
                self._key_checker.check_type(key)
            except TypeError as e:
                raise TypeError(f"Key: '{key}' of mapping: '{instance}' has wrong type.") from e

            try:
                self._value_checker.check_type(val)
            except TypeError as e:
                raise TypeError(f"Value: '{val}' of mapping: '{instance}' has wrong type.") from e


class GenericTypeChecker(TypeChecker):
    def __init__(self, origin_type, origin_checker: TypeChecker):
        super().__init__(origin_type)
        self._origin_checker = origin_checker

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "GenericTypeChecker":
        origin = get_origin(type_or_hint)
        origin_type_checker = ConcreteTypeChecker.make(origin, is_argument)
        # CONSIDER: how do we ensure that the bound type or constraints are respected by the type?
        return cls(type_or_hint, origin_type_checker)

    def check_subclass(self, type_) -> None:
        return self._check(self._origin_checker.check_subclass, type_)

    def check_type(self, instance) -> None:
        return self._check(self._origin_checker.check_type, instance)

    def _check(self, check_function: Callable[[Any], None], instance_or_type):
        try:
            return check_function(instance_or_type)
        except TypeError:
            raise
        except Exception as e:
            raise NotImplementedError(
                f"I could not check: '{instance_or_type}' with generic type hint: '{self._type_repr}'"
            ) from e


class TupleTypeChecker(TypeChecker):
    def __init__(self, tuple_type, tuple_checker: TypeChecker, item_checkers: Tuple[TypeChecker, ...]):
        super().__init__(tuple_type)
        self._tuple_checker = tuple_checker
        self._item_checkers = item_checkers

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> Union[CollectionTypeChecker, "TupleTypeChecker"]:
        tuple_type_checker = ConcreteTypeChecker(tuple)

        args = get_args(type_or_hint, evaluate=True)
        len_args = len(args)

        if len_args == 2 and args[1] is Ellipsis:
            return CollectionTypeChecker(type_or_hint, tuple_type_checker, cls.get(args[0]))

        checkers = tuple(cls.get(item_type) for item_type in args)
        return cls(type_or_hint, tuple_type_checker, checkers)

    def check_subclass(self, type_) -> None:
        return self._tuple_checker.check_subclass(type_)

    def check_type(self, instance) -> None:
        self._tuple_checker.check_type(instance)

        len_instance, len_args = len(instance), len(self._item_checkers)
        if not len_args:
            if len_instance > 1:
                raise TypeError(f"'Tuple' expects a tuple of len: 1. " f"Tuple: '{instance}' has len: {len_instance}.")
            return

        if len(instance) != len(self._item_checkers):
            raise TypeError(
                f"'{self._type_repr}' expects a tuple of len: {len_args}. "
                f"Tuple: '{instance}' has len: {len_instance}."
            )

        for i, (checker, item) in enumerate(zip(self._item_checkers, instance)):
            try:
                checker.check_type(item)
            except TypeError as e:
                raise TypeError(f"Item: {i} of tuple: '{instance}' with value: '{item}' has wrong type.") from e


class TypeTypeChecker(TypeChecker):
    def __init__(self, type_type, type_checker: TypeChecker):
        super().__init__(type_type)
        self._type_checker = type_checker

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "TypeTypeChecker":
        var_type = get_args(type_or_hint, evaluate=True)[0]
        return cls(type_or_hint, cls.get(var_type))

    def check_subclass(self, type_) -> None:
        return super().check_subclass(type_)

    def check_type(self, instance) -> None:
        return self._type_checker.check_subclass(instance)


class TypedDictChecker(TypeChecker):
    def __init__(self, typed_dict_type, dict_checker: TypeChecker, attribute_checkers: Mapping[str, TypeChecker]):
        super().__init__(typed_dict_type)
        self._dict_checker = dict_checker
        self._attribute_checkers = attribute_checkers

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "TypedDictChecker":
        attribute_hints = get_type_hints(type_or_hint)
        attribute_checkers = {name: cls.get(hint) for name, hint in attribute_hints.items()}
        dict_checker = ConcreteTypeChecker(dict)
        return cls(type_or_hint, dict_checker, attribute_checkers)

    def check_subclass(self, type_) -> None:
        return self._dict_checker.check_subclass(type_)

    def check_type(self, instance) -> None:
        instance_keys, typed_dict_keys = instance.keys(), self._attribute_checkers.keys()

        unknown_keys = instance_keys - typed_dict_keys
        if unknown_keys:
            raise TypeError(
                f"Keys: '{list(unknown_keys)}' of dict: {instance} are not part of typed dict: '{self._type_repr}'."
            )

        if getattr(self._type, "__total__", True):
            missing_keys = typed_dict_keys - instance_keys
            if missing_keys:
                raise TypeError(
                    f"Keys: '{list(missing_keys)}' of typed dict: '{self._type_repr}' are not set in '{instance}'."
                )

        for name, checker in self._attribute_checkers.items():
            val = instance[name]
            try:
                checker.check_type(val)
            except TypeError as e:
                raise TypeError(f"Key: '{name}' of TypedDict: '{instance}' with value: '{val}' has wrong type.") from e


class UnionTypeChecker(TypeChecker):
    def __init__(self, union_type, type_checkers: Tuple[TypeChecker, ...]):
        super().__init__(union_type)
        self._type_checkers = type_checkers

    @classmethod
    def make(cls, type_or_hint, is_argument: bool) -> "UnionTypeChecker":
        union_types = get_args(type_or_hint, evaluate=True)
        union_type_checkers = tuple(cls.get(type_) for type_ in union_types)
        return cls(type_or_hint, union_type_checkers)

    def check_subclass(self, type_) -> None:
        return self._iterate_checks((ckr.check_subclass for ckr in self._type_checkers), type_, False)

    def check_type(self, instance) -> None:
        return self._iterate_checks((ckr.check_type for ckr in self._type_checkers), instance, True)

    def _iterate_checks(
        self, check_functions: Iterable[Callable[[Any], None]], instance_or_type, instance_check: bool
    ) -> None:
        for check_function in check_functions:
            with suppress(TypeError):
                return check_function(instance_or_type)
        raise TypeError(
            f"{'Instance of' if instance_check else 'Type'}: "
            f"'{instance_or_type}' does not belong to: {self._type_repr}."
        )
