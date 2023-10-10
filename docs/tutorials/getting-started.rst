Getting Started
===============

This tutorial will guide you towards a working Taskcluster + Taskgraph setup
with your repo in as few steps as possible.

.. note::

   This tutorial has a heavy focus on the end result. If you prefer to build
   understanding as you go, you may wish to follow the
   :doc:`creating-a-task-graph` and :doc:`connecting-taskcluster` tutorials
   instead.

There are three steps to getting running tasks:

1. Install Taskcluster Github
2. Request Permissions
3. Define Tasks

Let's dive into each!

Install Taskcluster Github
--------------------------

.. note::

   If you are not using Github, skip to the next section.

Each Taskcluster deployment has an associated Github app that needs to be added
to your repo. Some apps for known Taskcluster deployments are as follows:

.. list-table:: Taskcluster Github Apps
   :widths: 20 60
   :header-rows: 1

   * - Instance
     - Github App
   * - `Firefox-CI <https://firefox-ci-tc.services.mozilla.com>`_
     - https://github.com/apps/firefoxci-taskcluster
   * - `Community <https://community-tc.services.mozilla.com>`_
     - https://github.com/apps/community-tc-integration

Follow the link to the Github app for your deployment and click ``Configure``
near the top right. Then select the repository you'd like to enable. If you are
not an admin of the organization you are enabling the repo for, this will send
a request to your Github administrators.

.. note::

   If you do not see a ``Configure`` button, contact your Github administrators
   for assistance.

Request Permissions
-------------------

Your repository is now connected to Taskcluster, but it won't have permission
to run anything. In the Taskcluster world, permissions are also known as
:term:`scopes <Scope>`. So the next step is to contact your Taskcluster
administrators and request scopes for your project so that it has access to the
resources it needs to run tasks.

Each Taskcluster instance can be managed differently, but here are the processes
to request scopes for some known Taskcluster deployments:

.. list-table:: Taskcluster Github Apps
   :widths: 20 60
   :header-rows: 1

   * - Instance
     - Process
   * - `Firefox-CI <https://firefox-ci-tc.services.mozilla.com>`_
     - `File a Bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Release%20Engineering&component=Firefox-CI%20Administration>`_
   * - `Community <https://community-tc.services.mozilla.com>`_
     - `File an Issue <https://github.com/taskcluster/community-tc-config/issues/new>`_

Use a title such as: *Please setup `org/my-repo` with Taskcluster*.

Create Tasks
------------

The last step is to define your tasks. You'll need:

1. A :term:`Decision Task` defined in ``.taskcluster.yml``
2. A Taskgraph setup in the ``taskcluster`` directory

Luckily Taskgraph provides an ``init`` command that can generate both of these
things automatically! Run:

.. code-block:: shell

   $ pip install taskcluster-taskgraph
   $ taskgraph init

This will automatically generate all the necessary files. Commit what was
generated:

.. code-block:: shell

   $ git add .
   $ git commit -m "Add Taskcluster files"

Now when you push, you should have a working Decision task that generates a
``hello-world`` task as well as a ``docker-image`` task that it depends on!

Further Reading
---------------

Now that you have a working Taskcluster setup, explore these docs to learn more
about using Taskgraph!

If you'd like to understand more about the files that the ``taskgraph init``
command generated, you can follow the :doc:`creating-a-task-graph` and
:doc:`connecting-taskcluster` tutorials

Check out the :doc:`/concepts/index` page if you'd like to learn more about how
Taskgraph works.

Or if you are ready to dive into creating more tasks, you may wish to learn how
to:

* :doc:`/howto/create-tasks`
* :doc:`/howto/run-locally`
* :doc:`/howto/debugging`
* :doc:`/howto/use-fetches`
* :doc:`/howto/docker`
