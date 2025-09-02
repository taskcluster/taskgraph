# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import pprint
from typing import List

import msgspec

import taskgraph
from taskgraph.util.keyed_by import evaluate_keyed_by, iter_dot_path


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
            # Use the validate class method for Schema subclasses
            schema.validate(obj)
        elif isinstance(schema, type) and issubclass(schema, msgspec.Struct):
            msgspec.convert(obj, schema)
        else:
            raise TypeError(f"Unsupported schema type: {type(schema)}")
    except (msgspec.ValidationError, msgspec.DecodeError, Exception) as exc:
        raise Exception(f"{msg_prefix}\n{str(exc)}\n{pprint.pformat(obj)}")


def optionally_keyed_by(*arguments):
    """
    Mark a schema value as optionally keyed by any of a number of fields.  The
    schema is the last argument, and the remaining fields are taken to be the
    field names.  For example:

        'some-value': optionally_keyed_by(
            'test-platform', 'build-platform',
            Any('a', 'b', 'c'))

    The resulting schema will allow nesting of `by-test-platform` and
    `by-build-platform` in either order.
    """
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
                    except Exception as e:
                        raise ValueError(f"Error in {k}.{kk}: {str(e)}") from e
                return res
            elif k.startswith("by-"):
                # Unknown by-field
                raise ValueError(f"Unknown key {k}")
        # Validate against the schema
        if isinstance(schema, type) and issubclass(schema, Schema):
            return schema.validate(obj)
        elif schema is str:
            # String validation
            if not isinstance(obj, str):
                raise TypeError(f"Expected string, got {type(obj).__name__}")
            return obj
        elif schema is int:
            # Int validation
            if not isinstance(obj, int):
                raise TypeError(f"Expected int, got {type(obj).__name__}")
            return obj
        elif isinstance(schema, type):
            # Type validation for built-in types
            if not isinstance(obj, schema):
                raise TypeError(f"Expected {schema.__name__}, got {type(obj).__name__}")
            return obj
        elif callable(schema):
            # Other callable validators
            try:
                return schema(obj)
            except:
                raise
        else:
            # Simple type validation
            if not isinstance(obj, schema):
                raise TypeError(
                    f"Expected {getattr(schema, '__name__', str(schema))}, got {type(obj).__name__}"
                )
            return obj

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


class Schema(msgspec.Struct, kw_only=True, omit_defaults=True, rename="kebab"):
    """
    Base schema class that extends msgspec.Struct.

    This allows schemas to be defined directly as:

        class MySchema(Schema):
            foo: str
            bar: int = 10

    Instead of wrapping msgspec.Struct types.
    Most schemas use kebab-case renaming by default.
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


# Optimization schema types using msgspec
class IndexSearchOptimization(Schema):
    """Search the index for the given index namespaces."""

    index_search: List[str]


class SkipUnlessChangedOptimization(Schema):
    """Skip this task if none of the given file patterns match."""

    skip_unless_changed: List[str]


# Task reference types using msgspec
class TaskReference(Schema):
    """Reference to another task."""

    task_reference: str


class ArtifactReference(Schema):
    """Reference to a task artifact."""

    artifact_reference: str


# Create a custom validator
class OptimizationValidator:
    """A validator that can validate optimization schemas."""

    def __call__(self, value):
        """Validate optimization value."""
        if value is None:
            return None
        if isinstance(value, dict):
            if "index-search" in value:
                try:
                    return msgspec.convert(value, IndexSearchOptimization)
                except msgspec.ValidationError:
                    pass
            if "skip-unless-changed" in value:
                try:
                    return msgspec.convert(value, SkipUnlessChangedOptimization)
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


class TaskRefValidator:
    """A validator that can validate task references."""

    def __call__(self, value):
        """Validate task reference value."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            if "task-reference" in value:
                try:
                    return msgspec.convert(value, TaskReference)
                except msgspec.ValidationError:
                    pass
            if "artifact-reference" in value:
                try:
                    return msgspec.convert(value, ArtifactReference)
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


# Keep the same names for backward compatibility
OptimizationSchema = OptimizationValidator()
taskref_or_string = TaskRefValidator()
