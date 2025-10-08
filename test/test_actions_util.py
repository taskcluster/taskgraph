import unittest
from unittest import mock

from taskgraph.actions.util import get_parameters


class TestActionsUtil(unittest.TestCase):
    @mock.patch("taskgraph.actions.util.get_artifact")
    def test_get_parameters_default_prefix(self, mock_get_artifact):
        mock_get_artifact.return_value = {"some": "parameters"}

        result = get_parameters("task-id-123")

        mock_get_artifact.assert_called_once_with(
            "task-id-123", "public/parameters.yml"
        )
        self.assertEqual(result, {"some": "parameters"})

    @mock.patch("taskgraph.actions.util.get_artifact")
    def test_get_parameters_custom_prefix(self, mock_get_artifact):
        mock_get_artifact.return_value = {"some": "parameters"}

        result = get_parameters("task-id-123", "custom-prefix")

        mock_get_artifact.assert_called_once_with(
            "task-id-123", "custom-prefix/parameters.yml"
        )
        self.assertEqual(result, {"some": "parameters"})
