# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import gc

import pytest

from taskgraph.util.memory import gc_disabled


@pytest.fixture
def restore_gc():
    was_enabled = gc.isenabled()
    yield
    if was_enabled:
        gc.enable()
    else:
        gc.disable()


def test_gc_disabled(restore_gc):
    gc.enable()
    with gc_disabled():
        assert not gc.isenabled()
    assert gc.isenabled()

    with pytest.raises(RuntimeError):
        with gc_disabled():
            raise RuntimeError()
    assert gc.isenabled()


def test_gc_disabled_keeps_disabled(restore_gc):
    gc.disable()
    with gc_disabled():
        assert not gc.isenabled()
    assert not gc.isenabled()
