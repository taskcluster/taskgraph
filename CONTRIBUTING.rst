Contributing to Taskgraph
=========================

Thanks for your interest in Taskgraph! To participate in this community, please
review our `code of conduct`_.

.. _code of conduct: https://github.com/taskcluster/taskgraph/blob/main/CODE_OF_CONDUCT.md

Clone the Repo
--------------

To contribute to Taskgraph or use the debugging tools, you'll need to clone the
repository:

.. code-block::

  # first fork taskgraph
  git clone https://github.com/<user>/taskgraph
  cd taskgraph
  git remote add upstream https://github.com/taskcluster/taskgraph

Run Taskgraph
-------------

We use a tool called `uv`_ to manage Taskgraph and its dependencies. First,
follow the `installation instructions`_. Then run:

.. code-block::

   uv run taskgraph --help

The ``uv run`` command does several things:

1. Creates a virtualenv for the project in a ``.venv`` directory (if necessary).
2. Syncs the project's dependencies as pinned in ``uv.lock`` (if necessary).
3. Installs ``taskgraph`` as an editable package (if necessary).
4. Invokes the specified command (in this case ``taskgraph --help``).

Anytime you wish to run a command within the project's virtualenv, prefix it
with ``uv run``. Alternatively you can activate the virtualenv as normal:

.. code-block::

   source .venv/bin/activate
   taskgraph --help

Just beware that with this method, the dependencies won't automatically be
synced prior to running your command. You can still sync dependencies manually
with:

.. code-block::

   uv sync

.. _uv: https://docs.astral.sh/uv/
.. _installation instructions: https://docs.astral.sh/uv/getting-started/installation/

Running Tests
-------------

Tests are run with the `pytest`_ framework:

.. code-block::

  uv run pytest

.. _pytest: https://docs.pytest.org

Running Checks
--------------

Linters and formatters are run via `pre-commit`_. To install the hooks, run:

.. code-block::

   $ pre-commit install -t pre-commit -t commit-msg

Now checks will automatically run on every commit. If you prefer to run checks
manually, you can use:

.. code-block::

   $ pre-commit run

Some of the checks we enforce include `ruff`_ and `yamllint`_. See
`pre-commit-config.yaml`_ for a full list.

.. _pre-commit: https://pre-commit.com/
.. _ruff: https://docs.astral.sh/ruff/
.. _yamllint: https://yamllint.readthedocs.io/en/stable/
.. _pre-commit-config.yaml: https://github.com/taskcluster/taskgraph/blob/main/.pre-commit-config.yaml

.. _working-on-taskgraph:

Working with Documentation
--------------------------

The Taskgraph repo uses `Sphinx`_ to generate the documentation. To work on the
docs, run:

.. code-block::

  uv run make livehtml

This will start a live server that automatically re-generates when you edit a
documentation file. Alternatively you can generate static docs under the
``docs/_build`` directory:

.. code-block::

  uv run make html

Taskgraph also uses the ``autodoc`` extension to generate an API reference.
When new modules are created, be sure to add an ``autodoc`` directive for
them in the source reference.

.. _Sphinx: https://www.sphinx-doc.org

Managing Dependencies
---------------------

Adding a New Dependency
~~~~~~~~~~~~~~~~~~~~~~~

To add a new dependency to Taskgraph, run:

.. code-block::

   uv add <dependency>

To add a new dependency that is only used in the development process, run:

.. code-block::

   uv add --dev <dependency>

Updating Existing Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you'd like to update all dependencies within their constraints defined in
the ``pyproject.toml`` file, run:

.. code-block::

   uv sync -U

Or if you'd like to update a specific dependency:

.. code-block::

   uv sync -P <package>

Releasing taskcluster-taskgraph
-------------------------------

In order to release a new version of Taskgraph, you will need to:

1. Update ``CHANGELOG.md``
2. Update ``version`` in ``pyproject.toml``
3. Run ``uv lock``
4. Commit, and land the above changes with a commit message like "chore: bump <version>"
5. Draft a release in Github pointing to the above commit.

   a. Create a new tag of the form ``X.Y.Z``
   b. Ensure "Set as latest release" is checked
   c. Submit the release

6. Wait for the ``pypi-publish`` Github workflow and ``push-image-decision`` task to finish.
7. Verify that expected version has been published to `pypi
   <https://pypi.org/project/taskcluster-taskgraph>`__ and pushed to `DockerHub`_.

.. _DockerHub: https://hub.docker.com/r/mozillareleases/taskgraph/tags

Releasing pytest-taskgraph
--------------------------

There's also a Pytest plugin packaged under ``packages/pytest-taskgraph``. The
release process for this package is:

1. Update ``version`` in ``packages/pytest-taskgraph/pyproject.toml``, and run ``uv lock``
2. Commit and land the changes with a commit message like "chore: bump pytest-taskgraph <version>"
3. Draft a release in Github pointing to the above commit.

   a. Create a new tag of the form ``pytest-taskgraph-vX.Y.Z``
   b. Uncheck "Set as latest release"
   c. Submit the release

4. Wait for the ``pypi-publish`` Github workflow to finish.
5. Verify that expected version has been published to `pypi <https://pypi.org/project/pytest-taskgraph>`__.


Building the Package
--------------------

Typically building the package manually is not required, as this is handled in
automation prior to release. However, if you'd like to test the package builds
manually, you can do so with:

.. code-block::

   uvx --from build pyproject-build --installer uv

Source and wheel distributions will be available under the ``dist/`` directory.
