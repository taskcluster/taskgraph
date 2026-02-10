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


class SampleSchema(Schema):
    x: int
    y: str


class TestValidateSchema(unittest.TestCase):
    def test_valid(self):
        validate_schema(SampleSchema, {"x": 10, "y": "foo"}, "pfx")

    def test_invalid(self):
        try:
            validate_schema(SampleSchema, {"x": "not-int"}, "pfx")
            self.fail("no exception raised")
        except Exception as e:
            self.assertTrue(str(e).startswith("pfx\n"))


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


def test_optionally_keyed_by():
    typ = optionally_keyed_by("foo", str, use_msgspec=True)
    assert msgspec.convert("baz", typ) == "baz"
    assert msgspec.convert({"by-foo": {"a": "b", "c": "d"}}, typ) == {
        "by-foo": {"a": "b", "c": "d"}
    }

    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"by-foo": {"a": 1, "c": "d"}}, typ)

    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"by-bar": {"a": "b"}}, typ)


def test_optionally_keyed_by_mulitple_keys():
    typ = optionally_keyed_by("foo", "bar", str, use_msgspec=True)
    assert msgspec.convert("baz", typ) == "baz"
    assert msgspec.convert({"by-foo": {"a": "b", "c": "d"}}, typ) == {
        "by-foo": {"a": "b", "c": "d"}
    }
    assert msgspec.convert({"by-bar": {"x": "y"}}, typ) == {"by-bar": {"x": "y"}}

    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"by-foo": {"a": 123, "c": "d"}}, typ)

    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"by-bar": {"a": 1}}, typ)

    with pytest.raises(msgspec.ValidationError):
        msgspec.convert({"by-unknown": {"a": "b"}}, typ)
