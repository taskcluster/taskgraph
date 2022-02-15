.. _using-taskgraph:

Using Taskgraph 
===============

.. _adding taskgraph:

Adding Taskgraph to a new Project
---------------------------------

1. If your project is in Github, install the `firefox-ci-taskcluster app <https://github.com/apps/firefoxci-taskcluster>`_ if it's not already installed. 
   If your project is in Mercurial, you’ll need to submit a pull-request to the `ci-configuration repo <https://hg.mozilla.org/ci/ci-configuration/>`_ 
   in order to add your project or file a `bugzilla bug <https://bugzilla.mozilla.org/enter_bug.cgi?product=Release%20Engineering&component=Firefox-CI%20Administration>`_ 
   and someone on the Releng team will do it for you.

2.  If you don’t have an existing `taskcluster.yml` file (which uses `json-e <https://json-e.js.org/#Language/language-reference>`_), you’ll need to create one at the root level. 
    The Taskcluster docs have a `detailed explanation <https://firefox-ci-tc.services.mozilla.com/docs/reference/integrations/github/taskcluster-yml-v1>`_ of how to create one. 
    Once created, this yaml file will create and run tasks in response to various Github actions but there are a few changes needed in order to use taskgraph (trust domains and scopes
    will be addresssed in the next section):
     
    a. In the tasks block, you need to specify the version of taskgraph you want to use:
    
    .. code-block:: yaml
     
     tasks:
      - $let:
            taskgraph:
                branch: taskgraph
                revision: b975005a3219b65ad0dd073263a19ec6c94d8b73
            trustDomain: mobile
    
    b. Add `json-e variables <https://github.com/mozilla-mobile/focus-android/blob/main/.taskcluster.yml#L12-L96>`_, for use in various code blocks later on.

    c. You'll also need to delegate to the taskgraph decision task in the if/then block, for example:
    
    .. code-block:: yaml

      metadata:
          $merge:
              - owner: "${ownerEmail}"
                source: '${repoUrl}/raw/${head_sha}/.taskcluster.yml'
              - $if: 'tasks_for in ["github-push", "github-pull-request", "github-release"]'
                then:
                    name: "Decision Task"
                    description: 'The task that creates all of the other tasks in the task graph'

    d. :term:`Scopes` and worker types that are mentioned in the taskcluster docs, are dealt with differently. Scopes are handled in the `ci-configuration repo <https://hg.mozilla.org/ci/ci-configuration/>`_ 
       and worker types are defined in the `ci/config.yml` file.
    
    .. note::

      The `json-e playground <https://json-e.js.org/#Playground/>`_ can be a helpful tool for debugging and validating changes to this file.


Trust Domains and Scopes
------------------------

:term:`Trust domains` roughly map to different products (see `cot_product <https://github.com/mozilla-releng/scriptworker/blob/a2bc6f4aef584ae475c23cae4adf129ef263d246/src/scriptworker/constants.py#L112-L128>`_) and if 
an existing trust domain is not sufficient for a new project, then a new trust domain can be created. This would require Release Engineering to spin up new worker pools, but this helps avoid security or cache issues
that might occur with a shared trust domain.

New projects need to be added to the `ci-configuration repo <https://hg.mozilla.org/ci/ci-configuration/>`_. The two files of interest will be projects.yml, 
where new projects are added and where they can opt in to certain features, and grants.yml, where we specify permissions - represented as :term:`scopes` - for tasks that are run on branches,
pull-requests, release actions, cron (needed for nightly tasks) and by level.


Adding the Config file and Kinds
--------------------------------

It's highly recommended to have read through the :ref:`intro-to-taskgraph` section before proceeding.

1. Create a taskcluster directory, with additional directories for `ci`, `docker`, `your_project_name_taskgraph`, and `scripts`. 
   This is where the kinds and config file will live, along with docker images, scripts and custom taskgraph code.

2. In the `ci` directory, create a `config.yml` file (this is only yaml, no json-e). The config file is used to define group names for `Treeherder <https://wiki.mozilla.org/EngineeringProductivity/Projects/Treeherder>`_ (which will be used in various kind files). 
   Its also used to register your custom taskgraph directory, and define worker aliases for resources and scriptworkers. Looking at `Focus for androids <https://github.com/mozilla-mobile/focus-android/blob/main/taskcluster/ci/config.yml>`_ 
   as an example, it has a few mobile-specific things - such as a mobile trust domain and b-android worker - but it is largely boilerplate that can be used as a guide for other projects.

3. A :term:`kind` is a yaml file that livez in a directory that describes the `kinds` of tasks it will contain. For example, a `build` directory will have a `kind.yml` file that can include multiple builds. Depending on how you define the tasks, they'll run only when specific
   actions are performed. If you have a debug build in the `build` kind, that task will be called `build-debug` when its created and run.

4. To start with getting a passing decision task and build, you'll want to create a `docker-image` directory and a `kind.yml`. This kind file will look different to the other kinds,
   as its used to define the docker images needed to run various jobs. These docker images should be broken down into distinct parts (such as the base image, anything specific to tests
   or say an android build should be broken out into separate images) and stored in the `ci/docker` directory.


How to Read a Kind
------------------

One of Taskgraph's features is the ability to extend standard taskgraph code with custom transforms and loaders. However, it can be confusing to understand which parts of a kind are standard taskgraph
and which are custom code. If we look at a simple build kind example, you'll notice at the top the `loader` and `transforms` are defined. These point to standard taskgraph, but if you wanted to use a custom loader or transform
it would be defined here pointing to `your_project_name_taskgraph` directory, eg `my_project_name_taskgraph.transforms.job`.

This can also be a clue of where to look if you are trying to understand what a specific yaml attribute does in an existing kind file (keeping in mind that these are written in snake case and the corresponding python functions aren't).

.. code-block:: yaml

  loader: taskgraph.loader.transform:loader

  transforms:
      - taskgraph.transforms.docker_image:transforms
      - taskgraph.transforms.cached_tasks:transforms
      - taskgraph.transforms.task:transforms

  jobs:
      android-build:  <-- this android-build image job (or task) is dependent on the the base image below, and will be referenced in a build kind.
          symbol: I(agb)
          parent: base
      base:
          symbol: I(base)
      ui-tests:
          symbol: I(ui-tests)
          parent: base

.. note::

  Taskgraph will optimize tasks, so you may not see all of the jobs defined in your kinds run in response to an action. You
  can verify this is the case by looking in the Decision task live backing log.
