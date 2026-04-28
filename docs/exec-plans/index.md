# Execution Plans & Decisions

Implementation roadmaps, phase status, and audit/decision documents.

## Structure

```
exec-plans/
├── active/                 ← Current implementation work
│   └── rust-port-2026-04.md ← Master plan for Rust port (phases 0-9)
├── completed/              ← Archived execution plans
└── audit-results/          ← Phase verification documents
    ├── DOMAIN_MODEL_VERIFICATION.md (Phase 0 summary)
    ├── geometry-verification.md (Phase 0.1)
    ├── plc-and-head-verification.md (Phase 0.0)
    ├── winder-state-verification.md (Phase 0.2)
    └── tension-measurement-verification.md (Phase 0.3)
```

## Authority

These documents are **CURRENT** for their phase:
- Active plans are the implementation roadmap
- Audit results document divergences between specs and implementation
- Completed plans are archived for reference

Updated as phases complete or decisions change.

## When to Update

- **Phase completes** → move plan to completed/, create new active plan
- **Phase audit finishes** → place verification document in audit-results/
- **Decision made** → document in the audit result for that module

## Related

- **Master plan details:** `.harness/plans/type-safety-first-port.json`
- **Harness runner:** `.harness/runner.py`
- **Authority framework:** `docs/STALENESS.md`
