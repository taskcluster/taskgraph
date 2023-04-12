from taskgraph.transforms.base import TransformSequence

transforms = TransformSequence()


@transforms.add
def add_task(_config, _tasks):
    yield {
        "label": "my-task",
        "description": "a task",
        "attributes": {},
        "task": {},
    }
