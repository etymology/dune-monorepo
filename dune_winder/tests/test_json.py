import datetime
import json
import unittest

from dune_winder.library.json import dumps


class JsonTests(unittest.TestCase):
  def test_dumps_serializes_nested_datetime_values(self):
    timestamp = datetime.datetime(2026, 3, 2, 22, 49, 10, 313941)
    data = {"timestamp": timestamp, "items": [1, timestamp]}

    result = json.loads(dumps(data))

    self.assertEqual(result["timestamp"], str(timestamp))
    self.assertEqual(result["items"][1], str(timestamp))
