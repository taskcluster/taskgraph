# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import pickle

import pytest

from taskgraph.util.readonlydict import ReadOnlyDict


def test_basic():
    original = {"foo": 1, "bar": 2}

    test = ReadOnlyDict(original)

    assert original == test
    assert test["foo"] == 1

    with pytest.raises(KeyError):
        test["missing"]

    with pytest.raises(Exception):
        test["baz"] = True


def test_update():
    original = {"foo": 1, "bar": 2}

    test = ReadOnlyDict(original)

    with pytest.raises(Exception):
        test.update(foo=2)

    assert original == test


def test_del():
    original = {"foo": 1, "bar": 2}

    test = ReadOnlyDict(original)

    with pytest.raises(Exception):
        del test["foo"]

    assert original == test


def test_copy():
    d = ReadOnlyDict(foo="bar")

    d_copy = d.copy()
    assert d == d_copy
    # TODO Returning a dict here feels like a bug, but there are places in-tree
    # relying on this behaviour.
    assert isinstance(d_copy, dict)

    d_copy = copy.copy(d)
    assert d == d_copy
    assert isinstance(d_copy, ReadOnlyDict)

    d_copy = copy.deepcopy(d)
    assert d == d_copy
    assert isinstance(d_copy, ReadOnlyDict)


def test_pickle():
    d = ReadOnlyDict(foo="bar")
    pickle.loads(pickle.dumps(d))
