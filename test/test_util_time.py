# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from taskgraph.util.time import (
    InvalidString,
    UnknownTimeMeasurement,
    current_json_time,
    json_time_from_now,
    value_of,
)


class FromNowTest(unittest.TestCase):
    def test_invalid_str(self):
        with self.assertRaises(InvalidString):
            value_of("wtfs")

    def test_missing_unit(self):
        with self.assertRaises(InvalidString):
            value_of("1")

    def test_missing_unknown_unit(self):
        with self.assertRaises(UnknownTimeMeasurement):
            value_of("1z")

    def test_value_of(self):
        self.assertEqual(value_of("1s").total_seconds(), 1)
        self.assertEqual(value_of("1 second").total_seconds(), 1)
        self.assertEqual(value_of("1min").total_seconds(), 60)
        self.assertEqual(value_of("1h").total_seconds(), 3600)
        self.assertEqual(value_of("1d").total_seconds(), 86400)
        self.assertEqual(value_of("1mo").total_seconds(), 2592000)
        self.assertEqual(value_of("1 month").total_seconds(), 2592000)
        self.assertEqual(value_of("1y").total_seconds(), 31536000)

        with self.assertRaises(UnknownTimeMeasurement):
            value_of("1m").total_seconds()  # ambiguous between minute and month

    def test_json_from_now_utc_now(self):
        # Just here to ensure we don't raise.
        json_time_from_now("1 years")

    def test_json_from_now(self):
        now = datetime(2014, 1, 1)
        self.assertEqual(json_time_from_now("1 years", now), "2015-01-01T00:00:00.000Z")
        self.assertEqual(json_time_from_now("6 days", now), "2014-01-07T00:00:00.000Z")

    def test_current_json_time(self):
        with patch("taskgraph.util.time.datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2014, 1, 1, tzinfo=timezone.utc)
            mock_datetime.side_effect = datetime

            assert current_json_time() == "2014-01-01T00:00:00.000Z"
            assert current_json_time(True) == datetime(2014, 1, 1, tzinfo=timezone.utc)

    def test_json_from_now_tzinfo(self):
        now = datetime(2014, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(json_time_from_now("1 years", now), "2015-01-01T00:00:00.000Z")
        self.assertEqual(json_time_from_now("6 days", now), "2014-01-07T00:00:00.000Z")
