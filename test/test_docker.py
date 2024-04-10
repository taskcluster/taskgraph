import pytest

from taskgraph import docker


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

    assert docker.build_image(image, None) is None
    m_stream.assert_called_once()
    m_run.assert_called_once_with(
        ["docker", "image", "build", "--no-cache", f"-t={tag}", "-"],
        input=b"xyz",
    )

    out, _ = capsys.readouterr()
    assert f"Successfully built {image} and tagged with {tag}" in out
    assert "Image is not suitable for deploying/pushing" not in out


def test_build_image_no_tag(capsys, mock_docker_build):
    m_stream, m_run = mock_docker_build
    image = "hello-world"

    assert docker.build_image(image, None) is None
    m_stream.assert_called_once()
    m_run.assert_called_once_with(
        ["docker", "image", "build", "--no-cache", "-"],
        input=b"xyz",
    )

    out, _ = capsys.readouterr()
    assert f"Successfully built {image}" in out
    assert "Image is not suitable for deploying/pushing" in out
