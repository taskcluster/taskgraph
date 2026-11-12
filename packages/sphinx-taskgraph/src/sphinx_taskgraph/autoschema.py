# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Autodoc integration for rendering msgspec based `taskgraph.util.schema.Schema`
classes.

Rather than relying on autodoc's default rendering (which shows Python
attribute names and the generated ``__init__`` signature), each schema class
gets a list of its fields as they would be written in YAML, along with their
types, defaults and descriptions.

Field descriptions are taken from ``#:`` comments (or attribute docstrings)
preceding each field, which Sphinx extracts from the source.
"""

import json
import sys
import types
import typing as t
from functools import cache
from textwrap import dedent

import msgspec
import sphinx.ext.autodoc as autodoc
from sphinx.errors import PycodeError
from sphinx.pycode import ModuleAnalyzer

try:
    from sphinx.ext.autodoc import _sentinels
except ImportError:  # Sphinx < 9
    _sentinels = None

# Placeholders autodoc passes to `autodoc-skip-member` in place of slotted
# attributes (like Struct fields), depending on the Sphinx version and whether
# the legacy class based implementation is in use.
SLOTS_SENTINELS = tuple(
    obj
    for obj in (
        getattr(_sentinels, "SLOTS_ATTR", None),
        getattr(autodoc, "SLOTSATTR", None),
    )
    if obj is not None
)


# `types.UnionType` (PEP 604 `X | Y` unions) only exists on Python 3.10+.
UNION_TYPES = (t.Union, getattr(types, "UnionType", t.Union))


def is_keyed_by(meta: t.Any) -> bool:
    """Return True if `meta` is a `taskgraph.util.schema.OptionallyKeyedBy`.

    Duck-typed to avoid depending on taskgraph itself.
    """
    return hasattr(meta, "fields") and hasattr(meta, "wrapped_type")


def is_struct(obj: t.Any) -> bool:
    return isinstance(obj, type) and issubclass(obj, msgspec.Struct)


def is_canonical(cls: type) -> bool:
    """Return True if `cls` can be referenced by its own name.

    Classes created dynamically (e.g. via `Schema.from_dict`) are typically
    not importable under their `__name__`, so they can't be cross-referenced
    and need to be rendered inline instead.
    """
    module = sys.modules.get(cls.__module__)
    return module is not None and getattr(module, cls.__qualname__, None) is cls


@cache
def _attr_docs(modname: str) -> dict[tuple[str, str], list[str]]:
    try:
        analyzer = ModuleAnalyzer.for_module(modname)
        return analyzer.find_attr_docs()
    except PycodeError:
        return {}


def field_description(cls: type, name: str) -> list[str]:
    """Return the doc comment lines for field `name` on `cls`.

    Fields may be inherited, so look up the comment on the class that
    actually defines the annotation.
    """
    for base in cls.__mro__:
        if name in base.__dict__.get("__annotations__", {}):
            docs = _attr_docs(base.__module__).get((base.__qualname__, name))
            if docs:
                return dedent("\n".join(docs)).strip("\n").splitlines()
            return []
    return []


def _literal(value: t.Any) -> str:
    try:
        text = json.dumps(value)
    except (TypeError, ValueError):
        text = repr(value)
    return f"``{text}``"


def _class_ref(cls: type) -> str:
    return f":class:`~{cls.__module__}.{cls.__qualname__}`"


class TypeFormatter:
    """Formats a type annotation as reStructuredText.

    Structs which can't be cross-referenced are collected in `inline` so
    their fields can be rendered beneath the type line.
    """

    def __init__(self):
        self.inline: list[type] = []

    def __call__(self, tp: t.Any) -> str:
        origin = t.get_origin(tp)
        args = t.get_args(tp)

        if origin is t.Annotated:
            inner, *metadata = args
            for meta in metadata:
                if is_keyed_by(meta):
                    fields = ", ".join(sorted(f[3:] for f in meta.fields))
                    return f"optionally-keyed-by({fields}; {self(meta.wrapped_type)})"
            return self(inner)

        if origin in UNION_TYPES:
            return " | ".join(self(a) for a in args)

        if origin is t.Literal:
            return " | ".join(_literal(a) for a in args)

        if origin is not None:
            name = getattr(origin, "__name__", str(origin))
            if not args:
                return name
            return f"{name}[{', '.join(self(a) for a in args)}]"

        if tp is type(None) or tp is None:
            return "null"

        if tp in (t.Any, object):
            return "any"

        if is_struct(tp):
            if is_canonical(tp):
                return _class_ref(tp)
            if tp not in self.inline:
                self.inline.append(tp)
            return "dict"

        if isinstance(tp, type):
            return tp.__name__

        return str(tp)


def _strip_optional(tp: t.Any) -> t.Any:
    """Remove `None` from a union type."""
    if t.get_origin(tp) in UNION_TYPES:
        args = [a for a in t.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
        return t.Union[tuple(args)]  # noqa: UP007
    return tp


def _keyed_by(tp: t.Any) -> t.Any:
    if t.get_origin(tp) is t.Annotated:
        for meta in t.get_args(tp)[1:]:
            if is_keyed_by(meta):
                return meta
    return None


def _get_default(field: msgspec.structs.FieldInfo) -> t.Any:
    if field.default is not msgspec.NODEFAULT:
        return field.default
    if field.default_factory is not msgspec.NODEFAULT:
        return field.default_factory()
    return msgspec.NODEFAULT


def iter_struct_lines(
    cls: type, indent: int = 0, seen: tuple[type, ...] = ()
) -> t.Generator[str, None, None]:
    prefix = " " * indent
    arg_prefix = prefix + "   "
    seen = seen + (cls,)

    config = cls.__struct_config__
    extra = "forbidden" if config.forbid_unknown_fields else "allowed"
    yield f"{prefix}*extra keys: {extra}*"
    yield ""

    fields = msgspec.structs.fields(cls)
    encode_names = {f.name: f.encode_name for f in fields}

    for group in getattr(cls, "exclusive", None) or ():
        names = ", ".join(f"``{encode_names.get(f, f)}``" for f in group)
        yield f"{prefix}**mutually exclusive**: {names}"
        yield ""

    for field in fields:
        tp = field.type
        default = _get_default(field)

        # Don't display `None` as a valid type if it's just the default.
        if default is None:
            tp = _strip_optional(tp)

        fmt = TypeFormatter()
        if keyed_by := _keyed_by(tp):
            type_str = fmt(keyed_by.wrapped_type)
        else:
            type_str = fmt(tp)

        status = "required" if field.required else "optional"
        yield f"{prefix}``{field.encode_name}`` ({status})"
        yield f"{arg_prefix}**type**: {type_str}"

        if keyed_by:
            fields_str = ", ".join(f"``{f[3:]}``" for f in sorted(keyed_by.fields))
            yield ""
            yield f"{arg_prefix}**optionally keyed by**: {fields_str}"

        if default not in (msgspec.NODEFAULT, None):
            yield ""
            yield f"{arg_prefix}**default**: {_literal(default)}"

        if desc := field_description(cls, field.name):
            yield ""
            for line in desc:
                yield f"{arg_prefix}{line}" if line else ""

        yield ""

        for sub in fmt.inline:
            if sub in seen:
                continue
            yield from iter_struct_lines(sub, indent + 3, seen)

    yield ""


# Names of fields belonging to schema classes in the module currently being
# documented. In Sphinx 9+, slotted members (like Struct fields) are passed to
# `autodoc-skip-member` as a sentinel without any reference to the class they
# belong to, and only after every class in the module has been processed.
_module_fields: set[str] = set()


def process_docstring(app, what, name, obj, options, lines):
    if what == "module":
        _module_fields.clear()

    if what not in ("class", "data", "attribute") or not is_struct(obj):
        return

    if what == "class":
        _module_fields.update(obj.__struct_fields__)

    # Aliases of documented classes (e.g. `CHUNK_SCHEMA = ChunkSchema`) just
    # link to the class.
    if name.rsplit(".", 1)[-1] != obj.__name__ and is_canonical(obj):
        return

    # Don't inherit the docstring of the `Schema` base class.
    if not obj.__dict__.get("__doc__"):
        lines.clear()
    elif lines and lines[-1]:
        lines.append("")

    lines.extend(iter_struct_lines(obj))


def process_signature(app, what, name, obj, options, signature, return_annotation):
    # Hide the generated `__init__` signature, as schemas are never
    # instantiated directly.
    if what == "class" and is_struct(obj):
        return "", return_annotation
    return None


def skip_member(app, what, name, obj, skip, options):
    # Fields are rendered as part of the class docstring.
    if what != "class":
        return None

    # Legacy class based autodoc passes the slot descriptor.
    objclass = getattr(obj, "__objclass__", None)
    if isinstance(obj, types.MemberDescriptorType) and is_struct(objclass):
        return name in objclass.__struct_fields__ or None  # type: ignore[union-attr]

    if any(obj is s for s in SLOTS_SENTINELS) and name in _module_fields:
        return True
    return None
