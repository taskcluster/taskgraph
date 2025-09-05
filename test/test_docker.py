import re
import tempfile

import pytest

from taskgraph import docker
from taskgraph.config import GraphConfig


@pytest.fixture(autouse=True, scope="module")
def mock_docker_path(module_mocker, datadir):
    module_mocker.patch(
        "taskgraph.util.docker.IMAGE_DIR", str(datadir / "taskcluster" / "docker")
    )


@pytest.fixture
def mock_docker_build(mocker):
    def side_effect(topsrcdir, context_dir, out_file, image_name=None, args=None):
        out_file.write(b"xyz")

    m_stream = mocker.patch.object(docker.docker, "stream_context_tar")
    m_stream.side_effect = side_effect

    m_run = mocker.patch.object(docker.subprocess, "run")
    return (m_stream, m_run)


def test_build_image(capsys, mock_docker_build):
    m_stream, m_run = mock_docker_build
    image = "hello-world-tag"
    tag = f"test/{image}:1.0"

    graph_config = GraphConfig(
        {
            "trust-domain": "test-domain",
            "docker-image-kind": "docker-image",
        },
        "test/data/taskcluster",
    )

    assert docker.build_image(image, None, graph_config=graph_config) is None
    m_stream.assert_called_once()
    m_run.assert_called_once_with(
        ["docker", "image", "build", "--no-cache", f"-t={tag}", "-"],
        input=b"xyz",
        check=True,
    )

    out, _ = capsys.readouterr()
    assert f"Successfully built {image} and tagged with {tag}" in out
    assert "Image is not suitable for deploying/pushing" not in out


def test_build_image_no_tag(capsys, mock_docker_build):
    m_stream, m_run = mock_docker_build
    image = "hello-world"

    graph_config = GraphConfig(
        {
            "trust-domain": "test-domain",
            "docker-image-kind": "docker-image",
        },
        "test/data/taskcluster",
    )

    assert docker.build_image(image, None, graph_config=graph_config) is None
    m_stream.assert_called_once()
    m_run.assert_called_once_with(
        ["docker", "image", "build", "--no-cache", "-"],
        input=b"xyz",
        check=True,
    )

    out, _ = capsys.readouterr()
    assert f"Successfully built {image}" in out
    assert "Image is not suitable for deploying/pushing" in out


def test_build_image_error(capsys, mock_docker_build):
    m_stream, m_run = mock_docker_build

    def mock_run(*popenargs, check=False, **kwargs):
        if check:
            raise docker.subprocess.CalledProcessError(1, popenargs)
        return 1

    m_run.side_effect = mock_run
    image = "hello-world"

    graph_config = GraphConfig(
        {
            "trust-domain": "test-domain",
            "docker-image-kind": "docker-image",
        },
        "test/data/taskcluster",
    )

    with pytest.raises(Exception):
        docker.build_image(image, None, graph_config=graph_config)
    m_stream.assert_called_once()
    m_run.assert_called_once_with(
        ["docker", "image", "build", "--no-cache", "-"],
        input=b"xyz",
        check=True,
    )

    out, _ = capsys.readouterr()
    assert f"Successfully built {image}" not in out


@pytest.fixture
def run_load_task(mocker):
    task_id = "abc"

    def inner(task, remove=False):
        proc = mocker.MagicMock()
        proc.returncode = 0

        mocks = {
            "get_task_definition": mocker.patch.object(
                docker, "get_task_definition", return_value=task
            ),
            "load_image_by_task_id": mocker.patch.object(
                docker, "load_image_by_task_id", return_value="image/tag"
            ),
            "subprocess_run": mocker.patch.object(
                docker.subprocess, "run", return_value=proc
            ),
        }

        ret = docker.load_task(task_id, remove=remove)
        return ret, mocks

    return inner


def test_load_task_invalid_task(run_load_task):
    task = {}
    assert run_load_task(task)[0] == 1

    task["payload"] = {}
    assert run_load_task(task)[0] == 1

    task["payload"] = {"command": [], "image": {"type": "task-image"}}
    assert run_load_task(task)[0] == 1

    task["payload"]["command"] = ["echo", "foo"]
    assert run_load_task(task)[0] == 1

    task["payload"]["image"]["type"] = "foobar"
    task["payload"]["command"] = ["run-task", "--", "bash", "-c", "echo foo"]
    assert run_load_task(task)[0] == 1


def test_load_task(run_load_task):
    image_task_id = "def"
    task = {
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--repo-checkout=/builds/worker/vcs/repo",
                "--task-cwd=/builds/worker/vcs/repo",
                "--",
                "echo foo",
            ],
            "image": {"taskId": image_task_id, "type": "task-image"},
        },
        "tags": {"worker-implementation": "docker-worker"},
    }
    ret, mocks = run_load_task(task)
    assert ret == 0

    mocks["get_task_definition"].assert_called_once_with("abc")
    mocks["load_image_by_task_id"].assert_called_once_with(image_task_id)

    expected = [
        "docker",
        "run",
        "-v",
        re.compile(f"{tempfile.gettempdir()}/tmp.*:/builds/worker/.bashrc"),
        re.compile(f"--env-file={tempfile.gettempdir()}/tmp.*"),
        "-it",
        "image/tag",
        "bash",
        "-c",
        "/usr/bin/run-task --repo-checkout=/builds/worker/vcs/repo "
        "--task-cwd=/builds/worker/vcs/repo -- echo 'Task setup complete!\n"
        "Run `exec-task` to execute the task'\"'\"'s command.' && cd $TASK_WORKDIR && su -p worker",
    ]

    mocks["subprocess_run"].assert_called_once()
    actual = mocks["subprocess_run"].call_args[0][0]

    print(expected)
    print(actual)
    assert len(expected) == len(actual)
    for i, exp in enumerate(expected):
        if isinstance(exp, re.Pattern):
            assert exp.match(actual[i])
        else:
            assert exp == actual[i]


def test_load_task_env_and_remove(run_load_task):
    image_task_id = "def"
    task = {
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--repo-checkout=/builds/worker/vcs/repo",
                "--task-cwd=/builds/worker/vcs/repo",
                "--",
                "echo foo",
            ],
            "env": {"FOO": "BAR", "BAZ": 1},
            "image": {"taskId": image_task_id, "type": "task-image"},
        },
    }
    ret, mocks = run_load_task(task, remove=True)
    assert ret == 0

    mocks["subprocess_run"].assert_called_once()
    actual = mocks["subprocess_run"].call_args[0][0]
    assert re.match(r"--env-file=/tmp/tmp.*", actual[4])
    assert actual[5] == "--rm"


@pytest.mark.parametrize(
    "image",
    [
        pytest.param({"type": "task-image", "taskId": "xyz"}, id="task_image"),
        pytest.param(
            {"type": "indexed-image", "namespace": "project.some-namespace.latest"},
            id="indexed_image",
        ),
    ],
)
def test_load_task_with_different_image_types(
    mocker,
    run_load_task,
    image,
):
    task_id = "abc"
    image_task_id = "xyz"
    task = {
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--task-cwd=/builds/worker",
                "--",
                "echo",
                "test",
            ],
            "image": image,
        },
        "tags": {"worker-implementation": "docker-worker"},
    }

    mocker.patch.object(docker, "find_task_id", return_value=image_task_id)

    ret, mocks = run_load_task(task)
    assert ret == 0

    mocks["get_task_definition"].assert_called_once_with(task_id)
    mocks["load_image_by_task_id"].assert_called_once_with(image_task_id)


def test_load_task_with_unsupported_image_type(capsys, run_load_task):
    task = {
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--task-cwd=/builds/worker",
                "--",
                "echo foo",
            ],
            "image": {"type": "unsupported-type", "path": "/some/path"},
        },
        "tags": {"worker-implementation": "docker-worker"},
    }

    ret, mocks = run_load_task(task)
    assert ret == 1

    out, _ = capsys.readouterr()
    assert "Tasks with unsupported-type images are not supported!" in out
