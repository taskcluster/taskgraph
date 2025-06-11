.. _from_deps transforms:

From Dependencies Transforms
============================

The :mod:`taskgraph.transforms.from_deps` transforms can be used to create
tasks based on the kind dependencies, filtering on common attributes like the
``build-type``.

These transforms are useful when you want to create follow-up tasks for some
indeterminate subset of existing tasks. For example, maybe you want to run
a signing task after each build task.

Schema
------

All tasks must conform to the :py:data:`from_deps schema
<taskgraph.transforms.from_deps.FROM_DEPS_SCHEMA>`.

Usage
-----

Add the transform to the ``transforms`` key in your ``kind.yml`` file:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.from_deps
     # ...

Then create a ``from-deps`` section in your task definition, e.g:

.. code-block:: yaml

   kind-dependencies:
     - build
     - toolchain

   tasks:
     signing:
       from-deps:
         kinds: [build]

This example will split the ``signing`` task into many, one for each build. If
``kinds`` is unspecified, then it defaults to all kinds listed in the
``kind-dependencies`` key. So the following is valid:

.. code-block:: yaml

   kind-dependencies:
     - build
     - toolchain

   tasks:
     signing:
       from-deps: {}

In this example, a task will be created for each build *and* each toolchain.

Limiting Dependencies by Attribute
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It may not be desirable to create a new task for *all* tasks in the given kind.
It's possible to limit the tasks given some attribute:

.. code-block:: yaml

   kind-dependencies:
     - build

   tasks:
     signing:
       from-deps:
         with-attributes:
           platform: linux

In the above example, follow-up tasks will only be created for builds whose
``platform`` attribute equals "linux". Multiple attributes can be specified,
these are resolved using the :func:`~taskgraph.util.attributes.attrmatch`
utility function.

Grouping Dependencies
~~~~~~~~~~~~~~~~~~~~~

Sometimes, it may be desirable to run a task after a group of related tasks
rather than an individual task. One example of this, is a task to notify when a
release is finished for each platform we're shipping. We want it to depend on
every task from that particular release phase.

To accomplish this, we specify the ``group-by`` key:

.. code-block:: yaml

   kind-dependencies:
     - build
     - signing
     - publish

   tasks:
     notify:
       from-deps:
         group-by:
           attribute: platform

In this example, tasks across the ``build``, ``signing`` and ``publish`` kinds will
be scanned for an attribute called "platform" and sorted into corresponding groups.
Assuming we're shipping on Windows, Mac and Linux, it might create the following
groups:

.. code-block::

   - build-windows, signing-windows, publish-windows
   - build-mac, signing-mac, publish-mac
   - build-linux, signing-linux, publish-linux

Then the ``notify`` task will be duplicated into three, one for each group. The
notify tasks will depend on each task in its associated group.

You may also provide a special value of ``all`` to the ``group-by`` function.
Using ``all`` will *always* result in one task being generated, with all tasks
from the included kinds to be set as dependencies. It is usually useful to also
set ``unique-kinds`` to ``False`` when using ``all``.

If we alter the ``kind`` definition from above as follows:

.. code-block:: yaml

   kind-dependencies:
     - build
     - signing
     - publish

   tasks:
     notify:
       from-deps:
         group-by: all

We would end up with a single ``notify`` task that depends on all tasks from
the ``build``, ``signing``, and ``publish`` kinds.


Custom Grouping
~~~~~~~~~~~~~~~

Only the default ``single``, ``all`` and the ``attribute`` group-by functions
are built-in. But if more complex grouping is needed, custom functions can be
implemented as well:

.. code-block:: python

   from typing import List

   from taskgraph.task import Task
   from taskgraph.transforms.base import TransformConfig
   from taskgraph.util.dependencies import group_by

   @group_by("custom-name")
   def group_by(config: TransformConfig, tasks: List[Task]) -> List[List[Task]]:
      pass

This can then be used in a task like so:

.. code-block:: yaml

   from-deps:
     group-by: custom-name

It's also possible to specify a schema for your custom group-by function, which
allows tasks to pass down additional context (such as with the built-in
``attribute`` function):

.. code-block:: python

   from typing import List

   from taskgraph.task import Task
   from taskgraph.transforms.base import TransformConfig
   from taskgraph.util.dependencies import group_by
   from taskgraph.util.schema import Schema

   @group_by("custom-name", schema=Schema(str))
   def group_by(config: TransformConfig, tasks: List[Task], ctx: str) -> List[List[Task]]:
      pass

The extra context can be passed by turning ``group-by`` into an object
instead of a string:

.. code-block:: yaml

   from-deps:
     group-by:
       custom-name: foobar

In the above example, the value ``foobar`` is what must conform to the schema defined
by the ``group_by`` function.

Unique Kinds
~~~~~~~~~~~~

By default, each group can contain only a single task from a given kind. I.e, a
group can contain a build task and a signing task, but not two build tasks.
This is enforced at task generation time. This is typically the desired behaviour
and the check is in place to prevent mistakes.

However, in some cases it may be desirable to depend on multiple tasks of the same
kind (e.g, if implementing a ``notify`` task). In this case it's possible to specify
``unique-kinds``:

.. code-block:: yaml

   tasks:
     notify:
       from-deps:
         unique-kinds: false
         group-by: custom

This will disable the uniqueness check and switch dependency edge names to the
dependency's label rather than its kind. Now the ``notify`` task can be used
with a custom group-by function that returns more than one kind per group.

Primary Kind
~~~~~~~~~~~~

Each task has a ``primary-kind``. This is the kind dependency in each grouping
that comes first in the list of supported kinds (either via the
``kind-dependencies`` in the ``kind.yml`` file, or via the ``from-deps.kinds``
key). Note that depending how the dependencies get grouped, a given group may
not contain a dependency for each kind. Therefore the list of kind dependencies
are ordered by preference. E.g, kinds earlier in the list will be chosen as the
primary kind before kinds later in the list.

The primary kind is used to derive the task's label, as well as copy attributes
if the ``copy-attributes`` key is set to ``True`` (see next section).

Each task created by the ``from_deps`` transforms, will have a
``primary-kind-dependency`` attribute set.

Copying Attributes
~~~~~~~~~~~~~~~~~~

It's often useful to copy attributes from a dependency. When this key is set to ``True``,
all attributes from the ``primary-kind`` (see above) will be copied over to the task. If
the task contains pre-existing attributes, they will not be overwritten.

Generated Task Names
~~~~~~~~~~~~~~~~~~~~

By default ``from_deps`` will derive a ``name`` for generated tasks from the ``name``
on the ``primary-kind``. This will override any ``name`` set in the ``kind``. In some
cases you may need or want precise control over the generated task ``name``. You can
use ``set-name: false`` to disable this behaviour:

.. code-block:: yaml

   tasks:
     notify:
       from-deps:
         set-name: false

Adding Fetches
~~~~~~~~~~~~~~

In many cases it is necessary to fetch artifacts from tasks that ``from_deps`` has added
as dependencies. This can be accomplished by adding a ``fetches`` block to your ``from-deps``
entry:

.. code-block:: yaml

   kind-dependencies:
     - build

   tasks:
     test:
       from-deps:
         fetches:
           build:
             - artifact: target.tar.gz

The above block will add a ``fetches`` entry to the task that is compatible with ``taskgraph`` 's
:mod:`~taskgraph.transforms.run` transforms.

In some cases, artifact names may be different for different upstream tasks within the same kind.
You can often handle this by setting an attribute in the upstream tasks, which ``from_deps`` can
substitute in. For example, suppose we have 3 ``build`` tasks with different suffixes for their
``target`` artifact (``tar.gz``, ``zip``, and ``apk``). You can use an entry like this to ensure
each generated ``test`` task looks for the appropriate artifact:

.. code-block:: yaml

   tasks:
     test:
       from-deps:
         fetches:
           build:
             - artifact: target.{target_suffix}

This can also be useful when combined with other transforms. For example, the
:mod:`~taskgraph.transforms.chunking` transform sets the ``this_chunk`` attribute
on the tasks it generates. In cases where the chunk number is used in artifacts
produced by the chunked tasks, you can make use of this to easily collect them all
in a downstream task:


.. code-block:: yaml

   tasks:
     summary:
       from-deps:
         group-by: all
         fetches:
           expensive-test:
             - artifact: test-summary-{this_chunk}.json
