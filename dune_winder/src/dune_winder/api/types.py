###############################################################################
# Name: types.py
# Uses: Shared command API types.
###############################################################################

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandError:
  code: str
  message: str

  def to_dict(self):
    return {"code": self.code, "message": self.message}


class CommandDispatchException(Exception):
  def __init__(self, code, message):
    super().__init__(message)
    self.error = CommandError(str(code), str(message))

