Use Secrets
===========

Tasks often need secrets such as an API tokens or private keys. Taskgraph can
have ``run-task`` fetch these automatically.

Using Secrets
-------------

Secrets are implemented as part of the :mod:`~taskgraph.transforms.run`
transforms, and are fetched by ``run-task``. So make sure your task uses those
transforms and a ``run-task`` based ``run.using``:

.. code-block:: yaml

   loader: taskgraph.loader.transform:loader

   transforms:
     - taskgraph.transforms.run:transforms
     - taskgraph.transforms.task:transforms

Then list the secrets in the task's ``secrets`` key:

.. code-block:: yaml

   tasks:
     deploy:
       run:
         using: run-task
         command: ./deploy.sh
       secrets:
         - type: github-repo-token
           app: my-github-app
           env: GITHUB_TOKEN
         - type: secret
           name: project/myproject/level-3/deploy
           key: privkey
           file: ~/.ssh/id_rsa

Here ``deploy.sh`` will find a GitHub token in the ``GITHUB_TOKEN`` env and a
``~/.ssh/id_rsa`` file containing a private ssh key.

The transforms add the scopes each secret needs and enable the
``taskclusterProxy`` feature, then pass the list to ``run-task`` in the
``RUN_TASK_SECRETS`` environment variable. No two secrets can be exported to
the same variable or file.

Substituting Values
-------------------

Secret names often depend on the level or project. Use the
:ref:`task_context <task_context transforms>` transforms, before the run
transforms, to substitute parameters into them:

.. code-block:: yaml

   transforms:
     - taskgraph.transforms.task_context
     - taskgraph.transforms.run:transforms
     - taskgraph.transforms.task:transforms

   tasks:
     deploy:
       task-context:
         from-parameters:
           level: level
           project: project
         substitution-fields: [secrets]
       run:
         using: run-task
         command: ./deploy.sh
       secrets:
         - type: secret
           name: project/{project}/level-{level}/deploy
           env: DEPLOY_TOKEN

Every string in ``secrets`` is formatted, so write a literal ``{`` or ``}`` as
``{{`` or ``}}``. ``secrets`` can also be keyed by a value as a whole, but not
entry by entry.

Secret Types
------------

``github-repo-token``
   An installation token of the GitHub App ``app``. ``repo`` defaults to the
   ``base_repository`` parameter, ``permissions`` to ``{"contents": "read"}``
   and ``env`` to ``GITHUB_TOKEN``. Adds an
   ``auth:github-repo-token:<app>/<owner>/<repo>:<permission>:<level>`` scope
   for each permission.

``secret``
   A secret from Taskcluster's secrets service, exported to ``env`` or written
   to ``file``. ``key`` exports a single key of the secret instead, using dots
   for nested keys such as ``foo.bar``. Adds a ``secrets:get:<name>`` scope.

See :ref:`run-task-secrets` for the details of each type, including what
happens when a secret can't be fetched.
