# Documentation Authority & Staleness Framework

**Purpose:** Make it crystal clear what's current, what's stale, and what to trust.

## Source of Truth Priority

### Tier 1: Authoritative (Current, Trust Completely)

#### Allium Specs (design-docs/allium-specs/)
- **Status:** ✅ CURRENT (Apr 26-27, 2026)
- **Authority:** Formal specification of the domain model
- **How to verify:** Check timestamps in each spec file
- **What to do:** Reference these for port implementation; they are ground truth
- **Files:**
  - `winder-states-safety.allium` (Apr 27)
  - `head-transfer.allium` (Apr 27)
  - `uv-layer-geometry.allium` (Apr 26)
  - `tension-measurement.allium` (Apr 27)

#### Active Execution Plans (exec-plans/active/)
- **Status:** ✅ CURRENT (updated as phases complete)
- **Authority:** Implementation roadmap and phase decisions
- **How to verify:** Check git log for phase status updates
- **What to do:** Follow phases; link to harness plan
- **Current:** `rust-port-2026-04.md`

#### Architecture Docs (design-docs/architecture/)
- **Status:** ✅ CURRENT (maintained alongside Allium)
- **Authority:** System boundaries, integration points, high-level design
- **How to verify:** Cross-reference with Allium specs; should not contradict
- **What to do:** Reference for understanding boundaries between dune_winder and dune_tension

#### Product Specs (product-specs/)
- **Status:** ✅ CURRENT (reflects actual operator workflows)
- **Authority:** What operators see/do; user-facing behavior
- **How to verify:** Run system and compare to spec
- **What to do:** Preserve these workflows during port; they are not negotiable

### Tier 2: Reference (Use with Verification)

#### Audit Results (exec-plans/audit-results/)
- **Status:** Current for the phase when generated
- **Authority:** Documents divergences between Allium and Python
- **How to verify:** Check which phase; see decision reasoning
- **What to do:** Use to understand Python deviations; reference when porting that module

#### References (docs/references/)
- **Status:** Generated or curated on-demand
- **Authority:** How-to guides, syntax help, constants
- **How to verify:** Check if doc explains its source (generated from code, from spec, manual)
- **What to do:** Use for learning; always cross-check critical constants against specs

### Tier 3: Stale (Historical Reference Only)

#### dune_winder/planning/ (Mar 29, 2026)
- **Status:** ❌ STALE (30+ days old)
- **Authority:** NONE — for context only
- **Files:** architecture-backlog.md, plc-architecture-proposals.md, plc-ladder-port.md, webui-hardening.md
- **What to do:** DO NOT use as authority; use `exec-plans/active/` instead
- **Why stale:** Superseded by exec-plans/ and Allium specs

#### dune_tension/streaming_*.md (Mar 29, 2026)
- **Status:** ❌ STALE (30+ days old)
- **Authority:** NONE — for context only
- **Files:** codex_streaming_PLAN.md, refactoring_audit.md, streaming_implementation.md, streaming_plan.md, streaming_status.md
- **What to do:** DO NOT use as authority; use `tension-measurement.allium` instead
- **Why stale:** Superseded by Allium spec and exec-plans/

---

## How to Detect Staleness

### 🚨 Definitely Stale

1. **Git commit date >30 days old**
   - Check: `git log -1 --format=%ai -- <file>`
   - Action: Verify against current Allium specs before using

2. **Contradicts current Allium spec**
   - Check: Read Allium spec, compare claims
   - Action: Trust Allium; document divergence in exec-plans/audit-results/

3. **Marked with temporary indicators**
   - Patterns: "plan", "proposal", "status", "audit", "TODO", "DEPRECATED"
   - Action: Use for historical context only; find current authority elsewhere

4. **References code that's been refactored**
   - Check: Does the referenced Python file/function still exist?
   - Action: Verify the doc is still relevant before acting on it

### ⚠️ Possibly Stale (Verify Before Using)

1. **Architecture doc but no Allium reference**
   - Check: Does an Allium spec exist for this domain area?
   - Action: If yes, verify architecture doc matches the spec

2. **Multiple conflicting documents**
   - Check: Which has the most recent git commit?
   - Action: Trust the most recent; document the conflict in exec-plans/audit-results/

3. **Doc claims "current implementation" but Python was recently refactored**
   - Check: git log for recent Python changes in that module
   - Action: Treat doc as historical; verify against current Python code

---

## What Happens When Docs Go Out of Date

### When Allium Spec Changes
1. Update the `.allium` file in `design-docs/allium-specs/`
2. Update the `index.md` in that directory (last updated date, scope, open questions)
3. If a rule or entity changed significantly, create a decision doc in `exec-plans/audit-results/`

### When Implementation Deviates from Spec
1. Document the divergence in `exec-plans/audit-results/DEVIATION_<component>.md`
2. Explain: Is Python wrong? Is spec wrong? Is it an acceptable optimization?
3. Make a decision: Port will follow spec, follow Python, or fix both

### When Operator Workflows Change
1. Update `product-specs/winder-operator-workflows.md` or `tension-measurement-workflows.md`
2. Note: These workflows must be preserved during port (they're non-negotiable)

### When Architecture Refactored
1. Update `design-docs/architecture/<component>.md`
2. Cross-check with Allium specs (should not contradict)
3. If Allium needs updating, update it first

### When a Temporary Planning Doc Becomes Done
1. Archive to `exec-plans/completed/`
2. Move any decision/learnings to a permanent location (architecture, Allium update, or decision doc)
3. Remove from `exec-plans/active/`

---

## Quick Decisions

**"I need to know how X works"**
- Check Allium spec first (design-docs/allium-specs/)
- If Allium contradicts Python, see exec-plans/audit-results/

**"I need to preserve operator behavior for X"**
- Check product-specs/ for current workflows
- These are non-negotiable during port

**"Which architecture doc should I trust?"**
- Check date: if >30 days old and contradicts Allium, trust Allium
- Check: does it reference an Allium spec? If yes and they agree, safe to use

**"I found two conflicting docs"**
- If one is Allium and one is markdown: trust Allium
- If one is recent and one is stale: trust recent
- If both recent: document the conflict in exec-plans/audit-results/

---

## Maintenance Schedule

| Document | Owner | Check Frequency | Update Trigger |
|----------|-------|-----------------|-----------------|
| Allium specs | System design (you) | Monthly | When spec evolves or bug found |
| design-docs/allium-specs/index.md | System design (you) | Monthly | When spec changes |
| exec-plans/active/ | You (harness runner) | Per phase | When phase completes |
| exec-plans/audit-results/ | Phase auditor | One-time per phase | After phase 0, 1, 2, etc. |
| product-specs/ | User research / operator feedback | Quarterly | When workflows change |
| design-docs/architecture/ | System design (you) | Quarterly | When refactoring or major changes |
| references/ | On-demand | As needed | When constants/syntax change |
| STALENESS.md (this file) | You | Quarterly | Framework or tier changes |

---

## Example: "Is dune_winder/planning/plc-architecture-proposals.md current?"

**Check:**
1. Git date: `git log -1 --format=%ai -- docs/dune_winder/planning/plc-architecture-proposals.md`
   - Result: `2026-03-29` (30 days old) → ⚠️ Likely stale
2. Does it contradict Allium? Compare claims to `winder-states-safety.allium` or `head-transfer.allium`
   - If yes → ❌ Definitely stale; ignore it
   - If no → Check if decision was made (see exec-plans/active/ for status)
3. Is it referenced in current work? Search exec-plans/active/ for mentions
   - If yes → Check the exec plan for current status
   - If no → Archive to exec-plans/completed/ or delete

**Decision:** Check exec-plans/active/rust-port-2026-04.md to see if this proposal was adopted or rejected. If nothing references it, it's background context; don't use as authority.
