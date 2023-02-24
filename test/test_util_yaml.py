# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from textwrap import dedent
from unittest import mock

from taskgraph.util import yaml

from .mockedopen import MockedOpen


def test_load():
    yaml.load_yaml.clear()
    with MockedOpen(
        {
            "/dir1/dir2/foo.yml": dedent(
                """\
                prop:
                    - val1
                """
            )
        }
    ):
        assert yaml.load_yaml("/dir1/dir2", "foo.yml") == {"prop": ["val1"]}


@mock.patch("taskgraph.util.yaml.load_stream")
def test_is_memoized(mocked_load_stream):
    yaml.load_yaml.clear()
    with MockedOpen(
        {
            "/dir1/dir2/foo.yml": dedent(
                """\
                prop:
                    - val1
                """
            )
        }
    ):
        yaml.load_yaml("/dir1/dir2", "foo.yml")
        yaml.load_yaml("/dir1/dir2", "foo.yml")
        yaml.load_yaml("/dir1/dir2", "foo.yml")
        assert mocked_load_stream.call_count == 1


def test_key_order():
    yaml.load_yaml.clear()
    with MockedOpen(
        {
            "/dir1/dir2/foo.yml": dedent(
                """\
                job:
                    foo: 1
                    bar: 2
                    xyz: 3
                """
            )
        }
    ):
        assert list(yaml.load_yaml("/dir1/dir2", "foo.yml")["job"].keys()) == [
            "foo",
            "bar",
            "xyz",
        ]
