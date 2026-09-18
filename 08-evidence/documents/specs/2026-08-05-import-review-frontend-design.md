# Import Review Frontend — Design (Phase 1b)

## Purpose

Phase 1 backend (complete, merged to `main`) built `POST /imports/parse` and
`POST /imports/confirm` in the monolith's Import Service. This is the
frontend that talks to those endpoints — PRD-01's Import Review flow
(App-Flow-Unifolio.md screens S8–S12), built as new React code since the
existing prototype at `CAS Parsers/mf-import/frontend` is vanilla TypeScript
with nothing to port (confirmed, ADR-001 corrected accordingly).

## Scope

**In scope:** the five Import flow screens (Upload, Parsing, Review, Error,
Confirmed) as a self-contained feature.

**Explicitly out of scope, decided during brainstorming:**
- No router library, no persistent nav shell. Nothing exists yet to route
  between (no Onboarding, no Dashboard) — per PRD-01's own scope boundary
  ("no auth in this build phase") and Phase 0/1's precedent of building only
  what's scoped. A real app shell is a later phase's job once there are
  multiple real destinations.
- No auth/session UI. `household_member_id` comes from a dev-seeded fixture
  (see "household_member_id sourcing" below), not a UI field.
- No live AMFI scheme search/autocomplete on manual override — a plain text
  input for the AMFI code, matching what the backend already accepts.
  Nothing in PRD-01 asks for search UX here.
- No E2E/Playwright — not currently set up in this project; Vitest +
  React Testing Library (already in the scaffold) covers this phase.

## household_member_id sourcing

No auth/onboarding UI exists yet (PRD-02, separate phase) to create a real
`HouseholdMember` row. A small Alembic data seed (or documented manual
step) creates one `User` + `HouseholdMember` fixture in the dev DB; the
frontend reads its UUID from `import.meta.env.VITE_DEV_HOUSEHOLD_MEMBER_ID`
(a Vite env var, documented in `frontend/.env.example`). This is plumbing,
not a feature — no UI surfaces it, and it's replaced outright once PRD-02's
auth flow exists to supply a real session-derived ID.

## Architecture

```
frontend/src/
  features/import/
    ImportFlow.tsx        # stateful parent — owns step + data, renders active child
    UploadForm.tsx         # S8
    ParsingIndicator.tsx   # S9
    ReviewTable.tsx        # S10
    ImportError.tsx        # S11
    ImportConfirmed.tsx    # S12
    api.ts                  # fetch wrappers: parseImport(), confirmImport()
    types.ts                 # request/response types mirroring backend Pydantic schemas
  components/
    Badge.tsx               # shared per Design Schema's Badge spec — reusable by Dashboard later
  styles/
    tokens.css               # design tokens as CSS custom properties, light + dark
```

`ImportFlow` holds:
```ts
type Step = 'upload' | 'parsing' | 'review' | 'error' | 'confirmed';
```
in `useState`, plus the current `ImportPreviewResponse | null`,
`ImportConfirmResponse | null`, and `{code, message} | null` (parse error).
No context, no reducer library — data flows down as props to whichever
child is active. This is a linear, short-lived flow (one CAS upload at a
time); a page refresh mid-review is expected to lose progress and restart
at Upload, matching the flow's actual lifecycle — no `sessionStorage`
persistence (considered and rejected during brainstorming: adds
serialization/sync complexity this flow doesn't need).

## Screens

| Screen | Maps to | Behavior |
|---|---|---|
| Upload | S8 | PDF file input + password field. Client-side rejects non-PDF before submit (mirrors the backend's own check). Submit → `POST /imports/parse` (multipart) → `step: 'parsing'`. |
| Parsing | S9 | Loading state while the request is in flight. |
| Review | S10 | Investor name + masked PAN (display only, never editable/re-sent). Scheme table: `Badge` for match-confidence (`confirmed`/`pending` → Design Schema's `positive`/`neutral` badge variants) and plan-type (`direct`/`regular`/`unclassified`). Per-scheme AMFI-code text input and plan-type dropdown, shown only where an override is needed. `parse_warnings` rendered as a list if non-empty. **Confirm is disabled until every `pending`-confidence or `unclassified`-plan-type scheme has an override filled in** — enforces FR-10's "never silently guess" as a UI guarantee, not just a server-side 409 the user has to hit first. |
| Confirmed | S12 | "N new, M duplicates skipped" (from `ImportConfirmResponse`). No Dashboard exists yet to land on — an "Import another CAS" button resets to Upload; this is a reset, not real navigation. |
| Error | S11 | The `ParseError` `{code, message}` displayed verbatim — already user-facing text per PRD-01 FR-12-14. "Try again" resets to Upload. |

## Error Handling

- **422 `ParseError`** (wrong password / scanned PDF / summary CAS / demat
  CAS / generic) → Error screen, backend message shown verbatim.
- **409 `SchemeConfidenceError`** on confirm → shouldn't normally trigger
  since Confirm is client-side disabled until every scheme is resolved, but
  if it does (stale state), shown as an inline banner on the Review screen
  ("some schemes still need review") — no navigation away, since the user
  is already on the screen that fixes it.
- **404 session-not-found** on confirm (server-side TTL sweep expired the
  in-memory preview) → inline banner on Review prompting re-upload.
- **Network failure** (fetch throws, no response) → generic "couldn't reach
  the server, try again" message, kept visually/textually distinct from a
  structured `ParseError` so it's never mistaken for a real parse failure.

## Styling

CSS Modules + CSS custom properties (decided during brainstorming over a
single global stylesheet, to avoid class-name collisions once
Dashboard/Analytics add their own screens later). `styles/tokens.css`
defines the Design Schema's tokens as custom properties — `--color-accent`,
`--color-positive`, `--color-negative`, `--color-neutral-badge`,
`--color-warning`, the type scale, the 4px spacing scale, `radius-sm/md/lg`
— light values as the default, dark values under
`@media (prefers-color-scheme: dark)` (no manual toggle — Design Schema
calls for both modes as first-class, and there's no Settings screen yet for
a manual override, so system-preference is the only trigger this phase).
Each component gets a co-located `.module.css` file importing these
custom properties.

`Badge` implements the Design Schema's spec exactly: `radius-sm`,
`type-caption` weight 500, 8px/2px padding, four variants (`positive` /
`neutral` / `warning` — no `negative` variant per the schema, losses live in
data cells not badges), always paired with a 1-2 word label, never
color-only (accessibility baseline).

Money/unit/NAV values from the API arrive as strings (backend's
`Decimal`-safe serialization) — displayed as-is, never parsed into JS
`number`, avoiding float precision issues on the frontend too.

## Testing

Vitest + React Testing Library (already in the scaffold, same pattern as
the existing `App.test.tsx`):
- `UploadForm` — rejects non-PDF client-side; calls `parseImport()` with
  correct `FormData` on submit.
- `ReviewTable` — renders the correct `Badge` variant per
  confidence/plan-type combination; Confirm stays disabled until every
  pending/unclassified scheme has an override, enables once resolved.
- `ImportFlow` — step transitions correctly on mocked `parseImport`/
  `confirmImport` responses: success, `ParseError`, `SchemeConfidenceError`,
  session-not-found, network failure.
- `api.ts` — request shape (multipart for parse, JSON for confirm) and
  response parsing, against a mocked `fetch`.

## Open Items Not Resolved Here

- Exact AMFI-override text input UX (autocomplete, validation feedback) —
  deferred, no PRD-01 requirement beyond accepting a string.
- Real navigation from Confirmed to a Dashboard — blocked on a Dashboard
  existing (future phase).
- Manual dark-mode toggle — blocked on a Settings screen existing (future
  phase); system-preference-only for now, per Design Schema's own framing
  of the manual override as belonging to "settings."
