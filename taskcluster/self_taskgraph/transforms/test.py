from taskgraph.transforms.base import TransformSequence
from taskgraph.util.copy import deepcopy

transforms = TransformSequence()


@transforms.add
def split_by_python_image(config, tasks):
    python_image_tasks = [
        task
        for task in config.kind_dependencies_tasks.values()
        if task.kind == "docker-image"
        if task.attributes["image_name"].startswith("py")
    ]
    artifact_dir = "/builds/worker/artifacts"
    for task in tasks:
        for image_task in python_image_tasks:
            image_name = image_task.attributes["image_name"]

            new_task = deepcopy(task)
            new_task["name"] = f"{task['name']}-{image_name}"

            attributes = new_task.setdefault("attributes", {})
            attributes["python_version"] = image_name

            worker = new_task.setdefault("worker", {})
            worker.setdefault("env", {})["MOZ_ARTIFACT_DIR"] = artifact_dir
            worker["docker-image"] = {"in-tree": image_name}
            worker.setdefault("artifacts", []).append(
                {
                    "type": "file",
                    "path": f"{artifact_dir}/coverage",
                    "name": f"public/coverage.{image_name}",
                }
            )

            treeherder = new_task.setdefault("treeherder", {})
            treeherder["symbol"] = f"unit({image_name})"

            yield new_task
