# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import os
import shutil
import stat
import tarfile
import tempfile
import unittest
from io import BufferedRandom, BytesIO
from unittest import mock

import taskcluster_urls as liburls

from taskgraph.config import GraphConfig
from taskgraph.util import docker

from .mockedopen import MockedOpen

MODE_STANDARD = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


@mock.patch.dict("os.environ", {"TASKCLUSTER_ROOT_URL": liburls.test_root_url()})
class TestDocker(unittest.TestCase):
    def test_generate_context_hash(self):
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, "docker", "my-image"))
            p = os.path.join(tmpdir, "docker", "my-image", "Dockerfile")
            with open(p, "w") as f:
                f.write("FROM node\nADD a-file\n")
            os.chmod(p, MODE_STANDARD)
            p = os.path.join(tmpdir, "docker", "my-image", "a-file")
            with open(p, "w") as f:
                f.write("data\n")
            os.chmod(p, MODE_STANDARD)
            self.assertEqual(
                docker.generate_context_hash(
                    tmpdir, os.path.join(tmpdir, "docker/my-image"), "my-image"
                ),
                "ab46d51b191eb6c595cccf1fa02485b4e1decc6ba9737a8b8613038d3661be52",
            )
        finally:
            shutil.rmtree(tmpdir)

    def test_docker_image_explicit_registry(self):
        files = {}
        files[f"{docker.IMAGE_DIR}/myimage/REGISTRY"] = "cool-images"
        files[f"{docker.IMAGE_DIR}/myimage/VERSION"] = "1.2.3"
        files[f"{docker.IMAGE_DIR}/myimage/HASH"] = "sha256:434..."
        with MockedOpen(files):
            self.assertEqual(
                docker.docker_image("myimage"), "cool-images/myimage@sha256:434..."
            )

    def test_docker_image_explicit_registry_by_tag(self):
        files = {}
        files[f"{docker.IMAGE_DIR}/myimage/REGISTRY"] = "myreg"
        files[f"{docker.IMAGE_DIR}/myimage/VERSION"] = "1.2.3"
        files[f"{docker.IMAGE_DIR}/myimage/HASH"] = "sha256:434..."
        with MockedOpen(files):
            self.assertEqual(
                docker.docker_image("myimage", by_tag=True), "myreg/myimage:1.2.3"
            )

    def test_docker_image_default_registry(self):
        files = {}
        files[f"{docker.IMAGE_DIR}/REGISTRY"] = "mozilla"
        files[f"{docker.IMAGE_DIR}/myimage/VERSION"] = "1.2.3"
        files[f"{docker.IMAGE_DIR}/myimage/HASH"] = "sha256:434..."
        with MockedOpen(files):
            self.assertEqual(
                docker.docker_image("myimage"), "mozilla/myimage@sha256:434..."
            )

    def test_docker_image_default_registry_by_tag(self):
        files = {}
        files[f"{docker.IMAGE_DIR}/REGISTRY"] = "mozilla"
        files[f"{docker.IMAGE_DIR}/myimage/VERSION"] = "1.2.3"
        files[f"{docker.IMAGE_DIR}/myimage/HASH"] = "sha256:434..."
        with MockedOpen(files):
            self.assertEqual(
                docker.docker_image("myimage", by_tag=True), "mozilla/myimage:1.2.3"
            )

    def test_create_context_tar_basic(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test_image")
            os.mkdir(d)
            with open(os.path.join(d, "Dockerfile"), "a"):
                pass
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            with open(os.path.join(d, "extra"), "a"):
                pass
            os.chmod(os.path.join(d, "extra"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp)
            self.assertEqual(
                h, "3134fa88c39a604132b260c2c3cf09f6fe4a8234475a4272fd9438aac47caaae"
            )

            # File prefix should be "my_image"
            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "extra",
                    ],
                )
        finally:
            shutil.rmtree(tmp)

    def test_create_context_topsrcdir_files(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)
            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include extra/file0\n")
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            extra = os.path.join(tmp, "extra")
            os.mkdir(extra)
            with open(os.path.join(extra, "file0"), "a"):
                pass
            os.chmod(os.path.join(extra, "file0"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp)
            self.assertEqual(
                h, "56657d2f428fe268cc3b0966649a3bf8477dcd2eade7a1d4accc5c312f075a2f"
            )

            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "topsrcdir/extra/file0",
                    ],
                )
        finally:
            shutil.rmtree(tmp)

    def test_create_context_absolute_path(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            # Absolute paths in %include syntax are not allowed.
            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include /etc/shadow\n")

            with self.assertRaisesRegex(Exception, "cannot be absolute"):
                docker.create_context_tar(tmp, d, os.path.join(tmp, "tar"))
        finally:
            shutil.rmtree(tmp)

    def test_create_context_outside_topsrcdir(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include foo/../../../etc/shadow\n")

            with self.assertRaisesRegex(Exception, "path outside topsrcdir"):
                docker.create_context_tar(tmp, d, os.path.join(tmp, "tar"))
        finally:
            shutil.rmtree(tmp)

    def test_create_context_missing_extra(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include does/not/exist\n")

            with self.assertRaisesRegex(Exception, "path does not exist"):
                docker.create_context_tar(tmp, d, os.path.join(tmp, "tar"))
        finally:
            shutil.rmtree(tmp)

    def test_create_context_extra_directory(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %include extra\n")
                fh.write(b"# %include file0\n")
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            extra = os.path.join(tmp, "extra")
            os.mkdir(extra)
            for i in range(3):
                p = os.path.join(extra, f"file{i}")
                with open(p, "wb") as fh:
                    fh.write(b"file%d" % i)
                os.chmod(p, MODE_STANDARD)

            with open(os.path.join(tmp, "file0"), "a"):
                pass
            os.chmod(os.path.join(tmp, "file0"), MODE_STANDARD)

            tp = os.path.join(tmp, "tar")
            h = docker.create_context_tar(tmp, d, tp)

            self.assertEqual(
                h, "ba7b62e8f25977e8e6629aee1d121ae92b6007258c90a53fb94c8607e1e96e10"
            )

            with tarfile.open(tp, "r:gz") as tf:
                self.assertEqual(
                    tf.getnames(),
                    [
                        "Dockerfile",
                        "topsrcdir/extra/file0",
                        "topsrcdir/extra/file1",
                        "topsrcdir/extra/file2",
                        "topsrcdir/file0",
                    ],
                )
        finally:
            shutil.rmtree(tmp)

    def test_stream_context_tar(self):
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "test-image")
            os.mkdir(d)

            with open(os.path.join(d, "Dockerfile"), "wb") as fh:
                fh.write(b"# %ARG PYTHON_VERSION\n")
                fh.write(b"# %include extra\n")
                fh.write(b"# %include file0\n")
            os.chmod(os.path.join(d, "Dockerfile"), MODE_STANDARD)

            extra = os.path.join(tmp, "extra")
            os.mkdir(extra)
            for i in range(3):
                p = os.path.join(extra, f"file{i}")
                with open(p, "wb") as fh:
                    fh.write(b"file%d" % i)
                os.chmod(p, MODE_STANDARD)

            with open(os.path.join(tmp, "file0"), "a"):
                pass
            os.chmod(os.path.join(tmp, "file0"), MODE_STANDARD)

            # file objects are BufferedRandom instances
            out_file = BufferedRandom(BytesIO(b""))
            h = docker.stream_context_tar(
                tmp, d, out_file, args={"PYTHON_VERSION": "3.8"}
            )

            self.assertEqual(
                h, "ba7b62e8f25977e8e6629aee1d121ae92b6007258c90a53fb94c8607e1e96e10"
            )
        finally:
            shutil.rmtree(tmp)

    def test_image_paths_with_custom_kind(self):
        """Test image_paths function with graph_config parameter."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create the kinds directory structure
            kinds_dir = os.path.join(temp_dir, "kinds", "docker-test-image")
            os.makedirs(kinds_dir)

            # Create the kind.yml file with task definitions
            kind_yml_path = os.path.join(kinds_dir, "kind.yml")
            with open(kind_yml_path, "w") as f:
                f.write("tasks:\n")
                f.write("  test-image:\n")
                f.write("    definition: test-image\n")
                f.write("  another-image:\n")
                f.write("    definition: custom-path\n")

            # Create graph config pointing to our test directory
            temp_graph_config = GraphConfig(
                {
                    "trust-domain": "test-domain",
                    "docker-image-kind": "docker-test-image",
                },
                temp_dir,
            )

            paths = docker.image_paths(temp_graph_config)

            expected_docker_dir = os.path.join(temp_graph_config.root_dir, "docker")
            self.assertEqual(
                paths["test-image"], os.path.join(expected_docker_dir, "test-image")
            )
            self.assertEqual(
                paths["another-image"], os.path.join(expected_docker_dir, "custom-path")
            )
        finally:
            shutil.rmtree(temp_dir)

    def test_parse_volumes_with_graph_config(self):
        """Test parse_volumes function with graph_config parameter."""
        temp_dir = tempfile.mkdtemp()
        try:
            kinds_dir = os.path.join(temp_dir, "kinds", "docker-test-image")
            os.makedirs(kinds_dir)

            kind_yml_path = os.path.join(kinds_dir, "kind.yml")
            with open(kind_yml_path, "w") as f:
                f.write("tasks:\n")
                f.write("  test-image:\n")
                f.write("    definition: test-image\n")

            docker_dir = os.path.join(temp_dir, "docker")
            os.makedirs(docker_dir)

            image_dir = os.path.join(docker_dir, "test-image")
            os.makedirs(image_dir)

            dockerfile_path = os.path.join(image_dir, "Dockerfile")
            with open(dockerfile_path, "wb") as fh:
                fh.write(b"VOLUME /foo/bar \n")
                fh.write(b"VOLUME /hello  /world \n")

            test_graph_config = GraphConfig(
                {
                    "trust-domain": "test-domain",
                    "docker-image-kind": "docker-test-image",
                },
                temp_dir,
            )

            volumes = docker.parse_volumes("test-image", test_graph_config)

            expected_volumes = {"/foo/bar", "/hello", "/world"}
            self.assertEqual(volumes, expected_volumes)

        finally:
            shutil.rmtree(temp_dir)
