###############################################################################
# Name: registry.py
# Uses: Registry and dispatcher for explicit remote commands.
###############################################################################

from dataclasses import dataclass
from typing import Any, Callable

from .types import CommandDispatchException


@dataclass(frozen=True)
class _CommandSpec:
  name: str
  handler: Callable[[dict], Any]
  isMutating: bool


class CommandRegistry:
  def __init__(self, log=None):
    self._commands = {}
    self._log = log

  # ---------------------------------------------------------------------------
  def register(self, name: str, handler: Callable[[dict], Any], isMutating=False):
    name = str(name).strip()
    if not name:
      raise ValueError("Command name cannot be empty.")
    if name in self._commands:
      raise ValueError("Duplicate command registration: " + name)
    if not callable(handler):
      raise ValueError("Handler for " + name + " must be callable.")

    self._commands[name] = _CommandSpec(name, handler, bool(isMutating))

  # ---------------------------------------------------------------------------
  def _dispatch(self, name: str, args: dict):
    if not isinstance(args, dict):
      raise CommandDispatchException(
        "VALIDATION_ERROR", "Command arguments must be a JSON object."
      )

    if name not in self._commands:
      raise CommandDispatchException("UNKNOWN_COMMAND", "Unknown command: " + str(name))

    commandSpec = self._commands[name]

    try:
      return commandSpec.handler(args)
    except CommandDispatchException:
      raise
    except (TypeError, ValueError, KeyError) as exception:
      raise CommandDispatchException("VALIDATION_ERROR", str(exception))

  # ---------------------------------------------------------------------------
  @staticmethod
  def _ok(data):
    return {"ok": True, "data": data, "error": None}

  # ---------------------------------------------------------------------------
  @staticmethod
  def _error(code, message):
    return {"ok": False, "data": None, "error": {"code": str(code), "message": str(message)}}

  # ---------------------------------------------------------------------------
  def execute(self, name: str, args=None):
    if args is None:
      args = {}

    try:
      data = self._dispatch(name, args)
      return CommandRegistry._ok(data)
    except CommandDispatchException as exception:
      return CommandRegistry._error(exception.error.code, exception.error.message)
    except Exception as exception:
      if self._log is not None:
        self._log.add(
          self.__class__.__name__,
          "DISPATCH",
          "Command execution failed.",
          [name, args, repr(exception)],
        )
      return CommandRegistry._error("INTERNAL_ERROR", "Internal error while executing command.")

  # ---------------------------------------------------------------------------
  def executeRequest(self, payload):
    if not isinstance(payload, dict):
      return CommandRegistry._error("BAD_REQUEST", "Request body must be a JSON object.")

    name = payload.get("name")
    if not isinstance(name, str) or len(name.strip()) == 0:
      return CommandRegistry._error("BAD_REQUEST", "Field 'name' must be a non-empty string.")

    args = payload.get("args", {})
    return self.execute(name.strip(), args=args)

  # ---------------------------------------------------------------------------
  def executeBatchRequest(self, payload):
    if not isinstance(payload, dict):
      return CommandRegistry._error("BAD_REQUEST", "Request body must be a JSON object.")

    requests = payload.get("requests")
    if not isinstance(requests, list):
      return CommandRegistry._error("BAD_REQUEST", "Field 'requests' must be a list.")

    results = {}
    for index, request in enumerate(requests):
      requestId = str(index)
      if isinstance(request, dict) and "id" in request:
        requestId = str(request["id"])

      if not isinstance(request, dict):
        results[requestId] = CommandRegistry._error(
          "BAD_REQUEST", "Each batch entry must be a JSON object."
        )
        continue

      results[requestId] = self.executeRequest(request)

    return {"ok": True, "data": {"results": results}, "error": None}

