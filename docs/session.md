تو در حال ادامه‌ی Phase 5 پروژه هستی: Review Workflow & Audit Trail.

جلسه قبلی به سقف رسید، پس باید از وضعیت فعلی ادامه بدهی، نه اینکه از صفر شروع کنی.
لطفاً قبل از هر چیز فقط context لازم را بخوان و از خواندن بازگشتی کل repo خودداری کن.

## وضعیت فعلی که قبلاً انجام شده
### Docs
- `docs/PHASE_5_HANDOFF.md` نوشته شده و باید مبنای ادامه کار باشد.
- فاز ۵ در handoff با تمرکز روی Review Workflow, Audit Trail, state machine, export metadata و test matrix تعریف شده.

### Backend model / schema / migration
فایل‌های زیر قبلاً ایجاد/ویرایش شده‌اند:
- `apps/api/src/atip_api/models/enums.py`
- `apps/api/src/atip_api/models/evidence.py`
- `apps/api/src/atip_api/models/__init__.py`
- `apps/api/alembic/versions/b7a3c9e51d24_add_review_workflow_and_audit_trail.py`
- `apps/api/src/atip_api/schemas/evidence.py`
- `apps/api/src/atip_api/repositories/evidence.py`
- `apps/api/src/atip_api/errors.py`
- `apps/api/src/atip_api/services/evidence.py`

### What the current implementation should already cover
- review status enum / workflow states
- review history / append-only event model
- migration for review workflow + audit trail
- repository helpers for queue/history/events
- service layer logic for transitions and audit logging
- custom errors for invalid review transitions / validation

## Invariants you must preserve
- UUIDv5 behavior for chunks must remain unchanged
- No fabricated citations / no invented provenance
- PDF traceability must remain intact
- `pdfjs-dist` must stay a direct dependency
- Review history must be append-only and non-destructive
- Do not silently destroy reviewed evidence on re-extraction
- Do not break Phase 3 `/ask`
- Do not break Phase 4 evidence extraction or PDF jumps
- Do not convert this into a large auth/RBAC/notifications project; keep it MVP-scoped

## Important architectural goal for Phase 5
We need a clean split:
- `evidence_items` = current workflow state
- `review_history` / review events = immutable audit log
- citations/provenance remain separate and immutable

## What still remains to do
### Backend
1. Finish/verify service logic for:
   - valid state transitions
   - event creation on every mutation
   - queue listing
   - history retrieval
   - export metadata enrichment
   - safe supersede/archive behavior if re-extraction is involved

2. Implement/verify router endpoints:
   - `POST /api/evidence/{id}/review`
   - `GET /api/evidence/{id}/history`
   - `GET /api/evidence/review-queue`
   - export endpoint updates if needed

3. Ensure schemas and repository methods line up with the actual API responses.

4. Add tests:
   - transition matrix
   - audit log integrity
   - filtering/sorting/pagination
   - export metadata
   - regression coverage for Phase 3 / Phase 4

### Web
5. Regenerate or update API types if needed.
6. Build the Review Queue UI:
   - filters
   - list rows
   - detail drawer
   - history timeline
   - review actions
7. Ensure citation clicks still jump to PDF viewer correctly.

### Docs / verification
8. Update:
   - `docs/02_ROADMAP.md`
   - `docs/PHASE_5_HANDOFF.md`
9. Run verification:
   - backend tests
   - lint
   - typecheck
   - web build
   - smoke test
10. Commit after each milestone and note it in the handoff.

## Suggested next execution order
1. Read the already-edited backend files to confirm consistency.
2. Fix any mismatches between model/schema/repository/service.
3. Add/adjust routers.
4. Write backend tests first.
5. Then implement the web Review Queue UI.
6. Finish docs and run verification.
7. Commit milestone-by-milestone.

## Current implementation style constraints
- Keep code ASCII unless the file already uses Unicode
- Add succinct comments only where logic is non-obvious
- Prefer minimal, targeted edits
- Use existing app patterns instead of inventing new abstractions
- If there are unexpected untracked/changed files unrelated to this task, do not revert them; ask before touching them

## Quick reminder of scope
This phase is about:
- human review loop
- audit trail
- review queue
- detail drawer
- history timeline
- export metadata

Not about:
- RBAC
- notifications
- assignments
- workflow automation
- background jobs
- major refactors

## If you need a short summary of the goal
Phase 5 should turn evidence into a reviewer-friendly system with:
- explicit status transitions
- append-only review events
- visible review queue
- history timeline
- audit-safe exports
- no regressions in provenance/PDF traceability

Now continue from the current codebase state and complete the remaining Phase 5 work.

# Start Phase 5: Review Workflow & Audit Trail

Phase 4 is complete, verified, and committed. The system currently supports:
- Verified RAG answers with inline citations
- PDF traceability from citations/evidence cards into the source PDF
- Evidence extraction with strict quote verification against chunk text
- Evidence export in JSON and Markdown
- Stable provenance snapshots that survive chunk reprocessing

## First step: preserve context
Create or update `docs/PHASE_5_HANDOFF.md` first.

That handoff file must summarize:
1. What was completed in Phases 1–4
2. The current state of retrieval, verification, PDF traceability, and evidence extraction
3. Architectural invariants that must not be broken:
   - stable chunk IDs
   - no invented provenance
   - verification must remain strict and verbatim
   - evidence citations are provenance snapshots and must survive reprocessing
   - PDF highlighting must gracefully fall back to page-level navigation
   - Phase 3 `/ask` must not regress
4. Known implementation constraints:
   - extraction is currently synchronous
   - `pdfjs-dist` must remain a direct dependency
   - avoid recursive repo scans; read only files necessary for this phase
5. A note about the re-extraction lifecycle risk:
   - reviewed evidence must not be silently destroyed by re-extraction

## Mission
Implement Phase 5: Review Workflow & Audit Trail.

## Product goal
Add a human review workflow on top of evidence/requirements so users can review, approve, reject, request revision, comment, and inspect a full audit trail — without breaking evidence provenance or PDF traceability.

---

## Definition of Done

### Functional
1. Each evidence item has an explicit review status:
   - `new`
   - `in_review`
   - `approved`
   - `rejected`
   - `needs_revision`

2. Review actions are supported:
   - `start_review`
   - `approve`
   - `reject`
   - `request_revision`
   - `comment`
   - optionally `set_risk` if needed

3. Every review mutation creates an append-only audit event containing:
   - evidence_item_id
   - action
   - previous_status
   - next_status
   - previous_risk
   - next_risk
   - actor_name
   - actor_type
   - comment
   - created_at

4. The web app provides a Review Queue with:
   - filtering by status, risk, and document
   - sorting by updated/created time and/or risk
   - item detail drawer/modal
   - review actions
   - history timeline
   - citation chips/buttons that still jump into the PDF viewer

5. Exports include review metadata and can optionally include history.

6. No regressions in:
   - Phase 3 `/ask`
   - verification logic
   - evidence extraction
   - PDF traceability

### Non-functional
1. Provenance snapshots must remain immutable
2. Review history must be append-only
3. Review data must stay separate from extraction provenance
4. Tests must cover transitions, audit events, filtering, export, and UI behavior
5. Update `docs/02_ROADMAP.md` and `docs/PHASE_5_HANDOFF.md`

---

## API contract to implement

### GET `/api/evidence`
List evidence items for the review queue.

Supported query params:
- `document_id`
- `status`
- `risk`
- `limit`
- `offset`
- `sort`

Return:
- paginated items
- current review status
- current risk
- citation count
- enough summary metadata for the queue UI

### GET `/api/evidence/{id}`
Return full evidence item detail:
- requirement/evidence text
- document metadata
- citations/provenance
- current review status
- current risk
- warnings if any
- created/updated timestamps
- lightweight history summary if useful

### POST `/api/evidence/{id}/review`
Submit a review action.

Request body should support:
- `action`
- `comment`
- `actor_name`
- `actor_type`
- optionally `risk`

Validation:
- `action`, `actor_name`, `actor_type` required
- `comment` should be required for `reject` and `request_revision`
- invalid transitions must be rejected cleanly

Response:
- updated item snapshot
- created review event

### GET `/api/evidence/{id}/history`
Return full review history / timeline for the evidence item.

### PATCH `/api/evidence/{id}`
Only if needed for small inline edits such as risk changes.
Important: any mutation here must still create an audit event and must not bypass review history.

### GET `/api/evidence/export`
Support:
- `format=json|md`
- filters like `status`, `risk`, `document_id`
- `include_history=true|false`

---

## DB schema direction

Use the existing evidence extraction tables as the provenance layer.

### Keep on `evidence_items`
Store current workflow snapshot fields such as:
- `review_status` (default `new`)
- current `risk` if not already present
- review update timestamps / last actor if useful

### Add a new append-only table
Create `evidence_review_events` with fields like:
- `id`
- `evidence_item_id`
- `action`
- `previous_status`
- `next_status`
- `previous_risk`
- `next_risk`
- `comment`
- `actor_name`
- `actor_type`
- `created_at`
- optional `metadata` JSONB

Add indexes appropriate for:
- item history lookup
- queue filtering/sorting

### Important lifecycle rule
Do not silently destroy reviewed evidence during re-extraction.
If evidence replacement logic exists today, introduce a safe strategy such as:
- supersede/archive old evidence items
- or otherwise preserve review/audit history explicitly

Document the chosen strategy in the handoff.

---

## UI states to implement

### Review Queue page
States:
- loading
- empty
- empty filtered
- populated
- error

Controls:
- filters for document/status/risk
- sort selector
- refresh
- export

### Detail drawer or modal
Sections:
- evidence/requirement text
- current status/risk badges
- provenance/citations
- review actions
- reviewer comment input
- history timeline

States:
- loading detail
- no history
- history loaded
- submitting action
- success
- error

### Interaction requirements
- action buttons disabled while submitting
- preserve typed comments on failed submit
- success/error toasts or clear inline feedback
- citation interactions must preserve the Phase 4 PDF traceability behavior

---

## Test matrix

### Backend
- valid transitions
- invalid transitions rejected
- comment-required rules
- event creation on every mutation
- filtering by status/risk/document
- pagination/sorting
- history retrieval
- export with and without history
- no regression in Phase 3/4 flows

### Integration
- extraction + review coexist correctly
- citations remain unchanged after review actions
- PDF file endpoint and viewer jump data still work
- re-extraction lifecycle behavior is explicitly tested

### Frontend
- queue loading/empty/populated/error states
- detail drawer rendering
- action submission flows
- history timeline rendering
- risk/status updates
- export UX
- citation click still opens viewer and navigates correctly

### E2E
At least:
1. upload document
2. extract evidence
3. queue shows item
4. open detail
5. start review
6. approve or reject with comment
7. history is visible
8. export includes review metadata
9. citation jump still works

---

## Risk register to address in implementation
Handle these explicitly in code/docs/tests:
1. Re-extraction destroying reviewed state
2. Audit trail bypass through direct PATCH updates
3. Ambiguous state/action rules
4. UI scope creep into a mini-Jira
5. Provenance contamination by review metadata
6. Regression in PDF traceability
7. Weak actor identity due to no full auth yet
8. Export inconsistency between current state and history

---

## Working style constraints
- Read only the minimum necessary files/docs first
- Do not recursively scan the whole repository
- Propose a short implementation plan before coding
- Keep the MVP focused and do not add auth/RBAC, notifications, assignment engines, or background jobs in this phase unless absolutely necessary
- Use clean, professional Tailwind + shadcn/ui patterns
- Update roadmap and handoff as progress is made
- Remind the user to `git push origin main` at the end

Start by:
1. reading the minimum necessary docs/files,
2. writing `docs/PHASE_5_HANDOFF.md`,
3. proposing a concrete implementation plan,
4. then implementing the backend/data model first, followed by UI, tests, and docs.