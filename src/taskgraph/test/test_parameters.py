# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import datetime
import gzip
from base64 import b64decode
from unittest import TestCase, mock

import pytest
from voluptuous import Optional, Required, Schema

import taskgraph  # noqa: F401
from taskgraph import parameters
from taskgraph.parameters import (
    ParameterMismatch,
    Parameters,
    extend_parameters_schema,
    load_parameters_file,
)

from .mockedopen import MockedOpen


class TestParameters(TestCase):

    vals = {
        "base_repository": "repository",
        "build_date": 0,
        "do_not_optimize": [],
        "existing_tasks": {},
        "filters": ["target_tasks_method"],
        "head_ref": "ref",
        "head_repository": "repository",
        "head_rev": "rev",
        "head_tag": "",
        "level": "3",
        "moz_build_date": "20191008095500",
        "optimize_target_tasks": True,
        "owner": "nobody@mozilla.com",
        "project": "project",
        "pushdate": 0,
        "pushlog_id": "0",
        "repository_type": "hg",
        "target_tasks_method": "default",
        "tasks_for": "github-push",
    }

    def test_Parameters_immutable(self):
        p = Parameters(**self.vals)

        def assign():
            p["owner"] = "nobody@example.test"

        self.assertRaises(Exception, assign)

    def test_Parameters_missing_KeyError(self):
        p = Parameters(**self.vals)
        self.assertRaises(KeyError, lambda: p["z"])

    def test_Parameters_invalid_KeyError(self):
        """even if the value is present, if it's not a valid property, raise KeyError"""
        p = Parameters(xyz=10, strict=True, **self.vals)
        self.assertRaises(ParameterMismatch, lambda: p.check())

    def test_Parameters_get(self):
        p = Parameters(owner="nobody@example.test", level=20)
        self.assertEqual(p["owner"], "nobody@example.test")

    def test_Parameters_check(self):
        p = Parameters(**self.vals)
        p.check()  # should not raise

    def test_Parameters_check_missing(self):
        p = Parameters()
        self.assertRaises(ParameterMismatch, lambda: p.check())

        p = Parameters(strict=False)
        p.check()  # should not raise

    def test_Parameters_check_extra(self):
        p = Parameters(xyz=10, **self.vals)
        self.assertRaises(ParameterMismatch, lambda: p.check())

        p = Parameters(strict=False, xyz=10, **self.vals)
        p.check()  # should not raise

    def test_Parameters_file_url_git_remote(self):
        vals = self.vals.copy()
        vals["repository_type"] = "git"

        vals["head_repository"] = "git@bitbucket.com:owner/repo.git"
        p = Parameters(**vals)
        self.assertRaises(ParameterMismatch, lambda: p.file_url(""))

        vals["head_repository"] = "git@github.com:owner/repo.git"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/owner/repo/blob/"
            )
        )

        vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/mozilla-mobile/reference-browser/blob/"
            )
        )

        vals["head_repository"] = "https://github.com/mozilla-mobile/reference-browser/"
        p = Parameters(**vals)
        self.assertTrue(
            p.file_url("", pretty=True).startswith(
                "https://github.com/mozilla-mobile/reference-browser/blob/"
            )
        )

    def test_load_parameters_file_yaml(self):
        with MockedOpen({"params.yml": "some: data\n"}):
            self.assertEqual(load_parameters_file("params.yml"), {"some": "data"})

    def test_load_parameters_file_json(self):
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(load_parameters_file("params.json"), {"some": "data"})

    @mock.patch(
        "taskgraph.util.taskcluster.PRODUCTION_TASKCLUSTER_ROOT_URL",
        "https://tc.example.com",
    )
    @mock.patch("taskgraph.parameters.find_task_id")
    @mock.patch("taskgraph.parameters.yaml.load_stream")
    @mock.patch("taskgraph.parameters.urlopen")
    def test_load_parameters_file_task_id(
        self, mock_urlopen, mock_load_stream, mock_find_task_id
    ):
        # Constants
        tid = "abc"
        project = "foo"
        trust_domain = "bar"
        expected = {"some": "data"}

        # Setup mocks
        mock_load_stream.return_value = expected.copy()
        mock_find_task_id.return_value = tid

        # Test `task-id=`
        ret = load_parameters_file(f"task-id={tid}")
        mock_load_stream.assert_called_with(mock_urlopen())
        self.assertEqual(dict(ret), expected)

        # Test `project=`
        ret = load_parameters_file(f"project={project}", trust_domain=trust_domain)
        mock_load_stream.assert_called_with(mock_urlopen())
        mock_find_task_id.assert_called_with(
            f"{trust_domain}.v2.{project}.latest.taskgraph.decision"
        )
        self.assertEqual(dict(ret), expected)
        self.assertRaises(ValueError, load_parameters_file, f"project={project}")

        # Test gzipped data
        r = mock.Mock()
        r.info.return_value = {"Content-Encoding": "gzip"}
        # 'some: data' gzipped then base64 encoded
        r.read.return_value = b64decode("H4sIAAAAAAAAAyvOz021UkhJLEnkAgB639AyCwAAAA==")
        mock_urlopen.return_value = r
        ret = load_parameters_file(f"task-id={tid}")
        f = mock_load_stream.call_args[0][0]
        self.assertIsInstance(f, gzip.GzipFile)
        self.assertEqual(f.read(), b"some: data\n")

    def test_load_parameters_override(self):
        """
        When ``load_parameters_file`` is passed overrides, they are included in
        the generated parameters.
        """
        self.assertEqual(
            load_parameters_file("", overrides={"some": "data"}), {"some": "data"}
        )

    def test_load_parameters_override_file(self):
        """
        When ``load_parameters_file`` is passed overrides, they overwrite data
        loaded from a file.
        """
        with MockedOpen({"params.json": '{"some": "data"}'}):
            self.assertEqual(
                load_parameters_file("params.json", overrides={"some": "other"}),
                {"some": "other"},
            )

    def test_moz_build_date_time(self):
        p = Parameters(**self.vals)
        self.assertEqual(p["moz_build_date"], "20191008095500")
        self.assertEqual(p.moz_build_date, datetime.datetime(2019, 10, 8, 9, 55, 0))


def test_parameters_id():
    # Some parameters rely on current time, ensure these are the same for the
    # purposes of this test.
    defaults = {
        "build_date": 0,
        "moz_build_date": "2021-08-23",
        "pushdate": 0,
    }

    params1 = Parameters(strict=False, spec=None, foo="bar", **defaults)
    assert params1.id
    assert len(params1.id) == 12

    params2 = Parameters(strict=False, spec="p2", foo="bar", **defaults)
    assert params1.id == params2.id

    params3 = Parameters(strict=False, spec="p3", foo="baz", **defaults)
    assert params1.id != params3.id


@pytest.mark.parametrize(
    "spec,expected",
    (
        (None, "defaults"),
        ("foo/bar.yaml", "bar"),
        ("foo/bar.yml", "bar"),
        ("/bar.json", "bar"),
        ("http://example.org/bar.yml?id=0", "bar"),
        ("task-id=123", "task-id=123"),
        ("project=autoland", "project=autoland"),
    ),
)
def test_parameters_format_spec(spec, expected):
    assert Parameters.format_spec(spec) == expected


def test_extend_parameters_schema(monkeypatch):
    monkeypatch.setattr(
        parameters,
        "base_schema",
        Schema(
            {
                Required("foo"): str,
            }
        ),
    )

    with pytest.raises(ParameterMismatch):
        Parameters(strict=False).check()

    with pytest.raises(ParameterMismatch):
        Parameters(foo="1", bar=True).check()

    extend_parameters_schema(
        {
            Optional("bar"): bool,
        },
        defaults_fn=lambda root: {"foo": "1", "bar": False},
    )

    params = Parameters(foo="1", bar=True)
    params.check()
    assert params["bar"] is True

    params = Parameters(foo="1")
    params.check()
    assert "bar" not in params

    params = Parameters(strict=False)
    params.check()
    assert params["foo"] == "1"
    assert params["bar"] is False
