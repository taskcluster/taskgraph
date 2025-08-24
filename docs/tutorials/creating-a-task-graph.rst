Creating a Simple Task Graph
============================

This tutorial will walk you through the process of creating a simple :ref:`task
graph <Task Graph>`.

We'll create the scaffolding for Taskgraph and set up a single "Hello World"
task. Once this is working, you will have the tools and knowledge to start
adding your own tasks, and modifying configuration to meet your repository's
needs.

For the purposes of this tutorial, we'll assume your repository is called
``myrepo``.

Create the File System Layout
-----------------------------

Create a file system layout similar to:

::

   taskcluster
   ├── config.yml
   ├── kinds
   │   └── hello
   |       └── kind.yml
   └── myrepo_taskgraph
       └── transforms
           └── hello.py

The ``taskcluster`` directory should appear at the root of the repository. It
is possible to rename / put it somewhere else, but you'll need to jump through
a couple extra steps in that case. The location of the transforms file is
similarly only a convention (but it must be importable).

Populate the Config File
------------------------

The config file lives at ``taskcluster/config.yml`` and must conform to the
:py:data:`~taskgraph.config.graph_config_schema`.

Create the ``config.yml`` file to look like:

.. code-block:: yaml

   ---
   trust-domain: myrepo
   task-priority: low
   workers:
       # Values here depend on your Taskcluster instance's configuration.
       aliases:
           linux:
               provisioner: '{trust-domain}-provisioner'
               implementation: docker-worker
               os: linux
               worker-type: '{trust-domain}-linux'
   taskgraph:
       repositories:
           myrepo:
               name: myrepo

Here's an explanation of the required top-level keys:

* ``trust-domain`` - :term:`Trust domains <Trust Domain>` help prevent
  permissions and worker pools from one project from being reused in another. The
  value you should use here will be configured by your Taskcluster administrator.
  But we'll use ``myrepo`` for the purposes of this tutorial.
* ``task-priority`` - The priority of tasks for this repo.
* ``workers`` - The set of worker pools available to the project. This will also
  be configured by your Taskcluster administrator.
* ``taskgraph`` - A dict containing some miscellaneous configuration needed by
  Taskgraph.


Define a Task
-------------

:term:`Kinds <Kind>` are groupings of tasks that share certain characteristics
with one another. Each subdirectory in ``taskcluster/kinds`` corresponds to a
different kind and contains a ``kind.yml`` file. These files define some
properties that control how Taskgraph will generate the tasks, as well as the
starting definitions of the tasks themselves. If you followed the layout above,
you have a ``hello`` kind. For this next section we'll be editing
``taskcluster/kinds/hello/kind.yml``.

#. Declare the set of :term:`transforms <transform>` that will be applied
   to tasks. By default, taskgraph will include the
   :mod:`~taskgraph.transforms.run` and :mod:`~taskgraph.transforms.task`
   transforms, which are used by the vast majority of simple tasks. It is also
   quite common for kind-specific transforms to be used, which we will do here
   for the purpose of demonstration. In our example:

   .. code-block:: yaml

    transforms:
        - myrepo_taskgraph.transforms.hello:transforms

#. Finally we define the task under the ``tasks`` key. The format for the
   initial definition here can vary wildly from one kind to another, it all
   depends on the transforms that are used. It's conventional for transforms to
   define a schema (but not required). So often you can look at the first
   transform file to see what schema is expected of your task. But since we
   haven't created the first transforms yet, let's define our task like this
   for now:

   .. code-block:: yaml

    tasks:
        taskcluster:
            description: "Says hello to Taskcluster"
            text: "Taskcluster!"

Here is the combined ``kind.yml`` file:

.. code-block:: yaml

 transforms:
     - myrepo_taskgraph.transforms.hello:transforms
 tasks:
     taskcluster:
         description: "Says hello to Taskcluster"
         text: "Taskcluster!"

Create the Transform
--------------------

:term:`Transforms <Transform>` are Python generators that take a
:class:`~taskgraph.transforms.base.TransformConfig` instance and a generator
that yields task definitions (in dictionary form) as input. It yields task
definitions (which may or may not be modified) from the original inputs.

Typically transform files contain a schema, followed by one or more transform
functions. Rather than break it down step by step, here's what our
``taskcluster/myrepo_taskgraph/transforms/hello.py`` file will look like (see
comments for explanations):

.. code-block:: python

   from voluptuous import Optional, Required

   from taskgraph.transforms.base import TransformSequence
   from taskgraph.util.schema import Schema

   # Define the schema. We use the `voluptuous` package to handle validation.
   hello_description_schema = Schema({
       Required("text"): str,
       Optional("description"): str,
   })

   # Create a 'TransformSequence' instance. This class collects transform
   # functions to run later.
   transforms = TransformSequence()

   # First let's validate tasks against the schema.
   transforms.add_validate(hello_description_schema)

   # Register our first transform functions via decorator.
   @transforms.add
   def set_command(config, tasks):
       """Builds the command the task will run."""
       for task in tasks:
           task["command"] = f"bash -cx 'echo Hello {task.pop('text')}'"
           yield task

   @transforms.add
   def build_task_description(config, tasks):
       """Sets the attributes required by transforms in
       `taskgraph.transforms.task`"""
       for task in tasks:
           if "description" not in task:
               task["description"] = f"Says Hello {task['text']}"
           task["label"] = f"{config.kind}-{task.pop('name')}"
           # This is what was defined in `taskcluster/config.yml`.
           task["worker-type"] = "linux"
           task["worker"] = {
               "command": task.pop["command"],
               "docker-image": "ubuntu:latest",
               "max-run-time": 300,  # seconds
           }
           yield task

.. _format Taskcluster expects: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema

Generate the Taskgraph
----------------------

Now it's time to see if everything works! If you haven't done so already,
follow the :ref:`installation` docs to install Taskgraph.

Next run the following command at the root of your repo:

.. code-block:: bash

 taskgraph full

If all goes well, you should see some log output followed by a single task
called ``hello-taskcluster``. Try adding a second task to your ``tasks`` key
in the ``kind.yml`` file and re-generating the graph. You should see both
task labels!

Now run:

.. code-block:: bash

 taskgraph morphed -J

The ``-J/--json`` flag will display the full JSON definition of your task.
Morphed is the final phase of :ref:`graph generation <graph generation>`, so
represents your task's final form before it would get submitted to Taskcluster.
In fact, if we hadn't made up the trust domain and worker pool in
``config.yml``, you could even copy / paste this definition into Taskcluster's
`task creator`_!

Next you can check out the :doc:`connecting-taskcluster` tutorial or learn more
about :doc:`generating the taskgraph locally </howto/run-locally>`.

.. _task creator: https://firefox-ci-tc.services.mozilla.com/tasks/create
