# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import io
import os
import shutil
import stat
import tarfile
import tempfile
import unittest

import pytest

from taskgraph.util.archive import (
    DEFAULT_MTIME,
    create_tar_from_files,
    create_tar_gz_from_files,
)

MODE_STANDARD = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


def file_hash(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        while True:
            data = fh.read(8192)
            if not data:
                break
            h.update(data)

    return h.hexdigest()


@pytest.fixture
def create_files(tmp_path):

    def inner():
        files = {}
        for i in range(10):
            p = tmp_path / f"file{i:02d}"
            p.write_bytes(b"file%02d" % i)
            # Need to set permissions or umask may influence testing.
            p.chmod(MODE_STANDARD)
            files[f"file{i:02d}"] = str(p)

        for i in range(10):
            files[f"file{i + 10:02d}"] = io.BytesIO(b"file%02d" % (i + 10))

        return files

    return inner


def verify_basic_tarfile(tf):
    assert len(tf.getmembers()) == 20

    names = [f"file{i:02d}" for i in range(20)]
    assert tf.getnames() == names

    for ti in tf.getmembers():
        assert ti.uid == 0
        assert ti.gid == 0
        assert ti.uname == ""
        assert ti.gname == ""
        assert ti.mode == MODE_STANDARD
        assert ti.mtime == DEFAULT_MTIME


@pytest.mark.xfail(
    reason="ValueError is not thrown despite being provided directory."
)
def test_dirs_refused(tmp_path):
    tp = tmp_path / "test.tar"
    with open(tp, "wb") as fh:
        with pytest.raises(ValueError, match="not a regular"):
            create_tar_from_files(fh, {"test": str(tmp_path)})


def test_setuid_setgid_refused(tmp_path):
    uid = tmp_path / "setuid"
    uid.touch()
    uid.chmod(MODE_STANDARD | stat.S_ISUID)

    gid = tmp_path / "setgid"
    gid.touch()
    gid.chmod(MODE_STANDARD | stat.S_ISGID)

    tp = tmp_path / "test.tar"
    with open(tp, "wb") as fh:
        with pytest.raises(ValueError, match="cannot add file with setuid"):
            create_tar_from_files(fh, {"test": str(uid)})
        with pytest.raises(ValueError, match="cannot add file with setuid"):
            create_tar_from_files(fh, {"test": str(gid)})


def test_create_tar_basic(tmp_path, create_files):
    files = create_files()

    tp = tmp_path / "test.tar"
    with open(tp, "wb") as fh:
        create_tar_from_files(fh, files)

    # Output should be deterministic.
    assert file_hash(tp) == "01cd314e277f060e98c7de6c8ea57f96b3a2065c"

    with tarfile.open(tp, "r") as tf:
        verify_basic_tarfile(tf)


@pytest.mark.xfail(reason="hash mismatch")
def test_executable_preserved():
    p = os.path.join(d, "exec")
    with open(p, "wb") as fh:
        fh.write(b"#!/bin/bash\n")
    os.chmod(p, MODE_STANDARD | stat.S_IXUSR)

    tp = os.path.join(d, "test.tar")
    with open(tp, "wb") as fh:
        create_tar_from_files(fh, {"exec": p})

    assert file_hash(tp) == "357e1b81c0b6cfdfa5d2d118d420025c3c76ee93"

    with tarfile.open(tp, "r") as tf:
        m = tf.getmember("exec")
        assert m.mode == MODE_STANDARD | stat.S_IXUSR


def test_create_tar_gz_basic(tmp_path, create_files):
    files = create_files()

    gp = tmp_path / "test.tar.gz"
    with open(gp, "wb") as fh:
        create_tar_gz_from_files(fh, files)

    assert file_hash(gp) == "7c4da5adc5088cdf00911d5daf9a67b15de714b7"

    with tarfile.open(gp, "r:gz") as tf:
        verify_basic_tarfile(tf)


def test_tar_gz_name(tmp_path, create_files):
    files = create_files()

    gp = tmp_path / "test.tar.gz"
    with open(gp, "wb") as fh:
        create_tar_gz_from_files(fh, files, filename="foobar")

    assert file_hash(gp) == "721e00083c17d16df2edbddf40136298c06d0c49"

    with tarfile.open(gp, "r:gz") as tf:
        verify_basic_tarfile(tf)
