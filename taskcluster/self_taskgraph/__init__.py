# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from importlib import import_module


def register(graph_config):
    """Setup for task generation."""
    # Import sibling modules, triggering decorators in the process
    _import_modules(
        [
            "custom_parameters",
            "custom_target_tasks",
        ]
    )


def _import_modules(modules):
    for module in modules:
        import_module(f".{module}", package=__name__)
