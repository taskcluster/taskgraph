Setting up Taskgraph
====================

This tutorial will walk you through getting your repository set up with
Taskgraph for the first time.

Configuring your Project
------------------------

Every Taskcluster instance has a set of configured repositories, with associated
:term:`scopes <Scope>`, worker pools, a :term:`trust domain <Trust Domain>`,
and more. So the first phase is to talk to your Taskcluster administrator and ask
them to help get your repository configured.

.. note::

   The configuration is typically managed by the `tc-admin`_ tool in its own
   dedicated repository. Here are some configuration repositories for known
   Taskcluster instances:

   * `Firefox-CI configuration`_ (managed by the Release Engineering team)
   * `Community configuration`_ (managed by the Taskcluster team)



If using Github, you'll also need to install the `Taskcluster Github
integration`_. Please note that only org administrators can enable the
integration.

.. note::

   The specific integration app depends on the Taskcluster instance you are
   using. Here are the Github integrations for known Taskcluster instances:

   * `Firefox-CI Github integration`_
   * `Community Github integration`_

.. _tc-admin: https://github.com/taskcluster/tc-admin
.. _Firefox-CI configuration: https://hg.mozilla.org/ci/ci-configuration/
.. _Community configuration: https://github.com/mozilla/community-tc-config
.. _Taskcluster Github integration: https://docs.taskcluster.net/docs/manual/using/github
.. _Firefox-CI Github integration: https://github.com/apps/firefoxci-taskcluster
.. _Community Github integration: https://github.com/apps/community-tc-integration

Create the Taskgraph Scaffolding
--------------------------------

The next phase is to create the scaffolding for Taskgraph. For now we'll set up
a single "Hello World" task. Once this is working, you will have the tools and
knowledge to start adding your own tasks, and modifying configuration to meet
your repository's needs.

Create the File System Layout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a file system layout similar to:

::

   taskcluster
   ├── requirements.in
   ├── ci
   │   ├── config.yml
   │   └── hello
   |       └── kind.yml
   └── myrepo_taskgraph
       └── transforms
           └── hello.py

The ``taskcluster`` directory should appear at the root of the repository. It
is possible to rename / put it somewhere else, but you'll need to jump through
a couple extra steps in that case. The location of the transforms file is
similarly only a convention (but it must be importable).

Populate the Config File
~~~~~~~~~~~~~~~~~~~~~~~~

The config file lives at ``taskcluster/ci/config.yml`` and must conform to the
:py:data:`~taskgraph.config.graph_config_schema`.

The required top-level keys are:

* ``trust-domain`` - This should match what was configured in the first phase. If
  :term:`trust domains <Trust Domain>` are not used in your instance, just use the
  repository name.
* ``task-priority`` - The priority of tasks for this repo.
* ``workers`` - The set of worker pools available to the project. This should
  have been configured in the first phase, speak to your Taskcluster administrator
  if unsure what to use.
* ``taskgraph`` - A dict containing some miscellaneous configuration needed by
  Taskgraph.

Here's an example of what a bare ``config.yml`` might look like:

.. code-block:: yaml

   ---
   trust-domain: myrepo
   task-priority: low
   workers:
       # Values here depend on your Taskcluster instance's configuration.
       aliases:
           linux:
               provisioner: '{trust-domain}-provisioner'
               implementation: docker-worker
               os: linux
               worker-type: '{trust-domain}-linux'
   taskgraph:
       repositories:
           myrepo:
               name: myrepo

Define a Task
~~~~~~~~~~~~~

:term:`Kinds <Kind>` are groupings of tasks that share certain characteristics
with one another. Each subdirectory in ``taskcluster/ci`` corresponds to a
different kind and contains a ``kind.yml`` file. These files define some
properties that control how Taskgraph will generate the tasks, as well as the
starting definitions of the tasks themselves. If you followed the layout above,
you have a ``hello`` kind.

#. First declare a loader. Loaders determine how the task definitions get read.
   The most common is the :func:`transform loader
   <taskgraph.loader.transform.loader>`:

   .. code-block:: yaml

    loader: taskgraph.loader.transform:loader

#. Next declare the set of :term:`transforms <transform>` that will be applied
   to tasks. Usually there is at least a kind specific set of transforms, as
   well as the general purpose :mod:`~taskgraph.transforms.task` transforms.
   Practically every task should use the latter, as they perform the final
   steps to modify the tasks into the `format Taskcluster expects`_. In our
   example:

   .. code-block:: yaml

    transforms:
        - myrepo_taskgraph.transforms.hello:transforms
        - taskgraph.transforms.task:transforms

#. Finally we define the task under the (confusingly named) ``jobs`` key.
   The format for the initial definition here can vary wildly from one kind
   to another, it all depends on the transforms that are used. It's conventional
   for transforms to define a schema (but not required). So often you can look
   at the first transform file to see what schema is expected of your job. But
   since we haven't created the first transforms yet, let's define our task
   like this for now:

   .. code-block:: yaml

    jobs:
        taskcluster:
            description: "Says hello to Taskcluster"
            text: "Taskcluster!"

Here is the combined ``kind.yml`` file:

.. code-block:: yaml

 loader: taskgraph.loader.transform:loader
 transforms:
     - myrepo_taskgraph.transforms.hello:transforms
     - taskgraph.transforms.task:transforms
 jobs:
     taskcluster:
         description: "Says hello to Taskcluster"
         text: "Taskcluster!"

Create the Transform
~~~~~~~~~~~~~~~~~~~~

:term:`Transforms <Transform>` are Python generators that take a
:class:`~taskgraph.transforms.base.TransformConfig` instance and a generator
that yields task definitions (in dictionary form) as input. It yields task
definitions (which may or may not be modified) from the original inputs.

Typically transform files contain a schema, followed by one or more transform
functions. Rather than break it down step by step, here's what our transform file
will look like (see comments for explanations):

.. code-block:: python

   from voluptuous import Optional, Required

   from taskgraph.transforms.base import TransformSequence
   from taskgraph.util.schema import Schema

   # Define the schema. We use the `voluptuous` package to handle validation.
   hello_description_schema = Schema({
       Required("text"): str,
       Optional("description"): str,
   })

   # Create a 'TransformSequence' instance. This class collects transform
   # functions to run later.
   transforms = TransformSequence()

   # First let's validate tasks against the schema.
   transforms.add_validate(hello_description_schema)

   # Register our first transform functions via decorator.
   @transforms.add
   def set_command(config, tasks):
       """Builds the command the task will run."""
       for task in tasks:
           task["command"] = f"bash -cx 'echo Hello {task.pop('text')}'"
           yield task

   @transforms.add
   def build_task_description(config, tasks):
       """Sets the attributes required by transforms in
       `taskgraph.transforms.task`"""
       for task in tasks:
           if "description" not in task:
               task["description"] = f"Says Hello {task['text']}"
           task["label"] = f"{config.kind}-{task.pop('name')}"
           # This is what was defined in `taskcluster/ci/config.yml`.
           task["worker-type"] = "linux"
           task["worker"] = {
               "command": task.pop["command"],
               "docker-image": "ubuntu:latest",
               "max-run-time": 300,  # seconds
           }
           yield task

.. _format Taskcluster expects: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema

Generate the Taskgraph
~~~~~~~~~~~~~~~~~~~~~~

Now it's time to see if everything works! If you haven't done so already,
follow the :ref:`installation` docs to install Taskgraph.

Next run the following command at the root of your repo:

.. code-block:: bash

 taskgraph full

If all goes well, you should see some log output followed by a single task
called ``hello-taskcluster``. Try adding a second task to your ``jobs`` key
in the ``kind.yml`` file and re-generating the graph. You should see both
task labels!

You can also pass in the ``-J/--json`` flag to see the JSON definition of your
tasks. This is what will be sent to Taskcluster! For more information on generating
graphs locally, see :doc:`/howto/debugging_and_testing`.

Populate the Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~

Finally, let's populate the requirements file. This will be used by the decision task
later on to install any dependencies needed to generate the graph. This will at least
include Taskgraph itself. We'll use a tool called `pip-compile`_ to help generate the
``requirements.txt``.

.. note::

   You may use other tools to create the ``requirements.txt`` as well, such as
   `hashin`_. As long as package hashes are included.

Run:

.. code-block:: bash

   cd taskcluster
   echo "taskcluster-taskgraph" > requirements.in
   # This works best if you use the same Python as the one used in the Decision
   # image (currently 3.6).
   pip-compile --generate-hashes --output-file requirements.txt requirements.in

If you intend to create transforms that require additional packages, feel free
to add them here as well. You may also use `version specifiers`_.

.. _pip-compile: https://github.com/jazzband/pip-tools
.. _hashin: https://github.com/peterbe/hashin
.. _version specifiers: https://pip.pypa.io/en/stable/cli/pip_install/#requirement-specifiers

Defining the Decision Task
--------------------------

So far we've:

1. Enabled our repository in Taskcluster's configuration.
2. Created the Taskgraph scaffolding and defined a task or two.
3. Tested out generating the graph locally.

The last phase connects the previous two phases by declaring when and how the
graph will be generated in response to various repository actions (like pushing
to the main branch or opening a pull request). To do this we define a
:ref:`decision task` in the repository's ``.taskcluster.yml`` file. If you
don't have a ``.taskcluster.yml`` file, create it using the `documentation`_
and/or `Github quickstart`_ resources.

.. note::

   The ``.taskcluster.yml`` file uses `JSON-e`_. If you are confused about the
   syntax, see the `JSON-e reference`_ or `playground`_ to learn more.

There are many different ways you could
set up the :ref:`decision task`. But here is the recommended method:

#. Setup the initial ``.taskcluster.yml``:

   .. code-block:: yaml

    ---
    version: 1
    reporting: checks-v1
    policy:
        pullRequests: collaborators
    tasks:
        -

#. It's often useful to define some variables that can be used later on in the
   file. We'll start by defining a :term:`Trust Domain`:

   .. code-block:: yaml

    tasks:
        - $let:
              trustDomain: my-project

   If using a Taskcluster instance that doesn't use trust domains, this part
   can be skipped.

#. If using Github, you'll want to define additional variables based on the Github
   `push`_, `pull request`_ or `release`_ events. For example:

   .. code-block:: yaml

    tasks:
        - $let:
              trustDomain: my-project

              # Normalize some variables that differ across Github events
              ownerEmail:
                  $if: 'tasks_for == "github-push"'
                  then: '${event.pusher.email}'
                  else:
                      $if: 'tasks_for == "github-pull-request"'
                      then: '${event.pull_request.user.login}@users.noreply.github.com'
                      else:
                          $if: 'tasks_for == "github-release"'
                          then: '${event.sender.login}@users.noreply.github.com'
              baseRepoUrl:
                  $if: 'tasks_for == "github-push"'
                  then: '${event.repository.html_url}'
                  else:
                      $if: 'tasks_for == "github-pull-request"'
                      then: '${event.pull_request.base.repo.html_url}'
              repoUrl:
                  $if: 'tasks_for == "github-push"'
                  then: '${event.repository.html_url}'
                  else:
                      $if: 'tasks_for == "github-pull-request"'
                      then: '${event.pull_request.head.repo.html_url}'
              project:
                  $if: 'tasks_for == "github-push"'
                  then: '${event.repository.name}'
                  else:
                      $if: 'tasks_for == "github-pull-request"'
                      then: '${event.pull_request.head.repo.name}'
              headBranch:
                  $if: 'tasks_for == "github-pull-request"'
                  then: ${event.pull_request.head.ref}
                  else:
                      $if: 'tasks_for == "github-push"'
                      then: ${event.ref}
              headSha:
                  $if: 'tasks_for == "github-push"'
                  then: '${event.after}'
                  else:
                      $if: 'tasks_for == "github-pull-request"'
                      then: '${event.pull_request.head.sha}'

   This isn't strictly necessary, but the format of the various Github events
   can vary considerably. By normalizing some of these values into variables
   early on, we can save considerable logic later in the file.

   Here's `Fenix's .taskcluster.yml`_ for an idea of other variables that may
   be useful to define.

#. Next we determine whether or not to generate tasks at all. For example, we
   may only want to run CI tasks on the ``main`` branch or with certain pull
   request actions. The easiest way to accomplish this is a `JSON-e if
   statement`_ which has no ``else`` clause (i.e, no task definition):

   .. code-block:: yaml

    tasks:
        - $let:
              ...
          in:
              $if: >
                  tasks_for == "github-push" && headBranch == "main"
                  || (tasks_for == "github-pull-request" && ${event.action} in ["opened", "reopened", "synchronize"])
              then:
                  # Task definition goes here. Since there is no "else" clause, if
                  # the above if statement evaluates to false, there will be no
                  # decision task.

#. Up to this point, we've defined some variables and decided when to generate
   tasks. Now it's time to create the Decision task definition! Like any task,
   the Decision task must conform to `Taskcluster's task schema`_. From here on
   out each step will highlight important top-level keys in the task
   definition. Depending on the key you may wish to use static values or JSON-e
   logic as necessary.

   a. Define ``taskId`` and ``taskGroupId``. This is passed into the
      ``.taskcluster.yml`` context as ``ownTaskId``. Decision tasks have
      ``taskGroupId`` set to their own id:

      .. code-block:: yaml

       then:
           taskId: '${ownTaskId}'
           taskGroupId: '${ownTaskId}'

   b. Define date fields. JSON-e has a convenient `fromNow`_ operator which can help
      populate the date fields like ``created``, ``deadline`` and ``expires``:

      .. code-block:: yaml

       then:
           created: {$fromNow: ''}
           deadline: {$fromNow: '1 day'}
           expires: {$fromNow: '1 year 1 second'}  # 1 second so artifacts expire first, despite rounding errors

   c. Define metadata:

      .. code-block:: yaml

       then:
           metadata:
               owner: "${ownerEmail}"
               name: "Decision Task"
               description: "Task that generates a taskgraph and submits it to Taskcluster"
               source: '${repoUrl}/raw/${headSha}/.taskcluster.yml'

   d. Define the ``provisionerId`` and ``workerType``. These values will depend on
      the Taskcluster configuration created for your repo in the first phase.
      Talk to an administrator if you are unsure what to use. For now, let's
      assume they are set as follows:

      .. code-block:: yaml

       then:
           provisionerId: "${trustDomain}-provisioner"
           workerType: "decision"

   e. Define :term:`scopes <Scope>`. Decision tasks need to have scopes to do
      anything other tasks in the graph do. While you could list them all out
      individually here, a better practice is to create a "role" associated with
      your repository in the Taskcluster configuration. Then all you need to do
      in your task definition is "assume" that role:

      .. code-block:: yaml

       then:
           scopes:
               $if: 'tasks_for == "github-push"'
               then:
                   # ${repoUrl[8:]} strips out the leading 'https://'
                   # while ${headBranch[11:]} strips out 'refs/heads/'
                   - 'assume:repo:${repoUrl[8:]}:branch:${headBranch[11:]}'
               else:
                   $if: 'tasks_for == "github-pull-request"'
                   then:
                       - 'assume:repo:github.com/${event.pull_request.base.repo.full_name}:pull-request'

      Notice how we assume different roles depending on whether the task is
      coming from a push or a pull request. This is useful when you have tasks
      that handle releases or other sensitive operations. You don't want those
      accidentally running on a pull request! By using different scopes, you can
      ensure it won't ever happen.

      The roles assumed above may vary depending on the Taskcluster
      configuration.

#. Last but not least we define the payload, which controls what the task
   actually does. The schema for the payload depends on the worker
   implementation your provisioner uses. This will typically either be
   `docker-worker`_ or `generic-worker`_. For now it's recommended to use the
   older ``docker-worker`` as that provides a simpler interface to Docker. But
   as ``generic-worker`` matures it will eventually subsume ``docker-worker``.
   For now, this tutorial will assume we're using the `docker-worker
   payload`__.

   a. Define the image. Taskgraph conveniently provides pre-built images for
      certain Decision task contexts. These are:

      * ``taskgraph:decision`` - A general purpose image.
      * ``taskgraph:decision-mobile`` - Built on top of ``taskgraph:decision`` with
        some additions needed for Android applications at Mozilla.

      You may also build your own image if desired, either on top of
      ``taskgraph:decision`` or from scratch. For this tutorial we'll just
      use the general purpose image:

      .. code-block:: yaml

       then:
           payload:
               image:
                   mozillareleases/taskgraph:decision-cf4b4b4baff57d84c1f9ec8fcd70c9839b70a7d66e6430a6c41ffe67252faa19@sha256:425e07f6813804483bc5a7258288a7684d182617ceeaa0176901ccc7702dfe28

      You should use the `latest versions of the images`_. Note that both the
      image id and sha256 are required (separated by ``@``).

   b. Enable the `taskclusterProxy`_ feature.

      .. code-block:: yaml

       then:
           payload:
               feature:
                   taskclusterProxy: true

   c. Define the environment and command. The Taskgraph docker images have a
      script called `run-task`_ baked in. Using this script is optional, but
      provides a few convenient wrappers for things like pulling your
      repository into the task and installing Taskgraph itself. You can specify
      repositories to clone via a combination of commandline arguments and
      environment variables. The final argument to ``run-task`` is the command
      we want to run, which in our case is ``taskgraph decision``. Here's an
      example:

      .. code-block:: yaml

       then:
           payload:
               env:
                   $merge:
                       # run-task uses these environment variables to clone your
                       # repo and checkout the proper revision
                       - MYREPO_BASE_REPOSITORY: '${baseRepoUrl}'
                         MYREPO_HEAD_REPOSITORY: '${repoUrl}'
                         MYREPO_HEAD_REF: '${headBranch}'
                         MYREPO_HEAD_REV: '${headSha}'
                         # run-task installs this requirements.txt before
                         # running your command
                         MYREPO_PIP_REQUIREMENTS: taskcluster/requirements.txt
                         REPOSITORIES: {$json: {myrepo: "MyRepo"}}
                       - $if: 'tasks_for in ["github-pull-request"]'
                         then:
                             MYREPO_PULL_REQUEST_NUMBER: '${event.pull_request.number}'
               command:
                   - /usr/local/bin/run-task
                   # This 'myrepo' gets uppercased and is how `run-task`
                   # knows to look for 'MYREPO_*' environment variables.
                   - '--myrepo-checkout=/builds/worker/checkouts/myrepo'
                   - '--task-cwd=/builds/worker/checkouts/myrepo'
                   - '--'
                   # Now for the actual command.
                   - bash
                   - -cx
                   - >
                     ~/.local/bin/taskgraph decision
                     --pushlog-id='0'
                     --pushdate='0'
                     --project='${project}'
                     --message=""
                     --owner='${ownerEmail}'
                     --level='1'
                     --base-repository="$MYREPO_BASE_REPOSITORY"
                     --head-repository="$MYREPO_HEAD_REPOSITORY"
                     --head-ref="$MYREPO_HEAD_REF"
                     --head-rev="$MYREPO_HEAD_REV"
                     --repository-type="$MYREPO_REPOSITORY_TYPE"
                     --tasks-for='${tasks_for}'

For convenience, the full ``.taskcluster.yml`` can be :download:`downloaded
here <example-taskcluster.yml>`.

Testing it Out
~~~~~~~~~~~~~~

From here you should be ready to commit to your repo (directly or via pull
request) and start testing things out! It's very likely that you'll run into
some error or another at first. If you suspect a problem in the task
configuration, see :doc:`/howto/debugging_and_testing` for tips on how to solve
it. Otherwise you might need to tweak the ``.taskcluster.yml`` or make changes
to your repo's Taskcluster configuration. If the latter is necessary, reach out
to your Taskcluster administrators for assistance.

Phew! While that was a lot, this only scratches the surface. You may also want
to incorporate:

* Dependencies
* Artifacts
* Docker images
* Action / Cron tasks
* Levels
* Treeherder support
* Chain of Trust
* Release tasks (using scriptworker)
* ..and much more

But hopefully this tutorial helped provide a solid foundation of knowledge upon
which to build.

.. _documentation: https://docs.taskcluster.net/docs/reference/integrations/github/taskcluster-yml-v1
.. _Github quickstart: https://firefox-ci-tc.services.mozilla.com/quickstart
.. _JSON-e: https://json-e.js.org/
.. _JSON-e reference: https://json-e.js.org/language.html
.. _playground: https://json-e.js.org/playground.html
.. _let: https://json-e.js.org/operators.html#let
.. _latest revision of Taskgraph: https://hg.mozilla.org/ci/taskgraph
.. _push: https://docs.github.com/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#push
.. _pull request: https://docs.github.com/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#pull_request
.. _release: https://docs.github.com/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#release
.. _Fenix's .taskcluster.yml: https://github.com/mozilla-mobile/fenix/blob/d1fbf309b35e94b1285aae74ebf72d8ff3910772/.taskcluster.yml#L15
.. _JSON-e if statement: https://json-e.js.org/operators.html#if---then---else
.. _Taskcluster's task schema: https://docs.taskcluster.net/docs/reference/platform/queue/task-schema
.. _fromNow: https://json-e.js.org/operators.html#fromnow
.. _docker-worker: https://docs.taskcluster.net/docs/reference/workers/docker-worker/payload
.. _generic-worker: https://docs.taskcluster.net/docs/reference/workers/generic-worker/docker-posix-payload
__ docker-worker_
.. _latest versions of the images: https://hub.docker.com/r/mozillareleases/taskgraph/tags
.. _taskclusterProxy: https://docs.taskcluster.net/docs/reference/workers/docker-worker/features#feature-taskclusterproxy
.. _run-task: https://hg.mozilla.org/ci/taskgraph/file/tip/src/taskgraph/run-task/run-task
