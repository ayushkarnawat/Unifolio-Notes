# Post-Merge Stabilization: Alembic Migrations & Windows Playwright Lifecycle

**Date:** 2026-08-21  
**Branch:** `feat/enhanced-ui`  
**Context:** Resolution of merge fallout and environment startup issues after landing both `authsetup` and `worktree-analytics-pdf-export` into `feat/enhanced-ui`.

---

## 1. Alembic Migration Head Split

### Problem
When `authsetup` and `feat/enhanced-ui` were developed in parallel, both branches created an Alembic migration with `Revision ID: 0004`:
- `authsetup`: `0004_multi_method_auth_identities.py` (which revised `0003` and led to `0005`, `0006`, `0007`, `0008`).
- `feat/enhanced-ui`: `0004_scheme_ter_nullable_value.py` (which revised `0003`).

Upon merging into `feat/enhanced-ui`, running `alembic upgrade head` failed with:
```
UserWarning: Revision 0004 is present more than once
ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'; please specify a specific target revision, '<branchname>@head' to narrow to a specific head, or 'heads' for all heads
```

### Solution
Linearized the migration history:
1. Renamed `backend/alembic/versions/0004_scheme_ter_nullable_value.py` to `backend/alembic/versions/0009_scheme_ter_nullable_value.py`.
2. Updated metadata in `0009_scheme_ter_nullable_value.py`:
   - `revision = "0009"`
   - `down_revision = "0008"`
3. The migration graph is now strictly linear: `0001` → `0002` → `0003` → `0004` (auth) → `0005` → `0006` → `0007` → `0008` → `0009` (scheme_ter nullable).

---

## 2. Local Database State Stamp Desync

### Problem
The local SQLite database (`unifolio_dev.db`) was previously upgraded while `0004` pointed to `scheme_ter_nullable_value`. As a result:
- `alembic_version` stored `version_num = '0004'`.
- `0004_multi_method_auth_identities.py` (which creates `auth_identities`) had never run on the local database.

When `alembic upgrade head` ran after renumbering `scheme_ter` to `0009`, Alembic resumed from version `0004` by running `0005_backfill_phone_otp_identities.py`, which immediately failed:
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: auth_identities
[SQL: SELECT auth_identities.provider_subject FROM auth_identities WHERE auth_identities.provider = ?]
```

### Solution
Reset the local database version pointer to `0003` and re-ran migrations:
```powershell
alembic stamp 0003
alembic upgrade head
```
This executed `0004` through `0009` sequentially, creating `auth_identities` and completing all auth backfills.

---

## 3. Windows `asyncio` Subprocess & Playwright Lifespan Failure

### Problem
The Analytics PDF Export feature (`app/services/analytics/pdf_export.py`) initializes a headless Chromium instance during FastAPI lifespan startup (`await start_browser()`).

Playwright launches browser processes using `asyncio.create_subprocess_exec()`. On Windows:
- `asyncio.SelectorEventLoop` raises `NotImplementedError` inside `_make_subprocess_transport()`.
- Only `asyncio.ProactorEventLoop` supports Windows subprocess pipes and transports.
- Uvicorn on Windows with `--reload` defaults its worker event loop to `SelectorEventLoop`, causing the server startup to crash:
```
future: <Task finished name='Task-3' coro=<Connection.run() done...> exception=NotImplementedError()>
Traceback (most recent call last):
  ...
  File "C:\Python313\Lib\asyncio\base_events.py", line 534, in _make_subprocess_transport
    raise NotImplementedError
NotImplementedError
ERROR: Application startup failed. Exiting.
```

### Solution
1. Added Windows Proactor loop policy enforcement to `backend/app/main.py`:
   ```python
   if sys.platform == "win32":
       asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
   ```
2. Updated `backend/scripts/run_server.py` to instantiate `asyncio.ProactorEventLoop()` on Windows.
3. Configured Uvicorn runner to specify the Proactor loop factory:
   ```powershell
   uvicorn app.main:app --reload --port 8000 --loop asyncio.ProactorEventLoop
   ```

---

## 4. Virtual Environment Synchronization (`.venv-win`)

### Problem
`playwright>=1.48.0` was added to `backend/requirements.txt` but was uninstalled in `.venv-win`, producing `ModuleNotFoundError: No module named 'playwright'`.

### Solution
```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 5. Verification Checklist

To confirm local parity across developer machines:
1. `alembic current` returns `0009 (head)`.
2. `alembic check` returns no schema drift.
3. Server boots cleanly without `NotImplementedError` or lifespan exceptions.
4. Full backend test suite passes: `pytest tests/`.
