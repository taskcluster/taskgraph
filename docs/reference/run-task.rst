run-task
========

`run-task`_ is a script in the Docker images provided by Taskgraph. It wraps a
task's command and handles setup such as cloning repositories, fetching
artifacts and installing Python requirements.

.. _run-task: https://github.com/taskcluster/taskgraph/blob/main/src/taskgraph/run-task/run-task

.. _run-task-secrets:

Secrets
-------

``run-task`` can fetch secrets before it clones anything, so the checkout and
the task can both use them. List them as JSON in ``RUN_TASK_SECRETS``:

.. code-block:: yaml

   payload:
       env:
           RUN_TASK_SECRETS:
               $json:
                   - type: github-repo-token
                     app: read
                     repo: https://github.com/myorg/myrepo

The only type so far is ``github-repo-token``. It asks Taskcluster's auth service
for an installation token of the GitHub App ``app``, scoped to ``repo``. Its
keys are:

``app`` (required)
   The name of the GitHub App registered with Taskcluster.
``repo`` (required)
   The GitHub repository the token is for.
``permissions``
   The token's permissions. Defaults to ``{"contents": "read"}``.
``env``
   The environment variable to export the token in. Defaults to
   ``GITHUB_TOKEN``. A variable that is already set is never replaced.

``run-task`` also keeps the token for its own GitHub requests. The task needs
the ``taskclusterProxy`` feature and an
``auth:github-repo-token:<app>/<owner>/<repo>:<permission>:<level>`` scope for
each permission. If a request fails, for example because a pull request from a
fork lacks the scope, ``run-task`` logs a warning and carries on without the
token. The same happens when the auth service rejects the request, such as for
an unknown ``app`` or invalid ``permissions``. Invalid JSON, an unknown ``type``
or key, or a ``repo`` that isn't on GitHub fails the task. Installation tokens
expire after an hour.
