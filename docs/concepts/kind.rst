Kinds
=====

Kinds are the focal point of this system. They provide an interface between the
large-scale graph-generation process and the small-scale task-definition needs
of different kinds of tasks. A kind.yml file contains data about the kind, as
well as referring to a Python class implementing the kind in its implementation
key. These Python classes can either be part of standard Taskgraph, or custom
transforms that extend Taskgraph functionality.

Certain attributes - such as `kind-dependencies` - can be used to determine
which kind should be loaded before another. This is useful when the kind will
use the list of already-created tasks to determine which tasks to create, for
example loading an `android-toolchain` (to install sdk and accept licenses)
before every (android) build task. In some cases, you'll need to use a custom
loader to avoid scheduling a task until the task it depends on is completed.

But dependencies can also be used to schedule follow-up work such as
summarizing test results. In the latter case, the summarization task will “pull
in” all of the tasks it depends on, even if those tasks might otherwise be
optimized away.

How to Read a Kind
------------------

One of Taskgraph's features is the ability to extend standard taskgraph code
with custom transforms and loaders. However, it can be confusing to understand
which parts of a kind are standard taskgraph and which are custom code. If we
look at a simple build kind example, you'll notice at the top the `loader` and
`transforms` are defined. These point to standard taskgraph, but if you wanted
to use a custom loader or transform it would be defined here pointing to
`your_project_name_taskgraph` directory, eg
`my_project_name_taskgraph.transforms.run`. If no loader is specified,
`taskgraph.loader.default:loader` will be used, which will bring with it
`taskgraph.transforms.run` and `taskgraph.transforms.task` as default
transforms.

This can also be a clue of where to look if you are trying to understand what a
specific yaml attribute does in an existing kind file (keeping in mind that
these are written in snake case and the corresponding python functions aren't).

.. code-block:: yaml

  loader: taskgraph.loader.transform:loader

  transforms:
      - taskgraph.transforms.docker_image:transforms
      - taskgraph.transforms.cached_tasks:transforms
      - taskgraph.transforms.task:transforms

  tasks:
      android-build:  <-- this android-build image task is dependent on the the base image below, and will be referenced in a build kind.
          symbol: I(agb)
          parent: base
      base:
          symbol: I(base)
      ui-tests:
          symbol: I(ui-tests)
          parent: base
