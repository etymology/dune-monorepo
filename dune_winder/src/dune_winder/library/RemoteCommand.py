###############################################################################
# Name: RemoteCommand.py
# Uses: Helpers for classifying remote UI commands.
###############################################################################
import re


READ_ONLY_REFERENCE = re.compile(r"^[A-Za-z0-9_.]+$")
READ_ONLY_METHOD = re.compile(r"^([A-Za-z0-9_.]+)\.([A-Za-z0-9_]+)\((.*)\)$")


# -----------------------------------------------------------------------------
def _hasSafeArguments(arguments):
  stack = []
  quote = None
  escaped = False
  index = 0
  length = len(arguments)

  while index < length:
    char = arguments[index]

    if quote is not None:
      if escaped:
        escaped = False
      elif char == "\\":
        escaped = True
      elif char == quote:
        quote = None
      index += 1
      continue

    if char in ('"', "'"):
      quote = char
      index += 1
      continue

    if char in "([{":
      stack.append(char)
      index += 1
      continue

    if char in ")]}":
      if len(stack) == 0:
        return False

      opening = stack.pop()
      if (
        (opening == "(" and char != ")")
        or (opening == "[" and char != "]")
        or (opening == "{" and char != "}")
      ):
        return False

      index += 1
      continue

    if char.isalpha() or char == "_":
      index += 1
      while index < length and (
        arguments[index].isalnum() or arguments[index] in "._"
      ):
        index += 1

      lookAhead = index
      while lookAhead < length and arguments[lookAhead].isspace():
        lookAhead += 1

      if lookAhead < length and arguments[lookAhead] == "(":
        return False

      continue

    index += 1

  return quote is None and len(stack) == 0


# -----------------------------------------------------------------------------
def _splitTopLevelListItems(query):
  items = []
  stack = []
  quote = None
  escaped = False
  start = 0

  for index, char in enumerate(query):
    if quote is not None:
      if escaped:
        escaped = False
      elif char == "\\":
        escaped = True
      elif char == quote:
        quote = None
      continue

    if char in ('"', "'"):
      quote = char
      continue

    if char in "([{":
      stack.append(char)
      continue

    if char in ")]}":
      if len(stack) == 0:
        return None

      opening = stack.pop()
      if (
        (opening == "(" and char != ")")
        or (opening == "[" and char != "]")
        or (opening == "{" and char != "}")
      ):
        return None
      continue

    if char == "," and len(stack) == 0:
      item = query[start:index].strip()
      if len(item) == 0:
        return None

      items.append(item)
      start = index + 1

  if quote is not None or len(stack) != 0:
    return None

  item = query[start:].strip()
  if len(item) == 0:
    return None

  items.append(item)
  return items


# -----------------------------------------------------------------------------
def _isReadOnlyMethodCall(query):
  match = READ_ONLY_METHOD.fullmatch(query)
  if match is None:
    return False

  methodName = match.group(2)
  if (
    not methodName.startswith("get")
    and not methodName.startswith("is")
  ):
    return False

  arguments = match.group(3)
  return _hasSafeArguments(arguments)


# -----------------------------------------------------------------------------
def _isReadOnlyListQuery(query):
  if not query.startswith("[") or not query.endswith("]"):
    return False

  items = _splitTopLevelListItems(query[1:-1].strip())
  if not items:
    return False

  return all(isReadOnlyRemoteCommand(item) for item in items)


# -----------------------------------------------------------------------------
def isReadOnlyRemoteCommand(command):
  if command is None:
    return False

  query = command.strip()
  if len(query) == 0:
    return False

  return (
    READ_ONLY_REFERENCE.fullmatch(query) is not None
    or _isReadOnlyMethodCall(query)
    or _isReadOnlyListQuery(query)
  )
