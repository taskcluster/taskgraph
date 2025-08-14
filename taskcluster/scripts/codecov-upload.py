# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import functools
import os
import stat
import subprocess
from pathlib import Path

import taskcluster

FETCHES_DIR = Path(os.environ["MOZ_FETCHES_DIR"])


@functools.lru_cache(maxsize=None)
def get_taskcluster_secrets():
    """Get a taskcluster secrets client."""
    if "TASKCLUSTER_PROXY_URL" in os.environ:
        secrets_options = {"rootUrl": os.environ["TASKCLUSTER_PROXY_URL"]}
    else:
        secrets_options = taskcluster.optionsFromEnvironment()

    return taskcluster.Secrets(secrets_options)


def fetch_secret(secret_name):
    """Retrieves the given taskcluster secret"""

    secrets_client = get_taskcluster_secrets()
    secret_data = secrets_client.get(secret_name)

    if secret_data and isinstance(secret_data, dict):
        secret_payload = secret_data.get("secret")
        if secret_payload and isinstance(secret_payload, dict):
            return secret_payload
    raise ValueError(f"Failed to retrieve secret: {secret_name}")


secret_data = fetch_secret("project/releng/taskgraph/ci")
if isinstance(secret_data, dict):
    token = secret_data["codecov_api_token"]
else:
    raise ValueError("Invalid secret data format")
uploader = FETCHES_DIR / "codecov"
uploader.chmod(uploader.stat().st_mode | stat.S_IEXEC)
subprocess.run(
    [
        str(uploader),
        "--verbose",
        "upload-process",
        "--fail-on-error",
        "--token",
        token,
        "-f",
        str(FETCHES_DIR / "coverage.xml"),
    ],
    check=True,
)
