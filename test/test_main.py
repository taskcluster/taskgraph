# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import sys
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
def run_taskgraph(maketgg, monkeypatch):
    def inner(args, **kwargs):
        kwargs.setdefault("target_tasks", ["_fake-t-0", "_fake-t-1"])
        tgg = maketgg(**kwargs)

        def fake_get_taskgraph_generator(*args):
            return tgg

        monkeypatch.setattr(
            taskgraph.main, "get_taskgraph_generator", fake_get_taskgraph_generator
        )
        try:
            return taskgraph_main(args)
        except SystemExit as e:
            return e.code

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
def test_show_taskgraph_attr(run_taskgraph, capsys, attr, expected):
    res = run_taskgraph([attr])
    assert res == 0

    out, err = capsys.readouterr()
    assert out.strip() == "\n".join(expected)
    assert "Dumping result" in err

    # Craft params to cause an exception
    res = run_taskgraph(["full"], params={"_kinds": None})
    assert res == 1


def test_show_taskgraph_parallel(run_taskgraph):
    res = run_taskgraph(["full", "-p", "taskcluster/test/params"])
    assert res == 0

    # Craft params to cause an exception
    res = run_taskgraph(
        ["full", "-p", "taskcluster/test/params"], params={"_kinds": None}
    )
    assert res == 1


def test_show_taskgraph_force_local_files_changed(mocker, run_taskgraph):
    repo = mocker.MagicMock()
    repo.get_changed_files.return_value = ["foo.txt"]

    m = mocker.MagicMock()
    m.get_repository.return_value = repo
    mocker.patch.dict(sys.modules, {"taskgraph.util.vcs": m})

    res = run_taskgraph(["full"])
    assert res == 0
    assert not repo.get_changed_files.called

    res = run_taskgraph(["full", "--force-local-files-changed"])
    assert res == 0
    assert not repo.get_changed_files.called

    res = run_taskgraph(
        [
            "full",
            "--force-local-files-changed",
            "-p",
            "taskcluster/test/params/mc-onpush.yml",
        ]
    )
    assert res == 0
    assert repo.get_changed_files.call_count == 1


def test_tasks_regex(run_taskgraph, capsys):
    run_taskgraph(["full", "--tasks=_.*-t-1"])
    out, _ = capsys.readouterr()
    assert out.strip() == "_fake-t-1"


def test_output_file(run_taskgraph, tmpdir):
    output_file = tmpdir.join("out.txt")
    assert not output_file.check()

    run_taskgraph(["full", f"--output-file={output_file.strpath}"])
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
                    "optimization": {"skip-unless-changed": True},
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
                    "optimization": {"skip-unless-changed": True},
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
                "optimization.skip-unless-changed",
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
                    "optimization": {},
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
            kind="task",
            label="b",
            attributes={"thing": True},
            optimization={"skip-unless-changed": True},
            task={"foo": {"baz": 1}},
        ),
    }

    graph = TaskGraph(tasks, Graph(set(tasks), {("a", "b", "dep")}))
    filtered = get_filtered_taskgraph(graph, regex, exclude)
    assert filtered.to_json() == expected


def test_init_taskgraph(mocker, tmp_path, project_root, repo_with_upstream):
    name = "bar"
    repo, _ = repo_with_upstream

    # Mock out upstream url to bypass the repo host check.
    if repo.tool == "hg":
        fake_url = f"https://hg.mozilla.org/foo/{name}"
        mocker.patch.object(HgRepository, "get_url").return_value = fake_url
    else:
        fake_url = f"https://github.com/foo/{name}.git"
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
    expected_files = [
        ".taskcluster.yml",
        "taskcluster/config.yml",
        "taskcluster/kinds/docker-image/kind.yml",
        "taskcluster/kinds/hello/kind.yml",
        f"taskcluster/{name}_taskgraph/transforms/hello.py",
    ]
    for f in expected_files:
        path = repo_root / f
        assert path.is_file(), f"{str(path)} not found!"

    c = load_yaml(str(repo_root / "taskcluster" / "config.yml"))
    assert c["trust-domain"] == "mozilla"
    assert c["taskgraph"]["cached-task-prefix"] == f"{c['trust-domain']}.v2.{name}"
    assert c["taskgraph"]["repositories"] == {name: {"name": name}}

    # Just assert we got the right .taskcluster.yml for the repo type
    tc_yml = load_yaml(repo_root / ".taskcluster.yml")
    if repo.tool == "hg":
        assert "reporting" not in tc_yml
    else:
        assert tc_yml["reporting"] == "checks-v1"


def test_init_taskgraph_unsupported(mocker, tmp_path, repo_with_upstream):
    repo, _ = repo_with_upstream

    # Point cookiecutter at temporary directories (in case test fails and
    # something gets generated).
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
        assert taskgraph_main(["init"]) == 1
    finally:
        os.chdir(oldcwd)


def test_action_callback(mocker, run_taskgraph):
    mocker.patch.dict(
        "os.environ",
        {
            "ACTION_TASK_ID": "null",
            "ACTION_TASK_GROUP_ID": "def",
            "ACTION_INPUT": '{"ship": true}',
            "ACTION_CALLBACK": "action",
        },
    )

    params_mock = mocker.patch("taskgraph.actions.util.get_parameters")
    params_mock.return_value = {"foo": "bar"}

    trigger_mock = mocker.patch("taskgraph.actions.trigger_action_callback")
    trigger_mock.return_value = "result"

    result = run_taskgraph(["action-callback"])
    assert result == "result"

    params_mock.assert_called_once_with("def")
    trigger_mock.assert_called_once_with(
        task_group_id="def",
        task_id=None,
        callback="action",
        input={"ship": True},
        parameters={"foo": "bar"},
        root="taskcluster",
        test=False,
    )
    root = Path(trigger_mock.call_args.kwargs["root"])
    assert root.joinpath("config.yml").is_file()
