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

Installation
------------

Taskgraph is on Pypi and can be installed via:

.. code-block::

   pip install taskcluster-taskgraph

This provides the ``taskgraph`` binary, see ``taskgraph --help`` for available
commands. To integrate Taskgraph in your project, see :ref:`adding taskgraph`.


.. _DAGs: https://en.wikipedia.org/wiki/Directed_acyclic_graph
.. _CI: https://en.wikipedia.org/wiki/Continuous_integration
.. _Taskcluster: https://taskcluster.net

Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   usage/using_taskgraph
   usage/debugging_and_testing
   concepts/index
   Contributing <contributing>
   source/modules

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
