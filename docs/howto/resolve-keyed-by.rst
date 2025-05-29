Use Keyed By
============

Often fields in a task can depend on other values in the task. For example, a
task's ``max-runtime`` may depend on the ``platform``. To handle this, you
could re-define ``max-runtime`` in each task's definition like so:

.. code-block:: yaml

   tasks:
     taskA:
       platform: android
       worker:
         max-runtime: 7200

     taskB:
       platform: ios
       worker:
         max-runtime: 7200

     taskC:
       platform: windows
       worker:
         max-runtime: 3600

     taskD:
       platform: mac
       worker:
         max-runtime: 1800

     ...

This is simple, but if you have lots of tasks it's also tedious and makes
updating the configuration a pain. To avoid this duplication you could use a
:doc:`transform </concepts/transforms>`:

.. code-block:: python

   @transforms.add
   def set_max_runtime(config, tasks):
       for task in tasks:
           if task["platform"] in ("android", "ios"):
               task["worker"]["max-runtime"] = 7200
           elif task["platform"] == "windows":
               task["worker"]["max-runtime"] = 3600
           else:
               task["worker"]["max-runtime"] = 1800

           yield task

This works but now we've hardcoded constants into our code logic far away from
the task's original definition! Besides this is pretty verbose and it can get
complicated if you want to be able to change these constants per task.

An Alternative Approach
-----------------------

Another way to accomplish the same thing is to use Taskgraph's "keyed by"
feature. This can be used in combination with the ``task-defaults`` key to
express the same logic directly in the ``kind.yml`` file:

.. code-block:: yaml

   task-defaults:
     worker:
       max-runtime:
         by-platform:
           (ios|android): 7200
           windows: 3600
           default: 1800

   tasks:
     taskA:
       platform: android

     taskB:
       platform: windows

     taskC:
       platform: mac

     ...


The structure under the ``by-platform`` key is resolved to a single value using
the :func:`~taskgraph.util.schema.resolve_keyed_by` utility function. When
"keying by" another attribute in the task, you must call this utility later on
in a transform:

.. code-block:: python

   from taskgraph.util.schema import resolve_keyed_by

   @transforms.add
   def resolve_max_runtime(config, tasks):
       for task in tasks:
           resolve_keyed_by(task, "worker.max-runtime", f"Task {task['label']")
           yield task

In this example, :func:`~taskgraph.util.schema.resolve_keyed_by` takes the root
container object (aka, the task), the subkey to operate on, and a descriptor
that will be used in any exceptions that get raised.

Exact matches are used immediately. If no exact matches are found, each
alternative is treated as a regular expression, matched against the whole
value. Thus ``android.*`` would match ``android-arm/debug``. If nothing
matches as a regular expression, but there is a ``default`` alternative, it is
used. Otherwise, an exception is raised and graph generation stops.

Passing Additional Context
--------------------------

By default when you use the pattern ``by-<name>`` and then feed it into
:func:`~taskgraph.util.schema.resolve_keyed_by`, ``<name>`` is assumed to be a
valid top-level key in the task definition. However, sometimes you want to key
by some other value that is either nested deeper in the task definition, or not
even known ahead of time!

For this reason you can specify additional context via ``**kwargs``. Typically
it will make the most sense to use this following a prior transform that sets
some value that's not known statically. This comes up frequently when splitting
a task from one definition into several. For example:

.. code-block:: yaml

   tasks:
     task:
       platforms: [android, windows, mac]
       worker:
         max-runtime:
           by-platform:
             (ios|android): 7200
             windows: 3600
             default: 1800

.. code-block:: python

   @transforms.add
   def split_platforms(config, tasks):
       for task in tasks:
           for platform in task.pop("platforms"):
               new_task = deepcopy(task)
               # ...
               resolve_keyed_by(
                   new_task,
                   "worker.max-runtime",
                   task["label"],
                   platform=platform,
               )
               yield new_task

Here we did not know the value of "platform" ahead of time, but it was still
possible to use it in a "keyed by" statement thanks to the ability to pass in
extra context.

.. note::
   A good rule of thumb is to only consider using "keyed by" in
   ``task-defaults`` or in a task definition that will be split into many
   tasks down the line.

Specifying the Subkey
---------------------

The subkey in :func:`~taskgraph.util.schema.resolve_keyed_by` is expressed in
dot path notation with each part of the path representing a nested dictionary.
If any part of the subkey is a list, you can use `[]` to operate on each item
in the list. For example, consider this excerpt of a task definition:

.. code-block:: yaml

    worker:
        artifacts:
            - name: foo
              path:
                  by-platform:
                      windows: foo.zip
                      default: foo.tar.gz
            - name: bar
              path:
                  by-platform:
                      windows: bar.zip
                      default: bar.tar.gz

With the associated transform:

.. code-block:: python

   @transforms.add
   def resolve_artifact_paths(config, tasks):
       for task in tasks:
           resolve_keyed_by(task, "worker.artifacts[].path", task["label"])
           yield task

In this example, Taskgraph resolves ``by-platform`` in both the *foo* and *bar*
artifacts.

.. note::
   Calling ``resolve_keyed_by`` on a subkey that doesn't contain a ``by-*``
   field is a no-op.

Creating Schemas with Keyed By
------------------------------

Having fields of a task that may or may not be keyed by another field, can cause
problems for any schemas your transforms define. For that reason Taskgraph provides
the :func:`~taskgraph.util.schema.optionally_keyed_by` utility function.

It can be used to generate a valid schema that allows a field to either use
"keyed by" or not. For example:

.. code-block:: python

   from taskgraph.util.schema import Schema, optionally_keyed_by


   schema = Schema({
       # ...
       Optional("worker"): {
           Optional("max-run-time"): optionally_keyed_by("platform", int),
       },
   })

   transforms.add_validate(schema)

The example above allows both of the following task definitions:

.. code-block:: yaml

   taskA:
       worker:
           max-run-time: 3600

   taskB:
       worker:
           max-run-time:
               by-platform:
                   windows: 7200
                   default: 3600

If there are more than one fields that another field may be keyed by, it
can be specified like this:

.. code-block:: python

   Optional("max-run-time"): optionally_keyed_by("platform", "build-type", int)


In this example either ``by-platform`` or ``by-build-type`` may be used. You
may specify as many fields as you like this way, as long as the last argument to
:func:`~taskgraph.util.schema.optionally_keyed_by` is the type of the field
after resolving is finished (or if keyed by is unused).
