# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Sphinx extension for rendering taskgraph schemas using autodoc with custom formatting.
"""


def setup(app):
    """
    Entry point for the Sphinx extension.
    """
    from .autoschema import SchemaDocumenter  # noqa: PLC0415

    # Register the custom autodocumenter.
    app.add_autodocumenter(SchemaDocumenter)

    # Return metadata about the extension.
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
