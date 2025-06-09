# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Custom autodoc integration for rendering `taskgraph.util.schema.Schema` instances.
"""

import typing as t
from textwrap import dedent
from types import FunctionType, NoneType

from sphinx.ext.autodoc import ClassDocumenter
from voluptuous import All, Any, Exclusive, Length, Marker, Schema

if t.TYPE_CHECKING:
    from docutils.statemachine import StringList


def name(item: t.Any) -> str:
    if isinstance(item, (bool, int, str, NoneType)):
        return str(item)

    if isinstance(item, (type, FunctionType)):
        return item.__name__

    if isinstance(item, Length):
        return repr(item)

    return item.__class__.__name__


def get_type_str(obj: t.Any) -> tuple[str, bool]:
    # Handle simple subtypes for lists and dicts so that we display
    # `type: dict[str, Any]` inline rather than expanded out at the
    # bottom.
    subtype_str = ""
    if isinstance(obj, (list, Any)):
        items = obj
        if isinstance(items, Any):
            items = items.validators

        if all(not isinstance(i, (list, dict, Any)) for i in items):
            subtype_str = f"[{' | '.join(name(i) for i in items)}]"

    elif isinstance(obj, dict):
        if all(not isinstance(k, (Marker, Any)) for k in obj.keys()) and all(
            not isinstance(v, (list, dict, Any, All)) for v in obj.values()
        ):
            subtype_str = f"[{' | '.join(name(k) for k in obj.keys())}, {' | '.join({name(v) for v in obj.values()})}]"

    return (
        f"{name(obj)}{subtype_str}",
        bool(subtype_str),
    )


def iter_schema_lines(obj: t.Any, indent: int = 0) -> t.Generator[str, None, None]:
    prefix = " " * indent
    arg_prefix = " " * (indent + 2)

    if isinstance(obj, Schema):
        # Display whether extra keys are allowed
        extra = obj._extra_to_name[obj.extra].split("_")[0].lower()
        yield f"{prefix}extra keys: {extra}{'d' if extra[-1] == 'e' else 'ed'}"
        yield ""
        yield from iter_schema_lines(obj.schema, indent)
        return

    if isinstance(obj, dict):
        for i, (key, value) in enumerate(obj.items()):
            subtypes_handled = False

            # Handle optionally_keyed_by
            keyed_by_str = ""
            if isinstance(value, FunctionType):
                keyed_by_str = ", ".join(getattr(value, "fields", ""))
                value = getattr(value, "schema", value)

            # If the key is a marker (aka Required, Optional, Exclusive),
            # display additional information if available, like the
            # description.
            if isinstance(key, Marker):
                # Add marker name and group for Exclusive.
                marker_str = f"{name(key).lower()}"
                if isinstance(key, Exclusive):
                    marker_str += f"={key.group_of_exclusion}"

                # Make it clear if an allowed value must be constant.
                type_ = "type"
                if isinstance(obj, (bool, int, str, NoneType)):
                    type_ = "constant"

                # Create the key header + type lines.
                yield f"{prefix}{key.schema} ({marker_str})"
                type_str, subtypes_handled = get_type_str(value)
                yield f"{arg_prefix}{type_}: {type_str}"

                # Create the keyed-by line if needed.
                if keyed_by_str:
                    yield ""
                    yield f"{arg_prefix}optionally keyed by: {keyed_by_str}"

                # Create the description if needed.
                if desc := getattr(key, "description", None):
                    yield ""
                    yield arg_prefix + f"\n{arg_prefix}".join(
                        dedent(l) for l in desc.splitlines()
                    )

            elif isinstance(key, Any):
                type_str, subtypes_handled = get_type_str(key)
                yield f"{prefix}{type_str}: {name(value)}"

            else:
                # If not a marker, simply create a `key: value` line.
                yield f"{prefix}{name(key)}: {name(value)}"

            yield ""

            # Recurse into values that contain additional schema, unless the
            # types for said containers are simple and we handled them in the
            # type line.
            if isinstance(value, (list, dict, All, Any)) and not subtypes_handled:
                yield from iter_schema_lines(value, indent + 2)

    elif isinstance(obj, (list, All, Any)):
        # Recurse into list, All and Any markers.
        op = "or" if isinstance(obj, (list, Any)) else "and"
        if isinstance(obj, (All, Any)):
            obj = obj.validators

        for i, item in enumerate(obj):
            if i != 0:
                yield ""
                yield f"{prefix}{op}"
                yield ""

            type_, subtypes_handled = get_type_str(item)
            yield f"{arg_prefix}{type_}"
            yield ""

            if isinstance(item, (list, dict, All, Any)) and not subtypes_handled:
                yield from iter_schema_lines(item, indent + 2)
    else:
        # Create line for leaf values.
        yield prefix + name(obj)
        yield ""


class SchemaDocumenter(ClassDocumenter):
    """
    Custom Sphinx autodocumenter for instances of `Schema`.
    """

    # Document only `Schema` instances.
    objtype = "schema"
    directivetype = "class"
    content_indent = "   "

    # Priority over the default ClassDocumenter.
    priority = 10

    @classmethod
    def can_document_member(
        cls, member: object, membername: str, isattr: bool, parent: object
    ) -> bool:
        return isinstance(member, Schema)

    def add_directive_header(self, sig: str) -> None:
        super().add_directive_header(sig)

    def add_content(
        self, more_content: t.Union["StringList", None], no_docstring: bool = False
    ) -> None:
        # Format schema rules recursively.
        for line in iter_schema_lines(self.object):
            self.add_line(line, "")
        self.add_line("", "")
