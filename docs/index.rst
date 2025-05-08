.. taskgraph documentation master file, created by
   sphinx-quickstart on Thu Nov 11 18:38:14 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Taskgraph
=========

Taskgraph is a Python library to generate `DAGs`_ of tasks for `Taskcluster`_,
the task execution framework which underpins Mozilla's `CI`_. The nodes of the
DAG represent tasks, while the edges represent the dependencies between them.

Taskgraph is designed to scale to any level of complexity. From a handful of
tasks, to the over 30,000 tasks and counting that make up Firefox's CI.

.. _installation:

Installation
------------

Taskgraph is on Pypi and can be installed via:

.. code-block::

   pip install taskcluster-taskgraph

This provides the ``taskgraph`` binary, see ``taskgraph --help`` for available
commands.

Alternatively you can install it by cloning the repo. This is useful if you
need to test against a specific revision:

.. code-block::

   git clone https://github.com/taskcluster/taskgraph
   cd taskgraph
   pip install --editable .

Getting Started
---------------

Once installed, you can quickly bootstrap a new Taskgraph setup by running the
following command within an existing repository:

.. code-block::

   taskgraph init

.. warning::

   Taskgraph currently only supports repositories hosted on Github or hg.mozilla.org.

You should notice a couple changes:

1. A new file called ``.taskcluster.yml``. This file is rendered via `JSON-e`_
   with context passed in from a Github webhook event (if your repository is
   hosted on Github). The rendered result contains a `task definition`_ for a
   special task called the :term:`Decision Task`.
2. A new directory called ``taskcluster``. This contains the :term:`kind
   <Kind>` definitions and :term:`transform <Transform>` files that will define
   your tasks.

In short, the Decision task will invoke ``taskgraph`` in your repository. This
command will then process the ``taskcluster`` directory, turn it into a graph
of tasks, and submit them all to Taskcluster. But you can also test out the
``taskgraph`` command locally! From the root of your repo, try running:

.. code-block::

   taskgraph full

You'll notice that ``taskgraph init`` has created a couple of tasks for us
already, namely ``docker-image-linux`` and ``hello-world``.

.. note::

   By default the ``taskgraph`` command will only output task labels. Try
   adding ``--json`` to the command to see the actual definitions.

See if you can create a new task by editing ``taskcluster/kinds/hello/kind.yml``,
and re-run ``taskgraph full`` to verify.

How It Works
------------

Taskgraph starts by loading :term:`kinds <Kind>`, which are logical groupings
of similar tasks. Each kind is defined in a ``taskcluster/kinds/<kind
name>/kind.yml`` file.

Once a kind has been loaded, Taskgraph passes each task defined therein through
a series of :term:`transforms <Transform>`. These are a functions that can
modify tasks, or even split one task into many! Transforms are defined in the
``kind.yml`` file and are applied in order one after the other. Along the way,
many transform files define schemas, allowing task authors to easily reason
about the state of a task as it marches towards its final definition.

Transforms can be defined within a project (like the ``hello.py``
transforms the ``init`` command created for us), or they can live in an
external module (like Taskgraph itself). By convention, most tasks in Taskgraph
end with the transforms defined at ``taskgraph.transforms.task``, or the
"task" transforms. These special transforms perform the final changes necessary
to format them according to Taskcluster's `task definition`_ schema.

Taskgraph's combination of static configuration with logic layered on top,
allows a project's CI to grow to arbitrary complexity.


Next Steps and Further Reading
------------------------------

After you have a working Taskgraph setup, you'll still need to integrate it with
Taskcluster. See :ref:`configure your project` for more details.

Here are some more resources to help get you started:

* Learn about :doc:`task graphs and how they are generated
  <concepts/task-graphs>`.
* Create a new Taskgraph setup from scratch to better understand what
  ``taskgraph init`` accomplished for us by following the tutorials:

  * :doc:`tutorials/creating-a-task-graph`
  * :doc:`tutorials/connecting-taskcluster`
* Read more details about :doc:`kinds <concepts/kind>` and :doc:`transforms <concepts/transforms>`.
* Learn more advanced tips for :doc:`running <howto/run-locally>` and :doc:`debugging
  <howto/debugging>` Taskgraph locally.

.. _DAGs: https://en.wikipedia.org/wiki/Directed_acyclic_graph
.. _CI: https://en.wikipedia.org/wiki/Continuous_integration
.. _Taskcluster: https://taskcluster.net
.. _JSON-e: https://json-e.js.org/
.. _task definition: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema


Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   tutorials/index
   howto/index
   concepts/index
   glossary
   reference/index
   Contributing <contributing>

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
