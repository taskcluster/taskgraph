from taskgraph.target_tasks import register_target_task, standard_filter


@register_target_task("release")
def target_tasks_release(full_task_graph, parameters, graph_config):
    tasks = {
        l: t for l, t in full_task_graph.tasks.items() if standard_filter(t, parameters)
    }

    # Ensure we don't run `taskcluster-taskgraph` release tasks when publishing
    # `pytest-taskgraph`.
    head_ref = parameters["head_ref"].rsplit("/", 1)[-1]
    if head_ref.startswith("pytest-taskgraph"):
        tasks = {
            l: t
            for l, t in tasks.items()
            if "github-release" not in t.attributes.get("run_on_tasks_for", [])
        }
    return list(tasks.keys())
