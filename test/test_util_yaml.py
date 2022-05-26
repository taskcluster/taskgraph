# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from textwrap import dedent

from taskgraph.util import yaml

from .mockedopen import MockedOpen


def test_load():
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


def test_key_order():
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
