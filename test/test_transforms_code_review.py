from types import SimpleNamespace

import pytest

from taskgraph.transforms.code_review import transforms


@pytest.mark.parametrize(
    "task, expected_dependencies",
    [
        pytest.param(
            {"soft-dependencies": ["existing"]},
            ["existing", "review-task"],
            id="default-upstream-attribute",
        ),
        pytest.param(
            {
                "upstream-attribute": "code-review-build-test",
                "soft-dependencies": ["existing"],
            },
            ["existing", "build-test-task"],
            id="custom-upstream-attribute",
        ),
    ],
)
def test_add_dependencies_uses_upstream_attribute(task, expected_dependencies):
    dependencies = {
        "review": SimpleNamespace(
            label="review-task",
            attributes={"code-review": True},
        ),
        "build-test": SimpleNamespace(
            label="build-test-task",
            attributes={"code-review-build-test": True},
        ),
    }
    config = SimpleNamespace(kind_dependencies_tasks=dependencies)

    [result] = transforms(config, [task])

    assert result["soft-dependencies"] == expected_dependencies
    assert "upstream-attribute" not in result
