# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest
from typing import Optional

import msgspec
import pytest

import taskgraph
from taskgraph.util.schema import (
    IndexSchema,
    Schema,
    SchemaValidationError,
    optionally_keyed_by,
    resolve_keyed_by,
    validate_schema,
)


class SampleSchema(Schema):
    x: int
    y: str


class TestSchemaValidationError(unittest.TestCase):
    """Schema validation errors use a dedicated class so callers can display
    the message without a full Python traceback."""

    def test_valid(self):
        validate_schema(SampleSchema, {"x": 10, "y": "foo"}, "pfx")

    def test_msgspec_schema_raises_schema_validation_error(self):
        with self.assertRaises(SchemaValidationError):
            validate_schema(SampleSchema, {"x": "not-int"}, "pfx")

    def test_dict_schema_raises_schema_validation_error(self):
        with self.assertRaises(SchemaValidationError):
            validate_schema({"name": str}, {"name": 123}, "pfx")

    def test_exception_chain_suppressed(self):
        """validate_schema uses `raise ... from None` so the underlying
        msgspec/voluptuous error doesn't show up as 'During handling of ...'"""
        try:
            validate_schema(SampleSchema, {"x": 1, "y": "a", "extra": True}, "pfx")
        except SchemaValidationError as exc:
            self.assertIsNone(exc.__cause__)
            self.assertTrue(exc.__suppress_context__)
        else:
            self.fail("no exception raised")

    def test_message_contains_prefix_and_object(self):
        try:
            validate_schema(SampleSchema, {"x": "not-int", "y": "a"}, "my-prefix")
        except SchemaValidationError as exc:
            msg = str(exc)
            self.assertTrue(msg.startswith("my-prefix\n"))
            self.assertIn("'x': 'not-int'", msg)
        else:
            self.fail("no exception raised")

    def test_schema_validate_propagates_msgspec_error(self):
        """Schema.validate raises msgspec.ValidationError directly without
        wrapping in an extra try/except."""
        with self.assertRaises(msgspec.ValidationError) as cm:
            SampleSchema.validate({"x": 1, "y": "a", "extra": True})
        # The redundant try/except that re-raised was removed, so there should
        # be no chained context exception.
        self.assertIsNone(cm.exception.__context__)


class TestSchemaFeatures(unittest.TestCase):
    def test_kebab_rename(self):
        """Schema renames snake_case fields to kebab-case."""
        result = msgspec.convert({"my-field": 42}, MyFieldSchema)
        assert result.my_field == 42

    def test_forbid_unknown_fields(self):
        """Schema rejects unknown fields by default."""
        with self.assertRaises((msgspec.ValidationError, msgspec.DecodeError)):
            msgspec.convert({"x": 1, "y": "a", "z": True}, SampleSchema)

    def test_allow_unknown_fields(self):
        """Schema with forbid_unknown_fields=False allows extra fields."""

        class OpenSchema(Schema, forbid_unknown_fields=False):
            x: int

        result = msgspec.convert({"x": 1, "extra": "ok"}, OpenSchema)
        assert result.x == 1


class MyFieldSchema(Schema):
    my_field: int


def test_validation_skipped(monkeypatch):
    """Validation is skipped when taskgraph.fast is True."""
    monkeypatch.setattr(taskgraph, "fast", True)
    # Pass invalid data — should not raise because validation is skipped
    validate_schema(SampleSchema, {"x": "not-int"}, "pfx")


class TestResolveKeyedBy(unittest.TestCase):
    def test_no_by(self):
        self.assertEqual(resolve_keyed_by({"x": 10}, "z", "n"), {"x": 10})

    def test_no_by_dotted(self):
        self.assertEqual(
            resolve_keyed_by({"x": {"y": 10}}, "x.z", "n"), {"x": {"y": 10}}
        )

    def test_no_by_not_dict(self):
        self.assertEqual(resolve_keyed_by({"x": 10}, "x.y", "n"), {"x": 10})

    def test_no_by_not_by(self):
        self.assertEqual(resolve_keyed_by({"x": {"a": 10}}, "x", "n"), {"x": {"a": 10}})

    def test_nested(self):
        x = {
            "by-foo": {
                "F1": {
                    "by-bar": {
                        "B1": 11,
                        "B2": 12,
                    },
                },
                "F2": 20,
                "default": 0,
            },
        }
        self.assertEqual(
            resolve_keyed_by({"x": x}, "x", "x", foo="F1", bar="B1"), {"x": 11}
        )
        self.assertEqual(
            resolve_keyed_by({"x": x}, "x", "x", foo="F1", bar="B2"), {"x": 12}
        )
        self.assertEqual(resolve_keyed_by({"x": x}, "x", "x", foo="F2"), {"x": 20})
        self.assertEqual(
            resolve_keyed_by({"x": x}, "x", "x", foo="F99", bar="B1"), {"x": 0}
        )

        # bar is deferred
        self.assertEqual(
            resolve_keyed_by({"x": x}, "x", "x", defer=["bar"], foo="F1", bar="B1"),
            {"x": {"by-bar": {"B1": 11, "B2": 12}}},
        )

    def test_list(self):
        item = {
            "y": {
                "by-foo": {
                    "F1": 10,
                    "F2": 20,
                },
            }
        }
        self.assertEqual(
            resolve_keyed_by({"x": [item, item]}, "x[].y", "name", foo="F1"),
            {"x": [{"y": 10}, {"y": 10}]},
        )

    def test_no_by_empty_dict(self):
        self.assertEqual(resolve_keyed_by({"x": {}}, "x", "n"), {"x": {}})

    def test_no_by_not_only_by(self):
        self.assertEqual(
            resolve_keyed_by({"x": {"by-y": True, "a": 10}}, "x", "n"),
            {"x": {"by-y": True, "a": 10}},
        )

    def test_match_nested_exact(self):
        self.assertEqual(
            resolve_keyed_by(
                {
                    "f": "shoes",
                    "x": {"y": {"by-f": {"shoes": "feet", "gloves": "hands"}}},
                },
                "x.y",
                "n",
            ),
            {"f": "shoes", "x": {"y": "feet"}},
        )

    def test_match_regexp(self):
        self.assertEqual(
            resolve_keyed_by(
                {
                    "f": "shoes",
                    "x": {"by-f": {"s?[hH]oes?": "feet", "gloves": "hands"}},
                },
                "x",
                "n",
            ),
            {"f": "shoes", "x": "feet"},
        )

    def test_match_partial_regexp(self):
        self.assertEqual(
            resolve_keyed_by(
                {"f": "shoes", "x": {"by-f": {"sh": "feet", "default": "hands"}}},
                "x",
                "n",
            ),
            {"f": "shoes", "x": "hands"},
        )

    def test_match_default(self):
        self.assertEqual(
            resolve_keyed_by(
                {"f": "shoes", "x": {"by-f": {"hat": "head", "default": "anywhere"}}},
                "x",
                "n",
            ),
            {"f": "shoes", "x": "anywhere"},
        )

    def test_match_extra_value(self):
        self.assertEqual(
            resolve_keyed_by({"f": {"by-foo": {"x": 10, "y": 20}}}, "f", "n", foo="y"),
            {"f": 20},
        )

    def test_no_match(self):
        self.assertRaises(
            Exception,
            resolve_keyed_by,
            {"f": "shoes", "x": {"by-f": {"hat": "head"}}},
            "x",
            "n",
        )

    def test_multiple_matches(self):
        self.assertRaises(
            Exception,
            resolve_keyed_by,
            {"f": "hats", "x": {"by-f": {"hat.*": "head", "ha.*": "hair"}}},
            "x",
            "n",
        )

        self.assertEqual(
            resolve_keyed_by(
                {"f": "hats", "x": {"by-f": {"hat.*": "head", "ha.*": "hair"}}},
                "x",
                "n",
                enforce_single_match=False,
            ),
            {"f": "hats", "x": "head"},
        )

    def test_no_key_no_default(self):
        """
        When the key referenced in `by-*` doesn't exist, and there is not default value,
        an exception is raised.
        """
        self.assertRaises(
            Exception,
            resolve_keyed_by,
            {"x": {"by-f": {"hat.*": "head", "ha.*": "hair"}}},
            "x",
            "n",
        )

    def test_no_key(self):
        """
        When the key referenced in `by-*` doesn't exist, and there is a default value,
        that value is used as the result.
        """
        self.assertEqual(
            resolve_keyed_by(
                {"x": {"by-f": {"hat": "head", "default": "anywhere"}}},
                "x",
                "n",
            ),
            {"x": "anywhere"},
        )


class TestNestedStructFieldsOptional(unittest.TestCase):
    """Regression test: bare keys in nested voluptuous dict schemas were optional
    by default. The msgspec migration must preserve this — nested struct fields
    without defaults should not be required."""

    def test_index_schema_accepts_partial_fields(self):
        """IndexSchema should accept data with only 'type', omitting product/job-name."""

        validate_schema(
            IndexSchema,
            {"type": "custom-index"},
            "index schema",
        )

    def test_index_schema_accepts_all_fields(self):
        """IndexSchema should still accept full data."""

        validate_schema(
            IndexSchema,
            {
                "type": "generic",
                "product": "firefox",
                "job-name": "build",
                "rank": "by-tier",
            },
            "index schema",
        )


class TestValidateSchemaDictHandler(unittest.TestCase):
    """validate_schema must accept plain dict schemas passed
    by downstream payload builders without raising TypeError."""

    def test_dict_schema_valid(self):
        validate_schema({"name": str, "count": int}, {"name": "a", "count": 1}, "pfx")

    def test_dict_schema_invalid(self):
        with self.assertRaises(Exception):
            validate_schema({"name": str}, {"name": 123}, "pfx")


def test_optionally_keyed_by():
    class TestSchema(Schema):
        field: optionally_keyed_by("foo", str, use_msgspec=True)  # type: ignore

    TestSchema.validate({"field": "baz"})
    TestSchema.validate({"field": {"by-foo": {"a": "b", "c": "d"}}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": 1})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-bar": "a"}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-bar": {1: "b"}}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-bar": {"a": "b"}}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-foo": {"a": 1, "c": "d"}}})


def test_optionally_keyed_by_multiple_keys():
    class TestSchema(Schema):
        field: optionally_keyed_by("foo", "bar", str, use_msgspec=True)  # type: ignore

    TestSchema.validate({"field": {"by-foo": {"a": "b"}}})
    TestSchema.validate({"field": {"by-bar": {"x": "y"}}})
    TestSchema.validate({"field": {"by-foo": {"a": {"by-bar": {"x": "y"}}}}})

    # Test invalid keyed-by field
    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-unknown": {"a": "b"}}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-foo": {"a": {"by-bar": {"x": 1}}}}})


def test_optionally_keyed_by_object_passthrough():
    """When the type argument is `object`, optionally_keyed_by returns object directly."""
    typ = optionally_keyed_by("foo", object, use_msgspec=True)
    assert typ is object
    # object accepts anything via msgspec.convert
    assert msgspec.convert("hello", typ) == "hello"
    assert msgspec.convert(42, typ) == 42
    assert msgspec.convert({"by-foo": {"a": "b"}}, typ) == {"by-foo": {"a": "b"}}
    assert msgspec.convert({"arbitrary": "dict"}, typ) == {"arbitrary": "dict"}


def test_optionally_keyed_by_dict():
    class TestSchema(Schema):
        field: optionally_keyed_by("foo", dict[str, str], use_msgspec=True)  # type: ignore

    TestSchema.validate({"field": {"by-foo": {"a": {"x": "y"}}}})
    TestSchema.validate({"field": {"a": "b"}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"a": 1}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-foo": {"a": {"x": 1}}}})

    with pytest.raises(msgspec.ValidationError):
        TestSchema.validate({"field": {"by-foo": {"a": "b"}}})


@pytest.mark.parametrize(
    "fields_dict, data, attr, expected",
    [
        ({"name": str}, {"name": "foo"}, "name", "foo"),
        ({"count": Optional[int]}, {}, "count", None),
        ({"tags": (list, [])}, {}, "tags", []),
        ({"my-field": str}, {"my-field": "bar"}, "my_field", "bar"),
    ],
)
def test_from_dict_valid(fields_dict, data, attr, expected):
    S = Schema.from_dict(fields_dict)
    result = msgspec.convert(data, S)
    assert getattr(result, attr) == expected


@pytest.mark.parametrize(
    "fields_dict, data",
    [
        ({"name": str}, {}),
        ({"my-field": str}, {"my_field": "bar"}),
    ],
)
def test_from_dict_invalid(fields_dict, data):
    S = Schema.from_dict(fields_dict)
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(data, S)


@pytest.mark.parametrize(
    "data, raises",
    [
        ({"a": "x", "b": "y"}, True),
        ({"a": "x"}, False),
        ({}, False),
    ],
)
def test_exclusive(data, raises):
    S = Schema.from_dict(
        {"a": Optional[str], "b": Optional[str]},
        exclusive=[["a", "b"]],
    )
    if raises:
        with pytest.raises(
            (ValueError, msgspec.ValidationError), match="mutually exclusive"
        ):
            msgspec.convert(data, S)
    else:
        msgspec.convert(data, S)
