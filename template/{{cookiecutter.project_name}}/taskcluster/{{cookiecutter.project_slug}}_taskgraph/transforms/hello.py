from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Schema


class HelloSchema(Schema):
    noun: str  # Required field


HELLO_SCHEMA = HelloSchema

transforms = TransformSequence()
transforms.add_validate(HELLO_SCHEMA)


@transforms.add
def add_noun(config, tasks):
    for task in tasks:
        noun = task.pop("noun").capitalize()
        task["description"] = f"Prints 'Hello {noun}'"

        env = task.setdefault("worker", {}).setdefault("env", {})
        env["NOUN"] = noun

        yield task
