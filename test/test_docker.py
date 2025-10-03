import logging
import os
import re
import tempfile

import pytest

from taskgraph import docker
from taskgraph.config import GraphConfig
from taskgraph.transforms.docker_image import IMAGE_BUILDER_IMAGE


@pytest.fixture
def root_url():
    return "https://tc.example.com"


@pytest.fixture(autouse=True)
def mock_environ(monkeypatch, root_url):
    # Ensure user specified environment variables don't interfere with URLs.
    monkeypatch.setattr(os, "environ", {"TASKCLUSTER_ROOT_URL": root_url})


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


@pytest.fixture
def run_load_task(mocker):
    def inner(
        task,
        remove=False,
        custom_image=None,
        pass_task_def=False,
        interactive=True,
        volumes=None,
    ):
        proc = mocker.MagicMock()
        proc.returncode = 0

        graph_config = GraphConfig(
            {
                "trust-domain": "test-domain",
                "docker-image-kind": "docker-image",
            },
            "test/data/taskcluster",
        )

        mocks = {
            "build_image": mocker.patch.object(
                docker, "build_image", return_value="taskcluster/hello-world:latest"
            ),
            "load_image_by_task_id": mocker.patch.object(
                docker, "load_image_by_task_id", return_value="image/tag"
            ),
            "subprocess_run": mocker.patch.object(
                docker.subprocess, "run", return_value=proc
            ),
        }

        # Mock sys.stdin.fileno() to avoid issues in pytest
        mock_stdin = mocker.MagicMock()
        mock_stdin.fileno.return_value = 0
        mocker.patch.object(docker.sys, "stdin", mock_stdin)
        mocker.patch.object(docker.os, "isatty", return_value=True)

        # If testing with task ID, mock get_task_definition
        if not pass_task_def:
            task_id = "abc"
            mocks["get_task_definition"] = mocker.patch.object(
                docker, "get_task_definition", return_value=task
            )
            input_arg = task_id
        else:
            # Testing with task definition directly
            input_arg = task

        ret = docker.load_task(
            graph_config,
            input_arg,
            remove=remove,
            custom_image=custom_image,
            interactive=interactive,
            volumes=volumes,
        )
        return ret, mocks

    return inner


def test_load_task_invalid_task(run_load_task):
    task = {"metadata": {"name": "abc"}}
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
        "metadata": {"name": "test-task"},
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
    }
    # Test with custom volumes
    volumes = {"/host/path": "/container/path", "/another/host": "/another/container"}
    ret, mocks = run_load_task(task, volumes=volumes)
    assert ret == 0

    if "get_task_definition" in mocks:
        mocks["get_task_definition"].assert_called_once_with("abc")
    mocks["load_image_by_task_id"].assert_called_once_with(image_task_id)

    expected = [
        "docker",
        "run",
        "-i",
        "-t",
        re.compile(f"--env-file={tempfile.gettempdir()}/tmp.*"),
        "-v",
        re.compile(f"{tempfile.gettempdir()}/tmp.*:/builds/worker/.bashrc"),
        "-v",
        "/host/path:/container/path",
        "-v",
        "/another/host:/another/container",
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


def test_load_task_env_init_and_remove(mocker, run_load_task):
    # Mock NamedTemporaryFile to capture what's written to it
    mock_envfile = mocker.MagicMock()
    mock_envfile.name = "/tmp/test_envfile"
    mock_envfile.fileno.return_value = 123  # Mock file descriptor

    written_env_content = []
    mock_envfile.write = lambda content: written_env_content.append(content)
    mock_envfile.close = mocker.MagicMock()

    mock_initfile = mocker.MagicMock()
    mock_initfile.name = "/tmp/test_initfile"
    mock_initfile.fileno.return_value = 456  # Mock file descriptor
    written_init_content = []
    mock_initfile.write = lambda content: written_init_content.append(content)
    mock_initfile.close = mocker.MagicMock()

    # Return different mocks for each call to NamedTemporaryFile
    mock_tempfile = mocker.patch.object(docker.tempfile, "NamedTemporaryFile")
    mock_tempfile.side_effect = [mock_envfile, mock_initfile]

    # Mock os.remove to prevent file deletion errors
    mock_os_remove = mocker.patch.object(docker.os, "remove")

    # Mock os.fchmod
    mocker.patch.object(docker.os, "fchmod")

    image_task_id = "def"
    task = {
        "metadata": {"name": "test-task-env"},
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--repo-checkout=/builds/worker/vcs/repo",
                "--task-cwd=/builds/worker/vcs/repo",
                "--",
                "echo foo",
            ],
            "env": {"FOO": "BAR", "BAZ": "1", "TASKCLUSTER_CACHES": "path"},
            "image": {"taskId": image_task_id, "type": "task-image"},
        },
    }
    ret, mocks = run_load_task(task, remove=True)
    assert ret == 0

    # NamedTemporaryFile was called twice (once for env, once for init)
    assert mock_tempfile.call_count == 2

    # Verify the environment content written to the file
    assert len(written_env_content) == 1
    env_lines = written_env_content[0].split("\n")

    # Verify written env is expected
    assert "TASKCLUSTER_CACHES=path" not in env_lines
    assert "FOO=BAR" in env_lines
    assert "BAZ=1" in env_lines

    # Check that the default env vars were included
    assert any("RUN_ID=0" in line for line in env_lines)
    assert any("TASK_ID=abc" in line for line in env_lines)
    assert any("TASK_GROUP_ID=" in line for line in env_lines)
    assert any("TASKCLUSTER_ROOT_URL=" in line for line in env_lines)

    # Both files were closed and removed
    mock_envfile.close.assert_called_once()
    mock_initfile.close.assert_called_once()
    assert mock_os_remove.call_count == 2
    assert mock_os_remove.call_args_list[0] == mocker.call("/tmp/test_envfile")
    assert mock_os_remove.call_args_list[1] == mocker.call("/tmp/test_initfile")

    # Verify subprocess was called with the correct env file and init file
    mocks["subprocess_run"].assert_called_once()
    actual = mocks["subprocess_run"].call_args[0][0]
    assert actual[4] == "--rm"
    assert actual[5] == "--env-file=/tmp/test_envfile"
    assert actual[6:8] == ["-v", "/tmp/test_initfile:/builds/worker/.bashrc"]


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
        "metadata": {"name": "test-task-image-types"},
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
    }

    mocker.patch.object(docker, "find_task_id", return_value=image_task_id)

    ret, mocks = run_load_task(task)
    assert ret == 0

    mocks["get_task_definition"].assert_called_once_with(task_id)
    mocks["load_image_by_task_id"].assert_called_once_with(image_task_id)


def test_load_task_with_local_image(
    mocker,
    run_load_task,
):
    task_id = "abc"
    image_task_id = "xyz"
    task = {
        "metadata": {"name": "test-task-image-types"},
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--task-cwd=/builds/worker",
                "--",
                "echo",
                "test",
            ],
            "image": "hello-world",
        },
    }

    mocker.patch.object(docker, "find_task_id", return_value=image_task_id)

    ret, mocks = run_load_task(task)
    assert ret == 0

    mocks["get_task_definition"].assert_called_once_with(task_id)
    mocks["build_image"].assert_called_once()
    assert mocks["build_image"].call_args[0][1] == "hello-world"


def test_load_task_with_unsupported_image_type(caplog, run_load_task):
    caplog.set_level(logging.DEBUG)
    task = {
        "metadata": {"name": "test-task-unsupported"},
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--task-cwd=/builds/worker",
                "--",
                "echo foo",
            ],
            "image": {"type": "unsupported-type", "path": "/some/path"},
        },
    }

    ret, _ = run_load_task(task)
    assert ret == 1

    assert "Tasks with unsupported-type images are not supported!" in caplog.text


def test_load_task_with_task_definition(run_load_task, caplog):
    # Test passing a task definition directly instead of a task ID
    caplog.set_level(logging.INFO)
    image_task_id = "def"
    task = {
        "metadata": {"name": "test-task-direct"},
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
    }

    ret, mocks = run_load_task(task, pass_task_def=True)
    assert ret == 0

    # Should not call get_task_definition when passing a definition directly
    assert "get_task_definition" not in mocks
    mocks["load_image_by_task_id"].assert_called_once_with(image_task_id)

    # Check logging output shows it's from provided definition
    assert "Loading 'test-task-direct' from provided definition" in caplog.text


def test_load_task_with_interactive_false(run_load_task):
    # Test non-interactive mode that doesn't require run-task
    # Task that doesn't use run-task (would fail in interactive mode)
    task = {
        "metadata": {"name": "test-task-non-interactive"},
        "payload": {
            "command": ["echo", "hello world"],
            "image": {"taskId": "def", "type": "task-image"},
        },
    }

    # Test with interactive=False - should succeed
    ret, mocks = run_load_task(task, pass_task_def=True, interactive=False)
    assert ret == 0

    # Verify subprocess was called
    mocks["subprocess_run"].assert_called_once()
    command = mocks["subprocess_run"].call_args[0][0]

    # Should run the task command directly
    # Find and remove --env-file arg as it contains a tempdir
    for i, arg in enumerate(command):
        if arg.startswith("--env-file="):
            del command[i]
            break

    assert command == [
        "docker",
        "run",
        "-i",
        "-t",
        "image/tag",
        "echo",
        "hello world",
    ]


@pytest.fixture
def task():
    return {
        "metadata": {"name": "test-task-fixture"},
        "payload": {
            "command": [
                "/usr/bin/run-task",
                "--task-cwd=/builds/worker",
                "--",
                "echo",
                "test",
            ],
            "image": {"type": "task-image", "taskId": "abc"},
        },
    }


def test_load_task_with_custom_image_in_tree(run_load_task, task):
    image = "hello-world"
    ret, mocks = run_load_task(task, custom_image=image)
    assert ret == 0

    mocks["build_image"].assert_called_once()
    args = mocks["subprocess_run"].call_args[0][0]
    # Find the image tag - it should be after all docker options and before the command
    # Structure: ['docker', 'run', ...options..., 'image:tag', ...command...]
    image_index = None
    for i, arg in enumerate(args):
        if (
            not arg.startswith("-")
            and not arg.startswith("/")
            and arg != "docker"
            and arg != "run"
            and ":" in arg
            and not arg.startswith("/tmp")
        ):
            image_index = i
            break
    assert image_index is not None, f"Could not find image tag in {args}"
    tag = args[image_index]
    assert tag == f"taskcluster/{image}:latest"


def test_load_task_with_custom_image_task_id(run_load_task, task):
    image = "task-id=abc"
    ret, mocks = run_load_task(task, custom_image=image)
    assert ret == 0
    mocks["load_image_by_task_id"].assert_called_once_with("abc")


def test_load_task_with_custom_image_index(mocker, run_load_task, task):
    image = "index=abc"
    mocker.patch.object(docker, "find_task_id", return_value="abc")
    ret, mocks = run_load_task(task, custom_image=image)
    assert ret == 0
    mocks["load_image_by_task_id"].assert_called_once_with("abc")


def test_load_task_with_custom_image_registry(mocker, run_load_task, task):
    image = "ubuntu:latest"
    ret, mocks = run_load_task(task, custom_image=image)
    assert ret == 0
    assert not mocks["load_image_by_task_id"].called
    assert not mocks["build_image"].called


@pytest.fixture
def run_build_image(mocker):
    def inner(image_name, save_image=None, context_file=None, image_task=None):
        graph_config = GraphConfig(
            {
                "trust-domain": "test-domain",
                "docker-image-kind": "docker-image",
            },
            "test/data/taskcluster",
        )

        # Mock the TemporaryDirectory context manager since the current build_image uses it
        temp_dir_mock = mocker.MagicMock()
        temp_dir_str = "/tmp/test_temp_dir"
        temp_dir_mock.__enter__ = mocker.MagicMock(return_value=temp_dir_str)
        temp_dir_mock.__exit__ = mocker.MagicMock(return_value=False)

        # Mock Path objects
        temp_dir_path = mocker.MagicMock()
        output_dir = mocker.MagicMock()

        # Mock Path constructor
        original_path = docker.Path

        def mock_path_constructor(path_arg):
            if str(path_arg) == temp_dir_str:
                return temp_dir_path
            elif str(path_arg).endswith(".tar.gz"):
                # This is the image_context path
                image_context_mock = mocker.MagicMock()
                image_context_mock.resolve.return_value = image_context_mock
                return image_context_mock
            elif save_image and str(path_arg) == save_image:
                save_path_mock = mocker.MagicMock()
                save_path_mock.resolve.return_value = save_path_mock
                save_path_mock.__str__ = lambda self: save_image
                return save_path_mock
            return original_path(path_arg)

        # Set up directory operations
        temp_dir_path.__truediv__ = mocker.MagicMock(return_value=output_dir)
        output_dir.mkdir = mocker.MagicMock()
        output_dir.__truediv__ = mocker.MagicMock()

        # Initialize mocks dictionary
        mocks = {
            "TemporaryDirectory": mocker.patch.object(
                docker.tempfile, "TemporaryDirectory", return_value=temp_dir_mock
            ),
            "Path": mocker.patch.object(
                docker, "Path", side_effect=mock_path_constructor
            ),
            "load_tasks_for_kind": mocker.patch.object(docker, "load_tasks_for_kind"),
            "load_task": mocker.patch.object(docker, "load_task"),
            "subprocess": mocker.patch.object(docker.subprocess, "run"),
            "shutil_copy": mocker.patch.object(docker.shutil, "copy"),
            "shutil_move": mocker.patch.object(docker.shutil, "move"),
            "isdir": mocker.patch.object(docker.os.path, "isdir", return_value=True),
            "getuid": mocker.patch.object(docker.os, "getuid", return_value=1000),
            "getgid": mocker.patch.object(docker.os, "getgid", return_value=1000),
        }

        # Mock image task
        if not image_task:
            image_task = mocker.MagicMock()
            image_task.task = {"payload": {"env": {}}}

        parent_image = mocker.MagicMock()
        parent_image.task = {"payload": {"env": {}}}

        mocks["image_task"] = image_task
        mocks["load_tasks_for_kind"].return_value = {
            f"docker-image-{image_name}": mocks["image_task"],
            "docker-image-parent": parent_image,
        }

        # Mock subprocess result for docker load
        mocks["proc_result"] = mocker.MagicMock()
        mocks["proc_result"].stdout = f"Loaded image: {image_name}:latest"
        mocks["subprocess"].return_value = mocks["proc_result"]

        # Add convenience references
        mocks["graph_config"] = graph_config
        mocks["temp_dir_path"] = temp_dir_path
        mocks["output_dir"] = output_dir

        # Run the build_image function
        result = docker.build_image(
            graph_config, image_name, context_file=context_file, save_image=save_image
        )

        return result, mocks

    return inner


def test_build_image(run_build_image):
    # Test building image without save_image
    result, mocks = run_build_image("hello-world")

    # Verify TemporaryDirectory is used for cleanup
    mocks["TemporaryDirectory"].assert_called_once()

    # Verify the function calls
    mocks["load_tasks_for_kind"].assert_called_once_with(
        {"do_not_optimize": ["docker-image-hello-world"]},
        "docker-image",
        graph_attr="morphed_task_graph",
        write_artifacts=True,
    )

    mocks["load_task"].assert_called_once()
    call_args = mocks["load_task"].call_args
    assert call_args[0][0] == mocks["graph_config"]
    assert call_args[0][1] == mocks["image_task"].task
    assert call_args[1]["custom_image"] == IMAGE_BUILDER_IMAGE
    assert call_args[1]["interactive"] is False
    assert "volumes" in call_args[1]

    # Verify docker load was called
    mocks["subprocess"].assert_called_once()
    docker_load_args = mocks["subprocess"].call_args[0][0]
    assert docker_load_args[:3] == ["docker", "load", "-i"]

    assert result == "hello-world:latest"


def test_build_image_with_parent(mocker, responses, root_url, run_build_image):
    parent_task_id = "abc"
    responses.get(f"{root_url}/api/queue/v1/task/{parent_task_id}/status")

    # Test building image that has a parent image
    image_task = mocker.MagicMock()
    image_task.task = {"payload": {"env": {"PARENT_TASK_ID": parent_task_id}}}
    result, mocks = run_build_image("hello-world", image_task=image_task)
    assert result == "hello-world:latest"

    # Verify the graph generation call
    mocks["load_tasks_for_kind"].assert_called_once_with(
        {"do_not_optimize": ["docker-image-hello-world"]},
        "docker-image",
        graph_attr="morphed_task_graph",
        write_artifacts=True,
    )

    # Verify load-task called (to invoke image_builder)
    mocks["load_task"].assert_called_once()
    call_args = mocks["load_task"].call_args
    assert call_args[0][0] == mocks["graph_config"]
    assert call_args[0][1] == mocks["image_task"].task
    assert call_args[1]["custom_image"] == IMAGE_BUILDER_IMAGE
    assert call_args[1]["interactive"] is False
    assert "volumes" in call_args[1]

    # Verify docker load was called
    mocks["subprocess"].assert_called_once()
    docker_load_args = mocks["subprocess"].call_args[0][0]
    assert docker_load_args[:3] == ["docker", "load", "-i"]


def test_build_image_with_parent_not_found(
    mocker, responses, root_url, run_build_image
):
    parent_task_id = "abc"
    responses.get(f"{root_url}/api/queue/v1/task/{parent_task_id}/status", status=404)

    # Test building image that uses DOCKER_IMAGE_PARENT
    image_task = mocker.MagicMock()
    image_task.task = {"payload": {"env": {"PARENT_TASK_ID": parent_task_id}}}
    image_task.dependencies = {"parent": "docker-image-parent"}
    result, mocks = run_build_image("hello-world", image_task=image_task)
    assert result == "hello-world:latest"

    # Verify the graph generation call
    assert mocks["load_tasks_for_kind"].call_count == 2
    assert mocks["load_tasks_for_kind"].call_args_list[0] == (
        ({"do_not_optimize": ["docker-image-hello-world"]}, "docker-image"),
        {"graph_attr": "morphed_task_graph", "write_artifacts": True},
    )
    assert mocks["load_tasks_for_kind"].call_args_list[1] == (
        ({"do_not_optimize": ["docker-image-parent"]}, "docker-image"),
        {"graph_attr": "morphed_task_graph", "write_artifacts": True},
    )

    # Verify load-task called (to invoke image_builder)
    assert mocks["load_task"].call_count == 2
    call_args = mocks["load_task"].call_args_list[0]
    assert call_args[0][0] == mocks["graph_config"]
    assert call_args[1]["custom_image"] == IMAGE_BUILDER_IMAGE
    assert call_args[1]["interactive"] is False
    assert "volumes" in call_args[1]

    # Verify docker load was called
    mocks["subprocess"].assert_called_once()
    docker_load_args = mocks["subprocess"].call_args[0][0]
    assert docker_load_args[:3] == ["docker", "load", "-i"]


def test_build_image_with_save_image(run_build_image):
    save_path = "/path/to/save.tar"

    # Test building image with save_image option
    result, mocks = run_build_image("test", save_image=save_path)

    # Verify TemporaryDirectory is used for cleanup
    mocks["TemporaryDirectory"].assert_called_once()

    # Verify copy was called instead of docker load
    mocks["shutil_copy"].assert_called_once()

    # Result should be the string representation of the save path
    assert save_path in str(result)


def test_build_image_context_only(run_build_image):
    context_path = "/path/to/context.tar"

    # Test building only the context file
    result, mocks = run_build_image("context-test", context_file=context_path)

    # Verify move was called for the context file
    mocks["shutil_move"].assert_called_once()

    assert result == ""
