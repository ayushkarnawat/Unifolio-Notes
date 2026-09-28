# PAN Storage: Flowchart & ER Diagram

**Date:** 2026-09-24
**Reflects:** the uncommitted PAN-at-upload change (spec `Docs/superpowers/specs/2026-09-24-pan-at-upload-attribution-design.md`)
**Code:** `backend/app/services/import_/pan_claims.py`, `service.py`, `api/imports.py`; `frontend/src/features/import/ImportFlow.tsx`, `features/auth/FamilyImportFlow.tsx`

> The diagrams are Mermaid. They render in VS Code's Markdown preview and on GitHub.

---

## 1. The short answer

PAN lives on **`household_members`**, in two columns, plus one status column:

| Column | What it holds | Written when | Screen at that moment |
|---|---|---|---|
| `pan_encrypted` | The real PAN, AES-256-GCM encrypted | **Upload**: the `/imports/parse` call, right after the file is read | "Parsing…" spinner, just before the Review screen appears |
| `pan_lookup_hash` | A one-way HMAC-SHA256 fingerprint of the PAN, used only to check "is this PAN already in Unifolio?" | **At the same moment, in the same database write** as `pan_encrypted` | The same "Parsing…" spinner |
| `pan_pending_until` | Not a PAN. It's a status timestamp. Set = the PAN is still *pending*. Empty = the PAN is *permanent*. | Set at **upload** (now + 65 min). Cleared (made empty) at **Confirm Import**. | Set on the spinner; cleared when you click **Confirm Import** |

**Key facts**

- **Both PAN columns go into the database together.** There is no step where one is saved and the other isn't. One `UPDATE household_members …` sets both, and one commit saves them.
- **Before that moment,** the PAN only exists in server memory, in the parsed CAS inside the review session. It's never written to disk in plain form.
- **Confirm Import doesn't touch the two PAN columns.** It only empties `pan_pending_until`, which turns the pending PAN into a permanent one.
- **An abandoned upload removes the PAN again.** All three columns are wiped if the user presses Try again or Cancel, or if 65 minutes pass without a Confirm.
- **A PAN conflict writes nothing.** That covers another family member, another account, or a different PAN from the one this member already has. The popup appears and the database is unchanged.

---

## 2. Just Me: full flow

```mermaid
flowchart TD
    A["Onboarding: Q4 Household screen"] -->|User clicks Just Me| B["SoloCasUpload screen loads"]
    B --> B1[("DB write 1<br/>INSERT household_members<br/>relationship = self<br/>pan_encrypted = NULL<br/>pan_lookup_hash = NULL<br/>pan_pending_until = NULL")]
    B1 --> C["Import screen: choose path<br/>(Request from CAMS / I already have a statement)"]
    C -->|I already have a statement| D["Upload form: pick CAS PDF + enter PDF password"]
    D -->|Clicks Upload Statement| E["'Parsing…' spinner shown"]
    E --> F["Browser → POST /imports/parse<br/>(file, password, household_member_id)"]
    F --> G{"Server: PDF valid<br/>and password correct?"}
    G -->|No| G1["Error screen with Try again<br/>(nothing written to DB)"]
    G -->|Yes| H["Server parses CAS in memory<br/>(raw PAN now in server memory only)"]
    H --> I["Server looks up fund details online (mfapi)<br/>and creates the review session in memory"]
    I --> J{"Server checks the PAN<br/>against household_members.pan_lookup_hash"}
    J -->|"PAN belongs to a<br/>different account"| K1["409 cross_account_pan_blocked<br/>(nothing written)"]
    K1 --> K1s["Popup: 'Import blocked'<br/>Back → household step"]
    J -->|"PAN belongs to another<br/>member of this account,<br/>or doesn't match this<br/>member's permanent PAN"| K2["409 pan_belongs_to_other_member /<br/>pan_mismatch_for_member<br/>(nothing written)"]
    K2 --> K2s["Popup: 'This PAN already exists'<br/>Change CAS file / Cancel → back to upload form"]
    J -->|"PAN is new, or already<br/>this member's"| L[("DB write 2: PAN ENTERS THE DATABASE<br/>UPDATE household_members SET<br/>pan_encrypted = encrypt(PAN)<br/>pan_lookup_hash = HMAC(PAN)<br/>pan_pending_until = now + 65 min<br/>→ COMMIT")]
    L --> M["Review screen: 'Review … CAS Import'<br/>(schemes, folios, transactions)"]
    M -->|User clicks Confirm Import| N["Browser → POST /imports/confirm"]
    N --> O[("DB write 3: PAN MADE PERMANENT<br/>UPDATE household_members<br/>SET pan_pending_until = NULL<br/>(pan_encrypted & pan_lookup_hash unchanged)")]
    O --> P[("DB write 4 (same transaction)<br/>INSERT imports (status = confirmed,<br/>file_reference, file_expires_at = +30 days)<br/>INSERT schemes (if new), folios, transactions<br/>CAS PDF saved to file storage (S3 / disk)<br/>→ COMMIT")]
    P --> Q["'Import complete' screen → next step"]
    M -.->|"User abandons: Try again after a<br/>failed confirm"| R["Browser → POST /imports/sessions/{id}/discard"]
    R --> S[("UPDATE household_members SET<br/>pan_encrypted = NULL, pan_lookup_hash = NULL,<br/>pan_pending_until = NULL → COMMIT")]
    M -.->|"User just closes the tab"| T["After 65 min the pending PAN counts as expired<br/>and is wiped the next time anyone checks that PAN"]

    classDef db fill:#fff4d6,stroke:#b8860b,color:#000
    classDef pan fill:#ffd6d6,stroke:#c0392b,color:#000,stroke-width:2px
    classDef popup fill:#e8e8ff,stroke:#5b5bd6,color:#000
    class B1,P,S db
    class L,O pan
    class K1s,K2s popup
```

**In a fresh Just Me account the popups can't normally appear.** There is only one member, and nobody has a PAN yet. The only possible one is "Import blocked", when the same CAS was already imported under another Unifolio account.

---

## 3. Family: full flow

Family is different in one important way. **Choosing files doesn't send anything to the server.** Files are queued in the browser, and each one is uploaded, and its PAN checked, only after **Import now**, one member at a time.

```mermaid
flowchart TD
    A["Onboarding: Q4 Household screen"] -->|User clicks Family Too| B["Add Family Members screen"]
    B -->|Each member added| B1[("DB write 1 (per member)<br/>INSERT household_members<br/>e.g. Mom, Dad<br/>all PAN columns = NULL")]
    B1 -->|Continue| C["Family CAS cards: one card per member"]
    C -->|"For each member: pick PDF + password<br/>(or Skip for now)"| C1["File QUEUED IN THE BROWSER ONLY<br/>nothing sent, nothing written"]
    C1 --> D["'Upload your own CAS?' screen"]
    D -->|Upload now| D1[("If no self member yet:<br/>INSERT household_members relationship = self<br/>PAN columns = NULL")]
    D1 --> D2["Own file also QUEUED in browser"]
    D -->|Upload later| E
    D2 --> E["Parse Queue screen: list of queued files"]
    E -->|User clicks Import now| F["Take the NEXT queued member (e.g. Mom)"]
    F --> G["'Parsing…' spinner<br/>Browser → POST /imports/parse<br/>(Mom's file, password, Mom's member id)"]
    G --> H{"PDF valid +<br/>password correct?"}
    H -->|No| H1["Per-member error screen<br/>Try again / Skip Mom for now<br/>(nothing written)"]
    H -->|Yes| I["Server parses CAS + looks up funds<br/>(PAN in server memory only)"]
    I --> J{"Server checks PAN against<br/>household_members.pan_lookup_hash"}
    J -->|"Any conflict:<br/>other account, other family member,<br/>or not Mom's permanent PAN"| K["409 (nothing written)"]
    K --> K1["Popup: 'This PAN already exists'<br/>'The statement you uploaded for Mom belongs to a PAN<br/>that's already in Unifolio. Please choose Mom's own CAS.'"]
    K1 -->|Change CAS file| K2["Upload form for Mom (with Back → popup)"]
    K2 -->|New file uploaded| G
    K1 -->|Skip Mom for now| X
    J -->|"PAN new, or already Mom's"| L[("DB write 2: PAN ENTERS THE DATABASE<br/>UPDATE household_members (Mom) SET<br/>pan_encrypted = encrypt(PAN)<br/>pan_lookup_hash = HMAC(PAN)<br/>pan_pending_until = now + 65 min<br/>→ COMMIT")]
    L --> M["Review screen: 'Review Mom's CAS Import'"]
    M -->|Confirm Import| N[("DB write 3: PAN MADE PERMANENT<br/>UPDATE household_members (Mom)<br/>SET pan_pending_until = NULL")]
    N --> O[("DB write 4 (same transaction)<br/>INSERT imports / folios / transactions<br/>CAS PDF saved, file_expires_at = +30 days<br/>→ COMMIT")]
    O --> X{"More queued members?"}
    X -->|"Yes (e.g. Dad)"| F
    X -->|No| Y["'Import complete' (all members combined) → Get my first score"]

    classDef db fill:#fff4d6,stroke:#b8860b,color:#000
    classDef pan fill:#ffd6d6,stroke:#c0392b,color:#000,stroke-width:2px
    classDef popup fill:#e8e8ff,stroke:#5b5bd6,color:#000
    classDef browser fill:#e6f7ea,stroke:#2e8b57,color:#000
    class B1,D1,O db
    class L,N pan
    class K1 popup
    class C1,D2 browser
```

**Why the queue order matters:** members are processed strictly one after another. Mom's PAN is permanent before Dad's file is uploaded. If Dad's slot contains Mom's statement by mistake, Dad's upload hits the conflict popup.

---

## 4. Timeline of one upload → confirm (what's in memory vs. the database)

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as Browser (ImportFlow / FamilyImportFlow)
    participant API as Backend /imports
    participant MEM as Server memory (review session)
    participant DB as Database (household_members)
    participant FS as File storage (S3 / disk)

    U->>FE: Pick CAS PDF + password, click Upload
    FE->>API: POST /imports/parse (file, password, member_id)
    API->>API: Check the member belongs to this user
    API->>API: Decrypt + parse PDF (casparser)
    Note over API: Raw PAN exists only in RAM from here
    API->>MEM: Create review session (parsed CAS incl. raw PAN, member_id, user_id)
    API->>DB: SELECT … WHERE pan_lookup_hash = HMAC(PAN)
    alt Conflict found
        API-->>MEM: Delete the review session
        API-->>FE: 409 + code
        FE-->>U: Popup (Import blocked / This PAN already exists)
        Note over DB: Nothing written
    else No conflict
        API->>DB: UPDATE pan_encrypted, pan_lookup_hash, pan_pending_until=now+65m
        API->>DB: COMMIT ← PAN IS NOW IN THE DATABASE (pending)
        API-->>FE: Preview (masked PAN only, e.g. L********R)
        FE-->>U: Review screen
        U->>FE: Click Confirm Import
        FE->>API: POST /imports/confirm (session_id, member_id)
        API->>MEM: Load review session (must be same user + member, < 60 min old)
        API->>DB: UPDATE pan_pending_until = NULL ← PAN NOW PERMANENT
        API->>DB: INSERT imports, schemes, folios, transactions
        API->>FS: Save CAS PDF (kept 30 days)
        API->>DB: COMMIT
        API-->>MEM: Delete the review session
        API-->>FE: added / skipped counts
        FE-->>U: Import complete
    end
```

---

## 5. Lifecycle of the PAN columns on one member

```mermaid
stateDiagram-v2
    [*] --> Empty: Member created (Just Me screen / Add Family Members)
    Empty: pan_encrypted = NULL<br/>pan_lookup_hash = NULL<br/>pan_pending_until = NULL
    Pending: pan_encrypted = encrypted PAN<br/>pan_lookup_hash = HMAC<br/>pan_pending_until = upload time + 65 min
    Permanent: pan_encrypted = encrypted PAN<br/>pan_lookup_hash = HMAC<br/>pan_pending_until = NULL

    Empty --> Pending: Upload accepted (POST /imports/parse)
    Pending --> Permanent: Confirm Import (POST /imports/confirm)
    Pending --> Empty: Discard (Try again / Cancel)
    Pending --> Empty: 65 min pass with no Confirm (wiped lazily on next check)
    Pending --> Pending: Same member uploads again (expiry refreshed, or a different PAN replaces it)
    Permanent --> Permanent: Later imports of the same PAN (no change)
    Permanent --> Permanent: Upload with a different PAN → refused, popup, no change
```

**The request-CAS email path** (`/cas-imports`) has no review screen. It goes straight from **Empty** to **Permanent** in one call. The current UI doesn't use it: its "I already have a statement" upload goes through `/imports/parse` like every other screen.

---

## 6. ER diagram (import-related tables)

```mermaid
erDiagram
    users ||--o{ household_members : "has"
    household_members ||--o{ imports : "owns"
    household_members ||--o{ folios : "owns"
    schemes ||--o{ folios : "is held in"
    folios ||--o{ transactions : "has" 
    imports ||--o{ transactions : "created"

    users {
        uuid id PK
        string phone_number UK
        string email
        timestamptz created_at
        string onboarding_step
        timestamptz onboarding_completed_at
        enum investor_type
        enum primary_goal
    }

    household_members {
        uuid id PK
        uuid user_id FK
        string name
        enum relationship "self | spouse | parent | child | sibling | other"
        string relationship_other_label
        timestamptz created_at
        string pan_encrypted "PAN column 1: AES-256-GCM ciphertext. Written at UPLOAD"
        string pan_lookup_hash UK "PAN column 2: HMAC-SHA256, UNIQUE index. Written at UPLOAD, same write as pan_encrypted"
        timestamptz pan_pending_until "Set at UPLOAD (+65 min), cleared to NULL at CONFIRM"
    }

    imports {
        uuid id PK
        uuid household_member_id FK
        enum status
        enum source_cas_type
        json raw_parser_output "parsed CAS with PAN REDACTED"
        timestamptz uploaded_at
        timestamptz confirmed_at
        string file_reference "stored CAS PDF key. Written at CONFIRM"
        timestamptz file_expires_at "CONFIRM + 30 days"
        int new_transactions_count
        int duplicate_transactions_count
    }

    folios {
        uuid id PK
        uuid household_member_id FK
        uuid scheme_id FK
        string folio_number
        enum plan_type
        bool has_coverage_gap
    }

    schemes {
        uuid id PK
        string amfi_code UK
        string isin
        string name
        string amc_name
        string sebi_category
    }

    transactions {
        uuid id PK
        uuid folio_id FK
        uuid import_id FK
        enum type
        date date
        numeric amount
        numeric units
        numeric nav
    }
```

**Where PAN is and isn't stored:**

| Place | PAN? |
|---|---|
| `household_members.pan_encrypted` | Yes, encrypted (recoverable only with the server key) |
| `household_members.pan_lookup_hash` | Yes, as a one-way fingerprint (cannot be turned back into the PAN) |
| `imports.raw_parser_output` | **No.** The PAN is removed before this is saved |
| Stored CAS PDF (`imports.file_reference`) | Inside the PDF itself, as the CAS prints it; deleted after 30 days |
| Any API response / screen | **No.** Only the masked form (`L********R`) |
| Server logs | **No.** Logs name the member id only |
| Server memory (review session) | Yes, raw, for at most 60 minutes, until Confirm / Discard / expiry |

**The unique index on `pan_lookup_hash`** is what enforces "one PAN, one member, across all of Unifolio". A *pending* PAN occupies it too. So while one member's review screen is open, no other member or account can claim the same PAN.
