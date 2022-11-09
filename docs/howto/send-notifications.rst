Send Notifications
==================

Taskcluster can `send notifications`_ when a task transitions states.

Notification Types
------------------

There are four supported notification types:

1. Email - An email can be sent to any address.
2. Pulse - A `pulse event`_ can be triggered.
3. Matrix - A Matrix room can be pinged. Requires the Taskcluster deployment to
   be configured with Matrix credentials and be invited to the room.
4. Slack - A slack channel can be pinged. Requires the Taskcluster deployment to
   be configured with Slack credentials and be invited to the room.

.. _status-types:

Status Types
------------

A notification can be sent on the following task status changes:

- ``on-defined`` - When the task is first submitted to Taskcluster.
- ``on-pending`` - When the task transitions to the ``pending`` status.
- ``on-running`` - When the task transitions to the ``running`` status.
- ``on-completed`` - When the task finishes successfully.
- ``on-failed`` - When the task finishes in the ``failed`` state.
- ``on-exception`` - When the task finishes in the ``exception`` state.
- ``on-resolved`` - When the task finishes in any state.
- ``on-transition`` - When any of the above are triggered.

Adding Notifications to a Task
------------------------------

Taskgraph supports these notifications via the ``notify`` transforms. Once these
have been added, a *notify* section can be used:

.. code-block:: yaml

   transforms:
       - taskgraph.transforms.notify:transforms

   tasks:
     my-task:
       # <rest of task definition>
       notify:
         recipients:
           - type: email
             address: list@example.com
             status-type: on-resolved
           - type: slack-channel
             channel-id: KQP51F7GF
             status-type: on-failed

The above task will notify the ``list@example.com`` mailing list anytime the
task resolves for any reason, as well as ping the specified Slack channel
whenever the task fails. A Matrix room can be notified using ``type: matrix``
and ``room-id: <id>``, and a pulse route can be notified using ``type: pulse``
and ``routing-key: <key>``.

For each recipient, the ``status-type`` key can be any one of the
aforementioned :ref:`status types <status-types>`. If not specified, it
defaults to ``on-completed``.

.. note::

   For a full reference, see the :py:data:`notify schema <taskgraph.transforms.notify.NOTIFY_SCHEMA>`.

Interpolating Recipients
~~~~~~~~~~~~~~~~~~~~~~~~

Each recipient value can be interpolated using Python's `format string syntax`_
and the ``task`` and :class:`kind config <taskgraph.generator.Kind>` objects as
context. For example:

.. code-block:: yaml

   notify:
     recipients:
       - type: email
         address: "{task[name]}-subscribers@example.com"

Custom Notification Content
---------------------------

The example in the previous section would just send a generic message. You can
customize the content of your notifications using the ``content`` subkey within
the ``notify`` block, for example:

.. code-block:: yaml

   transforms:
       - taskgraph.transforms.notify:transforms

   tasks:
     my-task:
       # <rest of task definition>
       notify:
         recipients:
           - type: email
             address: list@example.com
             status-type: on-resolved
           - type: slack-channel
             channel-id: KQP51F7GF
             status-type: on-failed
         content:
           email:
             subject: "A task has completed!"
           slack:
             text: "A task has failed!"

Each notification type has its own way of specifying content:

Email
~~~~~

Supports the following keys:

- ``subject`` - The subject of the email.
- ``content`` - The body of the email (markdown supported).
- ``link`` - An object of the form ``{"text": <text>, "href": <url>}`` which
  will add a button to the email with the specified text and linking to the
  specified url.

Matrix
~~~~~~

Supports the following keys:

- ``body`` - The plain text body of the message.
- ``formatted-body`` - A rich text message. If a client is unable to render
  this, the notification will fallback to the text in ``body``.
- ``format`` - The format of the ``formatted-body`` key, e.g ``org.matrix.custom.html``.
- ``msg-type`` - The type of Matrix message to send, e.g ``m.notice`` (default).

Slack
~~~~~

Supports the following keys:

- ``text`` - The simple text field for the message. Supports Slack-flavored markdown.
- ``blocks`` - A list of block objects conforming to `Slack's blocks format`_.
  If ``text`` is also specified, ``text`` will only be used as a fallback.
- ``attachments`` - A list of attachment objects conforming to `Slack's attachments format`_.

.. note::

   Taskcluster does not support different content between recipients of the
   same type.

Interpolating Content
---------------------

But specifying content as a plain string isn't be very useful. You'll want
to add some context to your content!

Similar to recipients, each content value can be interpolated using Python's
`format string syntax`_ and the ``task`` and :class:`kind config
<taskgraph.generator.Kind>` objects as context.

Taskcluster also supports `JSON-e`_ in any of these keys which can be useful to
interpolate values that are not known at Taskgraph run time (like the
``taskId`` or status of the task).

For example:

.. code-block:: yaml

   notify:
     content:
       slack:
         text: "{task[name]} with id $taskId has finished!"

In the above example, ``{task[name]}`` will be interpolated locally
by Taskgraph, whereas ``$taskId`` will be interpolated by Taskcluster using
JSON-e.

Of course it's also possible to perform your own more advanced interpolation in
a transform! E.g, you could implement a dedicated *notify* task which links to
artifacts from multiple dependencies.

.. _send notifications: https://docs.taskcluster.net/docs/reference/core/notify/usage
.. _pulse event: https://docs.taskcluster.net/docs/manual/design/apis/pulse
.. _format string syntax: https://docs.python.org/3/library/string.html#formatstrings
.. _Slack's blocks format: https://api.slack.com/reference/block-kit/blocks
.. _Slack's attachments format: https://api.slack.com/reference/messaging/attachments
.. _JSON-e: https://json-e.js.org/
