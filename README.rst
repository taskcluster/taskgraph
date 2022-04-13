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

  git clone https://github.com/taskcluster/taskgraph
  cd taskgraph
  python setup.py install

In both cases, it's recommended to use a Python `virtual environment`_.

.. _virtual environment: https://docs.python.org/3/tutorial/venv.html

Working on Taskgraph
--------------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the
repository, activate a virtualenv and install dependencies:

.. code-block::

  git clone https://github.com/taskcluster/taskgraph
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
When new modules are created, be sure to add an ``autodoc`` directive for
them in the source reference.

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

  pip-compile-multi -g base -g test -g dev --allow-unsafe

If you'd like to add a new package without upgrading any of the existing ones,
you can run:

.. code-block::

  pip-compile-multi -g base -g test -g dev --allow-unsafe --no-upgrade

.. _pyenv: https://github.com/pyenv/pyenv
.. _pip-compile-multi: https://pip-compile-multi.readthedocs.io/en/latest/

Releasing
---------

In order to release a new version of Taskgraph, you will need permission to the
`taskcluster-taskgraph`_ project in PyPI.
The following are **required** steps:

  1. Update ``CHANGELOG.md``
  2. Update ``version`` in ``setup.py``
  3. Commit, and land the above changes
  4. Make sure your ``hg status`` is clean
  5. Checkout the latest public revision ``hg checkout -r 'last(public())'``
  6. Pull latest revision ``hg pull -u``
  7. Verify ``hg ident`` outputs the desired revision
  8. Remove previously packaged releases ``rm -rf ./dist/*``
  9. Package the app ``python setup.py sdist bdist_wheel``
  10. Upload to PyPI using `twine`_ ``twine upload dist/*`` providing your
      username and API token

.. _taskcluster-taskgraph: https://pypi.org/project/taskcluster-taskgraph/
.. _twine: https://pypi.org/project/twine/

