Load Task Locally
=================

For tasks that use Docker, it might be useful to run the task's payload in a
local container. This allows for faster debugging and iteration.

Run:

.. code-block:: shell

   taskgraph load-task <task id>

This command does a few things:

1. Retrieves the task's definition.
2. Parses out the image that it uses.
3. Fetches the image into your local Docker registry.
4. Creates a container with the task's environment variables set.
5. Runs the task's command in the container.

Only tasks using the `docker-worker payload format`_ are supported.

Load Tasks Interactively
------------------------

For debugging purposes, you might want to do some set up before executing the
task. To accomplish this, use the ``-i/--interactive`` flag:

.. code-block:: shell

   taskgraph load-task -i <task id>

This does all the same things up until step 5 above. Instead of running the
task's command, it saves it to a binary called ``exec-task`` and drops you
into an interactive shell. The task's environment variables will be set, and
the repository will be cloned (if the task requires a source checkout).

This allows you to inspect the state of the container, setup debuggers, etc. If
and when you are ready, run ``exec-task`` to resume task execution.

.. warning::

   Only tasks that use the ``run-task`` script to bootstrap their commands
   are currently supported.


Reading Task Definitions from Stdin
-----------------------------------

Instead of specifying a task id, you may also pipe the entire task definition
via stdin. This is useful if you are making changes to the definition in your
local Taskgraph and want to quickly test it without submitting a real task.

For example, you can run:

.. code-block:: shell

   taskgraph morphed -J --tasks test-unit-py | jq -r 'to_entries | first | .value.task' | taskgraph load-task -

In this example, we're piping the definition of the task named ``test-unit-py``
into ``taskgraph load-task``. This allows you to quickly iterate on the task
and test that it runs as expected.

.. note::

   The output of ``taskgraph morphed -J`` looks something like:

   ``{ "<task id>": { "task": { <task definition> }}}``

   So we need to use ``jq`` to extract the definition of the first listed task.

Using a Custom Image
--------------------

We've seen how ``taskgraph load-task`` can be useful to debug and test tasks,
but it is also useful when working on images! You can pass the ``--image`` flag
to make the supplied task run in a custom Docker image. The image can be one of:

* ``task-id=<task id>`` - Loads the image from the specified task id. The task
  id must reference a ``docker-image`` task.
* ``index=<index>`` - Loads the image from the specified index path. The index
  path must reference a ``docker-image`` task.
* ``<name>`` - Build the image produced by the ``docker-image`` task from the
  local Taskgraph called ``<name>``.
* ``<registry>`` - Load the image from the specified Docker registry.

Specifying ``<name>`` is particularly useful when working on changes to the
image. For example, let's say you're making changes to
``taskcluster/docker/python/Dockerfile``, you can run:

.. code-block:: shell

   taskgraph load-task --image python <task id>

Where the task id is a task that uses the ``python`` image.

Working on an Image and Task Simultaneously
-------------------------------------------

Sometimes you might need to make changes to the task definition and the image
it uses in conjunction with one another. You can test changes to both simultaneously
by combining passing in a custom image locally, and piping a task definition via stdin:

.. code-block:: shell

   taskgraph morphed -J --tasks test-unit-py | jq -r 'to_entries | first | .value.task' | taskgraph load-task --image python -

.. _docker-worker payload format: https://docs.taskcluster.net/docs/reference/workers/docker-worker/payload
