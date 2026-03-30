from __future__ import annotations


class JSRRegistry:
  def __init__(self):
    self._targets = {}

  def register(self, name: str, target):
    self._targets[str(name)] = target

  def resolve(self, name: str):
    return self._targets.get(str(name))

  def names(self):
    return tuple(sorted(self._targets))
