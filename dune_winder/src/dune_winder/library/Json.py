###############################################################################
# Name: Json.py
# Uses: Shared JSON helpers for web responses.
###############################################################################
import json


def dumps(data):
  """
  Serialize data to JSON while stringifying unsupported leaf values such as
  datetimes.
  """
  return json.dumps(data, default=str)
