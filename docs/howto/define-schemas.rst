Define Schemas
==============

:doc:`Transforms </concepts/transforms>` can define schemas to validate task data at each step of the
pipeline. Taskgraph uses `msgspec`_ under the hood, and provides a
:class:`~taskgraph.util.schema.Schema` base class that integrates with
:meth:`TransformSequence.add_validate() <taskgraph.transforms.base.TransformSequence.add_validate>`.

There are two ways to define a schema: the **class based** approach and the
**dict based** approach. Both produce equivalent results; which one you prefer
is a matter of style.

.. _msgspec: https://jcristharif.com/msgspec/


Class Based Schemas
-------------------

Subclass :class:`~taskgraph.util.schema.Schema` and declare fields as class
attributes with type annotations:

.. code-block:: python

   from typing import Optional
   from taskgraph.transforms.base import TransformSequence
   from taskgraph.util.schema import Schema

   class MySubConfig(Schema):
       total_num: int
       fields: list[str] = []

   class MySchema(Schema, forbid_unknown_fields=False):
       config: Optional[MySubConfig] = None

   transforms = TransformSequence()
   transforms.add_validate(MySchema)

A few things to note:

- Field names use ``snake_case`` in Python but are **automatically renamed to
  ``kebab-case``** in YAML. So ``total_num`` in Python matches
  ``total-num`` in YAML.
- ``Optional[T]`` fields default to ``None`` unless you supply an explicit
  default.
- Fields without a default are **required**.
- ``forbid_unknown_fields=True`` (the default) causes validation to fail if the
  task data contains keys that are not declared in the schema. Set it to
  ``False`` on outer schemas so that fields belonging to later transforms are
  not rejected.


Dict Based Schemas
------------------

Call :meth:`Schema.from_dict() <taskgraph.util.schema.Schema.from_dict>` with a
dictionary mapping field names to ``type`` or ``(type, default)`` tuples:

.. code-block:: python

   from typing import Optional, Union
   from taskgraph.transforms.base import TransformSequence
   from taskgraph.util.schema import Schema

   MySchema = Schema.from_dict(
       {
           "config": Schema.from_dict(
               {
                   "total-num": int,
                   "fields": list[str] = []
               },
               optional=True,
           ),
       },
       forbid_unknown_fields=False,
   )

   transforms = TransformSequence()
   transforms.add_validate(MySchema)

This example is equivalent to the first example. One advantage with the dict based approach
is that you can write keys in **kebab-case** directly.

Field specifications follow these rules:

- A bare type (e.g. ``str``) means the field is required.
- ``Optional[T]`` means the field is optional and defaults to ``None``.
- A ``(type, default)`` tuple supplies an explicit default, e.g.
  ``(list[str], [])``.

Keyword arguments to ``from_dict`` are forwarded to ``msgspec.defstruct``.
The most commonly used ones are ``name`` (for better error messages) and
``forbid_unknown_fields``.

.. note::
   ``Schema.from_dict`` does **not** apply ``rename="kebab"`` automatically,
   because you can express the kebab-case names directly in the dict keys.
   Underscores in dict keys stay as underscores and dashes become valid
   kebab-case field names.


Nesting Schemas
---------------

Both approaches support nesting:

.. code-block:: python

   # Class-based nesting
   class Inner(Schema):
       value: str

   class Outer(Schema, forbid_unknown_fields=False, kw_only=True):
       inner: Optional[Inner] = None

   # Dict-based nesting
   Outer = Schema.from_dict(
       {
           "inner": Schema.from_dict({"value": str}, optional=True),
       },
       forbid_unknown_fields=False,
   )

Pass ``optional=True`` to ``from_dict`` to make the whole nested schema
optional. This is necessary as function calls are not allowed in type
annotations, so ``Optional[Schema.from_dict(...)]`` is not valid Python.


Mutually Exclusive Fields
-------------------------

Use the ``exclusive`` keyword to declare groups of fields where at most one
may be set at a time:

.. code-block:: python

   # Class-based
   class MySchema(Schema, exclusive=[["field_a", "field_b"]]):
       field_a: Optional[str] = None
       field_b: Optional[str] = None

   # Dict-based
   MySchema = Schema.from_dict(
       {
           "field-a": Optional[str],
           "field-b": Optional[str],
       },
       exclusive=[["field_a", "field_b"]],
   )

``exclusive`` takes a list of groups, where each group is a list of field
names (Python ``snake_case``). A validation error is raised if more than one
field in a group is set.

.. note::
   When using ``exclusive`` with the dict-based approach, refer to fields by
   their Python attribute names (``snake_case``), not their YAML keys.
