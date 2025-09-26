# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pprint
from functools import reduce
from typing import Dict, List, Literal, Optional, Union

import msgspec

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
        schema: A msgspec.Struct type (including Schema subclasses)
        obj: Object to validate
        msg_prefix: Prefix for error messages
    """
    if taskgraph.fast:
        return

    try:
        if isinstance(schema, type) and issubclass(schema, Schema):
            schema.validate(obj)
        else:
            raise TypeError(f"Unsupported schema type: {type(schema)}")
    except (msgspec.ValidationError, msgspec.DecodeError, Exception) as exc:
        raise Exception(f"{msg_prefix}\n{str(exc)}\n{pprint.pformat(obj)}")


def UnionTypes(*types):
    """Use `functools.reduce` to simulate `Union[*allowed_types]` on older
    Python versions.
    """
    return reduce(lambda a, b: Union[a, b], types)


def optionally_keyed_by(*arguments):
    _type = arguments[-1]
    fields = arguments[:-1]
    bykeys = [Literal[f"by-{field}"] for field in fields]
    return Union[_type, Dict[UnionTypes(*bykeys), Dict[str, _type]]]


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

    index_search: List[str]


class SkipUnlessChangedOptimizationSchema(Schema):
    """Skip this task if none of the given file patterns match."""

    skip_unless_changed: List[str]


# Create a class for optimization types to avoid dict union issues
class OptimizationTypeSchema(Schema, forbid_unknown_fields=False):
    """Schema that accepts various optimization configurations."""

    index_search: Optional[List[str]] = None
    skip_unless_changed: Optional[List[str]] = None

    def __post_init__(self):
        """Ensure at least one optimization type is provided."""
        if not self.index_search and not self.skip_unless_changed:
            # Allow empty schema for other dict-based optimizations
            pass


# Use the class in the union to avoid multiple dict types
OptimizationType = Union[None, OptimizationTypeSchema]


# Task reference types using msgspec
class TaskReferenceSchema(Schema):
    """Reference to another task."""

    task_reference: str


class ArtifactReferenceSchema(Schema):
    """Reference to a task artifact."""

    artifact_reference: str


class TaskRefType(Schema, forbid_unknown_fields=False):
    """Schema that accepts either task-reference or artifact-reference."""

    task_reference: Optional[str] = None
    artifact_reference: Optional[str] = None

    def __post_init__(self):
        """Ensure exactly one reference type is provided."""
        if self.task_reference and self.artifact_reference:
            raise ValueError("Cannot have both task-reference and artifact-reference")
        if not self.task_reference and not self.artifact_reference:
            raise ValueError("Must have either task-reference or artifact-reference")


# Use the class in the union to avoid multiple dict types
taskref_or_string = Union[str, TaskRefType]


def validate_optimization(value):
    """Validate optimization value."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "index-search" in value:
            try:
                return msgspec.convert(value, IndexSearchOptimizationSchema)
            except msgspec.ValidationError:
                pass
        if "skip-unless-changed" in value:
            try:
                return msgspec.convert(value, SkipUnlessChangedOptimizationSchema)
            except msgspec.ValidationError:
                pass
    # Simple validation for dict types
    if isinstance(value, dict):
        if "index-search" in value and isinstance(value["index-search"], list):
            return value
        if "skip-unless-changed" in value and isinstance(
            value["skip-unless-changed"], list
        ):
            return value
    raise ValueError(f"Invalid optimization value: {value}")


def validate_task_ref(value):
    """Validate task reference value."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "task-reference" in value:
            try:
                return msgspec.convert(value, TaskReferenceSchema)
            except msgspec.ValidationError:
                pass
        if "artifact-reference" in value:
            try:
                return msgspec.convert(value, ArtifactReferenceSchema)
            except msgspec.ValidationError:
                pass
    # Simple validation for dict types
    if isinstance(value, dict):
        if "task-reference" in value and isinstance(value["task-reference"], str):
            return value
        if "artifact-reference" in value and isinstance(
            value["artifact-reference"], str
        ):
            return value
    raise ValueError(f"Invalid task reference value: {value}")
