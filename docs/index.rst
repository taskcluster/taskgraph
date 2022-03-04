.. taskgraph documentation master file, created by
   sphinx-quickstart on Thu Nov 11 18:38:14 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Taskgraph
=========

Taskgraph is a Python library to generate `DAGs`_ of tasks for `Taskcluster`_,
Mozilla's `CI`_ service. The nodes of the DAG represent tasks, while the edges
represent the dependencies between them.

Taskgraph is designed to scale to any level of complexity. From a handful of
tasks, to the over 30,000 tasks and counting that make up Firefox's CI.

.. _installation:

Installation
------------

Taskgraph is on Pypi and can be installed via:

.. code-block::

   pip install taskcluster-taskgraph

This provides the ``taskgraph`` binary, see ``taskgraph --help`` for available
commands. To integrate Taskgraph in your project, see
:doc:`tutorials/creating-a-task-graph`.

Alternatively you can install it by cloning the repo. This is useful if you
need to test against a specific revision:

.. code-block::

   hg clone https://hg.mozilla.org/ci/taskgraph
   cd taskgraph
   python setup.py develop


How It Works
------------

Taskcluster tasks are defined in the ``tasks`` section of a `.taskcluster.yml`_
file at the repository root. This is adequate for simple CI systems which only
have a few tasks. But as the complexity of a CI system grows, trying to fit
all task definitions into a single file becomes difficult to maintain.

Instead of defining everything in the `.taskcluster.yml`_, Taskgraph consumers
define only a single task called the :ref:`decision task`. This task runs the
command ``taskgraph decision`` which at a very high level:

1. Reads a set of input YAML files defining :term:`tasks <Task>`.
2. Runs each task definition through a set of :term:`transforms <Transform>`.
3. Submits the resulting DAG of tasks (with Decision task as the root) to
   Taskcluster via its REST API.

Taskgraph's combination of static configuration with logic layered on top,
allows a project's CI to grow to arbitrary complexity.


.. _DAGs: https://en.wikipedia.org/wiki/Directed_acyclic_graph
.. _CI: https://en.wikipedia.org/wiki/Continuous_integration
.. _Taskcluster: https://taskcluster.net
.. _.taskcluster.yml: https://docs.taskcluster.net/docs/reference/integrations/github/taskcluster-yml-v1

Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   tutorials/index
   howto/index
   concepts/index
   glossary
   source/modules
   Contributing <contributing>

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
