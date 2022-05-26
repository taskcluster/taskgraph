# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# Imported from
# https://searchfox.org/mozilla-central/rev/c3ebaf6de2d481c262c04bb9657eaf76bf47e2ac/python/mozbuild/mozbuild/util.py#115-127

import unittest

from taskgraph.util.readonlydict import ReadOnlyDict


class TestReadOnlyDict(unittest.TestCase):
    def test_basic(self):
        original = {"foo": 1, "bar": 2}

        test = ReadOnlyDict(original)

        self.assertEqual(original, test)
        self.assertEqual(test["foo"], 1)

        with self.assertRaises(KeyError):
            test["missing"]

        with self.assertRaises(Exception):
            test["baz"] = True

    def test_update(self):
        original = {"foo": 1, "bar": 2}

        test = ReadOnlyDict(original)

        with self.assertRaises(Exception):
            test.update(foo=2)

        self.assertEqual(original, test)

    def test_del(self):
        original = {"foo": 1, "bar": 2}

        test = ReadOnlyDict(original)

        with self.assertRaises(Exception):
            del test["foo"]

        self.assertEqual(original, test)
