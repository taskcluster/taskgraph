import inspect

import pytest

from taskgraph.util.workertypes import get_worker_type

ALIASES = {
    "[bt]-linux": {
        "provisioner": "{trust-domain}-{level}",
        "implementation": "docker-worker",
        "os": "linux",
        "worker-type": "{alias}-gcp",
    }
}


@pytest.mark.parametrize(
    "alias,level,expected",
    (
        ("linux", 1, Exception),
        ("b-linux", 3, "test-domain-3/b-linux-gcp"),
        ("t-linux", 1, "test-domain-1/t-linux-gcp"),
    ),
)
def test_get_worker_type(graph_config, alias, level, expected):
    graph_config["workers"]["aliases"] = ALIASES

    if inspect.isclass(expected) and issubclass(expected, BaseException):
        with pytest.raises(expected):
            get_worker_type(graph_config, alias, level)
    else:
        worker_type = get_worker_type(graph_config, alias, level)
        print(f"worker type: {worker_type}")
        assert "/".join(worker_type) == expected
