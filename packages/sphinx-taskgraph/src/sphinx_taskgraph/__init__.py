# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Sphinx extension for rendering taskgraph schemas using autodoc with custom formatting.
"""

from importlib.metadata import version


def setup(app):
    """
    Entry point for the Sphinx extension.
    """
    from .autoschema import (  # noqa: PLC0415
        process_docstring,
        process_signature,
        skip_member,
    )

    app.setup_extension("sphinx.ext.autodoc")
    app.connect("autodoc-process-docstring", process_docstring)
    app.connect("autodoc-process-signature", process_signature)
    app.connect("autodoc-skip-member", skip_member)

    # Return metadata about the extension.
    return {
        "version": version("sphinx-taskgraph"),
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
