"""
Tests for the 'release_notifications' transforms.
"""

from copy import deepcopy

import pytest

from taskgraph.transforms import release_notifications

TASK_DEFAULTS = {
    "description": "fake description",
    "name": "fake-task-name",
}


@pytest.mark.parametrize(
    "task_input, extra_params, expected_task_output",
    (
        pytest.param({}, {}, {}, id="null"),
        pytest.param(
            {
                "owner": "me",
                "notify": {
                    "recipients": [
                        {"type": "email", "address": "some@email.address"},
                        {
                            "type": "email",
                            "address": "{task[owner]}@email.address",
                            "status-type": "on-running",
                        },
                        {"type": "matrix-room", "room-id": "!room"},
                        {
                            "type": "pulse",
                            "routing-key": "{config[params][tasks_for]}.foo.bar",
                        },
                        {"type": "slack-channel", "channel-id": "123"},
                    ],
                    "content": {
                        "matrix": {
                            "body": "Hello {task[owner]}!",
                            "msg-type": "notification",
                        },
                        "slack": {
                            "text": "Hello {task[owner]}!",
                            "blocks": [{"foo": "bar"}],
                        },
                        "email": {
                            "content": "Hello {task[owner]}!",
                        },
                    },
                },
            },
            {},
            {
                "owner": "me",
                "routes": [
                    "notify.email.some@email.address.on-completed",
                    "notify.email.me@email.address.on-running",
                    "notify.matrix-room.!room.on-completed",
                    "notify.pulse.hg-push.foo.bar.on-completed",
                    "notify.slack-channel.123.on-completed",
                ],
                "extra": {
                    "notify": {
                        "email": {
                            "content": "Hello me!",
                        },
                        "matrixBody": "Hello me!",
                        "matrixMsgType": "notification",
                        "slackText": "Hello me!",
                        "slackBlocks": [{"foo": "bar"}],
                    }
                },
            },
            id="basic",
        ),
        pytest.param(
            {
                "notifications": {
                    "subject": "Email about {config[params][project]} {config[params][version]} build{config[params][build_number]}",  # noqa E501
                    "emails": ["some@email.address"],
                },
            },
            {},
            {
                "extra": {
                    "notify": {
                        "email": {
                            "content": "Email about some-project 1.0.0 build1",
                            "subject": "Email about some-project 1.0.0 build1",
                        },
                    },
                },
                "routes": ["notify.email.some@email.address.on-completed"],
            },
            id="legacy",
        ),
        pytest.param(
            {
                "notifications": {
                    "subject": "Some subject",
                    "emails": {
                        "by-level": {
                            "3": ["level-3@email.address"],
                            "default": ["default@email.address"],
                        }
                    },
                },
            },
            {},
            {
                "extra": {
                    "notify": {
                        "email": {
                            "content": "Some subject",
                            "subject": "Some subject",
                        },
                    },
                },
                "routes": ["notify.email.default@email.address.on-completed"],
            },
            id="legacy",
        ),
        pytest.param(
            {
                "notifications": {
                    "subject": "Some subject",
                    "message": "Some message",
                    "emails": {
                        "by-level": {
                            "3": ["level-3@email.address"],
                            "default": ["default@email.address"],
                        }
                    },
                    "status-types": ["on-completed", "on-failed", "on-exception"],
                },
            },
            {"level": "3"},
            {
                "extra": {
                    "notify": {
                        "email": {
                            "content": "Some message",
                            "subject": "Some subject",
                        },
                    },
                },
                "routes": [
                    "notify.email.level-3@email.address.on-completed",
                    "notify.email.level-3@email.address.on-failed",
                    "notify.email.level-3@email.address.on-exception",
                ],
            },
            id="legacy",
        ),
        pytest.param(
            {
                "notifications": {
                    "subject": "Some subject",
                    "emails": {
                        "by-project": {
                            "some-project": [
                                "project@email.address",
                                "secondary@email.address",
                            ],
                            "default": ["default@email.address"],
                        }
                    },
                },
            },
            {},
            {
                "extra": {
                    "notify": {
                        "email": {
                            "content": "Some subject",
                            "subject": "Some subject",
                        },
                    },
                },
                "routes": [
                    "notify.email.project@email.address.on-completed",
                    "notify.email.secondary@email.address.on-completed",
                ],
            },
            id="legacy",
        ),
    ),
)
def test_transforms(
    make_transform_config, run_transform, task_input, extra_params, expected_task_output
):
    task = deepcopy(TASK_DEFAULTS)
    task.update(task_input)

    config = make_transform_config()
    config.params.update(extra_params)

    expected_task = deepcopy(TASK_DEFAULTS)
    expected_task.update(expected_task_output)

    assert (
        run_transform(release_notifications.transforms, task, config)[0]
        == expected_task
    )
