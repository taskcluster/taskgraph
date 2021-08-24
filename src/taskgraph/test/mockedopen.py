# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# Imported from
# https://searchfox.org/mozilla-central/rev/c3ebaf6de2d481c262c04bb9657eaf76bf47e2ac/config/mozunit/mozunit/mozunit.py#116-232

import sys
import os
from io import StringIO


class MockedFile(StringIO):
    def __init__(self, context, filename, content=""):
        self.context = context
        self.name = filename
        StringIO.__init__(self, content)

    def close(self):
        self.context.files[self.name] = self.getvalue()
        StringIO.close(self)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


def normcase(path):
    """
    Normalize the case of `path`.

    Don't use `os.path.normcase` because that also normalizes forward slashes
    to backslashes on Windows.
    """
    if sys.platform.startswith("win"):
        return path.lower()
    return path


class MockedOpen:
    """
    Context manager diverting the open builtin such that opening files
    can open "virtual" file instances given when creating a MockedOpen.

    with MockedOpen({'foo': 'foo', 'bar': 'bar'}):
        f = open('foo', 'r')

    will thus open the virtual file instance for the file 'foo' to f.

    If the content of a file is given as None, then that file will be
    represented as not existing (even if it does, actually, exist).

    MockedOpen also masks writes, so that creating or replacing files
    doesn't touch the file system, while subsequently opening the file
    will return the recorded content.

    with MockedOpen():
        f = open('foo', 'w')
        f.write('foo')
    self.assertRaises(Exception,f.open('foo', 'r'))
    """

    def __init__(self, files={}):
        self.files = {}
        for name, content in files.items():
            self.files[normcase(os.path.abspath(name))] = content

    def __call__(self, name, mode="r"):
        absname = normcase(os.path.abspath(name))
        if "w" in mode:
            file = MockedFile(self, absname)
        elif absname in self.files:
            content = self.files[absname]
            if content is None:
                raise OSError(2, "No such file or directory")
            file = MockedFile(self, absname, content)
        elif "a" in mode:
            file = MockedFile(self, absname, self.open(name, "r").read())
        else:
            file = self.open(name, mode)
        if "a" in mode:
            file.seek(0, os.SEEK_END)
        return file

    def __enter__(self):
        import builtins

        self.open = builtins.open
        self._orig_path_exists = os.path.exists
        self._orig_path_isdir = os.path.isdir
        self._orig_path_isfile = os.path.isfile
        builtins.open = self
        os.path.exists = self._wrapped_exists
        os.path.isdir = self._wrapped_isdir
        os.path.isfile = self._wrapped_isfile

    def __exit__(self, type, value, traceback):
        import builtins

        builtins.open = self.open
        os.path.exists = self._orig_path_exists
        os.path.isdir = self._orig_path_isdir
        os.path.isfile = self._orig_path_isfile

    def _wrapped_exists(self, p):
        return self._wrapped_isfile(p) or self._wrapped_isdir(p)

    def _wrapped_isfile(self, p):
        p = normcase(p)
        if p in self.files:
            return self.files[p] is not None

        abspath = normcase(os.path.abspath(p))
        if abspath in self.files:
            return self.files[abspath] is not None

        return self._orig_path_isfile(p)

    def _wrapped_isdir(self, p):
        p = normcase(p)
        p = p if p.endswith(("/", "\\")) else p + os.sep
        if any(f.startswith(p) for f in self.files):
            return True

        abspath = normcase(os.path.abspath(p) + os.sep)
        if any(f.startswith(abspath) for f in self.files):
            return True

        return self._orig_path_isdir(p)
