Use Artifacts from Dependencies
===============================

Tasks typically depend on other tasks in order to consume their output, or
artifacts. Taskgraph provides a declarative mechanism to use these artifacts
called "fetches".

At a high level, a task declares which artifacts it wishes to use in a
``fetches`` key in its task definition. Then this information is passed down to
the ``fetch-content`` script which runs immediately preceding the task's
command. The ``fetch-content`` script handles downloading (and possibly
extracting) the artifact to a known location. The task can then use the artifact
in its payload.

Using Fetches
-------------

Fetches are implemented as part of the :mod:`~taskgraph.transforms.run`
transforms. So first make sure your task's ``kind.yml`` file is using those
transforms:

.. code-block:: yaml

   loader: taskgraph.loader.transform:loader

   transforms:
     - taskgraph.transforms.run:transforms


Now let's say we're creating a test task. We'll need to download and
extract the build artifact from a build task. With fetches, this can be
accomplished like so:

.. code-block:: yaml

   test:
     dependencies:
       build: build-opt
     fetches:
       build:
         - build.zip
     # <remainder of task definition>

In this example, we first add a dependency edge (named ``build``) on the task
labelled ``build-opt``. Then we declare that we want to fetch the ``build.zip``
artifact from this dependency. Note that the key used in the ``fetches`` dict should
correspond to the name of a dependency edge.

Now before your task's payload is executed, the ``fetch-content`` script will
automatically download and extract the ``build.zip`` artifact to the
``$TASK_WORKDIR/fetches`` directory. Easy!

Configuring Fetches
-------------------

It's possible to configure the fetch by specifying a dict instead of a string.
For example:

.. code-block:: yaml

   test:
     dependencies:
       build: build-opt
     fetches:
       build:
         - artifact: build.zip
           extract: false
           dest: some/other/place

This will download the artifact to ``some/other/place`` and avoid extracting
it. If a string is used (like in the first example), the default values will be
used, ``{extract: true, dest: "fetches"}``.

Using ``fetch`` and ``toolchain`` Tasks
---------------------------------------

There are two special :term:`kinds <Kind>` of task that exist for the sole
purpose of exposing an artifact to downstream consumers:

1. ``fetch`` - Tasks that fetch a resource from the internet and adds it to
   Taskcluster's artifact storage.
2. ``toolchain`` - Tasks that build and/or package a resource.

Since these types of tasks expose a single well defined artifact, using them in
fetches is much simpler:

.. code-block:: yaml

   test:
     fetches:
       fetch:
         - grcov
       toolchain:
         - clang

There are a few differences from the earlier ``build`` examples here:

1. Instead of specifying the dependency edge name, the ``kind`` name is used.
2. Instead of specifying the name of the artifact, the label of the task is
   used (this example assumes that tasks called ``grcov`` and ``clang`` exist).
3. The dependency on the ``fetch`` or ``toolchain`` is implicitly added, so no
   need to specify them in the ``dependencies`` key.

.. note::

   It is not possible to configure the ``dest`` or ``extract`` values when using
   ``fetch`` or ``toolchain`` kinds.
