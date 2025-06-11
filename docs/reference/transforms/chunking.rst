.. _chunking transforms:

Chunking Transforms
===================

The :mod:`taskgraph.transforms.chunking` module contains transforms that aid
in splitting a single entry in a ``kind`` into multiple tasks. This is often
used to parallelize expensive or slow work.

Schema
------

All tasks must conform to the :py:data:`chunking schema
<taskgraph.transforms.chunking.CHUNK_SCHEMA>`.

Usage
-----

Chunking
~~~~~~~~

First, add the transform to the ``transforms`` key in your ``kind.yml`` file:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.chunking
     # ...

Then create a ``chunk`` section in your task definition, e.g:

.. code-block:: yaml

   tasks:
     test-{this_chunk}/{total_chunks}:
       description: my description {this_chunk}/{total_chunks}
       chunk:
         total-chunks: 4
         substitution-fields:
           - name
           - description

This will result in 4 tasks being generated from the single definition in the
``kind``, differing only by their description. (In practice, ``{this_chunk}``
and ``{total_chunks}`` are typically included in the environment or command,
but this is being omitted here for brevity).

Dynamic chunking
~~~~~~~~~~~~~~~~

It can sometimes be useful to have ``total-chunks`` defined at ``taskgraph``
runtime rather than hardcoded into a kind. To accomplish this you can combine
one of these transforms sequences with ``task-context`` to pull ``total-chunks``
from an outside source.

For example:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.task-context
     - taskgraph.transforms.chunking

   kind-dependencies:
     - build

   tasks:
     test-{this_chunk}/{total_chunks}:
       description: my description {this_chunk}/{total_chunks}
       task-context:
         from-parameters:
           test_task_chunks: test_task_chunks
         substitution-fields:
           - chunk.total-chunks
       chunk:
         total-chunks: "{test_task_chunks}"
         substitution-fields:
           - name
           - description

When run with a set of parameters that sets ``test_task_chunks`` to ``10``,
this will result in 10 test tasks.
