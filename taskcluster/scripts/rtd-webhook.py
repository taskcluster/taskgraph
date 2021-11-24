# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import requests
from redo import retry

SECRET_BASEURL_TPL = "http://taskcluster/secrets/v1/secret/{}"
TASKGRAPH_WEBHOOK_URL = (
    "https://readthedocs.org/api/v2/webhook/taskcluster-taskgraph/183005/"
)


def fetch_secret(secret_name):
    """Retrieves the given taskcluster secret"""
    secret_url = SECRET_BASEURL_TPL.format(secret_name)
    r = requests.get(secret_url)
    r.raise_for_status()
    return r.json()["secret"]


def post_doc_build():
    data = {
        "branches": "default",
        "token": fetch_secret("project/releng/taskgraph/ci")["readthedocs_token"],
    }
    r = requests.post(TASKGRAPH_WEBHOOK_URL, data=data)
    r.raise_for_status()


retry(post_doc_build, 3, 1)
