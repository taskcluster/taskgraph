import bz2
import gzip
import hashlib
import http.server
import io
import json
import lzma
import os
import pathlib
import shutil
import stat
import sys
import tarfile
import threading
import urllib.request
import zipfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from types import SimpleNamespace
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
    """Serves a single blob, optionally honouring range requests.

    ``faults`` maps a Range header value to a list of faults to inject, one
    per request for that range: "error" answers 500, "truncate" sends half of
    the body and closes the connection, and "slow" pauses half way through.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, content, ranges=True, accept_ranges="bytes", gzip=False, log=None
    ):
        super().__init__(("127.0.0.1", 0), RangeHandler)
        self.content = content
        self.ranges = ranges
        self.accept_ranges = accept_ranges
        self.gzip = gzip
        self.faults = {}
        self.requests = []
        self.log = log
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
            if self.server.log is not None:
                self.server.log.append((self.server, requested))
            faults = self.server.faults.get(requested)
            fault = faults.pop(0) if faults else None

        if fault == "error":
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        start, end = 0, len(content) - 1
        partial = False
        if requested and self.server.ranges:
            start, _, last = requested.partition("=")[2].partition("-")
            start, end = int(start), int(last)
            if start >= len(content):
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
        elif self.server.gzip and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = gzip.compress(body)
            self.send_header("Content-Encoding", "gzip")
        if self.server.accept_ranges:
            self.send_header("Accept-Ranges", self.server.accept_ranges)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if fault == "truncate":
            self.wfile.write(body[: len(body) // 2])
            self.close_connection = True
            return
        if fault == "slow":
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            threading.Event().wait(1)
            self.wfile.write(body[len(body) // 2 :])
            return
        self.wfile.write(body)


@pytest.fixture
def serve():
    servers = []

    def inner(content, **kwargs):
        server = RangeServer(content, **kwargs)
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        servers.append(server)
        return server

    yield inner

    for server in servers:
        server.shutdown()
        server.server_close()


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


def _make_tar(path, files):
    with tarfile.open(path, "w") as tar:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


@pytest.fixture(params=("stream", "file"))
def mock_downloads(request, monkeypatch, fetch_content_mod):
    """Serve downloads from a dict of names to content, streamed or not."""
    monkeypatch.setenv(
        "TASKGRAPH_FETCH_STREAM", "1" if request.param == "stream" else "0"
    )
    contents = {}

    def mock_download_to_path(url, path, sha256=None, size=None, headers=None):
        path.write_bytes(contents[url.rsplit("/", 1)[-1]])

    def mock_stream_download(url, sha256=None, size=None, headers=None):
        data = contents[url.rsplit("/", 1)[-1]]
        for i in range(0, len(data), 1000):
            yield data[i : i + 1000]

    monkeypatch.setattr(fetch_content_mod, "download_to_path", mock_download_to_path)
    monkeypatch.setattr(fetch_content_mod, "stream_download", mock_stream_download)
    return contents


def test_fetch_urls_merges_staged_extractions(
    tmp_path, fetch_content_mod, mock_downloads
):
    archives = tmp_path / "archives"
    archives.mkdir()
    _make_tar(
        archives / "common.tar",
        {"tests/common/a.txt": "a", "tests/shared.txt": "first"},
    )
    _make_tar(
        archives / "suite.tar",
        {"tests/suite/b.txt": "b", "tests/shared.txt": "second"},
    )
    dest = tmp_path / "fetches"
    dest.mkdir()
    for name in ("common.tar", "suite.tar"):
        mock_downloads[name] = (archives / name).read_bytes()

    fetch_content_mod.fetch_urls(
        [
            ("https://example.com/common.tar", dest, True, None),
            ("https://example.com/suite.tar", dest, True, None),
        ]
    )

    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*")) == [
        "tests",
        "tests/common",
        "tests/common/a.txt",
        "tests/shared.txt",
        "tests/suite",
        "tests/suite/b.txt",
    ]
    assert (dest / "tests" / "shared.txt").read_text() == "second"


def test_open_for_append_preserves_existing_content(tmp_path, fetch_content_mod):
    path = tmp_path / "forward"
    path.write_bytes(b"existing\n")

    fd = fetch_content_mod.open_for_append(str(path))
    try:
        os.write(fd, b"appended\n")
    finally:
        os.close(fd)

    assert path.read_bytes() == b"existing\nappended\n"


def test_open_for_append_windows(fetch_content_mod, monkeypatch, mocker):
    winapi = SimpleNamespace(CreateFile=mocker.Mock(return_value=123), OPEN_EXISTING=3)
    msvcrt = SimpleNamespace(open_osfhandle=mocker.Mock(return_value=456))
    monkeypatch.setitem(sys.modules, "_winapi", winapi)
    monkeypatch.setitem(sys.modules, "msvcrt", msvcrt)
    monkeypatch.setattr(fetch_content_mod, "sys", SimpleNamespace(platform="win32"))

    assert fetch_content_mod.open_for_append("forward") == 456

    # Append-only access and shared read/write/delete are required for concurrent
    # writers; the forward file must already exist.
    winapi.CreateFile.assert_called_once_with("forward", 0x4, 0x7, 0, 3, 0, 0)
    msvcrt.open_osfhandle.assert_called_once_with(123, 0)


@pytest.mark.parametrize("forward", [None, ""])
def test_record_marker_disabled(fetch_content_mod, monkeypatch, mocker, forward):
    monkeypatch.delenv("MOZ_RESOURCE_MONITOR_FORWARD", raising=False)
    if forward is not None:
        monkeypatch.setenv("MOZ_RESOURCE_MONITOR_FORWARD", forward)
    open_for_append = mocker.patch.object(fetch_content_mod, "open_for_append")

    fetch_content_mod.record_marker("fetch-content", 1, 2, "url")

    open_for_append.assert_not_called()


@pytest.mark.parametrize("failure", ["open", "write"])
def test_record_marker_ignores_io_errors(
    fetch_content_mod, monkeypatch, mocker, failure
):
    monkeypatch.setenv("MOZ_RESOURCE_MONITOR_FORWARD", "forward")
    open_for_append = mocker.patch.object(
        fetch_content_mod, "open_for_append", return_value=123
    )
    write = mocker.patch.object(fetch_content_mod.os, "write")
    close = mocker.patch.object(fetch_content_mod.os, "close")
    if failure == "open":
        open_for_append.side_effect = OSError("cannot open")
    else:
        write.side_effect = OSError("cannot write")

    fetch_content_mod.record_marker("fetch-content", 1, 2, "url")

    open_for_append.assert_called_once_with("forward")
    if failure == "open":
        write.assert_not_called()
        close.assert_not_called()
    else:
        write.assert_called_once_with(
            123,
            b'["marker", "fetch-content", 1, 2, {"type": "Text", "text": "url"}, 2]\n',
        )
        close.assert_called_once_with(123)


def test_fetch_and_extract_records_marker_on_failure(fetch_content_mod, mocker):
    error = fetch_content_mod.IntegrityError("invalid checksum")
    fetch = mocker.patch.object(
        fetch_content_mod, "fetch_and_extract", side_effect=error
    )
    record_marker = mocker.patch.object(fetch_content_mod, "record_marker")
    mocker.patch.object(fetch_content_mod.time, "monotonic", side_effect=[10, 20])

    with pytest.raises(fetch_content_mod.IntegrityError) as exc:
        fetch_content_mod.fetch_and_extract_with_marker("url", "dest", True, "sha", 42)

    assert exc.value is error
    fetch.assert_called_once_with("url", "dest", True, "sha", 42)
    record_marker.assert_called_once_with("fetch-content", 10, 20, "url")


@pytest.mark.parametrize("command", ["static-url", "git-checkout-archive"])
@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
def test_fetch_commands_record_markers(
    tmp_path, fetch_content_mod, monkeypatch, mocker, command, fail
):
    forward = tmp_path / "forward"
    forward.touch()
    monkeypatch.setenv("MOZ_RESOURCE_MONITOR_FORWARD", str(forward))
    dest = tmp_path / "fetches" / "archive.tar.zst"
    url = (
        "https://example.com/repo"
        if command == "git-checkout-archive"
        else "https://example.com/archive.tar.gz"
    )
    error = RuntimeError("fetch failed")

    def finish(*args, **kwargs):
        # The marker must cover the final archive creation, not just the download.
        assert forward.read_bytes() == b""
        if fail:
            raise error
        dest.write_bytes(b"archive")

    if command == "git-checkout-archive":
        args = SimpleNamespace(
            dest=str(dest),
            repo=url,
            commit="revision",
            path_prefix="repo",
            ssh_key_secret=None,
            include_dot_git=False,
        )

        def checkout(path, *args, **kwargs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"partial archive")
            finish()

        mocker.patch.object(
            fetch_content_mod, "git_checkout_archive", side_effect=checkout
        )
        run = fetch_content_mod.command_git_checkout_archive
    else:
        args = SimpleNamespace(
            dest=str(dest),
            url=url,
            sha256="sha",
            size=42,
            headers=[],
            gpg_sig_url=None,
            gpg_key_env=None,
            force_archive=False,
            strip_components=0,
            add_prefix="",
        )

        def download(url, path, **kwargs):
            path.write_bytes(b"download")

        mocker.patch.object(fetch_content_mod, "download_to_path", side_effect=download)
        mocker.patch.object(fetch_content_mod, "repack_archive", side_effect=finish)
        run = fetch_content_mod.command_static_url

    mocker.patch.object(fetch_content_mod.time, "monotonic", side_effect=[10, 20])
    if fail:
        with pytest.raises(RuntimeError) as exc:
            run(args)
        assert exc.value is error
        assert not dest.exists()
    else:
        run(args)
        assert dest.read_bytes() == b"archive"

    assert list(dest.parent.iterdir()) == ([] if fail else [dest])
    assert [json.loads(line) for line in forward.read_text().splitlines()] == [
        ["marker", "fetch-content", 10, 20, {"type": "Text", "text": url}, 2]
    ]


def test_fetch_urls_records_markers(
    tmp_path, fetch_content_mod, mock_downloads, monkeypatch
):
    forward = tmp_path / "forward"
    forward.touch()
    monkeypatch.setenv("MOZ_RESOURCE_MONITOR_FORWARD", str(forward))
    dest = tmp_path / "fetches"
    dest.mkdir()
    mock_downloads["a.txt"] = b"a"
    mock_downloads["b.txt"] = b"b"
    urls = ["https://example.com/a.txt", "https://example.com/b.txt"]

    fetch_content_mod.fetch_urls([(url, dest, False, None) for url in urls])

    records = [json.loads(line) for line in forward.read_text().splitlines()]
    assert sorted(r[4]["text"] for r in records) == urls
    for kind, name, start, end, data, category in records:
        assert (kind, name, data["type"], category) == (
            "marker",
            "fetch-content",
            "Text",
            2,
        )
        assert start <= end


def test_fetch_urls_places_unextracted_files(
    tmp_path, fetch_content_mod, mock_downloads
):
    archives = tmp_path / "archives"
    archives.mkdir()
    _make_tar(archives / "tool.tar", {"tool/bin/tool": "t"})
    dest = tmp_path / "fetches"
    dest.mkdir()
    mock_downloads["tool.tar"] = (archives / "tool.tar").read_bytes()
    mock_downloads["plain.txt"] = mock_downloads["notatar.txt"] = b"plain"

    fetch_content_mod.fetch_urls(
        [
            ("https://example.com/tool.tar", dest, True, None),
            ("https://example.com/plain.txt", dest, False, None),
            ("https://example.com/notatar.txt", dest, True, None),
        ]
    )

    assert sorted(p.name for p in dest.iterdir()) == [
        "notatar.txt",
        "plain.txt",
        "tool",
    ]
    assert (dest / "tool" / "bin" / "tool").read_text() == "t"
    assert (dest / "notatar.txt").read_text() == "plain"


def test_merge_tree_replaces_conflicting_entries(tmp_path, fetch_content_mod):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "dir").mkdir(parents=True)
    (src / "dir" / "new.txt").write_text("new")
    (src / "file").write_text("file")
    (dest / "dir" / "kept").mkdir(parents=True)
    (dest / "dir" / "new.txt").write_text("old")
    (dest / "file").mkdir()

    fetch_content_mod.merge_tree(src, dest)

    assert not src.exists()
    assert (dest / "dir" / "new.txt").read_text() == "new"
    assert (dest / "dir" / "kept").is_dir()
    assert (dest / "file").is_file()


@pytest.mark.skipif(
    sys.platform == "win32" or os.getuid() == 0, reason="needs POSIX directory modes"
)
def test_merge_tree_readonly_dir_from_later_fetch(tmp_path, fetch_content_mod):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "tests").mkdir(parents=True)
    (src / "tests" / "b.txt").write_text("b")
    (dest / "tests").mkdir(parents=True)
    (dest / "tests" / "a.txt").write_text("a")
    (src / "tests").chmod(0o555)

    fetch_content_mod.merge_tree(src, dest)

    assert (dest / "tests" / "a.txt").read_text() == "a"
    assert (dest / "tests" / "b.txt").read_text() == "b"
    assert stat.S_IMODE((dest / "tests").stat().st_mode) == 0o555


@pytest.fixture
def popen_calls(monkeypatch, fetch_content_mod):
    """Record the arguments of every subprocess.Popen call, letting them run."""
    calls = []
    real_popen = fetch_content_mod.subprocess.Popen

    def recording_popen(args, *a, **kw):
        calls.append(args)
        return real_popen(args, *a, **kw)

    monkeypatch.setattr(fetch_content_mod.subprocess, "Popen", recording_popen)
    return calls


def _tar_bytes(tmp_path, files):
    _make_tar(tmp_path / "raw.tar", files)
    return (tmp_path / "raw.tar").read_bytes()


def _make_tar_zst(path, files):
    zstandard = pytest.importorskip("zstandard")
    path.write_bytes(
        zstandard.ZstdCompressor().compress(_tar_bytes(path.parent, files))
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
@pytest.mark.skipif(not shutil.which("zstd"), reason="needs the zstd program")
def test_extract_archive_zstd_with_tar(tmp_path, fetch_content_mod, popen_calls):
    archive = tmp_path / "archive.tar.zst"
    _make_tar_zst(archive, {"dir/a.txt": "a", "b.txt": "b"})
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.extract_archive(archive, dest)

    assert popen_calls == [
        ["tar", "--use-compress-program=zstd", "-xf", str(archive.resolve())]
    ]
    assert (dest / "dir" / "a.txt").read_text() == "a"
    assert (dest / "b.txt").read_text() == "b"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
def test_extract_archive_zstd_without_zstd_program(
    tmp_path, fetch_content_mod, popen_calls, monkeypatch
):
    """Without a zstd program, decompress in Python and pipe to tar."""
    archive = tmp_path / "archive.tar.zst"
    _make_tar_zst(archive, {"dir/a.txt": "a"})
    dest = tmp_path / "dest"
    dest.mkdir()
    monkeypatch.setattr(fetch_content_mod.shutil, "which", lambda name: None)

    fetch_content_mod.extract_archive(archive, dest)

    assert popen_calls == [["tar", "xf", "-"]]
    assert (dest / "dir" / "a.txt").read_text() == "a"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
def test_extract_archive_other_compression_pipes_to_tar(
    tmp_path, fetch_content_mod, popen_calls
):
    """Only zstd is handed to tar; other formats still go through the pipe."""
    archive = tmp_path / "archive.tar.xz"
    archive.write_bytes(lzma.compress(_tar_bytes(tmp_path, {"dir/a.txt": "a"})))
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.extract_archive(archive, dest)

    assert popen_calls == [["tar", "xf", "-"]]
    assert (dest / "dir" / "a.txt").read_text() == "a"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
@pytest.mark.skipif(not shutil.which("zstd"), reason="needs the zstd program")
def test_extract_archive_zstd_tar_failure(tmp_path, fetch_content_mod):
    """A corrupt archive makes tar exit non-zero, which must be reported."""
    archive = tmp_path / "archive.tar.zst"
    # Incompressible, so that the tar header survives the truncation.
    _make_tar_zst(archive, {"a.txt": os.urandom(1000000).hex()})
    data = archive.read_bytes()
    archive.write_bytes(data[: len(data) // 2])
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(Exception, match="exited"):
        fetch_content_mod.extract_archive(archive, dest)


def _compress(data, compression):
    if compression == "zst":
        zstandard = pytest.importorskip("zstandard")
        return zstandard.ZstdCompressor(write_checksum=True).compress(data)
    return {
        "tar": lambda d: d,
        "gz": gzip.compress,
        "xz": lzma.compress,
        "bz2": bz2.compress,
    }[compression](data)


@pytest.fixture
def streamed(monkeypatch, fetch_content_mod):
    """Enable streaming, and make sure nothing goes through a file."""
    monkeypatch.setenv("TASKGRAPH_FETCH_STREAM", "1")
    monkeypatch.setattr(fetch_content_mod.time, "sleep", lambda s: None)
    downloaded = []

    def recording_download_to_path(url, path, *args, **kwargs):
        downloaded.append(path.name)
        return real_download_to_path(url, path, *args, **kwargs)

    real_download_to_path = fetch_content_mod.download_to_path
    monkeypatch.setattr(
        fetch_content_mod, "download_to_path", recording_download_to_path
    )
    return downloaded


def _archive_url(server, name):
    return server.url.replace("/blob", f"/{name}")


STREAM_FILES = {
    "dir/a.txt": "a",
    "dir/sub/b.txt": "b" * 5000,
    # Big and incompressible enough to span many chunks.
    "big.txt": os.urandom(300000).hex(),
}


def _assert_extracted(dest, files=STREAM_FILES):
    extracted = {
        p.relative_to(dest).as_posix(): p.read_text()
        for p in dest.rglob("*")
        if p.is_file()
    }
    assert extracted == files


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
@pytest.mark.parametrize(
    "compression,commands",
    (
        pytest.param("zst", [["zstd", "-dcq"], ["tar", "xf", "-"]]),
        pytest.param("gz", [["tar", "xf", "-"]]),
        pytest.param("xz", [["tar", "xf", "-"]]),
        pytest.param("bz2", [["tar", "xf", "-"]]),
        pytest.param("tar", [["tar", "xf", "-"]]),
    ),
)
def test_stream_extract(
    tmp_path, fetch_content_mod, serve, streamed, popen_calls, compression, commands
):
    if compression == "zst" and not shutil.which("zstd"):
        pytest.skip("needs the zstd program")
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), compression)
    server = serve(data)
    dest = tmp_path / "fetches"
    dest.mkdir()

    fetch_content_mod.fetch_urls(
        [
            (
                _archive_url(server, f"archive.tar.{compression}"),
                dest,
                True,
                hashlib.sha256(data).hexdigest(),
                len(data),
            )
        ]
    )

    _assert_extracted(dest)
    assert server.requests == [None]
    assert streamed == []
    assert popen_calls == commands


@pytest.mark.skipif(sys.platform == "win32", reason="Windows extracts with tarfile")
def test_stream_extract_zstd_without_zstd_program(
    tmp_path, fetch_content_mod, serve, streamed, popen_calls, monkeypatch
):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "zst")
    server = serve(data)
    monkeypatch.setattr(fetch_content_mod.shutil, "which", lambda name: None)
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(_archive_url(server, "a.tar.zst"), dest)

    _assert_extracted(dest)
    assert streamed == []
    assert popen_calls == [["tar", "xf", "-"]]


def test_stream_extract_windows(
    tmp_path, fetch_content_mod, serve, streamed, popen_calls, monkeypatch
):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "gz")
    server = serve(data)
    monkeypatch.setattr(fetch_content_mod.sys, "platform", "win32")
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(_archive_url(server, "a.tar.gz"), dest)

    _assert_extracted(dest)
    assert streamed == []
    assert popen_calls == []


def test_stream_extract_retry(tmp_path, fetch_content_mod, serve, streamed):
    """A stream that breaks off is extracted again from scratch."""
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "gz")
    server = serve(data)
    server.faults[None] = ["truncate"]
    dest = tmp_path / "fetches"
    dest.mkdir()

    fetch_content_mod.fetch_urls(
        [(_archive_url(server, "a.tar.gz"), dest, True, None, None)]
    )

    _assert_extracted(dest)
    assert server.requests == [None, None]
    assert streamed == []


def test_stream_extract_partial_output_not_merged(
    tmp_path, fetch_content_mod, serve, streamed, monkeypatch
):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "tar")
    server = serve(data)
    server.faults[None] = ["truncate"] * 5
    dest = tmp_path / "fetches"
    dest.mkdir()
    emptied = []
    real_empty_directory = fetch_content_mod.empty_directory

    def recording_empty_directory(path):
        # Half of the archive made it, so some files were extracted.
        emptied.append(sorted(p.name for p in pathlib.Path(path).rglob("*")))
        real_empty_directory(path)

    monkeypatch.setattr(fetch_content_mod, "empty_directory", recording_empty_directory)

    with pytest.raises(Exception, match="no more retries"):
        fetch_content_mod.fetch_urls(
            [(_archive_url(server, "a.tar"), dest, True, None, None)]
        )

    assert len(emptied) == 5
    assert all("a.txt" in names for names in emptied), emptied
    # Only the empty staging directory is left behind.
    (staging,) = dest.iterdir()
    assert staging.name.startswith(".fetch.")
    assert list(staging.iterdir()) == []


@pytest.mark.parametrize("mismatch", ("sha256", "size"))
def test_stream_extract_integrity_mismatch(
    tmp_path, fetch_content_mod, serve, streamed, mismatch
):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "gz")
    server = serve(data)
    dest = tmp_path / "fetches"
    dest.mkdir()
    sha256 = "0" * 64 if mismatch == "sha256" else None
    size = len(data) + 1 if mismatch == "size" else None

    with pytest.raises(Exception, match="no more retries"):
        fetch_content_mod.fetch_urls(
            [(_archive_url(server, "a.tar.gz"), dest, True, sha256, size)]
        )

    assert len(server.requests) == 5
    assert [p.name for p in dest.rglob("*") if not p.name.startswith(".fetch.")] == []


@pytest.mark.parametrize("compression", ("gz", "zst"))
def test_stream_extract_broken_archive_not_retried(
    tmp_path, fetch_content_mod, serve, streamed, compression
):
    """An intact download of a broken archive fails without retrying."""
    good = _compress(_tar_bytes(tmp_path, STREAM_FILES), compression)
    # Corrupt the middle, well after the start used to detect the type.
    mid = len(good) // 2
    data = (
        good[:mid]
        + bytes(b ^ 0xFF for b in good[mid : mid + 2000])
        + good[mid + 2000 :]
    )
    server = serve(data)
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(Exception) as excinfo:
        fetch_content_mod.fetch_and_extract(
            _archive_url(server, f"a.tar.{compression}"),
            dest,
            sha256=hashlib.sha256(data).hexdigest(),
        )

    assert "no more retries" not in str(excinfo.value)
    assert server.requests == [None]
    assert list(dest.iterdir()) == []


def test_stream_extract_not_an_archive(tmp_path, fetch_content_mod, serve, streamed):
    """Something that isn't a tar is written out whole, from one request."""
    data = os.urandom(3 * 1024 * 1024)
    server = serve(data)
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(
        _archive_url(server, "tool.exe"), dest, sha256=hashlib.sha256(data).hexdigest()
    )

    assert (dest / "tool.exe").read_bytes() == data
    assert server.requests == [None]
    assert streamed == []


@pytest.mark.skipif(not shutil.which("unzip"), reason="needs unzip")
def test_zip_goes_through_file(tmp_path, fetch_content_mod, serve, streamed):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("dir/a.txt", "a")
    server = serve(archive.read_bytes())
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(_archive_url(server, "archive.zip"), dest)

    assert streamed == ["archive.zip"]
    assert (dest / "dir" / "a.txt").read_text() == "a"
    assert not (dest / "archive.zip").exists()


def test_no_extract_goes_through_file(tmp_path, fetch_content_mod, serve, streamed):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "gz")
    server = serve(data)
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(
        _archive_url(server, "a.tar.gz"), dest, extract=False
    )

    assert streamed == ["a.tar.gz"]
    assert (dest / "a.tar.gz").read_bytes() == data


def test_stream_disabled(tmp_path, fetch_content_mod, serve, streamed, monkeypatch):
    data = _compress(_tar_bytes(tmp_path, STREAM_FILES), "gz")
    server = serve(data)
    monkeypatch.setenv("TASKGRAPH_FETCH_STREAM", "0")
    dest = tmp_path / "dest"
    dest.mkdir()

    fetch_content_mod.fetch_and_extract(_archive_url(server, "a.tar.gz"), dest)

    assert streamed == ["a.tar.gz"]
    _assert_extracted(dest)


@pytest.mark.parametrize(
    "value,expected",
    (
        pytest.param(None, True, id="unset"),
        pytest.param("1", True, id="1"),
        pytest.param("0", False, id="0"),
        pytest.param("false", False, id="false"),
    ),
)
def test_streaming_enabled(fetch_content_mod, monkeypatch, value, expected):
    monkeypatch.delenv("TASKGRAPH_FETCH_STREAM", raising=False)
    if value is not None:
        monkeypatch.setenv("TASKGRAPH_FETCH_STREAM", value)
    assert fetch_content_mod.streaming_enabled() is expected


def test_iter_reader_iter_from_start(fetch_content_mod):
    chunks = [b"abc", b"defg", b"hi"]
    reader = fetch_content_mod.IterReader(iter(chunks))
    fh = io.BufferedReader(reader, 2)
    assert fh.read(5) == b"abcde"
    assert b"".join(reader.iter_from_start()) == b"abcdefghi"


def test_iter_reader_failure(fetch_content_mod):
    def chunks():
        yield b"abc"
        raise OSError("connection reset")

    reader = fetch_content_mod.IterReader(chunks())
    assert reader.read(10) == b"abc"
    assert not reader.failed
    with pytest.raises(OSError):
        reader.drain()
    assert reader.failed


@pytest.mark.skipif(
    sys.platform == "win32" or os.getuid() == 0, reason="needs POSIX directory modes"
)
def test_empty_directory_readonly(tmp_path, fetch_content_mod):
    (tmp_path / "ro" / "sub").mkdir(parents=True)
    (tmp_path / "ro" / "sub" / "f").write_text("f")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside)
    (tmp_path / "ro" / "sub").chmod(0o555)
    (tmp_path / "ro").chmod(0o555)

    fetch_content_mod.empty_directory(tmp_path)

    assert list(tmp_path.iterdir()) == []
    assert outside.exists()


def test_stream_extract_verifies_unread_tail(
    tmp_path, fetch_content_mod, serve, streamed, monkeypatch
):
    """tarfile stops reading at the end of the archive, which may come well
    before the end of the download. The whole download must still get
    verified."""
    # Trailing zeros are valid tar padding.
    data = _tar_bytes(tmp_path, STREAM_FILES) + bytes(5 * 1024 * 1024)
    server = serve(data)
    monkeypatch.setattr(fetch_content_mod.sys, "platform", "win32")
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(Exception, match="no more retries"):
        fetch_content_mod.fetch_and_extract(
            _archive_url(server, "a.tar"), dest, sha256="0" * 64
        )
    assert list(dest.iterdir()) == []

    fetch_content_mod.fetch_and_extract(
        _archive_url(server, "a.tar"), dest, sha256=hashlib.sha256(data).hexdigest()
    )
    _assert_extracted(dest)
