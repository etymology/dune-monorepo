"""Measurement engine package.

This package holds the tensiometer measurement core, carved out of the former
monolithic :mod:`dune_tension.tensiometer` module. Stage 1 extracts the pure,
zero-state leaves (value types, the legacy-condition compiler, and generic
concurrency/pitch helpers); later stages move the collaborators and the engine
itself. ``dune_tension.tensiometer`` re-exports from here to keep import sites
stable.
"""

from __future__ import annotations
