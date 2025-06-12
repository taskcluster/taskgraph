.. _matrix transforms:

Matrix Transforms
=================

The :mod:`taskgraph.transforms.matrix` transforms can be used to split a base
task into many subtasks based on a defined matrix.

These transforms are useful if you need to have many tasks that are very
similar except for some small configuration differences.

Schema
------

All tasks must conform to the :py:data:`matrix schema
<taskgraph.transforms.matrix.MATRIX_SCHEMA>`.

Usage
-----

Add the transform to the ``transforms`` key in your ``kind.yml`` file:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.matrix
     # ...

Then create a ``matrix`` section in your task definition, e.g:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         os: ["win", "mac", "linux"]

       # rest of task definition

This will split the ``test`` task into three; ``test-win``, ``test-mac`` and
``test-linux``.

Matrix with Multiple Rows
~~~~~~~~~~~~~~~~~~~~~~~~~

You can add as many rows as you like to the matrix, and every combination of
tasks will be generated. For example, the following matrix:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         os: ["win", "mac", "linux"]
         python: ["py312", "py311"]

       # rest of task definition

Will generate these tasks:

- ``test-win-py312``
- ``test-win-py311``
- ``test-mac-py312``
- ``test-mac-py311``
- ``test-linux-py312``
- ``test-linux-py311``

Note that the name of the tasks will be built based on the order of rows in the
matrix.

Substituting Matrix Context into the Task Definition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Of course these tasks will be identical, so you'll want to change other parts
of the task definition based on the matrix values.

Substituting Values in Yaml
```````````````````````````

The simplest way to change a matrix task's definition, is to use the built-in
yaml substitution:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         os: ["win", "mac", "linux"]
       description: Run {matrix[os]} tests
       worker-type: {matrix[os]}-worker

Limiting Substitution
'''''''''''''''''''''

By default, all keys and values in the task definition will be checked for
substitution parameters. But in some cases, it might be desirable to limit which
keys get substituted, such as when using the ``matrix`` transforms alongside
other transforms that perform substitution, such as the
:mod:`~taskgraph.transforms.task_context` or
:mod:`~taskgraph.transforms.chunking` transforms.

To limit the fields that will be evaluated for substitution, you can pass in the
``substitution-fields`` config:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         substitution-fields: ["worker-type"]
         os: ["win"]
       description: Run {matrix[os]} tests
       worker-type: {matrix[os]}-worker

In the example above, ``worker-type`` will evaluate to ``win-worker``, whereas
the description will be the literal string ``Run {matrix[os]} tests``. Dot
notation can be used in ``substitution-fields`` to limit substitution to some
sub configuration of the task definition.

Substituting Values in a Later Transform
````````````````````````````````````````

For more advanced cases, you may wish to use a later transform to act on the
result of the matrix evaluation. To accomplish this, the ``matrix`` transforms
will set a ``matrix`` attribute that contains all matrix values applicable to
the task.

For example, let's say you have a ``kind.yml`` like:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.matrix
     - custom_taskgraph.transforms.custom
     # ...

   tasks:
     test:
       matrix:
         os: ["win", "mac", "linux"]

Then in your ``custom.py`` transform file, you could add:

.. code-block:: python

   @transforms.add
   def set_worker_type_and_description(config, tasks):
       for task in tasks:
           matrix = task["attributes"]["matrix"]
           task["description"] = f"Run {matrix['os']} tests"
           task["worker-type"] = f"{matrix['os']}-worker"
           yield task

This example will yield the exact same result as the yaml example above, but it
allows for more complex logic.

Excluding Matrix Combinations
-----------------------------

Sometimes you might not want to generate *every* possible combination of tasks,
and there may be some you wish to exclude. This can be accomplished using the
``exclude`` config:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         os: ["win", "mac"]
         arch: ["x86", "arm64"]
         python: ["py312", "py311"]
         exclude:
           - os: mac
             arch: x86
           - os: win
             arch: arm64
             python: py311

This will cause all combinations where ``os == mac and arch == x86`` to be
skipped, as well as the specific combination where ``os == win and arch ==
arm64 and python == py311``. This means the following tasks will be generated:

  * test-win-x86-py311
  * test-win-x86-py312
  * test-win-arm64-py312
  * test-mac-arm64-py311
  * test-mac-arm64-py312

Customizing Task Names
----------------------

By default, the ``matrix`` transforms will append each matrix value to the
task's name, separated by a dash. If some other format is desired, you can specify
the ``set-name`` config:

.. code-block:: yaml

   tasks:
     test:
       matrix:
         set-name: "test-{matrix[os]}/{matrix[python]}"
         os: ["win"]
         python: ["py312"]

Instead of creating a task with the name ``test-win-py312``, the name will be
``test-win/py312``.
