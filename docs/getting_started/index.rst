Getting Started
===============

Taskgraph is a Python library to generate graphs of tasks for the `Taskcluster CI <https://taskcluster.net/>`_ service. It is
the recommended approach for configuring your tasks once your project outgrows a single `.taskcluster.yml` file.

If you're new to Taskgraph its recommended to start with the :ref:`intro-to-taskgraph` section. If you understand the basics
and want to use it in a project, you can jump to the :ref:`using-taskgraph` section.

Common tasks pertaining to contributing to Taskgraph can be found below.

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

In both cases, it's recommended to use a Python `virtual environment <https://docs.python.org/3/tutorial/venv.html>`_. Refer to the
:ref:`using-taskgraph` section for tips on how to get started with Taskgraph.

.. _working-on-taskgraph:

Working on Taskgraph
--------------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the repository, activate a virtualenv and install
dependencies:

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

We also enforce the `black <https://black.readthedocs.io>`_ formatter and `flake8 <https://flake8.pycqa.org/en/latest/>`_ linter in Taskgraph's CI:

.. code-block::

  black .
  flake8

Working with Documentation
--------------------------

The Taskgraph repo uses `Sphinx <https://www.sphinx-doc.org>`_ to generate the documentation. To work on the docs, run:

.. code-block::

  make livehtml

This will start a live server that automatically re-generates when you edit a documentation file.
Alternatively you can generate static docs under the `docs/_build` directory:

.. code-block::

  make html

Taskgraph also uses the `autodoc` extension to generate an API reference. When new modules are
created, the API docs need to be regenerated using the following command:

.. code-block::

  sphinx-apidoc -o docs/source --ext-autodoc -H "API Reference" src/taskgraph "src/taskgraph/test"

Managing Dependencies
---------------------

WARNING: Ensure you always update packages using the minimum supported Python. Otherwise you may
break the workflow of people trying to develop Taskgraph with an older version of Python. The
`pyenv <https://github.com/pyenv/pyenv>`_ tool can help with managing multiple Python versions at once.

To help lock dependencies, Taskgraph uses a tool called `pip-compile-multi <https://pip-compile-multi.readthedocs.io/en/latest/>`_. To add or update a
dependency first edit the relevant `.in` file under the `requirements` directory. If the dependency
is needed by the actual Taskgraph library, edit `requirements/base.in`. If it's required by the CI
system, edit `requirements/test.in`. And if it's only needed for developing Taskgraph, edit
`requirements/dev.in`.

Next run the following command from the repository root:

.. code-block::

  pip-compile-multi -g base -g test -g dev --allow-unsafe -P <package>

Where `<package>` is the name of the package you added or updated. Note the `-P` flag can be passed
multiple times if multiple dependencies were changed.


