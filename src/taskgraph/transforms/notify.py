# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Add notifications to tasks via Taskcluster's notify service.

See https://docs.taskcluster.net/docs/reference/core/notify/usage for
more information.
"""

from typing import Literal, Optional, Union

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Schema, optionally_keyed_by, resolve_keyed_by

StatusType = Literal[
    "on-completed",
    "on-defined",
    "on-exception",
    "on-failed",
    "on-pending",
    "on-resolved",
    "on-running",
]

Recipient = Union[
    Schema.from_dict(
        {
            "address": optionally_keyed_by("project", "level", str, use_msgspec=True),
            "status-type": Optional[StatusType],
        },
        name="EmailRecipient",
        tag_field="type",
        tag="email",
    ),  # type: ignore [invalid-type-form]
    Schema.from_dict(
        {
            "room-id": str,
            "status-type": Optional[StatusType],
        },
        name="MatrixRoomRecipient",
        tag_field="type",
        tag="matrix-room",
    ),  # type: ignore [invalid-type-form]
    Schema.from_dict(
        {
            "routing-key": str,
            "status-type": Optional[StatusType],
        },
        name="PulseRecipient",
        tag_field="type",
        tag="pulse",
    ),  # type: ignore [invalid-type-form]
    Schema.from_dict(
        {
            "channel-id": str,
            "status-type": Optional[StatusType],
        },
        name="SlackChannelRecipient",
        tag_field="type",
        tag="slack-channel",
    ),  # type: ignore [invalid-type-form]
]

Content = Schema.from_dict(
    {
        "email": Schema.from_dict(
            {
                "subject": Optional[str],
                "content": Optional[str],
                "link": Schema.from_dict(
                    {
                        "text": str,
                        "href": str,
                    },
                    optional=True,
                ),
            },
            name="EmailContent",
            optional=True,
        ),
        "matrix": Schema.from_dict(
            {
                "body": Optional[str],
                "formatted-body": Optional[str],
                "format": Optional[str],
                "msg-type": Optional[str],
            },
            name="MatrixContent",
            optional=True,
        ),
        "slack": Schema.from_dict(
            {
                "text": Optional[str],
                "blocks": Optional[list],
                "attachments": Optional[list],
            },
            name="SlackContent",
            optional=True,
        ),
    },
    optional=True,
    name="NotifyContentConfig",
)


_route_keys = {
    "email": "address",
    "matrix-room": "room-id",
    "pulse": "routing-key",
    "slack-channel": "channel-id",
}
"""Map each type to its primary key that will be used in the route."""


#: Schema for notify transforms
NOTIFY_SCHEMA = Schema.from_dict(
    {
        "notify": Schema.from_dict(
            {
                "recipients": list[Recipient],
                "content": Content,
            },
            optional=True,
        ),
        # Continue supporting the legacy schema for backwards compat.
        "notifications": Schema.from_dict(
            {
                "emails": optionally_keyed_by(
                    "project", "level", list[str], use_msgspec=True
                ),
                "subject": str,
                "message": Optional[str],
                "status-types": Optional[list[StatusType]],
            },
            optional=True,
        ),
    },
    exclusive=[("notify", "notifications")],
    forbid_unknown_fields=False,
)

transforms = TransformSequence()
transforms.add_validate(NOTIFY_SCHEMA)


def _convert_legacy(config, legacy, label):
    """Convert the legacy format to the new one."""
    notify = {
        "recipients": [],
        "content": {"email": {"subject": legacy["subject"]}},
    }
    resolve_keyed_by(
        legacy,
        "emails",
        label,
        **{
            "level": config.params["level"],
            "project": config.params["project"],
        },
    )

    status_types = legacy.get("status-types", ["on-completed"])
    for email in legacy["emails"]:
        for status_type in status_types:
            notify["recipients"].append(
                {"type": "email", "address": email, "status-type": status_type}
            )

    notify["content"]["email"]["content"] = legacy.get("message", legacy["subject"])
    return notify


def _convert_content(content):
    """Convert the notify content to Taskcluster's format.

    The Taskcluster notification format is described here:
    https://docs.taskcluster.net/docs/reference/core/notify/usage
    """
    tc = {}
    if "email" in content:
        tc["email"] = content.pop("email")

    for key, obj in content.items():
        for name in obj.keys():
            tc_name = "".join(part.capitalize() for part in name.split("-"))
            tc[f"{key}{tc_name}"] = obj[name]
    return tc


@transforms.add
def add_notifications(config, tasks):
    for task in tasks:
        label = "{}-{}".format(config.kind, task["name"])
        if "notifications" in task:
            notify = _convert_legacy(config, task.pop("notifications"), label)
        else:
            notify = task.pop("notify", None)

        if not notify:
            yield task
            continue

        format_kwargs = dict(
            task=task,
            config=config.__dict__,
        )

        def substitute(ctx):
            """Recursively find all strings in a simple nested dict (no lists),
            and format them in-place using `format_kwargs`."""
            for key, val in ctx.items():
                if isinstance(val, str):
                    ctx[key] = val.format(**format_kwargs)
                elif isinstance(val, dict):
                    ctx[key] = substitute(val)
            return ctx

        task.setdefault("routes", [])
        for recipient in notify["recipients"]:
            type = recipient["type"]
            recipient.setdefault("status-type", "on-completed")
            substitute(recipient)

            if type == "email":
                resolve_keyed_by(
                    recipient,
                    "address",
                    label,
                    **{
                        "level": config.params["level"],
                        "project": config.params["project"],
                    },
                )

            task["routes"].append(
                f"notify.{type}.{recipient[_route_keys[type]]}.{recipient['status-type']}"
            )

        if "content" in notify:
            task.setdefault("extra", {}).update(
                {"notify": _convert_content(substitute(notify["content"]))}
            )
        yield task
