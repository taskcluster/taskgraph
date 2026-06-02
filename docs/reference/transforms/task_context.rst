.. _task_context transforms:

Task Context Transforms
=======================

The :mod:`taskgraph.transforms.task_context` transform can be used to
resolve keys and/or substitute values into any field in a task with data
that is not known until ``taskgraph`` runs.

This data can be provided in a few ways, as described below.

Schema
------

All tasks must conform to the :py:data:`task_context schema
<taskgraph.transforms.task_context.SCHEMA>`.

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
       description:
        by-foo:
          bar: super special description for bar tasks
          default: my description of {foo}
       task-context:
         from-parameters:
           foo: foo
         substitution-fields:
           - description

When ``taskgraph`` is run the value of ``foo`` in the parameters it is provided
will be substituted into the description. For example, if the following parameters
are used:

.. code-block:: yaml

   foo: bar

...the description will end up with a value of "super special description for bar tasks".

When ``foo`` is set to any other value (eg: ``bar``) the description will end with the
``default`` value with the value of ``foo`` substituted in (eg: ``my description of bar``).

This pattern is often used to configure things vary based on how tasks are created. For example, the following can be used to adjust the scopes a task is given depending on the GitHub event that created the decision task:

.. code-block:: yaml

   tasks:
     build:
       task-context:
         from-parameters:
           tasks_for: tasks_for
         substitution-fields:
           - scopes

       scopes:
         by-tasks-for:
           github-push:
             - secrets:get:project/foo/api_token
           default: []

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

Implicit Context
~~~~~~~~~~~~~~~~

Finally, the name of the task is added to the context implicitly. For example:

.. code-block:: yaml

   task-defaults:
     description: run {name}
     task-context:
       substitution-fields:
         - description

   tasks:
     foo: {}
     bar: {}

This will evaluate the description correctly, even though there are no
``task-context`` keys defined on the individual tasks.

Order of Operations & Precedence
--------------------------------

Keys will be resolved on ``substitution-fields`` first, then substitution
will be performed on the resolved value.

If the same key is found in multiple places the order of precedence is as
follows: ``from-parameters``, ``from-object`` keys, ``from-file`` and finally
implicit context.

That is to say: parameters will always override anything else.
