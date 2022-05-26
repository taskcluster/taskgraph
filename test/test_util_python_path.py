# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import sys

import pytest

from taskgraph.util import python_path


@pytest.fixture(scope="module", autouse=True)
def add_datadir_to_sys_path(datadir):
    sys.path.insert(0, str(datadir))


def test_find_object_no_such_module():
    """find_object raises ImportError for a nonexistent module"""
    with pytest.raises(ImportError):
        python_path.find_object("no_such_module:someobj")


def test_find_object_no_such_object():
    """find_object raises AttributeError for a nonexistent object"""
    with pytest.raises(AttributeError):
        python_path.find_object("testmod:NoSuchObject")


def test_find_object_exists():
    """find_object finds an existing object"""
    from testmod.thing import TestObject

    obj = python_path.find_object("testmod.thing:TestObject.testClassProperty")
    assert obj is TestObject.testClassProperty
