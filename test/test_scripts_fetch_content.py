import hashlib
import http.server
import json
import os
import pathlib
import threading
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


class RangeServer(http.server.ThreadingHTTPServer):
    """Serves a single blob, optionally honouring range requests."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, content, ranges=True):
        super().__init__(("127.0.0.1", 0), RangeHandler)
        self.content = content
        self.ranges = ranges
        self.requests = []
        self.lock = threading.Lock()

    @property
    def url(self):
        return "http://{}:{}/blob".format(*self.server_address)


class RangeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        content = self.server.content
        requested = self.headers.get("Range")
        with self.server.lock:
            self.server.requests.append(requested)

        start, end = 0, len(content) - 1
        partial = False
        if requested and self.server.ranges:
            start, _, last = requested.partition("=")[2].partition("-")
            start, end = int(start), int(last)
            if start >= len(content):
                # An empty object makes every range unsatisfiable.
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(content)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, len(content) - 1)
            partial = True

        body = content[start : end + 1]
        self.send_response(206 if partial else 200)
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def serve():
    servers = []

    def inner(content, ranges=True):
        server = RangeServer(content, ranges=ranges)
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        servers.append(server)
        return server

    yield inner

    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def sliced(monkeypatch, fetch_content_mod):
    """Enable slicing with boundaries small enough to exercise in a test."""

    def inner(slices=4, min_bytes=1024, probe=256):
        monkeypatch.setenv("TASKGRAPH_FETCH_SLICES", str(slices))
        monkeypatch.setenv("TASKGRAPH_FETCH_SLICE_MIN_BYTES", str(min_bytes))
        monkeypatch.setattr(fetch_content_mod, "PROBE_BYTES", probe)
        # remaining_slices refuses to make slices smaller than a megabyte,
        # which would collapse every test case down to a single slice.
        monkeypatch.setattr(fetch_content_mod, "MIN_SLICE_BYTES", 64)

    return inner


def test_sliced_download(tmp_path, fetch_content_mod, serve, sliced):
    content = os.urandom(4096)
    server = serve(content)
    sliced(slices=4)
    dest = tmp_path / "blob"

    assert fetch_content_mod.sliced_download_to_path(
        server.url,
        dest,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )
    assert dest.read_bytes() == content
    # The probe, plus one request per remaining slice.
    assert len(server.requests) == 5
    assert server.requests[0] == "bytes=0-255"


def test_sliced_download_reassembles_out_of_order(
    tmp_path, fetch_content_mod, serve, sliced
):
    """Slices land at the right offsets no matter what order they finish in."""
    content = bytes(i % 251 for i in range(100000))
    server = serve(content)
    sliced(slices=8)
    dest = tmp_path / "blob"

    assert fetch_content_mod.sliced_download_to_path(server.url, dest)
    assert dest.read_bytes() == content


def test_sliced_download_disabled(tmp_path, fetch_content_mod, serve, monkeypatch):
    server = serve(b"x" * 4096)
    monkeypatch.setenv("TASKGRAPH_FETCH_SLICES", "1")
    dest = tmp_path / "blob"

    assert not fetch_content_mod.sliced_download_to_path(server.url, dest)
    assert server.requests == []
    assert not dest.exists()


def test_sliced_download_known_small_size_skips_probe(
    tmp_path, fetch_content_mod, serve, sliced
):
    content = b"x" * 512
    server = serve(content)
    sliced(slices=4, min_bytes=1024)
    dest = tmp_path / "blob"

    assert not fetch_content_mod.sliced_download_to_path(
        server.url, dest, size=len(content)
    )
    assert server.requests == []


def test_sliced_download_unknown_small_size_finishes_in_probe(
    tmp_path, fetch_content_mod, serve, sliced
):
    """A file the probe swallows whole costs exactly one request."""
    content = b"x" * 200
    server = serve(content)
    sliced(slices=4, min_bytes=1024, probe=256)
    dest = tmp_path / "blob"

    assert fetch_content_mod.sliced_download_to_path(server.url, dest)
    assert dest.read_bytes() == content
    assert len(server.requests) == 1


def test_sliced_download_no_range_support(tmp_path, fetch_content_mod, serve, sliced):
    server = serve(b"x" * 4096, ranges=False)
    sliced()
    dest = tmp_path / "blob"

    assert not fetch_content_mod.sliced_download_to_path(server.url, dest)
    assert not dest.exists()


def test_sliced_download_empty_object(tmp_path, fetch_content_mod, serve, sliced):
    """A zero length artifact 416s, and must fall back rather than blow up."""
    server = serve(b"")
    sliced()
    dest = tmp_path / "blob"

    assert not fetch_content_mod.sliced_download_to_path(server.url, dest)
    assert not dest.exists()

    # ...and the fallback still downloads it.
    fetch_content_mod.download_to_path(server.url, dest)
    assert dest.read_bytes() == b""


def test_sliced_download_bad_sha256(tmp_path, fetch_content_mod, serve, sliced):
    server = serve(os.urandom(4096))
    sliced()
    dest = tmp_path / "blob"

    with pytest.raises(fetch_content_mod.IntegrityError):
        fetch_content_mod.sliced_download_to_path(server.url, dest, sha256="0" * 64)

    assert not dest.exists()
    assert not dest.with_name(f"{dest.name}.tmp").exists()


def test_sliced_download_bad_size(tmp_path, fetch_content_mod, serve, sliced):
    server = serve(os.urandom(4096))
    sliced()
    dest = tmp_path / "blob"

    with pytest.raises(fetch_content_mod.IntegrityError):
        fetch_content_mod.sliced_download_to_path(server.url, dest, size=9999)

    assert not dest.exists()
    assert not dest.with_name(f"{dest.name}.tmp").exists()


def test_sliced_download_forwards_headers(tmp_path, fetch_content_mod, serve, sliced):
    """Caller supplied headers reach every request, not just the probe."""
    seen = []

    class Recording(RangeHandler):
        def do_GET(self):
            seen.append(self.headers.get("X-Taskcluster-Skip-Cdn"))
            super().do_GET()

    server = serve(os.urandom(4096))
    server.RequestHandlerClass = Recording
    sliced(slices=4)

    assert fetch_content_mod.sliced_download_to_path(
        server.url, tmp_path / "blob", headers=["x-taskcluster-skip-cdn: true"]
    )
    assert seen == ["true"] * 5


@pytest.mark.parametrize(
    "start,total,slices,expected",
    (
        pytest.param(
            0, 400, 4, [(0, 99), (100, 199), (200, 299), (300, 399)], id="even"
        ),
        pytest.param(
            0, 10, 4, [(0, 1), (2, 3), (4, 5), (6, 9)], id="remainder to last"
        ),
        pytest.param(64, 128, 2, [(64, 95), (96, 127)], id="offset start"),
        pytest.param(100, 100, 4, [], id="nothing left"),
        pytest.param(200, 100, 4, [], id="past the end"),
        pytest.param(0, 100, 1, [(0, 99)], id="single"),
    ),
)
def test_remaining_slices(
    fetch_content_mod, monkeypatch, start, total, slices, expected
):
    monkeypatch.setattr(fetch_content_mod, "MIN_SLICE_BYTES", 1)
    assert fetch_content_mod.remaining_slices(start, total, slices) == expected
    if expected:
        # The ranges must tile the region exactly, with no gaps or overlaps.
        assert expected[0][0] == start
        assert expected[-1][1] == total - 1
        for (_, prev_end), (next_start, _) in zip(expected, expected[1:]):
            assert next_start == prev_end + 1


def test_remaining_slices_respects_minimum(fetch_content_mod):
    """Slices below the minimum are merged rather than each taking a connection."""
    assert fetch_content_mod.remaining_slices(0, 1024, 8) == [(0, 1023)]


@pytest.mark.parametrize(
    "headers,expected",
    (
        pytest.param(["Foo: bar"], {"Foo": "bar"}, id="simple"),
        pytest.param([], {}, id="empty"),
        pytest.param(None, {}, id="none"),
        pytest.param(
            ["Location: https://example.com:443/x"],
            {"Location": "https://example.com:443/x"},
            id="colon in value",
        ),
    ),
)
def test_parse_headers(fetch_content_mod, headers, expected):
    assert fetch_content_mod.parse_headers(headers) == expected


@pytest.mark.parametrize(
    "value,expected",
    (
        pytest.param(None, None, id="unset"),
        pytest.param("1", ["x-taskcluster-skip-cdn: true"], id="1"),
        pytest.param("true", ["x-taskcluster-skip-cdn: true"], id="true"),
        pytest.param("0", None, id="0"),
    ),
)
def test_command_task_artifacts_skip_cdn(
    monkeypatch, tmp_path, fetch_content_mod, value, expected
):
    fetches = [{"task": "abc123", "artifact": "public/foo.zip", "extract": False}]
    monkeypatch.setenv("MOZ_FETCHES", json.dumps(fetches))
    monkeypatch.setenv("TASKCLUSTER_ROOT_URL", "https://tc.example.com")
    monkeypatch.delenv("TASKGRAPH_SKIP_CDN", raising=False)
    if value is not None:
        monkeypatch.setenv("TASKGRAPH_SKIP_CDN", value)

    captured = []
    monkeypatch.setattr(fetch_content_mod, "fetch_urls", captured.extend)

    args = MagicMock()
    args.dest = str(tmp_path)
    fetch_content_mod.command_task_artifacts(args)

    assert [download[5] for download in captured] == [expected]


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
            # stream_download adds accept-encoding
            assert len(req.headers) == len(headers) + 1
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
        for url, dest_dir, extract, sha256, size, headers in downloads:
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

    def mock_download_to_path(url, path, sha256=None, size=None, headers=None):
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
