Bootstrap Taskgraph in Decision Task
====================================

This how-to guide outlines the recommended way to bootstrap Taskgraph (and
other task generation dependencies) in a :term:`Decision Task`.

Using the Pre-Built Docker Images
---------------------------------

The simplest way to make Taskgraph available to your Decision task is to use
Taskgraph's pre-built Docker images under the `mozillareleases/taskgraph`_ Docker Hub
repository.

In your Decision task definition in ``.taskcluster.yml``, add the following to the task's
``payload`` section:

.. code-block:: yaml

   payload:
     image: mozillareleases/taskgraph:decision-latest

This will ensure your Decision task always run with the latest version of Taskgraph.
Of course, it's best practice to pin your CI dependencies, so it's recommended to pin
to a specific version:

.. code-block:: yaml

   payload:
     image: mozillareleases/taskgraph:decision-v7.3.0

While not required, it's also best practice to specify the image hash:

.. code-block:: yaml

   payload:
     image: mozillareleases/taskgraph:decision-v7.3.0@sha256:f954e54d427d08b18954a4ff4541d43c76c476d0738f341e4fa82a959939d3fa

The hash can be found on the Docker Hub page for the specific tag you are
pinning to.

.. _mozillareleases/taskgraph: https://hub.docker.com/r/mozillareleases/taskgraph/tags


Using a Python Requirements File
--------------------------------

Sometimes you might have more complex generation logic that requires other
packages in addition to ``taskgraph``. In this case you'll want to use a
`requirements file`_.

Like before, we'll use a pre-built Docker image provided by Taskgraph:

.. code-block:: yaml

   payload:
     image: mozillareleases/taskgraph:run-task-v7.3.0

The only difference with this ``run-task`` image, is that it *only* contains
the ``run-task`` script necessary to bootstrap the repository and not the full
Taskgraph package. It leaves how to get Taskgraph bootstrapped into the task up
to you.

This section outlines the recommended way to do that.

.. note::
   If you'd like to follow along, you can download the example
   :download:`.taskcluster.yml </tutorials/example-taskcluster.yml>` file.

.. _requirements file: https://pip.pypa.io/en/stable/reference/requirements-file-format/

.. _define requirements:

Define Requirements
~~~~~~~~~~~~~~~~~~~

We'll use a tool called `pip-compile`_ to help generate the
``requirements.txt`` that will contain our Decision task dependencies,
including Taskgraph itself.

.. note::

   You may use other tools to create the ``requirements.txt``, such as
   `hashin`_. As long as package hashes are included.

First make sure you have ``pip-compile`` installed:

.. code-block:: bash

   pip install pip-tools

Next, create the ``requirements.in`` file. For this example, let's pretend that
in addition to ``taskcluster-taskgraph`` we also want to depend on
``requests``:

.. code-block:: bash

   cd taskcluster
   cat << EOF > requirements.in
   taskcluster-taskgraph
   requests
   EOF

   # This works best if you use the same Python as the one used in the Decision
   # image (currently 3.11).
   pip-compile --generate-hashes --output-file requirements.txt requirements.in

.. note::

   You may add `version specifiers`_ to packages (e.g,
   ``taskcluster-taskgraph==7.3.0``), but either way the actual version that
   gets used will be pinned once we generate the ``requirements.txt``.

If you end up creating transforms that require additional packages, add them to
``requirements.in`` and re-generate the lock file.

.. _pip-compile: https://github.com/jazzband/pip-tools
.. _hashin: https://github.com/peterbe/hashin
.. _version specifiers: https://pip.pypa.io/en/stable/cli/pip_install/#requirement-specifiers

Instruct ``run-task`` to Install Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `docker images`_ provided by Taskgraph contain a script called `run-task`_.
This script acts as a wrapper around the command you'd like to run and handles
some initial setup such as cloning repositories needed by the task.

When ``run-task`` clones a repository, it can optionally install Python
dependencies that are defined within it. We accomplish this with a set of
environment variables and a command line argument. Let's assume the repo is
called ``myrepo``.

In the Decision task definition (in ``.taskcluster.yml``), we first define an
env called ``REPOSITORIES``:

.. code-block:: yaml

   payload:
       env:
           REPOSITORIES: {$json: {myrepo: "My Repository"}}

This tells ``run-task`` which repositories will need to be cloned. For this guide,
we'll only be cloning our single repository.

Next we define some environment variables that will tell ``run-task`` *how* to clone the
repo. Each environment variable is uppercase prefixed by the key you specified in the
``REPOSITORIES`` env:

.. code-block:: yaml

   payload:
       env:
           REPOSITORIES: {$json: {myrepo: "My Repository"}}
           MYREPO_HEAD_REPOSITORY: <repository url>
           MYREPO_HEAD_REF: <branch or ref to fetch>
           MYREPO_HEAD_REV: <revision to checkout>
           MYREPO_REPOSITORY_TYPE: git
           MYREPO_PIP_REQUIREMENTS: taskcluster/requirements.txt

The last environment variable should point at the ``requirements.txt`` file we
just created.

Finally, we pass in the ``--myrepo-checkout`` flag to ``run-task``. The name of
the argument again depends on the key you defined in the ``REPOSITORIES`` env:

.. code-block:: yaml

   payload:
       command:
           - /usr/local/bin/run-task
           - '--myrepo-checkout=/builds/worker/checkouts/myrepo'
           - ...

Now ``run-task`` will both clone your repo, as well as install any packages
defined in ``taskcluster/requirements.txt``, ensuring Taskgraph is bootstrapped
and ready to go.

.. _docker images: https://hub.docker.com/repository/docker/mozillareleases/taskgraph
.. _run-task: https://github.com/taskcluster/taskgraph/blob/main/src/taskgraph/run-task/run-task

Upgrading Taskgraph
~~~~~~~~~~~~~~~~~~~

To upgrade Taskgraph to a newer version, re-generate the ``requirements.txt``
file:

.. code-block:: shell

   cd taskcluster
   pip-compile --generate-hashes --output-file requirements.txt requirements.in

If you pinned the package to a specific version don't forget to update
``requirements.in`` first.

.. note::

   Taskgraph follows `semantic versioning`_, so minor
   and patch versions should be fully backwards compatible.

.. _semantic versioning: https://semver.org

Testing Pre-Release Versions of Taskgraph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes you may wish to test against pre-release revisions of Taskgraph,
especially if you are working on changes to Taskgraph itself. This can be
accomplished using `pip's version control support`_:

.. code-block:: shell

   cd taskcluster
   echo "taskcluster-taskgraph@git+https://github.com/taskcluster/taskgraph@refs/pull/123/head" > requirements.in
   pip-compile --output-file requirements.txt requirements.in

Next edit your ``.taskcluster.yml`` to disable hashing since pip does not
support `hashes with url requirements`_:

.. code-block:: yaml

   payload:
      env:
          PIP_DISABLE_REQUIRE_HASHES: 1

.. note::

   Be sure to omit the ``--generate-hashes`` argument to ``pip-compile``
   otherwise ``pip`` will implicitly turn hashing back on.

This way you can push an experimental change to a PR and then install it in
your repo's decision task.

.. _pip's version control support: https://pip.pypa.io/en/stable/topics/vcs-support/
.. _hashes with url requirements: https://github.com/pypa/pip/issues/6469
