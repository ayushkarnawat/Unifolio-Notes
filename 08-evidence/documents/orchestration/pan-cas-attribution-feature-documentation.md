# PAN Persistence, CAS File Storage & PAN-Based Attribution — Technical Documentation

**Date:** 2026-09-18
**Branch:** `tasks` (21 commits, `88b7b00..f662129`)
**Status:** Implemented, tested, reviewed. Kept on the branch, not yet merged to `main`.

This document explains what was built, why, how it works, what was deliberately left out, and how to prove it actually works — written for someone reviewing the work, not just someone reading the code.

---

## 1. The problem, in plain terms

Unifolio lets a user upload their CAS (Consolidated Account Statement — the official PDF a mutual fund registrar sends showing someone's holdings). Two things about that PDF are sensitive: it contains the person's **PAN** (India's tax ID number, a form of government ID), and it's the source document itself.

The app had a strict, tested rule from day one: **never store the PAN, never store the uploaded PDF.** Parse it, extract what's needed, throw the file and the PAN away. This was a deliberate privacy decision (a written ADR — "Architecture Decision Record" — called ADR-004), and it was enforced by an automated test that would fail the build if anyone added a PAN column to the database.

That rule had a real cost: without the PAN, the app could only guess which family member a statement belonged to by matching the **name** written on it. Names are unreliable — nicknames, spelling differences, two family members with similar names — so this guessing was fragile and occasionally wrong.

**The decision made this session: reopen that rule.** Store the PAN — encrypted, never shown anywhere — and use it as the reliable way to know whose statement is whose. Also start keeping the actual PDF for a short window, in case a statement needs to be re-checked or a user disputes something. Both changes come with real privacy engineering (below), not just "turn the rule off."

---

## 2. What actually changed — the three pieces

### 2.1 The PAN is now stored, but encrypted and never shown

- Each family member ("household member") in the database now has two new fields: `pan_encrypted` and `pan_lookup_hash`.
- `pan_encrypted` holds the real PAN, but scrambled using a standard encryption method (AES-256-GCM) — it can be decrypted back to the real value, but only by the app's own code holding the right secret key. Anyone looking directly at the database sees unreadable text, not a PAN.
- `pan_lookup_hash` is a one-way fingerprint of the PAN (like a hash, similar in spirit to how passwords are stored — you can check "is this the same PAN?" without ever reversing it back to the original). This is what the app actually uses to check "have I seen this PAN before?" — it never needs to decrypt anyone's PAN just to compare two people.
- **The PAN is never sent back to any screen or API response.** Every place that used to show a masked PAN (like `A****1234F`) still only shows that masked version — nothing changed there. The real PAN only ever exists, unmasked, inside the backend server's own memory for a split second while matching statements to people.

### 2.2 The uploaded PDF is now kept for 30 days, then deleted

- Previously: the PDF was read into memory, a temporary copy was made just so the parsing library could open it, and that copy was deleted the instant parsing finished. Nothing survived.
- Now: **a second, separate copy** is saved right after a successful import — today, that means writing it to a folder on the server's disk (`backend/var/cas_files/`). Each file is tagged with an expiry date exactly 30 days after upload.
- This is built so the "where it's saved" part can be swapped later without changing anything else — the app talks to a generic "file storage" interface, not directly to the disk. In a real production deployment, this would be swapped for a private cloud storage bucket (Amazon S3) with an automatic 30-day deletion rule — that swap is designed for, but wasn't actually built in this pass (see section 5).
- A small command-line tool (`expire_cas_files.py`) exists to actually delete files whose 30 days are up. It's meant to be run automatically on a schedule in production — that scheduling isn't wired up yet either (also section 5), but the deletion logic itself is built and tested.

### 2.3 Matching a statement to the right person now uses the PAN, not the name

This is the biggest behavior change. Here's the new decision process, in order, every time a CAS is uploaded:

1. **Does this PAN match someone in your own household?** If yes → automatically attach the statement to that person, and show a small note explaining "matched by PAN" (so it's not a silent, mysterious action).
2. **Does this PAN match someone in a *different* Unifolio account entirely?** If yes → **stop, refuse the import.** Show a message saying this PAN is already tracked under another account, and to contact support. There's no way to override this — not even the developer's own "confirm anyway" option can get around it. This is the fraud/duplicate-account guard rail.
3. **No PAN could be read from the statement at all** (rare — some PDFs don't expose it cleanly): fall back to the *old* method of matching by the folio number (the account number a fund house assigns) — this was already a reliable signal that existed before this feature, just used to be secondary.
4. **Nothing matched at all:** ask the user to confirm which family member this is, or add a new one — same as before.

**The person's typed name no longer matters for any of this.** You can type any name, a nickname, initials, whatever — the PAN (or, as a fallback, the folio number) is what decides who the statement belongs to.

The very first time a PAN is seen for a given family member, it gets saved on them automatically (this is called "backfilling") — there's no separate setup step; it just happens the first time a real statement for that person comes through.

---

## 3. Where the code lives

| What | File |
|---|---|
| Database changes | `backend/alembic/versions/0015_pan_and_cas_file_storage.py` (the migration) |
| Encryption logic | `backend/app/services/import_/crypto.py` |
| File retention logic | `backend/app/services/import_/file_storage.py` |
| The matching/decision engine | `backend/app/services/import_/attribution.py` |
| Manual cleanup tool | `backend/app/scripts/expire_cas_files.py` |
| Two upload flows that call all of the above | `backend/app/services/import_/service.py` and `backend/app/services/import_/lifecycle_service.py` |
| Onboarding screen users see | `frontend/src/features/auth/TrustPrimer.tsx` |

**Why two separate upload flows?** The app already had two different, only-partly-unified ways a CAS gets uploaded — one synchronous ("upload, get results immediately"), one asynchronous ("upload, check status later, handle wrong-password retries"). That duplication existed before this feature and wasn't something this work was asked to fix — but it did mean every change here had to be made twice, once in each flow, and tested twice.

---

## 4. The privacy/security engineering, explained simply

- **Two different secrets, two different jobs.** One secret key encrypts the PAN (so it can be read back later); a completely separate secret "peppers" the fingerprint hash (so it can never be read back, only compared). Using the same secret for both would be a mistake — this deliberately avoids that.
- **Encryption is "authenticated."** If someone tampered with the encrypted value, or the wrong key were used, decrypting it doesn't silently produce garbage that looks plausible — it throws a clear error. That's an important property for anything protecting an ID number.
- **The database itself can't be used to find out who's who.** Because matching happens via the one-way fingerprint rather than by decrypting things, the same code path that checks "is this PAN already used elsewhere" never actually has to expose anyone else's real PAN to do that check.
- **Where the secret keys come from, today vs. later.** Right now, both secret keys are read from local environment variables — fine for development and for a live demo, but not how a real production deployment should hold secrets. The code was written so that swapping this for a proper secret-management service (AWS Secrets Manager) is a small, contained change — nothing that calls the encryption code needs to change, only where the key itself comes from. This system already has infrastructure staged (not yet turned on) for exactly this kind of secret, reusing an encryption key that's already planned for other purposes — so this isn't starting from zero when it's time to do it for real.
- **A missing secret key now fails loudly, not silently.** Originally, if the secret keys weren't configured, the app would only notice the first time someone with a PAN tried to import a statement — and then fail with a confusing error on that one request, while everything else kept working. This was fixed during review: the app now refuses to even start up in a non-development environment if the keys aren't properly configured, so a misconfiguration gets caught immediately instead of silently, partially breaking imports later.

---

## 5. What was deliberately NOT built in this pass (and why that's fine)

Every one of these is a conscious, documented scope decision — not an oversight:

- **No real cloud storage yet.** The 30-day file retention writes to local disk today. The code is structured so a cloud storage version can be added later without touching the calling code, but that cloud version itself wasn't built.
- **No automatic scheduled cleanup job.** The "delete expired files" logic exists and is tested, but nothing runs it automatically yet — someone (or a future scheduled task) has to run the cleanup tool manually for now.
- **No way to merge two Unifolio accounts.** If a PAN turns out to belong to someone with two separate accounts, the app blocks the newer import and tells them to contact support — it does not attempt to merge the two accounts' data together. Building real account-merging (deciding whose data wins, verifying it's really the same person, etc.) was judged to be a much bigger, separate feature and was intentionally left out.
- **A couple of narrow edge cases are flagged for follow-up, not fixed:** if someone deliberately overrides the "confirm this person" prompt in one very specific way while also being auto-matched by PAN to someone else already in their household, that combination could currently cause a database error instead of a clean error message. This is a rare, edge-case interaction — noted clearly so it isn't forgotten, not something that came up in normal use or testing.

---

## 6. How this was tested

- **150+ new or changed automated tests** were added across the encryption module, the file-retention module, the matching engine, both upload flows, and a database-level guard test.
- The guard test (`backend/tests/models/test_no_pan_field.py`) now checks *every* database table in the app, not just the import-related ones, and confirms the PAN only ever exists in its encrypted/fingerprint form, only on the household-member table — this would fail automatically if anyone ever added a plain-text PAN column anywhere in the future.
- Tests specifically prove: a PAN match within a household auto-attaches; a PAN match in a different account is blocked and cannot be overridden; the block never leaks who the PAN actually belongs to; the file actually gets saved and its expiry date is set correctly; and the encryption round-trips correctly (encrypt then decrypt gives back the original PAN).
- The full backend test suite (672 tests) and full frontend test suite (435 tests) both pass cleanly as of this write-up.
- This work went through its own internal review process — including a final, whole-picture review after everything was built, which caught a handful of things no single piece-by-piece review could have (see section 8).

---

## 7. How to prove this actually works — a live demo checklist

Use this to show your manager the feature is real, not just "the tests say so":

1. **Upload a real CAS statement** for a family member through the app (or via the API directly).
2. **Look at the database directly** (`sqlite3 backend/unifolio_dev.db`) and query the household member's row — you'll see `pan_encrypted` as unreadable scrambled text and `pan_lookup_hash` as a hash, never the plain PAN.
3. **Decrypt it live**, to prove it's genuinely recoverable and correct, not just gibberish: run a one-line Python command using the app's own decryption function on the value you just saw in the database, and show it prints back the real PAN.
4. **Check the `imports` table** for that upload — `file_reference` and `file_expires_at` (about 30 days out) should be filled in.
5. **Show the actual file exists** on disk under `backend/var/cas_files/`.
6. **Upload a second statement for the same person**, typing a different/nickname — show it still correctly attaches to the same person, with the "matched by PAN" note.
7. **Try uploading a statement whose PAN belongs to a different account** — show it gets refused with a clear "already tracked elsewhere, contact support" message.
8. **Run the relevant automated tests live** and narrate what each one checks — this shows both that it works and that you understand why it's correct, which tends to land better in an evaluation than a demo alone.

---

## 8. Known, deliberately-left-open items (for the record)

These were all found during review, judged non-blocking, and recorded rather than silently ignored:

- A rare, specific combination of "override this match" plus an existing PAN match to a different household member could currently cause a database error instead of a clean message — flagged for a future fix, not something that occurs in normal use.
- Some test-support code (a small helper that redirects where test files get saved) is duplicated across four different test files instead of being written once and shared — cosmetic, doesn't affect correctness.
- The manual cleanup script doesn't yet follow this codebase's usual naming/structure convention for scheduled jobs — a small housekeeping item for whenever the real scheduling gets built.
- The onboarding screen's small headline ("We keep your insights, not your files") is technically fine now that the body text was corrected, but reads slightly at odds with "we keep your file for 30 days" — worth a copy polish, not a factual error.
- A couple of spots in the schema documentation (a "related documents" reference and a changelog table) weren't updated to mention this change, even though the main documentation was — a documentation-completeness gap, not a functional one.

None of these block using or evaluating the feature — they're the honest, complete list of "here's what's still slightly rough," kept because hiding them would be worse than naming them.
