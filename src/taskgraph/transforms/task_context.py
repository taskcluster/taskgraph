from typing import Any, Dict, List, Optional, Union

import msgspec

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Schema
from taskgraph.util.templates import deep_get, substitute_task_fields
from taskgraph.util.yaml import load_yaml


class TaskContextConfig(Schema):
    """
    `task-context` can be used to substitute values into any field in a
    task with data that is not known until `taskgraph` runs.

    This data can be provided via `from-parameters` or `from-file`,
    which can pull in values from parameters and a defined yml file
    respectively.

    Data may also be provided directly in the `from-object` section of
    `task-context`. This can be useful in `kinds` that define most of
    their contents in `task-defaults`, but have some values that may
    differ for various concrete `tasks` in the `kind`.

    If the same key is found in multiple places the order of precedence
    is as follows:
      - Parameters
      - `from-object` keys
      - File

    That is to say: parameters will always override anything else.
    """

    # Required field first
    # A list of fields in the task to substitute the provided values
    # into.
    substitution_fields: List[str]

    # Optional fields
    # Retrieve task context values from parameters. A single
    # parameter may be provided or a list of parameters in
    # priority order. The latter can be useful in implementing a
    # "default" value if some other parameter is not provided.
    from_parameters: Optional[Dict[str, Union[List[str], str]]] = None
    # Retrieve task context values from a yaml file. The provided
    # file should usually only contain top level keys and values
    # (eg: nested objects will not be interpolated - they will be
    # substituted as text representations of the object).
    from_file: Optional[str] = None
    # Key/value pairs to be used as task context
    from_object: Optional[Any] = None


#: Schema for the task_context transforms
class TaskContextSchema(Schema):
    # Required field first
    task_context: TaskContextConfig

    # Optional fields
    name: Optional[str] = None
    __extras__: Dict[str, Any] = msgspec.field(default_factory=dict)


SCHEMA = TaskContextSchema

transforms = TransformSequence()
transforms.add_validate(SCHEMA)


@transforms.add
def render_task(config, tasks):
    for task in tasks:
        sub_config = task.pop("task-context")
        params_context = {}
        for var, path in sub_config.pop("from-parameters", {}).items():
            if isinstance(path, str):
                params_context[var] = deep_get(config.params, path)
            else:
                for choice in path:
                    value = deep_get(config.params, choice)
                    if value is not None:
                        params_context[var] = value
                        break

        file_context = {}
        from_file = sub_config.pop("from-file", None)
        if from_file:
            file_context = load_yaml(from_file)

        fields = sub_config.pop("substitution-fields")

        subs = {}
        subs.update(file_context)
        # We've popped away the configuration; everything left in `sub_config` is
        # substitution key/value pairs.
        subs.update(sub_config.pop("from-object", {}))
        subs.update(params_context)
        if "name" in task:
            subs.setdefault("name", task["name"])

        # Now that we have our combined context, we can substitute.
        substitute_task_fields(task, fields, **subs)
        yield task
