Glossary of Terms
=================

.. glossary::

  Task
    Code containing repository data and commands to run, called the `task
    definition`, that is submitted to Taskcluster for execution.

  Decision task
    The decision task is the first task created when a new graph begins. It is
    responsible for creating the rest of the task graph.

  Kind
    Tasks of the same `kind` have substantial similarities or share common
    processing logic and are grouped together in a kind.yml file.

  Loader
    Parses each of the kinds, applies logic in the transforms, and determines
    the order in which to create and schedule tasks.

  Transform
    Applies logic to the kind tasks in response to task attributes. This can
    involve things like executing a script in response to certain attribute
    values in a kind file, or creating a payload to submit to a scriptworker to
    perform a specific action.

  Scriptworker
    `Scripts <https://github.com/mozilla-releng/scriptworker-scripts>`_
    controlled by Release Engineering that perform certain actions required to
    complete a kind task, such as signing binaries to pushing packages to the
    Google Play store or to Mozilla archives.

  Trust Domains
    These consist of scopes, routes and worker pools that are grouped roughly
    by product so as to minimize security risks and manage resources. The
    smaller the trust domain, the more secure but the harder it is to maintain
    and manage resources.

  Scopes
    Taskcluster permissions required to perform a particular action. Each task
    has a set of these permissions determining what it can do.
