from __future__ import annotations

from dataclasses import dataclass

from .jsr_registry import JSRRegistry
from .tags import TagStore


@dataclass
class ScanContext:
  tag_store: TagStore
  jsr_registry: JSRRegistry
  current_program: str | None = None
  scan_count: int = 0
