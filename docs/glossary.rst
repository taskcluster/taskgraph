Glossary
========

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

  Trust Domain
    Trust domains are a concept frequently used in the Firefox-CI cluster. They
    act as a prefix for scopes, routes and worker pools and roughly correspond
    to a project or group of related projects. Trust domains ensure that a task
    from one project isn't accidentally granted scopes to another. This reduces
    the attack surface should the task get compromised. The more granular the
    trust domain, the more secure it is. But granular trust domains are also
    harder to maintain.

  Scope
    Taskcluster permission required to perform a particular action. Each task
    has a set of these permissions determining what it can do.

  Parameters
    A set of runtime values passed into the Decision task that define the
    context the graph is being generated in. For instance, parameters can be
    used to specify whether the generation is for a pull request or a push.
