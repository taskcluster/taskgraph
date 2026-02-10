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


class EmailRecipient(Schema, tag_field="type", tag="email", kw_only=True):
    address: optionally_keyed_by("project", "level", str, use_msgspec=True)  # type: ignore
    status_type: Optional[StatusType] = None


class MatrixRoomRecipient(Schema, tag_field="type", tag="matrix-room", kw_only=True):
    room_id: str
    status_type: Optional[StatusType] = None


class PulseRecipient(Schema, tag_field="type", tag="pulse", kw_only=True):
    routing_key: str
    status_type: Optional[StatusType] = None


class SlackChannelRecipient(
    Schema, tag_field="type", tag="slack-channel", kw_only=True
):
    channel_id: str
    status_type: Optional[StatusType] = None


Recipient = Union[
    EmailRecipient, MatrixRoomRecipient, PulseRecipient, SlackChannelRecipient
]


_route_keys = {
    "email": "address",
    "matrix-room": "room-id",
    "pulse": "routing-key",
    "slack-channel": "channel-id",
}
"""Map each type to its primary key that will be used in the route."""


class EmailLinkContent(Schema):
    text: str
    href: str


class EmailContent(Schema):
    subject: Optional[str] = None
    content: Optional[str] = None
    link: Optional[EmailLinkContent] = None


class MatrixContent(Schema):
    body: Optional[str] = None
    formatted_body: Optional[str] = None
    format: Optional[str] = None
    msg_type: Optional[str] = None


class SlackContent(Schema):
    text: Optional[str] = None
    blocks: Optional[list] = None
    attachments: Optional[list] = None


class NotifyContentConfig(Schema):
    email: Optional[EmailContent] = None
    matrix: Optional[MatrixContent] = None
    slack: Optional[SlackContent] = None


class NotifyConfig(Schema):
    recipients: list[Recipient]
    content: Optional[NotifyContentConfig] = None


class LegacyNotificationsConfig(Schema):
    # Continue supporting the legacy schema for backwards compat.
    emails: optionally_keyed_by("project", "level", list[str], use_msgspec=True)  # type: ignore
    subject: str
    message: Optional[str] = None
    status_types: Optional[list[StatusType]] = None


#: Schema for notify transforms
class NotifySchema(Schema, forbid_unknown_fields=False, kw_only=True):
    notify: Optional[NotifyConfig] = None
    notifications: Optional[LegacyNotificationsConfig] = None

    def __post_init__(self):
        if self.notify is not None and self.notifications is not None:
            raise ValueError("'notify' and 'notifications' are mutually exclusive")


NOTIFY_SCHEMA = NotifySchema

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
