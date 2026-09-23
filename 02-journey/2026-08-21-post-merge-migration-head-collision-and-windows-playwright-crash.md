# Merging two parallel branches splits the migration history in two, and a Windows-only Playwright crash is found and fixed

## For stakeholders

Two features that had been built in parallel — the multi-method
authentication work and the Analytics PDF export — each added a database
migration using the same revision number, so merging them together broke
the database upgrade path outright. The team put the migrations back into
a single, correct order. Separately, the same merge exposed a
Windows-specific crash: the new PDF-export feature starts a browser
process in the background when the server boots, and Windows' default
way of managing background processes cannot do that at all, unlike Linux
— so the server crashed on startup for every Windows developer machine
until a Windows-specific setting was added.

## Technical detail

### Intended outcome

Get the `authsetup` branch (multi-method identity, ADR-008) and the
`worktree-analytics-pdf-export` work merged into `feat/enhanced-ui`
cleanly, with a working local dev environment on both Windows and other
platforms.

### What actually happened

**Migration head collision.** Both branches independently created an
Alembic migration numbered `0004` — `authsetup`'s
`0004_multi_method_auth_identities.py` (chaining to `0005`-`0008`) and
`feat/enhanced-ui`'s own `0004_scheme_ter_nullable_value.py`. Merging
produced two head revisions and a hard `alembic upgrade head` failure.
Fixed by renumbering the `feat/enhanced-ui` migration to `0009`
(`down_revision = "0008"`), making the chain strictly linear:
`0001` → … → `0008` (auth) → `0009` (scheme TER nullable). This is what
migration `0009` is — the previously-unaccounted-for entry the vault's
own migration-chain record had a gap at (see the resolution appended to
[R-050](../07-risks-and-debt.md)).

A second-order problem followed: a local SQLite dev database had already
been stamped at `0004` under the old numbering, before the rename, so a
straight `alembic upgrade head` after the rename tried to resume from a
migration (`0005`, auth's `backfill_phone_otp_identities`) against a
database missing the `auth_identities` table `0004` (auth) was supposed
to have created first. Fixed by resetting the local stamp to `0003` and
re-running the full `0004`-`0009` chain from there.

**A Windows-only Playwright startup crash.** The Analytics PDF export
feature (2026-08-20, [ADR-013](../03-decisions/ADR-013-analytics-pdf-export-architecture.md))
starts a shared headless Chromium instance during FastAPI's lifespan
startup. Playwright launches that browser via
`asyncio.create_subprocess_exec()`, which Windows' default
`SelectorEventLoop` cannot support at all (`NotImplementedError` inside
`_make_subprocess_transport`) — only `ProactorEventLoop` supports
subprocess pipes on Windows, and Uvicorn's Windows `--reload` path
defaults to the unsupported loop. Fixed by forcing
`asyncio.WindowsProactorEventLoopPolicy()` in `backend/app/main.py` when
`sys.platform == "win32"`, updating the local-dev launcher
(`backend/scripts/run_server.py`) to instantiate a `ProactorEventLoop`
directly, and documenting the Uvicorn `--loop` flag needed to match.
Linux was never affected — its default loop already supports subprocess
creation, which is why this was never hit before a feature that starts a
background browser process existed.

A smaller, related gap: `playwright>=1.48.0` had been added to
`backend/requirements.txt` but the Windows dev virtual environment
(`.venv-win`) had not been reinstalled, producing a plain
`ModuleNotFoundError` until `pip install -r requirements.txt` and
`python -m playwright install chromium` were rerun.

### Deviation (if any) — decision or response taken

None of this was a design change — it is environment/tooling stabilization
work required to make two already-decided features (ADR-008, ADR-013)
actually mergeable and runnable, not a reconsideration of either.

### Result

`feat/enhanced-ui`'s migration history is linear through `0009`; the local
dev database on both branches converges correctly; the server boots
cleanly on Windows with the PDF-export feature's background browser
process; full backend suite green. This directly resolves the vault's own
open traceability question about what migration `0009` was
([R-050](../07-risks-and-debt.md)).

### Related

- ADR-008 — phone-anchored multi-method identity (the branch this merge reconciled)
- ADR-013 — analytics PDF export architecture (the other branch, and the source of the Windows browser-startup crash)
- R-050 — migration `0009` traceability gap (resolved by this stage)
- Evidence: `08-evidence/documents/orchestration/post-merge-environment-and-migration-fixes.md`
