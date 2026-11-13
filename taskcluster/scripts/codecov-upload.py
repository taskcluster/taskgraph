# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
import stat
import subprocess
from pathlib import Path

# run-task exports the upload token in CODECOV_TOKEN, which the uploader reads.
FETCHES_DIR = Path(os.environ["MOZ_FETCHES_DIR"])
uploader = FETCHES_DIR / "codecov"
uploader.chmod(uploader.stat().st_mode | stat.S_IEXEC)
subprocess.run(
    [
        str(uploader),
        "--verbose",
        "upload-process",
        "--fail-on-error",
        "-f",
        str(FETCHES_DIR / "coverage.xml"),
    ],
    check=True,
)
