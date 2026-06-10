# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Define a collection of custom task-context providers.
# Note: this is stored here instead of where it is used in the
# `task_context` transform to give consumers a chance to register their own
# providers before the `task_context` schema is created.
CUSTOM_CONTEXT_MAP = {}


def custom_context(name):
    def wrapper(func):
        assert name not in CUSTOM_CONTEXT_MAP, (
            f"duplicate custom_context function name {name} ({func} and {CUSTOM_CONTEXT_MAP[name]})"
        )
        CUSTOM_CONTEXT_MAP[name] = func
        return func

    return wrapper
