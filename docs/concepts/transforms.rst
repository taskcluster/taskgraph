Transforms
==========

Often tasks grow in complexity such that it is annoying or even impossible to
specify as a YAML object. Taskgraph has the concept of :term:`transforms
<Transform>` to help deal with this. Transforms allow you to layer programmatic
logic on top of your task definitions.

Overview
--------

To begin, a kind implementation generates a collection of tasks; see
:doc:`loading`. These are Python dictionaries that describe semantically
what the task should do.

The kind also defines a sequence of transformations. These are applied in order
to each task. Early transforms might apply default values or break tasks up
into smaller tasks (for example, chunking a test suite). Later transforms
rewrite the tasks entirely, with the final result being a task definition conforming
to the `Taskcluster task schema`_.

Specifying Transforms
.....................

Transforms are specified as a list of strings, where each string references a
:class:`taskgraph.transforms.base.TransformSequence`. For example, in a ``kind.yml``
file, you may add:

.. code-block:: yaml

   transforms:
     - project_taskgraph.transforms:transforms
     - taskgraph.transforms.task:transforms

The format of the reference is ``<module path>:<object>``. So the above example
will first load the ``transforms`` object from the
``project_taskgraph.transforms`` module, then the ``transforms`` object from
the ``taskgraph.transforms.task`` module. All referenced modules must be
available in the Python path. Note how transforms can be defined both within
the project that needs them, or in third party packages (like Taskgraph itself).

The ``taskgraph.transforms.task`` transforms are a special set of transforms that
nearly every task should use. These transforms are responsible for formatting a task
into a `valid Taskcluster task definition`_.

.. _valid Taskcluster task definition: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema

Default Object
``````````````

Using the name ``transforms`` for the object is a convention, and Taskgraph will
use that by default if no object is specified. So the following example is equivalent
to the previous one:

.. code-block:: yaml

   transforms:
     - project_taskgraph.transforms
     - taskgraph.transforms.task

Transform Functions
...................

Each transform function looks like:

.. code-block:: python

    from typing import Dict, Iterator

    from taskgraph.transforms.base import TransformConfig, TransformSequence

    transforms = TransformSequence()

    @transforms.add
    def transform_a_task(config: TransformConfig, tasks: Iterator[Dict]) -> Iterator[Dict]:
        """This transform ..."""  # always include a docstring!
        for task in tasks:
            # do stuff to the task..
            yield task

The ``config`` argument is a Python object containing useful configuration for
the kind, and is an instance of
:class:`taskgraph.transforms.base.TransformConfig`, which specifies a few of
its attributes. Kinds may subclass and add additional attributes if necessary.

While most transforms yield one task for each task consumed, this is not always
the case. Tasks that are not yielded are effectively filtered out. Yielding
multiple tasks for each consumed task is a form of duplication. This is how
test chunking is accomplished, for example.

The ``transforms`` object is an instance of
:class:`taskgraph.transforms.base.TransformSequence`, which serves as a simple
mechanism to combine a sequence of transforms into one.

Schemas
.......

The tasks used in transforms can be validated against some schemas at
various points in the transformation process. These schemas accomplish two
things: they provide a place to add comments about the meaning of each field,
and they enforce that the fields are actually used in the documented fashion.

Using schemas is a best practice as it allows others to more easily reason
about the state of the tasks at given points. Here is an example:

.. code-block:: python

   from voluptuous import Optional, Required

   from taskgraph.transforms.base import TransformSequence
   from taskgraph.util.schema import Schema

   my_schema = Schema({
       Required("foo"): str,
       Optional("bar"): bool,
   })

   transforms.add_validate(my_schema)

In the above example, we can be sure that every task dict has a string field
called ``foo``, and may or may not have a boolean field called ``bar``.

Organization
-------------

Task creation operates broadly in a few phases, with the interfaces of those
stages defined by schemas. The process begins with the raw data structures
parsed from the YAML files in the kind configuration. This data can processed
by kind-specific transforms resulting in a "kind specific description".

From there, it's common for tasks to use the :mod:`run transforms
<taskgraph.transforms.run>` which provide convenient utilities for things such
as cloning repositories, downloading artifacts, caching and much more! After
these transforms tasks will conform to the "run description".

Finally almost all kinds should use the :mod:`task transforms
<taskgraph.transforms.task>`. These transforms massage the task into the
`Taskcluster task schema`_

Run Descriptions
................

A *run description* defines what to run in the task. It is a combination of a
``run`` section and all of the fields from a task description. The run section
has a ``using`` property that defines how this task should be run; for example,
``run-task`` to run arbitrary commands, or ``toolchain-script`` to invoke a
well defined script. The remainder of the run section is specific to the
run-using implementation.

The effect of a run description is to say "run this thing on this worker". The
run description must contain enough information about the worker to identify
the workerType and the implementation (docker-worker, generic-worker, etc.).
Alternatively, run descriptions can specify the ``platforms`` field in
conjunction with the ``by-platform`` key to specify multiple workerTypes and
implementations. Any other task-description information is passed along
verbatim, although it is augmented by the run-using implementation.

The following ``run-using`` values are supported:

  * ``run-task``
  * ``toolchain-script``
  * ``index-search``


Task Descriptions
.................

Every kind needs to create tasks, and all of those tasks have some things in
common. E.g, they all run on one of a small set of worker implementations, each
with their own idiosyncrasies.

The transforms in :mod:`taskgraph.transforms.task` implement this common
functionality. They expect a "task description" and produce a task
definition.  The schema for a task description is defined at the top of
``task.py``, with copious comments. Go forth and read it now!

In general, the task-description transforms handle functionality that is common
to all tasks. While the schema is the definitive reference, the
functionality includes:

* Build index routes
* Information about the projects on which this task should run
* Optimizations
* Defaults for ``expires-after`` and and ``deadline-after``, based on project
* Worker configuration

The parts of the task description that are specific to a worker implementation
are isolated in a ``task_description['worker']`` object which has an
``implementation`` property naming the worker implementation.  Each worker
implementation has its own section of the schema describing the fields it
expects. Thus the transforms that produce a task description must be aware of
the worker implementation to be used, but need not be aware of the details of
its payload format.

The ``task.py`` file also contains a dictionary mapping treeherder groups to
group names using an internal list of group names.  Feel free to add additional
groups to this list as necessary.

.. _Taskcluster task schema: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema
