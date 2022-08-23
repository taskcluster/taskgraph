
.. image:: https://firefox-ci-tc.services.mozilla.com/api/github/v1/repository/taskcluster/taskgraph/main/badge.svg
   :target: https://firefox-ci-tc.services.mozilla.com/api/github/v1/repository/taskcluster/taskgraph/main/latest
   :alt: Task Status

.. image:: https://results.pre-commit.ci/badge/github/taskcluster/taskgraph/main.svg
   :target: https://results.pre-commit.ci/latest/github/taskcluster/taskgraph/main
   :alt: pre-commit.ci status

.. image:: https://codecov.io/gh/taskcluster/taskgraph/branch/main/graph/badge.svg?token=GJIV52ZQNP
   :target: https://codecov.io/gh/taskcluster/taskgraph
   :alt: Code Coverage

.. image:: https://badge.fury.io/py/taskcluster-taskgraph.svg
   :target: https://badge.fury.io/py/taskcluster-taskgraph
   :alt: Pypi Version

.. image:: https://readthedocs.org/projects/taskcluster-taskgraph/badge/?version=latest
   :target: https://taskcluster-taskgraph.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

.. image:: https://img.shields.io/badge/license-MPL%202.0-orange.svg
   :target: http://mozilla.org/MPL/2.0
   :alt: License

Taskgraph
=========

Taskgraph is a Python library to generate graphs of tasks for the `Taskcluster
CI`_ service. It is the recommended approach for configuring tasks once your
project outgrows a single `.taskcluster.yml`_ file and is what powers the over
30,000 tasks and counting that make up Firefox's CI.

For more information and usage instructions, `see the docs`_.

How It Works
------------

Taskgraph leverages the fact that Taskcluster is a generic task execution
platform. This means that tasks can be scheduled via its `comprehensive API`_,
and aren't limited to being triggered in response to supported events.

Taskgraph leverages this execution platform to allow CI systems to scale to any
size or complexity.

1. A *decision task* is created via Taskcluster's normal `.taskcluster.yml`_
   file. This task invokes ``taskgraph``.
3. Taskgraph evaluates a series of yaml based task definitions (similar to
   those other CI offerings provide).
4. Taskgraph applies transforms on top of these task definitions. Transforms
   are Python functions that can programmatically alter or even clone a task
   definition.
5. Taskgraph applies some optional optimization logic to remove unnecessary
   tasks.
6. Taskgraph submits the resulting *task graph* to Taskcluster via its API.

Taskgraph's combination of declarative task configuration combined with
programmatic alteration are what allow it to support CI systems of any scale.
Taskgraph is the library that powers the 30,000+ tasks making up `Firefox's
CI`_.

.. _Taskcluster CI: https://taskcluster.net/
.. _comprehensive API: https://docs.taskcluster.net/docs/reference/platform/queue/api
.. _.taskcluster.yml: https://docs.taskcluster.net/docs/reference/integrations/github/taskcluster-yml-v1
.. _Firefox's CI: https://treeherder.mozilla.org/jobs?repo=mozilla-central
.. _see the docs: https://taskcluster-taskgraph.readthedocs.io

Installation
------------

Taskgraph supports Python 3.6 and up, and can be installed from Pypi:

.. code-block::

  pip install taskcluster-taskgraph


Alternatively, the repo can be cloned and installed directly:

.. code-block::

  git clone https://github.com/taskcluster/taskgraph
  cd taskgraph
  python setup.py install

In both cases, it's recommended to use a Python `virtual environment`_.

.. _virtual environment: https://docs.python.org/3/tutorial/venv.html

Get Involved
------------

If you'd like to get involved, please see our `contributing docs`_!

.. _contributing docs: https://github.com/taskcluster/taskgraph/blob/main/CONTRIBUTING.rst
