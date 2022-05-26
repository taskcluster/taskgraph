# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# Imported from
# https://searchfox.org/mozilla-central/rev/c3ebaf6de2d481c262c04bb9657eaf76bf47e2ac/python/mozbuild/mozbuild/test/test_util.py#584-635

import sys
import unittest

from taskgraph.util.memoize import memoize


class TestMemoize(unittest.TestCase):
    def test_memoize(self):
        self._count = 0

        @memoize
        def wrapped(a, b):
            self._count += 1
            return a + b

        self.assertEqual(self._count, 0)
        self.assertEqual(wrapped(1, 1), 2)
        self.assertEqual(self._count, 1)
        self.assertEqual(wrapped(1, 1), 2)
        self.assertEqual(self._count, 1)
        self.assertEqual(wrapped(2, 1), 3)
        self.assertEqual(self._count, 2)
        self.assertEqual(wrapped(1, 2), 3)
        self.assertEqual(self._count, 3)
        self.assertEqual(wrapped(1, 2), 3)
        self.assertEqual(self._count, 3)
        self.assertEqual(wrapped(1, 1), 2)
        self.assertEqual(self._count, 3)

    def test_memoize_method(self):
        class foo:
            def __init__(self):
                self._count = 0

            @memoize
            def wrapped(self, a, b):
                self._count += 1
                return a + b

        instance = foo()
        refcount = sys.getrefcount(instance)
        self.assertEqual(instance._count, 0)
        self.assertEqual(instance.wrapped(1, 1), 2)
        self.assertEqual(instance._count, 1)
        self.assertEqual(instance.wrapped(1, 1), 2)
        self.assertEqual(instance._count, 1)
        self.assertEqual(instance.wrapped(2, 1), 3)
        self.assertEqual(instance._count, 2)
        self.assertEqual(instance.wrapped(1, 2), 3)
        self.assertEqual(instance._count, 3)
        self.assertEqual(instance.wrapped(1, 2), 3)
        self.assertEqual(instance._count, 3)
        self.assertEqual(instance.wrapped(1, 1), 2)
        self.assertEqual(instance._count, 3)

        # Memoization of methods is expected to not keep references to
        # instances, so the refcount shouldn't have changed after executing the
        # memoized method.
        self.assertEqual(refcount, sys.getrefcount(instance))
