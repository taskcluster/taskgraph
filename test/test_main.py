# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
from pathlib import Path
from textwrap import dedent

import pytest

import taskgraph
from taskgraph.graph import Graph
from taskgraph.main import get_filtered_taskgraph
from taskgraph.main import main as taskgraph_main
from taskgraph.task import Task
from taskgraph.taskgraph import TaskGraph
from taskgraph.util.vcs import GitRepository, HgRepository
from taskgraph.util.yaml import load_yaml


@pytest.fixture
def run_show_taskgraph(maketgg, monkeypatch):
    def inner(args, **kwargs):
        kwargs.setdefault("target_tasks", ["_fake-t-0", "_fake-t-1"])
        tgg = maketgg(**kwargs)

        def fake_get_taskgraph_generator(*args):
            return tgg

        monkeypatch.setattr(
            taskgraph.main, "get_taskgraph_generator", fake_get_taskgraph_generator
        )
        taskgraph_main(args)
        return tgg

    return inner


@pytest.mark.parametrize(
    "attr,expected",
    (
        ("tasks", ["_fake-t-0", "_fake-t-1", "_fake-t-2"]),
        ("full", ["_fake-t-0", "_fake-t-1", "_fake-t-2"]),
        ("target", ["_fake-t-0", "_fake-t-1"]),
        ("target-graph", ["_fake-t-0", "_fake-t-1"]),
        ("optimized", ["_fake-t-0", "_fake-t-1"]),
        ("morphed", ["_fake-t-0", "_fake-t-1"]),
    ),
)
def test_show_taskgraph(run_show_taskgraph, capsys, attr, expected):
    run_show_taskgraph([attr])
    out, err = capsys.readouterr()
    assert out.strip() == "\n".join(expected)
    assert "Dumping result" in err


def test_tasks_regex(run_show_taskgraph, capsys):
    run_show_taskgraph(["full", "--tasks=_.*-t-1"])
    out, _ = capsys.readouterr()
    assert out.strip() == "_fake-t-1"


def test_output_file(run_show_taskgraph, tmpdir):
    output_file = tmpdir.join("out.txt")
    assert not output_file.check()

    run_show_taskgraph(["full", f"--output-file={output_file.strpath}"])
    assert output_file.check()
    assert output_file.read_text("utf-8").strip() == "\n".join(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )


@pytest.mark.parametrize(
    "regex,exclude,expected",
    (
        pytest.param(
            None,
            None,
            {
                "a": {
                    "attributes": {"kind": "task"},
                    "dependencies": {"dep": "b"},
                    "description": "",
                    "kind": "task",
                    "label": "a",
                    "optimization": None,
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "task": {
                        "foo": {"bar": 1},
                    },
                },
                "b": {
                    "attributes": {"kind": "task", "thing": True},
                    "dependencies": {},
                    "description": "",
                    "kind": "task",
                    "label": "b",
                    "optimization": None,
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "task": {
                        "foo": {"baz": 1},
                    },
                },
            },
            id="no-op",
        ),
        pytest.param(
            "^b",
            None,
            {
                "b": {
                    "attributes": {"kind": "task", "thing": True},
                    "dependencies": {},
                    "description": "",
                    "kind": "task",
                    "label": "b",
                    "optimization": None,
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "task": {
                        "foo": {"baz": 1},
                    },
                },
            },
            id="regex-b-only",
        ),
        pytest.param(
            None,
            [
                "attributes.thing",
                "task.foo.baz",
            ],
            {
                "a": {
                    "attributes": {"kind": "task"},
                    "dependencies": {"dep": "b"},
                    "description": "",
                    "kind": "task",
                    "label": "a",
                    "optimization": None,
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "task": {
                        "foo": {"bar": 1},
                    },
                },
                "b": {
                    "attributes": {"kind": "task"},
                    "dependencies": {},
                    "description": "",
                    "kind": "task",
                    "label": "b",
                    "optimization": None,
                    "soft_dependencies": [],
                    "if_dependencies": [],
                    "task": {
                        "foo": {},
                    },
                },
            },
            id="exclude-keys",
        ),
    ),
)
def test_get_filtered_taskgraph(regex, exclude, expected):
    tasks = {
        "a": Task(kind="task", label="a", attributes={}, task={"foo": {"bar": 1}}),
        "b": Task(
            kind="task", label="b", attributes={"thing": True}, task={"foo": {"baz": 1}}
        ),
    }

    graph = TaskGraph(tasks, Graph(set(tasks), {("a", "b", "dep")}))
    filtered = get_filtered_taskgraph(graph, regex, exclude)
    assert filtered.to_json() == expected


def test_init_taskgraph(mocker, tmp_path, project_root, repo_with_upstream):
    repo, _ = repo_with_upstream

    # Mock out upstream url to bypass the repo host check.
    if repo.tool == "hg":
        fake_url = "https://hg.mozilla.org/foo"
        mocker.patch.object(HgRepository, "get_url").return_value = fake_url
    else:
        fake_url = "https://github.com/foo"
        mocker.patch.object(GitRepository, "get_url").return_value = fake_url

    # Point cookiecutter at temporary directories.
    d = tmp_path / "cookiecutter"
    d.mkdir()

    config = d / "config.yml"
    config.write_text(
        dedent(
            f"""
        cookiecutters_dir: {d / 'cookiecutters'}
        replay_dir: {d / 'replay'}
    """
        )
    )
    mocker.patch.dict("os.environ", {"COOKIECUTTER_CONFIG": str(config)})

    repo_root = Path(repo.path)
    oldcwd = Path.cwd()
    try:
        os.chdir(repo_root)
        taskgraph_main(["init", "--template", str(project_root)])
    finally:
        os.chdir(oldcwd)

    # Make assertions about the repository state.
    name = repo_root.name
    expected_files = [
        ".taskcluster.yml",
        "taskcluster/ci/config.yml",
        "taskcluster/ci/docker-image/kind.yml",
        "taskcluster/ci/hello/kind.yml",
        f"taskcluster/{name}_taskgraph/transforms/hello.py",
    ]
    for f in expected_files:
        assert (repo_root / f).is_file()

    c = load_yaml(str(repo_root / "taskcluster" / "ci" / "config.yml"))
    assert c["trust-domain"] == "mozilla"
    assert c["taskgraph"]["cached-task-prefix"] == f"{c['trust-domain']}.v2.{name}"
    assert c["taskgraph"]["repositories"] == {name: {"name": name}}

    # Just assert we got the right .taskcluster.yml for the repo type
    tc_yml = load_yaml(repo_root / ".taskcluster.yml")
    if repo.tool == "hg":
        assert "reporting" not in tc_yml
    else:
        assert tc_yml["reporting"] == "checks-v1"
