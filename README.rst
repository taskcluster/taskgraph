Taskgraph
=========

Taskgraph is a Python library to generate graphs of tasks for the `Taskcluster
CI`_ service. It is the recommended approach for configuring your tasks once
your project outgrows a single `.taskcluster.yml` file.

For more information and usage instructions, `see the docs`_.

.. _Taskcluster CI: https://taskcluster.net/
.. _see the docs: https://taskcluster-taskgraph.readthedocs.io

Installation
------------

Taskgraph supports Python 3.6 and up, and can be installed from Pypi:

.. code-block::

  pip install taskcluster-taskgraph


Alternatively, the repo can be cloned and installed directly:

.. code-block::

  hg clone https://hg.mozilla.org/ci/taskgraph
  cd taskgraph
  python setup.py install

In both cases, it's recommended to use a Python `virtual environment`_.

.. _virtual environment: https://docs.python.org/3/tutorial/venv.html

Working on Taskgraph
--------------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the
repository, activate a virtualenv and install dependencies:

.. code-block::

  hg clone https://hg.mozilla.org/ci/taskgraph
  cd taskgraph
  python -m venv taskgraph && source taskgraph/bin/activate
  pip install -r requirements/dev.txt
  $ python setup.py develop

Running Tests and Linters
-------------------------

Tests are run with the `pytest <https://docs.pytest.org>`_ framework:

.. code-block::

  pytest src

We also enforce the `black`_ formatter and `flake8`_ linter in Taskgraph's CI:

.. code-block::

  black .
  flake8

.. _black: https://black.readthedocs.io
.. _flake8: https://flake8.pycqa.org/en/latest/

.. _working-on-taskgraph:

Working with Documentation
--------------------------

The Taskgraph repo uses `Sphinx`_ to generate the documentation. To work on the
docs, run:

.. code-block::

  make livehtml

This will start a live server that automatically re-generates when you edit a
documentation file. Alternatively you can generate static docs under the
``docs/_build`` directory:

.. code-block::

  make html

Taskgraph also uses the ``autodoc`` extension to generate an API reference.
When new modules are created, the API docs need to be regenerated using the
following command:

.. code-block::

  sphinx-apidoc -o docs/source --ext-autodoc -H "API Reference" src/taskgraph "src/taskgraph/test"

.. _Sphinx: https://www.sphinx-doc.org

Managing Dependencies
---------------------

.. warning:: 
   Ensure you always update packages using the minimum supported Python.
   Otherwise you may break the workflow of people trying to develop Taskgraph
   with an older version of Python. The `pyenv`_ tool can help with managing
   multiple Python versions at once.

To help lock dependencies, Taskgraph uses a tool called `pip-compile-multi`_.
To add or update a dependency first edit the relevant ``.in`` file under the
``requirements`` directory. If the dependency is needed by the actual Taskgraph
library, edit ``requirements/base.in``. If it's required by the CI system, edit
``requirements/test.in``. And if it's only needed for developing Taskgraph,
edit ``requirements/dev.in``.

Next run the following command from the repository root:

.. code-block::

  pip-compile-multi -g base -g test -g dev --allow-unsafe -P <package>

Where ``<package>`` is the name of the package you added or updated. Note the
``-P`` flag can be passed multiple times if multiple dependencies were changed.

.. _pyenv: https://github.com/pyenv/pyenv
.. _pip-compile-multi: https://pip-compile-multi.readthedocs.io/en/latest/
