Create Tasks
============

If you've followed the tutorials, you may have a working Taskcluster +
Taskgraph setup, but could be left wondering how to add a new task. This guide
will teach you the basics of creating tasks!

Create a Kind
-------------

Before we can define tasks, we need to define a :term:`Kind`. Kinds are groups
of tasks that share some commonality with one another (how common they are
depends on how you choose to organize them). So the first step is to define a
kind for your task.

If we're creating a build task, you might define a ``build`` kind by creating
``taskcluster/kinds/build/kind.yml``. Simply creating this file is enough to
define a kind, though in practice you'll likely add extra configuration such
as a :term:`loader <Loader>` or :term:`transforms <Transform>`.

Add Tasks to your Kind
----------------------

Tasks are defined in the ``kind.yml`` under a ``tasks`` key. For example, our
``build-linux`` task might look like:

.. code-block:: yaml
   :caption: taskcluster/kinds/build/kind.yml

   tasks:
     build-linux:
       description: "Build the app on Linux"
       worker-type: b-linux
       worker:
         docker-image: {in-tree: build}
       run:
         using: run-task
         cwd: '{checkout}'
         command: ./scripts/build.sh

If we want to add another task, say ``build-windows``, we can just append it
to the ``tasks`` object:

.. code-block:: yaml
   :caption: taskcluster/kinds/build/kind.yml

   tasks:
     build-linux:
       description: "Build the app"
       worker-type: b-linux
       worker:
         docker-image: {in-tree: build}
       run:
         using: run-task
         cwd: '{checkout}'
         command: ./scripts/build.sh

     build-windows:
       description: "Build the app"
       worker-type: b-windows
       run:
         using: run-task
         cwd: '{checkout}'
         command: ./scripts/build.ps1

.. note::

   The format of the tasks depends heavily on which :term:`transforms
   <Transform>` the kind uses. In this example, Taskgraph is implicitly adding
   the :mod:`~taskgraph.transforms.run` and :mod:`~taskgraph.transforms.task`
   transforms. See :doc:`/concepts/transforms` for more information.

Task Defaults
-------------

You may find that as you add more tasks, a certain amount of boilerplate gets
copied from one task to the next. A ``task-defaults`` key can be used to
reduce this overhead. The previous example can be re-written as:

.. code-block:: yaml
   :caption: taskcluster/kinds/build/kind.yml

   task-defaults:
     description: "Build the app"
     run:
       using: run-task
       cwd: '{checkout}'

   tasks:
     build-linux:
       worker-type: b-linux
       worker:
         docker-image: {in-tree: build}
       run:
         command: ./scripts/build.sh

     build-windows:
       worker-type: b-windows
       run:
         command: ./scripts/build.ps1

Using ``task-defaults`` recursively merges task configuration into the defaults
for each task.

Tasks From
----------

If you have a kind with a lot of tasks, the ``kind.yml`` file may grow to
unmanageable sizes. To help mitigate this, you can use the ``tasks-from`` key.
This allows you to define your tasks in any number of Yaml files outside of
``kind.yml``. For example, the following example is equivalent to the previous two:

.. code-block:: yaml
   :caption: taskcluster/kinds/build/kind.yml

   task-defaults:
     description: "Build the app"
     run:
       using: run-task
       cwd: '{checkout}'

   tasks-from:
     - linux.yml
     - windows.yml

.. code-block:: yaml
   :caption: taskcluster/kinds/build/linux.yml

   tasks:
     build-linux:
       worker-type: b-linux
       worker:
         docker-image: {in-tree: build}
       run:
         command: ./scripts/build.sh


.. code-block:: yaml
   :caption: taskcluster/kinds/build/windows.yml

   tasks:
     build-windows:
       worker-type: b-windows
       run:
         command: ./scripts/build.ps1

All three of the previous examples should result in identical task definitions.

Further Reading
---------------

Next you may want to learn about using :doc:`/concepts/transforms` or how to
:doc:`/howto/run-locally`.
