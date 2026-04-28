# Design Documentation

Authoritative specifications and architectural decisions.

## Structure

```
design-docs/
├── allium-specs/           ← Formal domain model (CURRENT: Apr 26-27)
│   ├── index.md            ← Overview of all 4 specs
│   └── *.allium            ← Formal specifications
├── architecture/           ← System design and boundaries
│   ├── index.md
│   ├── shared-domain-model.md      ← Geometry, PLC, math (shared by both apps)
│   ├── dune-winder-application.md  ← Winding-specific design
│   └── dune-tension-application.md ← Tension-specific design
└── core-beliefs.md         ← Design principles and values
```

## Authority

These documents are **AUTHORITATIVE**:
- Allium specs define what the system does
- Architecture explains why components are organized this way
- Core beliefs guide design decisions

**Reference for truth priority:**
1. Allium specs (formal specification)
2. Architecture docs (system design)
3. Allium specs again (when in doubt)

See [`docs/STALENESS.md`](../STALENESS.md) for complete authority framework.

## When to Update

- **Allium spec evolves** → update the .allium file and index.md
- **Architecture decision changes** → update architecture/*.md
- **Design principle clarified** → update core-beliefs.md

Always update architecture docs when Allium specs change, to keep them in sync.
