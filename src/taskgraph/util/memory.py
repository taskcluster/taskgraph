# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import gc
from contextlib import contextmanager


@contextmanager
def gc_disabled():
    """Disable the garbage collector for the duration of the block, restoring
    its previous state afterwards.

    Generating or loading a task graph creates millions of objects that stay
    alive, so collections keep traversing a growing heap without freeing
    anything.
    """
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
