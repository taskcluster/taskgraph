# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Add notifications to tasks via Taskcluster's notify service.

See https://docs.taskcluster.net/docs/reference/core/notify/usage for
more information.
"""

from typing import Any, Literal, Optional, Union

import msgspec

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Struct, optionally_keyed_by, resolve_keyed_by

StatusType = Literal[
    "on-completed",
    "on-defined",
    "on-exception",
    "on-failed",
    "on-pending",
    "on-resolved",
    "on-running",
]


class EmailRecipientStruct(Struct, tag_field="type", tag="email"):
    """Email notification recipient."""

    address: optionally_keyed_by("project", "level", str, use_msgspec=True)  # type: ignore
    status_type: Optional[StatusType] = None


class MatrixRoomRecipientStruct(Struct, tag_field="type", tag="matrix-room"):
    """Matrix room notification recipient."""

    room_id: str
    status_type: Optional[StatusType] = None


class PulseRecipientStruct(Struct, tag_field="type", tag="pulse"):
    """Pulse notification recipient."""

    routing_key: str
    status_type: Optional[StatusType] = None


class SlackChannelRecipientStruct(Struct, tag_field="type", tag="slack-channel"):
    """Slack channel notification recipient."""

    channel_id: str
    status_type: Optional[StatusType] = None


Recipient = Union[
    EmailRecipientStruct,
    MatrixRoomRecipientStruct,
    PulseRecipientStruct,
    SlackChannelRecipientStruct,
]

_route_keys = {
    "email": "address",
    "matrix-room": "room-id",
    "pulse": "routing-key",
    "slack-channel": "channel-id",
}
"""Map each type to its primary key that will be used in the route."""


class EmailLinkStruct(Struct, rename=None, omit_defaults=False):
    """Email link configuration."""

    text: str
    href: str


class EmailContentStruct(Struct, rename=None):
    """Email notification content."""

    subject: Optional[str] = None
    content: Optional[str] = None
    link: Optional[EmailLinkStruct] = None


class MatrixContentStruct(Struct):
    """Matrix notification content."""

    body: Optional[str] = None
    formatted_body: Optional[str] = None
    format: Optional[str] = None
    msg_type: Optional[str] = None


class SlackContentStruct(Struct, rename=None):
    """Slack notification content."""

    text: Optional[str] = None
    blocks: Optional[list[Any]] = None
    attachments: Optional[list[Any]] = None


class NotifyContentStruct(Struct, rename=None):
    """Notification content configuration."""

    email: Optional[EmailContentStruct] = None
    matrix: Optional[MatrixContentStruct] = None
    slack: Optional[SlackContentStruct] = None


RecipientSchema = Union[
    EmailRecipientStruct,
    MatrixRoomRecipientStruct,
    PulseRecipientStruct,
    SlackChannelRecipientStruct,
]


class NotifyConfigStruct(Struct, rename=None):
    """Modern notification configuration."""

    recipients: list[RecipientSchema]
    content: Optional[NotifyContentStruct] = None


class LegacyNotificationsConfigStruct(Struct, rename="kebab"):
    """Legacy notification configuration for backwards compatibility."""

    emails: Union[list[str], dict[str, Any]]  # Can be keyed-by
    subject: str
    message: Optional[str] = None
    status_types: Optional[list[StatusType]] = None


#: Schema for notify transforms
class NotifyStruct(Struct, tag_field="notify_type", forbid_unknown_fields=False):
    """Schema for notify transforms.

    Note: This schema allows either 'notify' or 'notifications' field,
    but not both. The validation will be done in __post_init__.
    """

    notify: Optional[NotifyConfigStruct] = None
    notifications: Optional[LegacyNotificationsConfigStruct] = None

    def __post_init__(self):
        # Ensure only one of notify or notifications is present
        if self.notify and self.notifications:
            raise msgspec.ValidationError(
                "Cannot specify both 'notify' and 'notifications'"
            )


transforms = TransformSequence()
transforms.add_validate(NotifyStruct)


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
