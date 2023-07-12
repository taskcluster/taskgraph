.. _task_context:

Task Context
============

The :mod:`taskgraph.transforms.task_context` transform can be used to
substitute values into any field in a task with data that is not known
until ``taskgraph`` runs.

This data can be provided in a few ways, as described below.

Usage
-----

from-parameters
~~~~~~~~~~~~~~~

Context can be pulled from parameters that are provided to ``taskgraph``.

First, add the transform to the ``transforms`` key in your ``kind.yml`` file:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.task_context
     # ...

Then create a ``task-context`` section in your task definition, e.g:

.. code-block:: yaml

   tasks:
     build:
       description: my description {foo}
       task-context:
         from-parameters:
           foo: foo
         substitution-fields:
           - description

When ``taskgraph`` is run the value of ``foo`` in the parameters it is provided
will be substituted into the description. For example, if the following parameters
are used:

.. code-block:: yaml

   foo: with some extra

...the description will end up with a value of "my description with some extra".

When using ``from-parameters`` you may also provide an ordered list of keys to
look for in the parameters, with the first one found being used. For example,
with the this ``kind``:

.. code-block:: yaml

   tasks:
     build:
       description: my description {foo}
       task-context:
         from-parameters:
           foo:
             - foo
             - default
         substitution-fields:
           - description

...the description will bring in the value ``foo`` from the parameters if
present, or ``default`` otherwise.

from-file
~~~~~~~~~

Context may also be provided from a defined yaml file. The provided file
should usually only contain top level keys and values (eg: nested objects
will not be interpolated - they will be substituted as text representations
of the object).

For example, with this kind definition:

.. code-block:: yaml

   tasks:
     build:
       description: my description {foo}
       task-context:
         from-file: some_file.yaml
         substitution-fields:
           - description

And this in ``some_file.yaml``:

.. code-block:: yaml

   foo: from a file

...description will end up with "my description from a file".


from-object
~~~~~~~~~~~

You may also specify context as direct keys and values in the ``task-context``
configuration in ``from-object`` . This can be useful in ``kinds`` that define
most of their contents in ``task-defaults``, but have some values that may
differ for various concrete ``tasks`` in the ``kind``.

For example:

.. code-block:: yaml

   task-defaults:
     description: my description {extra_desc}
     task-context:
       substitution-fields:
         - description

   tasks:
     build1:
       task-context:
         from-object:
           extra_desc: build1
     build2:
       task-context:
         from-object:
           extra_desc: build2

This will give build1 and build2 descriptions with their ``extra_desc``
included while allowing them to share the rest of their task definition.

Precedence
----------

If the same key is found in multiple places the order of precedence
is as follows: ``from-parameters``, ``from-object`` keys, ``from-file``.

That is to say: parameters will always override anything else.
