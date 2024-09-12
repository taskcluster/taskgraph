from taskgraph.transforms.base import TransformSequence
from taskgraph.util.copy import deepcopy

transforms = TransformSequence()


@transforms.add
def split_by_python_version(config, tasks):
    artifact_dir = "/builds/worker/artifacts"
    for task in tasks:
        for python_version in task.pop("python-versions"):
            py_name = f"py{python_version.replace('.', '')}"
            new_task = deepcopy(task)
            new_task["name"] = f"{task['name']}-{py_name}"

            attributes = new_task.setdefault("attributes", {})
            attributes["python_version"] = py_name

            worker = new_task.setdefault("worker", {})
            worker.setdefault("artifacts", []).append(
                {
                    "type": "file",
                    "path": f"{artifact_dir}/coverage",
                    "name": f"public/coverage.{py_name}",
                }
            )
            env = worker.setdefault("env", {})
            env["MOZ_ARTIFACT_DIR"] = artifact_dir
            env["UV_PYTHON"] = python_version

            treeherder = new_task.setdefault("treeherder", {})
            treeherder["symbol"] = f"unit({py_name})"

            yield new_task
