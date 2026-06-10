import json
import os
import pathlib
import urllib.request
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest.mock import MagicMock

import pytest

import taskgraph


@pytest.fixture(scope="module")
def fetch_content_mod():
    spec = spec_from_loader(
        "fetch-content",
        SourceFileLoader(
            "fetch-content",
            os.path.join(
                os.path.dirname(taskgraph.__file__), "run-task", "fetch-content"
            ),
        ),
    )
    assert spec
    assert spec.loader
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "url,sha256,size,headers,raises",
    (
        pytest.param(
            "https://example.com",
            "c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2",
            6,
            ["User-Agent: foobar"],
            False,
            id="valid",
        ),
        pytest.param(
            "https://example.com",
            "abcdef",
            6,
            ["User-Agent: foobar"],
            True,
            id="invalid sha256",
        ),
        pytest.param(
            "https://example.com",
            "c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2",
            123,
            ["User-Agent: foobar"],
            True,
            id="invalid size",
        ),
    ),
)
def test_stream_download(
    monkeypatch, fetch_content_mod, url, sha256, size, headers, raises
):
    def mock_urlopen(req, timeout=None, *, context=None):
        assert req._full_url == url
        assert timeout is not None
        if headers:
            assert len(req.headers) == len(headers)
            for header in headers:
                k, v = header.split(":")
                k = k.lower().capitalize().strip()
                assert k in req.headers
                assert req.headers[k] == v.strip()

        # create a mock context manager
        cm = MagicMock()
        cm.getcode.return_value = 200

        def getheader(field):
            if field.lower() == "content-length":
                return size

        # simulates chunking
        cm.getheader = getheader
        cm.read.side_effect = [b"foo", b"bar", None]
        cm.__enter__.return_value = cm
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    result = b""
    try:
        for chunk in fetch_content_mod.stream_download(url, sha256, size, headers):
            result += chunk
        assert result == b"foobar"
    except fetch_content_mod.IntegrityError:
        if not raises:
            raise


@pytest.mark.parametrize(
    "artifact,expected_url_suffix",
    (
        pytest.param(
            "public/foo.apworld",
            "task/abc123/artifacts/public/foo.apworld",
            id="simple artifact name",
        ),
        pytest.param(
            "public/Twilight Princess-0.2.3.apworld",
            "task/abc123/artifacts/public/Twilight%20Princess-0.2.3.apworld",
            id="artifact name with space",
        ),
    ),
)
def test_command_task_artifacts_url_encoding(
    monkeypatch,
    tmp_path,
    fetch_content_mod,
    artifact,
    expected_url_suffix,
):
    fetches = [{"task": "abc123", "artifact": artifact, "extract": False}]
    monkeypatch.setenv("MOZ_FETCHES", json.dumps(fetches))
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", "https://tc.example.com")

    captured_urls = []

    def mock_fetch_urls(downloads):
        for url, dest_dir, extract, sha256 in downloads:
            captured_urls.append(url)

    monkeypatch.setattr(fetch_content_mod, "fetch_urls", mock_fetch_urls)

    args = MagicMock()
    args.dest = str(tmp_path)
    fetch_content_mod.command_task_artifacts(args)

    assert len(captured_urls) == 1
    url = captured_urls[0]
    assert url == f"https://tc.example.com/api/queue/v1/{expected_url_suffix}"


@pytest.mark.parametrize(
    "url,expected_dest_filename",
    (
        pytest.param(
            "https://tc.example.com/api/queue/v1/task/abc/artifacts/public/foo.apworld",
            "foo.apworld",
            id="simple",
        ),
        pytest.param(
            "https://tc.example.com/api/queue/v1/task/abc/artifacts/public/Twilight%20Princess-0.2.3.apworld",
            "Twilight Princess-0.2.3.apworld",
            id="url-encoded space",
        ),
    ),
)
def test_fetch_and_extract_dest_filename(
    monkeypatch,
    tmp_path,
    fetch_content_mod,
    url,
    expected_dest_filename,
):
    downloaded_to = []

    def mock_download_to_path(url, path, sha256=None, size=None):
        downloaded_to.append(path)
        path.touch()

    monkeypatch.setattr(fetch_content_mod, "download_to_path", mock_download_to_path)

    fetch_content_mod.fetch_and_extract(url, tmp_path, extract=False)

    assert len(downloaded_to) == 1
    assert downloaded_to[0].name == expected_dest_filename


@pytest.mark.parametrize(
    "expected,orig,dest,strip_components,add_prefix",
    [
        # Archives to repack
        (True, pathlib.Path("archive"), pathlib.Path("archive.tar.zst"), 0, ""),
        (True, pathlib.Path("archive.tar"), pathlib.Path("archive.tar.zst"), 0, ""),
        (True, pathlib.Path("archive.tgz"), pathlib.Path("archive.tar.zst"), 0, ""),
        (True, pathlib.Path("archive.zip"), pathlib.Path("archive.tar.zst"), 0, ""),
        (True, pathlib.Path("archive.tar.xz"), pathlib.Path("archive.tar.zst"), 0, ""),
        (True, pathlib.Path("archive.zst"), pathlib.Path("archive.tar.zst"), 0, ""),
        # Path is exactly the same
        (False, pathlib.Path("archive"), pathlib.Path("archive"), 0, ""),
        (False, pathlib.Path("file.txt"), pathlib.Path("file.txt"), 0, ""),
        (False, pathlib.Path("archive.tar"), pathlib.Path("archive.tar"), 0, ""),
        (False, pathlib.Path("archive.tgz"), pathlib.Path("archive.tgz"), 0, ""),
        (False, pathlib.Path("archive.zip"), pathlib.Path("archive.zip"), 0, ""),
        (
            False,
            pathlib.Path("archive.tar.zst"),
            pathlib.Path("archive.tar.zst"),
            0,
            "",
        ),
        (
            False,
            pathlib.Path("archive-before.tar.zst"),
            pathlib.Path("archive-after.tar.zst"),
            0,
            "",
        ),
        (
            False,
            pathlib.Path("before.foo.bar.baz"),
            pathlib.Path("after.foo.bar.baz"),
            0,
            "",
        ),
        # Non-default values for strip_components and add_prefix parameters
        (True, pathlib.Path("archive.tar.zst"), pathlib.Path("archive.tar.zst"), 1, ""),
        (
            True,
            pathlib.Path("archive.tar.zst"),
            pathlib.Path("archive.tar.zst"),
            0,
            "prefix",
        ),
        (
            True,
            pathlib.Path("archive.tar.zst"),
            pathlib.Path("archive.tar.zst"),
            1,
            "prefix",
        ),
        # Real edge cases that should not be repacks
        (
            False,
            pathlib.Path("python-3.8.10-amd64.exe"),
            pathlib.Path("python.exe"),
            0,
            "",
        ),
        (
            False,
            pathlib.Path("9ee26e91-9b52-44ba-8d30-c0230dd587b2.bin"),
            pathlib.Path("model.esen.intgemm.alphas.bin"),
            0,
            "",
        ),
    ],
)
def test_should_repack_archive(
    fetch_content_mod, orig, dest, expected, strip_components, add_prefix
):
    assert (
        fetch_content_mod.should_repack_archive(
            orig, dest, strip_components, add_prefix
        )
        == expected
    ), (
        f"Failed for orig: {orig}, dest: {dest}, strip_components: {strip_components}, add_prefix: {add_prefix}, expected {expected} but received {not expected}"
    )
