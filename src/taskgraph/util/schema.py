# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import inspect
import pprint
import re
import threading
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Optional, Union, get_args, get_origin

import msgspec
import voluptuous

import taskgraph
from taskgraph.util.keyed_by import evaluate_keyed_by, iter_dot_path

_schema_creation_lock = threading.RLock()

# Common type definitions that are used across multiple schemas
TaskPriority = Literal[
    "highest", "very-high", "high", "medium", "low", "very-low", "lowest"
]


def validate_schema(schema, obj, msg_prefix):
    """
    Validate that object satisfies schema.  If not, generate a useful exception
    beginning with msg_prefix.

    Args:
        schema: A voluptuous.Schema or msgspec-based StructSchema type
        obj: Object to validate
        msg_prefix: Prefix for error messages
    """
    if taskgraph.fast:
        return

    try:
        # Handle voluptuous Schema
        if isinstance(schema, voluptuous.Schema):
            schema(obj)
        # Handle msgspec-based schemas (StructSchema and its subclasses)
        elif isinstance(schema, type) and issubclass(schema, msgspec.Struct):
            # Check if it's our Struct subclass with validate method
            if issubclass(schema, Schema):
                schema.validate(obj)
            else:
                # Fall back to msgspec.convert for validation
                msgspec.convert(obj, schema)
        # Handle plain Python types (e.g. str, int) via msgspec.convert
        elif isinstance(schema, type):
            msgspec.convert(obj, schema)
        # Handle plain dict schemas (e.g. from downstream payload builders)
        elif isinstance(schema, dict):
            voluptuous.Schema(schema)(obj)
        else:
            raise TypeError(f"Unsupported schema type: {type(schema)}")
    except (
        voluptuous.MultipleInvalid,
        msgspec.ValidationError,
        msgspec.DecodeError,
    ) as exc:
        if isinstance(exc, voluptuous.MultipleInvalid):
            msg = [msg_prefix]
            for error in exc.errors:
                msg.append(str(error))
            raise Exception("\n".join(msg) + "\n" + pprint.pformat(obj))
        else:
            raise Exception(f"{msg_prefix}\n{str(exc)}\n{pprint.pformat(obj)}")


class OptionallyKeyedBy:
    """Metadata class for optionally_keyed_by fields in msgspec schemas."""

    def __init__(self, *fields, wrapped_type):
        self.fields = {f"by-{field}" for field in fields}
        self.wrapped_type = wrapped_type

    def uses_keyed_by(self, obj) -> bool:
        if not isinstance(obj, dict) or len(obj) != 1:
            return False

        key = list(obj)[0]
        if key not in self.fields:
            return False

        return True

    def validate(self, obj) -> None:
        if not self.uses_keyed_by(obj):
            # Not using keyed by, validate directly against wrapped type
            msgspec.convert(obj, self.wrapped_type)
            return

        # First validate the outer keyed-by dict
        msgspec.convert(obj, dict[str, dict])

        # Next validate each inner value. We call self.validate recursively to
        # support nested `by-*` keys.
        keyed_by_dict = list(obj.values())[0]
        for value in keyed_by_dict.values():
            self.validate(value)


def optionally_keyed_by(*arguments, use_msgspec=False):
    """
    Mark a schema value as optionally keyed by any of a number of fields.

    Args:
        *arguments: Field names followed by the schema
        use_msgspec: If True, return msgspec type hints; if False, return voluptuous validator
    """
    if use_msgspec:
        # msgspec implementation - use Annotated[Any, OptionallyKeyedBy]
        _type = arguments[-1]
        if _type is object:
            return object
        fields = arguments[:-1]
        wrapper = OptionallyKeyedBy(*fields, wrapped_type=_type)
        # Annotating Any allows msgspec to accept any value without validation.
        # The actual validation then happens in Schema.__post_init__
        return Annotated[Any, wrapper]
    else:
        # voluptuous implementation - return validator function
        schema = arguments[-1]
        fields = arguments[:-1]

        def validator(obj):
            if isinstance(obj, dict) and len(obj) == 1:
                k, v = list(obj.items())[0]
                if k.startswith("by-") and k[len("by-") :] in fields:
                    res = {}
                    for kk, vv in v.items():
                        try:
                            res[kk] = validator(vv)
                        except voluptuous.Invalid as e:
                            e.prepend([k, kk])
                            raise
                    return res
            return LegacySchema(schema)(obj)

        # set to assist autodoc
        setattr(validator, "schema", schema)
        setattr(validator, "fields", fields)
        return validator


def resolve_keyed_by(
    item, field, item_name, defer=None, enforce_single_match=True, **extra_values
):
    """
    For values which can either accept a literal value, or be keyed by some
    other attribute of the item, perform that lookup and replacement in-place
    (modifying `item` directly).  The field is specified using dotted notation
    to traverse dictionaries.

    For example, given item::

        task:
            test-platform: linux128
            chunks:
                by-test-platform:
                    macosx-10.11/debug: 13
                    win.*: 6
                    default: 12

    a call to `resolve_keyed_by(item, 'task.chunks', item['thing-name'])`
    would mutate item in-place to::

        task:
            test-platform: linux128
            chunks: 12

    The `item_name` parameter is used to generate useful error messages.

    If extra_values are supplied, they represent additional values available
    for reference from by-<field>.

    Items can be nested as deeply as the schema will allow::

        chunks:
            by-test-platform:
                win.*:
                    by-project:
                        ash: ..
                        cedar: ..
                linux: 13
                default: 12

    Args:
        item (dict): Object being evaluated.
        field (str): Name of the key to perform evaluation on.
        item_name (str): Used to generate useful error messages.
        defer (list):
            Allows evaluating a by-* entry at a later time. In the example
            above it's possible that the project attribute hasn't been set yet,
            in which case we'd want to stop before resolving that subkey and
            then call this function again later. This can be accomplished by
            setting `defer=["project"]` in this example.
        enforce_single_match (bool):
            If True (default), each task may only match a single arm of the
            evaluation.
        extra_values (kwargs):
            If supplied, represent additional values available
            for reference from by-<field>.

    Returns:
        dict: item which has also been modified in-place.
    """
    for container, subfield in iter_dot_path(item, field):
        container[subfield] = evaluate_keyed_by(
            value=container[subfield],
            item_name=f"`{field}` in `{item_name}`",
            defer=defer,
            enforce_single_match=enforce_single_match,
            attributes=dict(item, **extra_values),
        )

    return item


# Schemas for YAML files should use dashed identifiers by default.  If there are
# components of the schema for which there is a good reason to use another format,
# they can be excepted here.
EXCEPTED_SCHEMA_IDENTIFIERS = [
    # upstream-artifacts and artifact-map are handed directly to scriptWorker,
    # which expects interCaps
    "upstream-artifacts",
    "artifact-map",
]


def check_schema(schema):
    identifier_re = re.compile(r"^\$?[a-z][a-z0-9-]*$")

    def excepted(item):
        for esi in EXCEPTED_SCHEMA_IDENTIFIERS:
            if isinstance(esi, str):
                if f"[{esi!r}]" in item:
                    return True
            elif esi(item):
                return True
        return False

    def iter(path, sch):
        def check_identifier(path, k):
            if k in (str,) or k in (str, voluptuous.Extra):
                pass
            elif isinstance(k, voluptuous.NotIn):
                pass
            elif isinstance(k, str):
                if not identifier_re.match(k) and not excepted(path):
                    raise RuntimeError(
                        "YAML schemas should use dashed lower-case identifiers, "
                        f"not {k!r} @ {path}"
                    )
            elif isinstance(k, (voluptuous.Optional, voluptuous.Required)):
                check_identifier(path, k.schema)
            elif isinstance(k, (voluptuous.Any, voluptuous.All)):
                for v in k.validators:
                    check_identifier(path, v)
            elif not excepted(path):
                raise RuntimeError(
                    f"Unexpected type in YAML schema: {type(k).__name__} @ {path}"
                )

        if isinstance(sch, Mapping):
            for k, v in sch.items():
                child = f"{path}[{k!r}]"
                check_identifier(child, k)
                iter(child, v)
        elif isinstance(sch, (list, tuple)):
            for i, v in enumerate(sch):
                iter(f"{path}[{i}]", v)
        elif isinstance(sch, voluptuous.Any):
            for v in sch.validators:
                iter(path, v)

    iter("schema", schema.schema)


class LegacySchema(voluptuous.Schema):
    """
    Operates identically to voluptuous.Schema, but applying some taskgraph-specific checks
    in the process.

    voluptuous.Schema's `_compile` method is thread-unsafe. Any usage (whether direct or
    indirect) of it must be protected by a lock.
    """

    def __init__(self, *args, check=True, **kwargs):
        with _schema_creation_lock:
            # this constructor may call `_compile`
            super().__init__(*args, **kwargs)

            self.check = check
            if not taskgraph.fast and self.check:
                check_schema(self)

    def extend(self, *args, **kwargs):
        with _schema_creation_lock:
            # `extend` may create a new Schema object, which may call `_compile`
            schema = super().extend(*args, **kwargs)

            if self.check:
                check_schema(schema)
            # We want twice extend schema to be checked too.
            schema.__class__ = LegacySchema
            return schema

    def _compile(self, schema):
        with _schema_creation_lock:
            if taskgraph.fast:
                return
            return super()._compile(schema)

    def __getitem__(self, item):
        return self.schema[item]  # type: ignore


def _caller_module_name(depth=1):
    frame = inspect.stack()[depth + 1].frame
    return frame.f_globals.get("__name__", "schema")


class Schema(
    msgspec.Struct,
    kw_only=True,
    omit_defaults=True,
    rename="kebab",
    forbid_unknown_fields=True,
):
    """
    Base schema class that extends msgspec.Struct.

    This allows schemas to be defined directly as:

        class MySchema(Schema):
            foo: str
            bar: int = 10

    Instead of wrapping msgspec.Struct types.
    Most schemas use kebab-case renaming by default.

    By default, forbid_unknown_fields is True, meaning extra fields
    will cause validation errors. Child classes can override this by
    setting forbid_unknown_fields=False in their class definition:

        class MySchema(Schema, forbid_unknown_fields=False, kw_only=True):
            foo: str
    """

    def __init_subclass__(cls, exclusive=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if exclusive is not None:
            cls.exclusive = exclusive

    def __post_init__(self):
        if taskgraph.fast:
            return

        # Validate fields that use optionally_keyed_by. We need to validate this
        # manually because msgspec doesn't support union types with multiple
        # dicts. Any fields that use `optionally_keyed_by("foo", dict)` would
        # otherwise raise an exception.
        for field_name, field_type in self.__class__.__annotations__.items():
            origin = get_origin(field_type)
            args = get_args(field_type)

            if (
                origin is not Annotated
                or len(args) < 2
                or not isinstance(args[1], OptionallyKeyedBy)
            ):
                # Not using `optionally_keyed_by`
                continue

            keyed_by = args[1]
            obj = getattr(self, field_name)

            keyed_by.validate(obj)

        # Validate mutually exclusive field groups.
        for group in getattr(self, "exclusive", []):
            set_fields = [f for f in group if getattr(self, f) is not None]
            if len(set_fields) > 1:
                raise ValueError(
                    f"{' and '.join(repr(f) for f in set_fields)} are mutually exclusive"
                )

    @classmethod
    def from_dict(
        cls,
        fields_dict: dict[str, Any],
        name: Optional[str] = None,
        optional: bool = False,
        **kwargs,
    ) -> Union[type[msgspec.Struct], type[Optional[msgspec.Struct]]]:
        """Create a Schema subclass dynamically from a dict of field definitions.

        Each key is a field name and each value is either a type annotation or a
        ``(type, default)`` tuple.  Fields typed as ``Optional[...]`` automatically
        receive a default of ``None`` when no explicit default is provided.

        Usage::

            Schema.from_dict("MySchema", {
                "required_field": str,
                "optional_field": Optional[int],         # default None inferred
                "explicit_default": (list[str], []),     # explicit default
            })

        Keyword arguments are forwarded to ``msgspec.defstruct`` (e.g.
        ``forbid_unknown_fields=False``).
        """
        # Don't use `rename=kebab` by default as we can define kebab case
        # properly in dicts.
        kwargs.setdefault("rename", None)

        # Ensure name and module are set correctly for error messages.
        caller_module = _caller_module_name()
        kwargs.setdefault("module", caller_module)
        name = name or caller_module.rsplit(".", 1)[-1]

        fields = []
        for field_name, field_spec in fields_dict.items():
            python_name = field_name.replace("-", "_")

            if isinstance(field_spec, tuple):
                typ, default = field_spec
            else:
                typ = field_spec
                if get_origin(typ) is Union and type(None) in get_args(typ):
                    default = None
                else:
                    default = msgspec.NODEFAULT

            if field_name != python_name:
                # Use msgspec.field to preserve the kebab-case encoded name.
                # Explicit field names take priority over the struct-level rename.
                fields.append(
                    (python_name, typ, msgspec.field(name=field_name, default=default))
                )
            else:
                fields.append((python_name, typ, default))

        exclusive = kwargs.pop("exclusive", None)
        result = msgspec.defstruct(name or "Schema", fields, bases=(cls,), **kwargs)
        if exclusive:
            result.exclusive = exclusive  # type: ignore[attr-defined]
        return Optional[result] if optional else result  # type: ignore[valid-type]

    @classmethod
    def validate(cls, data):
        """Validate data against this schema."""
        if taskgraph.fast:
            return data

        try:
            msgspec.convert(data, cls)
        except (msgspec.ValidationError, msgspec.DecodeError) as e:
            raise msgspec.ValidationError(str(e))


class IndexSchema(Schema):
    # the name of the product this build produces
    product: Optional[str] = None
    # the names to use for this task in the TaskCluster index
    job_name: Optional[str] = None
    # Type of gecko v2 index to use
    type: str = "generic"
    # The rank that the task will receive in the TaskCluster
    # index.  A newly completed task supersedes the currently
    # indexed task iff it has a higher rank.  If unspecified,
    # 'by-tier' behavior will be used.
    rank: Union[Literal["by-tier", "build_date"], int] = "by-tier"


class TreeherderConfig(Schema):
    # Either a bare symbol, or 'grp(sym)'. Defaults to the
    # uppercased first letter of each section of the kind
    # (delimited by '-') all smooshed together.
    symbol: Optional[str] = None
    # The task kind. Defaults to 'build', 'test', or 'other'
    # based on the kind name.
    kind: Optional[Literal["build", "test", "other"]] = None
    # Tier for this task. Defaults to 1.
    tier: Optional[int] = None
    # Task platform in the form platform/collection, used to
    # set treeherder.machine.platform and
    # treeherder.collection or treeherder.labels Defaults to
    # 'default/opt'.
    platform: Optional[str] = None


class IndexSearchOptimizationSchema(Schema):
    """Search the index for the given index namespaces."""

    index_search: list[str]


class SkipUnlessChangedOptimizationSchema(Schema):
    """Skip this task if none of the given file patterns match."""

    skip_unless_changed: list[str]


# Create a class for optimization types to avoid dict union issues
class OptimizationTypeSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    """Schema that accepts various optimization configurations."""

    index_search: Optional[list[str]] = None
    skip_unless_changed: Optional[list[str]] = None

    def __post_init__(self):
        """Ensure at least one optimization type is provided."""
        if not self.index_search and not self.skip_unless_changed:
            # Allow empty schema for other dict-based optimizations
            pass


OptimizationType = Union[None, OptimizationTypeSchema]


# Task reference types using msgspec
class TaskReferenceSchema(Schema):
    """Reference to another task (msgspec version)."""

    task_reference: str


class ArtifactReferenceSchema(Schema):
    """Reference to a task artifact (msgspec version)."""

    artifact_reference: str


class TaskRefTypeSchema(Schema, forbid_unknown_fields=False, kw_only=True):
    """Schema that accepts either task-reference or artifact-reference (msgspec version)."""

    task_reference: Optional[str] = None
    artifact_reference: Optional[str] = None

    def __post_init__(self):
        """Ensure exactly one reference type is provided."""
        if self.task_reference and self.artifact_reference:
            raise ValueError("Cannot have both task-reference and artifact-reference")
        if not self.task_reference and not self.artifact_reference:
            raise ValueError("Must have either task-reference or artifact-reference")


taskref_or_string_msgspec = Union[str, TaskRefTypeSchema]

OptimizationSchema = voluptuous.Any(
    # always run this task (default)
    None,
    # search the index for the given index namespaces, and replace this task if found
    # the search occurs in order, with the first match winning
    {"index-search": [str]},
    # skip this task if none of the given file patterns match
    {"skip-unless-changed": [str]},
)

# shortcut for a string where task references are allowed
taskref_or_string = voluptuous.Any(
    str,
    {voluptuous.Required("task-reference"): str},
    {voluptuous.Required("artifact-reference"): str},
)
