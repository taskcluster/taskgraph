# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import copy
from typing import Any, Dict, List, Optional

import msgspec

from taskgraph.transforms.base import TransformSequence
from taskgraph.util.schema import Schema
from taskgraph.util.templates import substitute


class ChunkConfig(Schema):
    """
    `chunk` can be used to split one task into `total-chunks`
    tasks, substituting `this_chunk` and `total_chunks` into any
    fields in `substitution-fields`.
    """

    # The total number of chunks to split the task into.
    total_chunks: int
    # A list of fields that need to have `{this_chunk}` and/or
    # `{total_chunks}` replaced in them.
    substitution_fields: Optional[List[str]] = None


#: Schema for chunking transforms
class ChunkSchema(Schema):
    # Optional, so it can be used for a subset of tasks in a kind
    chunk: Optional[ChunkConfig] = None
    __extras__: Dict[str, Any] = msgspec.field(default_factory=dict)


CHUNK_SCHEMA = ChunkSchema

transforms = TransformSequence()
transforms.add_validate(CHUNK_SCHEMA)


@transforms.add
def chunk_tasks(config, tasks):
    for task in tasks:
        chunk_config = task.pop("chunk", None)
        if not chunk_config:
            yield task
            continue

        total_chunks = chunk_config["total-chunks"]

        for this_chunk in range(1, total_chunks + 1):
            subtask = copy.deepcopy(task)

            subs = {
                "this_chunk": this_chunk,
                "total_chunks": total_chunks,
            }
            subtask.setdefault("attributes", {})
            subtask["attributes"].update(subs)

            for field in chunk_config["substitution-fields"]:
                container, subfield = subtask, field
                while "." in subfield:
                    f, subfield = subfield.split(".", 1)
                    container = container[f]

                subcontainer = copy.deepcopy(container[subfield])
                subfield = substitute(subfield, **subs)
                container[subfield] = substitute(subcontainer, **subs)

            yield subtask
