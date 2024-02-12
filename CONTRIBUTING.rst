Contributing to Taskgraph
=========================

Thanks for your interest in Taskgraph! To participate in this community, please
review our `code of conduct`_.

.. _code of conduct: https://github.com/taskcluster/taskgraph/blob/main/CODE_OF_CONDUCT.md

Clone the Repo
--------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the
repository, activate a virtualenv and install dependencies:

.. code-block::

  # first fork taskgraph
  git clone https://github.com/<user>/taskgraph
  cd taskgraph
  git remote add upstream https://github.com/taskcluster/taskgraph
  python -m venv taskgraph && source taskgraph/bin/activate
  pip install -r requirements/dev.txt
  python setup.py develop

Running Tests
-------------

Tests are run with the `pytest`_ framework:

.. code-block::

  pytest

We use `tox`_ to run tests across multiple versions of Python.

.. _pytest: https://pre-commit.com/
.. _tox: https://tox.wiki/en/latest/

Running Checks
--------------

Linters and formatters are run via `pre-commit`_. To install the hooks, run:

.. code-block::

   $ pre-commit install -t pre-commit -t commit-msg

Now checks will automatically run on every commit. If you prefer to run checks
manually, you can use:

.. code-block::

   $ pre-commit run

Some of the checks we enforce include `black`_, `flake8`_ and `yamllint`_. See
`pre-commit-config.yaml`_ for a full list.

.. _pre-commit: https://pre-commit.com/
.. _black: https://black.readthedocs.io
.. _flake8: https://flake8.pycqa.org/en/latest/
.. _yamllint: https://yamllint.readthedocs.io/en/stable/
.. _pre-commit-config.yaml: https://github.com/taskcluster/taskgraph/blob/main/.pre-commit-config.yaml

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

In order to release a new version of Taskgraph, you will need to:

1. Update ``CHANGELOG.md``
2. Update ``__version__`` in ``src/taskgraph/__init__.py``
3. Commit, and land the above changes with a commit message like "chore: bump <version>"
4. Create a release in Github pointing to the above commit. Be sure to also
   create a new tag matching this version.
5. Wait for the ``pypi-publish`` Github workflow and ``push-image-decision`` task to finish.
6. Verify that expected version has been published to `pypi`_ and pushed to `DockerHub`_.

.. _pypi: https://pypi.org/project/taskcluster-taskgraph
.. _DockerHub: https://hub.docker.com/r/mozillareleases/taskgraph/tags
