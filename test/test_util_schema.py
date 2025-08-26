# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

import msgspec
import pytest

import taskgraph
from taskgraph.util.schema import (
    Schema,
    optionally_keyed_by,
    resolve_keyed_by,
    validate_schema,
)


class SimpleTestSchema(Schema, rename=None, omit_defaults=False):
    x: int
    y: str


struct = SimpleTestSchema


class TestValidateSchema(unittest.TestCase):
    def test_valid(self):
        validate_schema(struct, {"x": 10, "y": "foo"}, "pfx")

    def test_invalid(self):
        try:
            validate_schema(struct, {"x": "not-int"}, "pfx")
            self.fail("no exception raised")
        except Exception as e:
            # Our new implementation includes pfx in the error message
            self.assertTrue("pfx" in str(e))


class TestCheckSchema(unittest.TestCase):
    def test_schema(self):
        "Creating a msgspec schema works correctly."

        class CamelCaseSchema(
            Schema, rename=None, omit_defaults=False, forbid_unknown_fields=False
        ):
            camelCase: int

        struct = CamelCaseSchema
        # Test that it validates correctly
        result = struct.validate({"camelCase": 42})
        assert result.camelCase == 42

        with self.assertRaises(msgspec.ValidationError):
            struct.validate({"camelCase": "not-an-int"})

    def test_extend_not_supported(self):
        "Extension is not supported for msgspec schemas."

        class SimpleSchema(
            Schema, rename=None, omit_defaults=False, forbid_unknown_fields=False
        ):
            kebab_case: int

        struct = SimpleSchema
        # Schema classes no longer have extend method
        self.assertFalse(hasattr(struct, "extend"))


def test_check_skipped(monkeypatch):
    """Schema not validated if taskgraph.fast is set."""

    class SimpleSchema(
        Schema, rename=None, omit_defaults=False, forbid_unknown_fields=False
    ):
        value: int

    monkeypatch.setattr(taskgraph, "fast", True)
    struct = SimpleSchema
    # When fast mode is on, validation is skipped
    result = struct.validate({"value": "not-an-int"})  # Should not raise
    assert result == {"value": "not-an-int"}


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


def test_optionally_keyed_by():
    # Test voluptuous behavior (default)
    validator = optionally_keyed_by("foo", str)
    # It returns a validator function
    assert callable(validator)

    # Test msgspec behavior
    type_annotation = optionally_keyed_by("foo", str, use_msgspec=True)

    # Create a struct with this type annotation to test validation
    class TestSchema(Schema, forbid_unknown_fields=False):
        value: type_annotation

    # Test that a simple string is accepted
    result = msgspec.convert({"value": "baz"}, TestSchema)
    assert result.value == "baz"

    # Test that keyed-by structure is accepted and works
    result = msgspec.convert({"value": {"by-foo": {"a": "b", "c": "d"}}}, TestSchema)
    assert result.value == {"by-foo": {"a": "b", "c": "d"}}

    # Test that invalid value types are rejected
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"value": {"by-foo": {"a": 1, "c": "d"}}}, TestSchema)

    # Test that unknown by-keys are rejected due to Literal constraint
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"value": {"by-bar": {"a": "b"}}}, TestSchema)


def test_optionally_keyed_by_mulitple_keys():
    # Test voluptuous behavior (default)
    validator = optionally_keyed_by("foo", "bar", str)
    assert callable(validator)

    # Test msgspec behavior
    type_annotation = optionally_keyed_by("foo", "bar", str, use_msgspec=True)

    # Create a struct with this type annotation to test validation
    class TestSchema(Schema, forbid_unknown_fields=False):
        value: type_annotation

    # Test that a simple string is accepted
    result = msgspec.convert({"value": "baz"}, TestSchema)
    assert result.value == "baz"

    # Test that keyed-by with "foo" is accepted
    result = msgspec.convert({"value": {"by-foo": {"a": "b", "c": "d"}}}, TestSchema)
    assert result.value == {"by-foo": {"a": "b", "c": "d"}}

    # Test that keyed-by with "bar" is accepted
    result = msgspec.convert({"value": {"by-bar": {"x": "y"}}}, TestSchema)
    assert result.value == {"by-bar": {"x": "y"}}

    # Test that invalid value types in by-foo are rejected
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"value": {"by-foo": {"a": 123, "c": "d"}}}, TestSchema)

    # Test that invalid value types in by-bar are rejected
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"value": {"by-bar": {"a": 1}}}, TestSchema)

    # Test that unknown by-keys are rejected due to Literal constraint
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"value": {"by-unknown": {"a": "b"}}}, TestSchema)
