# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint
import re
from collections.abc import Mapping
from functools import reduce
from typing import Any, Literal, Optional, Union

import msgspec
import voluptuous

import taskgraph
from taskgraph.util.keyed_by import evaluate_keyed_by, iter_dot_path

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


def UnionTypes(*types):
    """Use `functools.reduce` to simulate `Union[*allowed_types]` on older
    Python versions.
    """
    return reduce(lambda a, b: Union[a, b], types)


def optionally_keyed_by(*arguments, use_msgspec=False):
    """
    Mark a schema value as optionally keyed by any of a number of fields.

    Args:
        *arguments: Field names followed by the schema
        use_msgspec: If True, return msgspec type hints; if False, return voluptuous validator
    """
    if use_msgspec:
        # msgspec implementation - return type hints
        _type = arguments[-1]
        if _type is object:
            return object
        fields = arguments[:-1]
        bykeys = [Literal[f"by-{field}"] for field in fields]
        return Union[_type, dict[UnionTypes(*bykeys), dict[str, Any]]]
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
    """

    def __init__(self, *args, check=True, **kwargs):
        super().__init__(*args, **kwargs)

        self.check = check
        if not taskgraph.fast and self.check:
            check_schema(self)

    def extend(self, *args, **kwargs):
        schema = super().extend(*args, **kwargs)

        if self.check:
            check_schema(schema)
        # We want twice extend schema to be checked too.
        schema.__class__ = LegacySchema
        return schema

    def _compile(self, schema):
        if taskgraph.fast:
            return
        return super()._compile(schema)

    def __getitem__(self, item):
        return self.schema[item]  # type: ignore


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

        class MySchema(Schema, forbid_unknown_fields=False):
            foo: str
    """

    @classmethod
    def validate(cls, data):
        """Validate data against this schema."""
        if taskgraph.fast:
            return data

        try:
            return msgspec.convert(data, cls)
        except (msgspec.ValidationError, msgspec.DecodeError) as e:
            raise msgspec.ValidationError(str(e))


class IndexSearchOptimizationSchema(Schema):
    """Search the index for the given index namespaces."""

    index_search: list[str]


class SkipUnlessChangedOptimizationSchema(Schema):
    """Skip this task if none of the given file patterns match."""

    skip_unless_changed: list[str]


# Create a class for optimization types to avoid dict union issues
class OptimizationTypeSchema(Schema, forbid_unknown_fields=False):
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


class TaskRefTypeSchema(Schema, forbid_unknown_fields=False):
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
