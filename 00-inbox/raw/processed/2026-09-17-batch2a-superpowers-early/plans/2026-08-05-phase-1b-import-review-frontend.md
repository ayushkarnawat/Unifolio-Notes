# Phase 1b — Import Review Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Import Review frontend (PRD-01 / App-Flow screens S8–S12:
Upload, Parsing, Review, Error, Confirmed) as a self-contained React feature
talking to the live `POST /imports/parse` and `POST /imports/confirm`
endpoints Phase 1 backend built.

**Architecture:** One stateful parent component (`ImportFlow`) owns a step
enum and the current preview/confirm/error data in `useState`, rendering
whichever of five child screens is active. No router, no context, no state
library — a linear, short-lived flow. Styling via CSS Modules with design
tokens (from `Design-Schema-Unifolio.md`) as CSS custom properties. Full
detail and rationale: `Docs/superpowers/specs/2026-08-05-import-review-frontend-design.md`.

**Tech Stack:** React 19, Vite, TypeScript (`verbatimModuleSyntax` —
type-only imports required), Vitest + React Testing Library (already in the
scaffold), CSS Modules (native to Vite, no new dependency).

## Global Constraints

- No router library, no persistent nav shell — this phase builds only the
  Import flow (design spec's explicit scope decision).
- `household_member_id` comes from `import.meta.env.VITE_DEV_HOUSEHOLD_MEMBER_ID`
  (a dev-seeded fixture), never a UI field — no auth exists yet.
- Money/unit/NAV values from the API are strings — display as-is, never
  parse into JS `number` (avoids float precision issues on the frontend too,
  consistent with the backend's Decimal-everywhere non-negotiable).
- Confirm must be disabled client-side until every `pending`-confidence or
  `unclassified`-plan-type scheme has an override filled in — this is how
  FR-10's "never silently guess" becomes a UI guarantee, not just a
  server-side 409 backstop.
- Test-driven: every task is red→green→commit.
- `tsconfig.app.json` has `verbatimModuleSyntax: true` — every type-only
  import must use `import type { X } from '...'`, not `import { X }`.
  `noUnusedLocals`/`noUnusedParameters` are on — no dead imports/params.

## File Structure

```
frontend/
  .env.example                          # CREATE
  src/
    App.tsx                              # MODIFY — mount ImportFlow
    components/
      Badge.tsx                           # CREATE
      Badge.module.css                     # CREATE
      Badge.test.tsx                        # CREATE
    features/import/
      types.ts                              # CREATE
      api.ts                                  # CREATE
      api.test.ts                              # CREATE
      UploadForm.tsx                            # CREATE
      UploadForm.module.css                      # CREATE
      UploadForm.test.tsx                          # CREATE
      ParsingIndicator.tsx                          # CREATE
      ParsingIndicator.module.css                    # CREATE
      ImportError.tsx                                 # CREATE
      ImportError.module.css                           # CREATE
      ImportConfirmed.tsx                                # CREATE
      ImportConfirmed.module.css                          # CREATE
      ReviewTable.tsx                                      # CREATE
      ReviewTable.module.css                                # CREATE
      ReviewTable.test.tsx                                    # CREATE
      ImportFlow.tsx                                           # CREATE
      ImportFlow.test.tsx                                       # CREATE
    styles/
      tokens.css                                                 # CREATE
    index.css                                                     # MODIFY

backend/
  app/main.py                             # MODIFY — add CORS middleware
  tests/test_health.py                     # MODIFY — CORS test
  scripts/seed_dev_household_member.py      # CREATE
```

---

### Task 1: Design tokens and the shared Badge component

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/index.css`
- Create: `frontend/src/components/Badge.tsx`
- Create: `frontend/src/components/Badge.module.css`
- Create: `frontend/src/components/Badge.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: CSS custom properties (`--color-*`, `--font-*`, `--type-*`,
  `--space-*`, `--radius-*`, `--motion-*`) available globally once
  `index.css` is loaded (already imported by `main.tsx`). `Badge` component:
  `<Badge variant="positive" | "neutral" | "warning">{label}</Badge>`.
  Tasks 3–6 import and use `Badge`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/Badge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders the label text", () => {
    render(<Badge variant="positive">confirmed</Badge>);
    expect(screen.getByText("confirmed")).toBeInTheDocument();
  });

  it("applies the variant class", () => {
    render(<Badge variant="warning">stale</Badge>);
    expect(screen.getByText("stale").className).toContain("warning");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- Badge.test.tsx`
Expected: FAIL — `Cannot find module './Badge'`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/styles/tokens.css`:
```css
:root {
  /* Color tokens — light mode (Design-Schema-Unifolio.md) */
  --color-bg: #FCFCFC;
  --color-ink: #111111;
  --color-surface: #FFFFFF;
  --color-border: #E5E5E5;
  --color-text-secondary: #5C5C5C;
  --color-accent: #22C55E;
  --color-positive: #16A34A;
  --color-negative: #EF4444;
  --color-neutral-badge: #94A3B8;
  --color-warning: #F59E0B;

  /* Typography */
  --font-display: "DM Sans", sans-serif;
  --font-body: "Manrope", sans-serif;
  --type-h1-size: 24px;
  --type-h2-size: 18px;
  --type-body-size: 15px;
  --type-caption-size: 13px;
  --type-data-size: 15px;

  /* Spacing scale (4px base) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;

  /* Shape */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 20px;

  /* Motion */
  --motion-fast: 150ms ease-out;
  --motion-reveal: 400ms ease-in-out;
  --motion-page: 300ms ease-in-out;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0F0F0F;
    --color-ink: #F5F5F5;
    --color-surface: #1A1A1A;
    --color-border: #2A2A2A;
    --color-text-secondary: #A3A3A3;
    --color-positive: #22C55E;
    --color-negative: #F87171;
  }
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fast: 0ms;
    --motion-reveal: 0ms;
    --motion-page: 0ms;
  }
}
```

`frontend/src/index.css` (replace entire contents — the prior content was
Vite's generic scaffold theme, unrelated to Unifolio's brand):
```css
@import "./styles/tokens.css";

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-ink);
  font-family: var(--font-body);
  font-size: var(--type-body-size);
  line-height: 1.5;
}

h1 {
  font-family: var(--font-display);
  font-size: var(--type-h1-size);
  font-weight: 700;
  margin: 0 0 var(--space-4);
}

h2 {
  font-family: var(--font-display);
  font-size: var(--type-h2-size);
  font-weight: 600;
  margin: 0 0 var(--space-2);
}
```

`frontend/src/components/Badge.tsx`:
```tsx
import styles from "./Badge.module.css";

export type BadgeVariant = "positive" | "neutral" | "warning";

interface BadgeProps {
  variant: BadgeVariant;
  children: string;
}

export function Badge({ variant, children }: BadgeProps) {
  return <span className={`${styles.badge} ${styles[variant]}`}>{children}</span>;
}
```

`frontend/src/components/Badge.module.css`:
```css
.badge {
  display: inline-block;
  border-radius: var(--radius-sm);
  padding: 2px var(--space-2);
  font-family: var(--font-body);
  font-size: var(--type-caption-size);
  font-weight: 500;
  line-height: 1.4;
}

.positive {
  background: color-mix(in srgb, var(--color-positive) 15%, transparent);
  color: var(--color-positive);
}

.neutral {
  background: color-mix(in srgb, var(--color-neutral-badge) 20%, transparent);
  color: var(--color-neutral-badge);
}

.warning {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- Badge.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd "/mnt/d/Unifolio code"
git add frontend/src/styles frontend/src/index.css frontend/src/components
git commit -m "feat(import-frontend): design tokens and shared Badge component"
```

---

### Task 2: API contract types and fetch wrapper

**Files:**
- Create: `frontend/src/features/import/types.ts`
- Create: `frontend/src/features/import/api.ts`
- Create: `frontend/src/features/import/api.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: types `SchemeMatchPreview`, `TransactionPreview`,
  `ImportPreviewResponse`, `SchemeConfirmation`, `ImportConfirmResponse`,
  `ParseErrorPayload` (mirroring `backend/app/services/import_/schemas.py`
  exactly). Functions `parseImport(file: File, password: string): Promise<ImportPreviewResponse>`,
  `confirmImport(sessionId: string, confirmations: SchemeConfirmation[]): Promise<ImportConfirmResponse>`.
  Class `ApiError extends Error` with `status: number` and
  `payload: ParseErrorPayload | string`. Tasks 3–6 import all of these.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/import/types.ts` (no test needed — pure type
definitions, verified by the compiler and by every other test importing
them):
```ts
export interface SchemeMatchPreview {
  temp_id: string;
  name: string;
  isin: string | null;
  amfi_code: string | null;
  suggested_amfi_code: string | null;
  suggested_name: string | null;
  match_confidence: number;
  match_status: string;
  folio: string;
  amc: string;
  transaction_count: number;
  plan_type: string;
  category: string | null;
}

export interface TransactionPreview {
  folio: string;
  scheme_name: string;
  txn_date: string;
  txn_type: string;
  description: string | null;
  amount: string | null;
  units: string | null;
  nav: string | null;
}

export interface ImportPreviewResponse {
  session_id: string;
  filename: string;
  investor_name: string | null;
  investor_email: string | null;
  pan_masked: string | null;
  schemes: SchemeMatchPreview[];
  transactions: TransactionPreview[];
  transaction_count: number;
  parse_warnings: string[];
  cas_type: string;
  file_type: string;
}

export interface SchemeConfirmation {
  temp_id: string;
  amfi_code?: string;
  plan_type_override?: "direct" | "regular" | "unclassified";
}

export interface ImportConfirmResponse {
  added: number;
  skipped: number;
  import_id: string;
}

export interface ParseErrorPayload {
  code: string;
  message: string;
}
```

`frontend/src/features/import/api.test.ts`:
```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, confirmImport, parseImport } from "./api";

describe("parseImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the file and password as multipart form data", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: "s1", schemes: [], transactions: [] }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
    await parseImport(file, "secret");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/imports/parse");
    expect(options.method).toBe("POST");
    const body = options.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("password")).toBe("secret");
  });

  it("throws ApiError with the structured payload on a 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "wrong_password", message: "Incorrect PDF password." } }),
          { status: 422 },
        ),
      ),
    );

    const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
    await expect(parseImport(file, "wrong")).rejects.toMatchObject({
      status: 422,
      payload: { code: "wrong_password", message: "Incorrect PDF password." },
    });
  });
});

describe("confirmImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends session_id and scheme_confirmations as JSON", async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ added: 1, skipped: 0, import_id: "imp1" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", mockFetch);

    await confirmImport("sess1", [{ temp_id: "t1", amfi_code: "12345" }]);

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/imports/confirm");
    const body = JSON.parse(options.body as string);
    expect(body.session_id).toBe("sess1");
    expect(body.scheme_confirmations).toEqual([{ temp_id: "t1", amfi_code: "12345" }]);
  });

  it("throws ApiError with a string payload on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Import session not found." }), { status: 404 }),
      ),
    );

    await expect(confirmImport("gone", [])).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- api.test.ts`
Expected: FAIL — `Cannot find module './api'`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/features/import/api.ts`:
```ts
import type {
  ImportConfirmResponse,
  ImportPreviewResponse,
  ParseErrorPayload,
  SchemeConfirmation,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const HOUSEHOLD_MEMBER_ID = import.meta.env.VITE_DEV_HOUSEHOLD_MEMBER_ID ?? "";

export class ApiError extends Error {
  status: number;
  payload: ParseErrorPayload | string;

  constructor(status: number, payload: ParseErrorPayload | string) {
    super(typeof payload === "string" ? payload : payload.message);
    this.status = status;
    this.payload = payload;
  }
}

async function parseErrorDetail(response: Response): Promise<ParseErrorPayload | string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail) && "code" in detail) {
      return detail as ParseErrorPayload;
    }
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === "string") {
      return detail[0].msg as string;
    }
    return `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function parseImport(file: File, password: string): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", password);

  const response = await fetch(`${API_BASE_URL}/imports/parse`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }

  return (await response.json()) as ImportPreviewResponse;
}

export async function confirmImport(
  sessionId: string,
  schemeConfirmations: SchemeConfirmation[],
): Promise<ImportConfirmResponse> {
  const response = await fetch(`${API_BASE_URL}/imports/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      household_member_id: HOUSEHOLD_MEMBER_ID,
      scheme_confirmations: schemeConfirmations,
    }),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }

  return (await response.json()) as ImportConfirmResponse;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- api.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/types.ts frontend/src/features/import/api.ts frontend/src/features/import/api.test.ts
git commit -m "feat(import-frontend): API contract types and fetch wrapper"
```

---

### Task 3: UploadForm (S8)

**Files:**
- Create: `frontend/src/features/import/UploadForm.tsx`
- Create: `frontend/src/features/import/UploadForm.module.css`
- Create: `frontend/src/features/import/UploadForm.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `<UploadForm onSubmit={(file: File, password: string) => void} />`.
  Task 6 (`ImportFlow`) renders this for the `upload` step.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/features/import/UploadForm.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UploadForm } from "./UploadForm";

describe("UploadForm", () => {
  it("rejects a non-PDF file before submit", () => {
    const onSubmit = vi.fn();
    render(<UploadForm onSubmit={onSubmit} />);

    const file = new File(["not a pdf"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [file] } });

    expect(screen.getByText(/please choose a pdf file/i)).toBeInTheDocument();
  });

  it("calls onSubmit with the file and password for a valid PDF", () => {
    const onSubmit = vi.fn();
    render(<UploadForm onSubmit={onSubmit} />);

    const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /upload/i }));

    expect(onSubmit).toHaveBeenCalledWith(file, "secret");
  });

  it("shows an error and does not submit when no file is chosen", () => {
    const onSubmit = vi.fn();
    render(<UploadForm onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: /upload/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/please choose a pdf file/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- UploadForm.test.tsx`
Expected: FAIL — `Cannot find module './UploadForm'`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/features/import/UploadForm.tsx`:
```tsx
import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import styles from "./UploadForm.module.css";

interface UploadFormProps {
  onSubmit: (file: File, password: string) => void;
}

export function UploadForm({ onSubmit }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    if (selected && !selected.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setFileError("Please choose a PDF file.");
      return;
    }
    setFile(selected);
    setFileError(null);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setFileError("Please choose a PDF file.");
      return;
    }
    onSubmit(file, password);
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <h1>Import your CAS</h1>
      <label className={styles.field}>
        CAS PDF
        <input type="file" accept="application/pdf" onChange={handleFileChange} />
      </label>
      {fileError && <p className={styles.error}>{fileError}</p>}
      <label className={styles.field}>
        PDF password
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      <button type="submit">Upload</button>
    </form>
  );
}
```

`frontend/src/features/import/UploadForm.module.css`:
```css
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 420px;
  margin: 0 auto;
  padding: var(--space-8);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--type-body-size);
}

.field input {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  font-size: var(--type-body-size);
  background: var(--color-surface);
  color: var(--color-ink);
}

.error {
  color: var(--color-negative);
  font-size: var(--type-caption-size);
  margin: 0;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- UploadForm.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/UploadForm.tsx frontend/src/features/import/UploadForm.module.css frontend/src/features/import/UploadForm.test.tsx
git commit -m "feat(import-frontend): UploadForm screen (S8)"
```

---

### Task 4: ParsingIndicator, ImportError, ImportConfirmed (S9, S11, S12)

Three small, display-only screens bundled in one task — none has enough
independent complexity to warrant its own reviewer gate.

**Files:**
- Create: `frontend/src/features/import/ParsingIndicator.tsx`
- Create: `frontend/src/features/import/ParsingIndicator.module.css`
- Create: `frontend/src/features/import/ImportError.tsx`
- Create: `frontend/src/features/import/ImportError.module.css`
- Create: `frontend/src/features/import/ImportConfirmed.tsx`
- Create: `frontend/src/features/import/ImportConfirmed.module.css`
- Create: `frontend/src/features/import/ImportError.test.tsx`
- Create: `frontend/src/features/import/ImportConfirmed.test.tsx`

**Interfaces:**
- Consumes: `ParseErrorPayload`, `ImportConfirmResponse` (Task 2).
- Produces: `<ParsingIndicator />`, `<ImportError error={ParseErrorPayload} onRetry={() => void} />`,
  `<ImportConfirmed result={ImportConfirmResponse} onImportAnother={() => void} />`.
  Task 6 renders all three.

`ParsingIndicator` has no test — it's a pure static render with no
props/branches to verify beyond "it renders," which `ImportFlow`'s own
test (Task 6) already exercises by mounting the full flow through the
parsing step.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/features/import/ImportError.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportError } from "./ImportError";

describe("ImportError", () => {
  it("shows the error message and calls onRetry", () => {
    const onRetry = vi.fn();
    render(<ImportError error={{ code: "wrong_password", message: "Incorrect PDF password." }} onRetry={onRetry} />);

    expect(screen.getByText("Incorrect PDF password.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});
```

```tsx
// frontend/src/features/import/ImportConfirmed.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportConfirmed } from "./ImportConfirmed";

describe("ImportConfirmed", () => {
  it("shows added/skipped counts and calls onImportAnother", () => {
    const onImportAnother = vi.fn();
    render(<ImportConfirmed result={{ added: 3, skipped: 1, import_id: "imp1" }} onImportAnother={onImportAnother} />);

    expect(screen.getByText(/3 new transactions added, 1 duplicate skipped/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /import another cas/i }));
    expect(onImportAnother).toHaveBeenCalled();
  });

  it("uses singular wording for one transaction and no duplicates clause when zero", () => {
    render(<ImportConfirmed result={{ added: 1, skipped: 0, import_id: "imp2" }} onImportAnother={vi.fn()} />);

    expect(screen.getByText(/1 new transaction added\./i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- ImportError.test.tsx ImportConfirmed.test.tsx`
Expected: FAIL — modules don't exist

- [ ] **Step 3: Write minimal implementation**

`frontend/src/features/import/ParsingIndicator.tsx`:
```tsx
import styles from "./ParsingIndicator.module.css";

export function ParsingIndicator() {
  return (
    <div className={styles.container} role="status">
      <div className={styles.spinner} />
      <p>Parsing your CAS...</p>
    </div>
  );
}
```

`frontend/src/features/import/ParsingIndicator.module.css`:
```css
.container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-16);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
```

`frontend/src/features/import/ImportError.tsx`:
```tsx
import type { ParseErrorPayload } from "./types";
import styles from "./ImportError.module.css";

interface ImportErrorProps {
  error: ParseErrorPayload;
  onRetry: () => void;
}

export function ImportError({ error, onRetry }: ImportErrorProps) {
  return (
    <div className={styles.container}>
      <h1>Import failed</h1>
      <p>{error.message}</p>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
```

`frontend/src/features/import/ImportError.module.css`:
```css
.container {
  max-width: 420px;
  margin: 0 auto;
  padding: var(--space-8);
  text-align: center;
}
```

`frontend/src/features/import/ImportConfirmed.tsx`:
```tsx
import type { ImportConfirmResponse } from "./types";
import styles from "./ImportConfirmed.module.css";

interface ImportConfirmedProps {
  result: ImportConfirmResponse;
  onImportAnother: () => void;
}

export function ImportConfirmed({ result, onImportAnother }: ImportConfirmedProps) {
  const addedText = `${result.added} new transaction${result.added === 1 ? "" : "s"} added`;
  const skippedText =
    result.skipped > 0 ? `, ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped` : "";

  return (
    <div className={styles.container}>
      <h1>Import complete</h1>
      <p>{`${addedText}${skippedText}.`}</p>
      <button type="button" onClick={onImportAnother}>
        Import another CAS
      </button>
    </div>
  );
}
```

`frontend/src/features/import/ImportConfirmed.module.css`:
```css
.container {
  max-width: 420px;
  margin: 0 auto;
  padding: var(--space-8);
  text-align: center;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- ImportError.test.tsx ImportConfirmed.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/ParsingIndicator.tsx frontend/src/features/import/ParsingIndicator.module.css \
        frontend/src/features/import/ImportError.tsx frontend/src/features/import/ImportError.module.css frontend/src/features/import/ImportError.test.tsx \
        frontend/src/features/import/ImportConfirmed.tsx frontend/src/features/import/ImportConfirmed.module.css frontend/src/features/import/ImportConfirmed.test.tsx
git commit -m "feat(import-frontend): Parsing, Error, and Confirmed screens (S9, S11, S12)"
```

---

### Task 5: ReviewTable (S10) — confidence/plan-type badges, override inputs, gated Confirm

**Files:**
- Create: `frontend/src/features/import/ReviewTable.tsx`
- Create: `frontend/src/features/import/ReviewTable.module.css`
- Create: `frontend/src/features/import/ReviewTable.test.tsx`

**Interfaces:**
- Consumes: `Badge` (Task 1), `ImportPreviewResponse`, `SchemeConfirmation`
  (Task 2).
- Produces: `<ReviewTable preview={ImportPreviewResponse} confirming={boolean} onConfirm={(confirmations: SchemeConfirmation[]) => void} />`.
  Task 6 renders this for the `review` step.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/features/import/ReviewTable.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewTable } from "./ReviewTable";
import type { ImportPreviewResponse } from "./types";

function buildPreview(overrides: Partial<ImportPreviewResponse> = {}): ImportPreviewResponse {
  return {
    session_id: "sess1",
    filename: "cas.pdf",
    investor_name: "Test Investor",
    investor_email: "t@example.com",
    pan_masked: "A********F",
    schemes: [],
    transactions: [],
    transaction_count: 0,
    parse_warnings: [],
    cas_type: "DETAILED",
    file_type: "FileType.CAMS",
    ...overrides,
  };
}

describe("ReviewTable", () => {
  it("disables Confirm when a pending scheme has no AMFI override", () => {
    const preview = buildPreview({
      schemes: [
        {
          temp_id: "t1", name: "Ambiguous Fund", isin: null, amfi_code: null,
          suggested_amfi_code: null, suggested_name: null, match_confidence: 0.5,
          match_status: "pending", folio: "F1", amc: "AMC1", transaction_count: 1,
          plan_type: "direct", category: null,
        },
      ],
    });
    render(<ReviewTable preview={preview} confirming={false} onConfirm={vi.fn()} />);

    expect(screen.getByRole("button", { name: /confirm import/i })).toBeDisabled();
  });

  it("enables Confirm once every pending/unclassified scheme has an override", () => {
    const preview = buildPreview({
      schemes: [
        {
          temp_id: "t1", name: "Ambiguous Fund", isin: null, amfi_code: null,
          suggested_amfi_code: null, suggested_name: null, match_confidence: 0.5,
          match_status: "pending", folio: "F1", amc: "AMC1", transaction_count: 1,
          plan_type: "unclassified", category: null,
        },
      ],
    });
    render(<ReviewTable preview={preview} confirming={false} onConfirm={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText(/amfi code/i), { target: { value: "125497" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "direct" } });

    expect(screen.getByRole("button", { name: /confirm import/i })).toBeEnabled();
  });

  it("calls onConfirm with only the filled-in overrides, omitting already-confident schemes", () => {
    const onConfirm = vi.fn();
    const preview = buildPreview({
      schemes: [
        {
          temp_id: "t1", name: "Confident Fund", isin: null, amfi_code: "999",
          suggested_amfi_code: "999", suggested_name: "Confident Fund", match_confidence: 1,
          match_status: "confirmed", folio: "F1", amc: "AMC1", transaction_count: 1,
          plan_type: "direct", category: null,
        },
      ],
    });
    render(<ReviewTable preview={preview} confirming={false} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it("renders parse warnings when present", () => {
    const preview = buildPreview({ parse_warnings: ["Skipped transaction on 2024-01-01: missing amount"] });
    render(<ReviewTable preview={preview} confirming={false} onConfirm={vi.fn()} />);

    expect(screen.getByText(/skipped transaction on 2024-01-01/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- ReviewTable.test.tsx`
Expected: FAIL — `Cannot find module './ReviewTable'`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/features/import/ReviewTable.tsx`:
```tsx
import { useState } from "react";
import { Badge } from "../../components/Badge";
import type { ImportPreviewResponse, SchemeConfirmation } from "./types";
import styles from "./ReviewTable.module.css";

interface ReviewTableProps {
  preview: ImportPreviewResponse;
  confirming: boolean;
  onConfirm: (confirmations: SchemeConfirmation[]) => void;
}

interface OverrideState {
  amfiCode: string;
  planType: "" | "direct" | "regular";
}

function needsAmfiOverride(matchStatus: string): boolean {
  return matchStatus !== "confirmed";
}

function needsPlanTypeOverride(planType: string): boolean {
  return planType === "unclassified";
}

export function ReviewTable({ preview, confirming, onConfirm }: ReviewTableProps) {
  const [overrides, setOverrides] = useState<Record<string, OverrideState>>({});

  const updateOverride = (tempId: string, patch: Partial<OverrideState>) => {
    setOverrides((prev) => ({
      ...prev,
      [tempId]: { amfiCode: "", planType: "", ...prev[tempId], ...patch },
    }));
  };

  const allResolved = preview.schemes.every((scheme) => {
    const override = overrides[scheme.temp_id];
    if (needsAmfiOverride(scheme.match_status) && !override?.amfiCode.trim()) {
      return false;
    }
    if (needsPlanTypeOverride(scheme.plan_type) && !override?.planType) {
      return false;
    }
    return true;
  });

  const handleConfirm = () => {
    const confirmations: SchemeConfirmation[] = preview.schemes
      .filter((scheme) => overrides[scheme.temp_id])
      .map((scheme) => {
        const override = overrides[scheme.temp_id];
        const confirmation: SchemeConfirmation = { temp_id: scheme.temp_id };
        if (override.amfiCode.trim()) {
          confirmation.amfi_code = override.amfiCode.trim();
        }
        if (override.planType) {
          confirmation.plan_type_override = override.planType;
        }
        return confirmation;
      });
    onConfirm(confirmations);
  };

  return (
    <div className={styles.container}>
      <h1>Review CAS Import</h1>
      <dl className={styles.investorInfo}>
        <dt>Investor</dt>
        <dd>{preview.investor_name ?? "Not found in CAS"}</dd>
        <dt>PAN</dt>
        <dd>{preview.pan_masked ?? "Not found in CAS"}</dd>
        <dt>Transactions found</dt>
        <dd>{preview.transaction_count}</dd>
      </dl>

      {preview.parse_warnings.length > 0 && (
        <ul className={styles.warnings}>
          {preview.parse_warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Scheme</th>
            <th>Folio / AMC</th>
            <th>AMFI Match</th>
            <th>Plan Type</th>
            <th>Txns</th>
          </tr>
        </thead>
        <tbody>
          {preview.schemes.map((scheme) => (
            <tr key={scheme.temp_id}>
              <td>{scheme.name}</td>
              <td>
                {scheme.folio} / {scheme.amc}
              </td>
              <td>
                <Badge variant={scheme.match_status === "confirmed" ? "positive" : "neutral"}>
                  {scheme.match_status}
                </Badge>
                {scheme.suggested_name && <div className={styles.suggestion}>{scheme.suggested_name}</div>}
                {needsAmfiOverride(scheme.match_status) && (
                  <input
                    type="text"
                    placeholder="AMFI code"
                    value={overrides[scheme.temp_id]?.amfiCode ?? ""}
                    onChange={(event) => updateOverride(scheme.temp_id, { amfiCode: event.target.value })}
                  />
                )}
              </td>
              <td>
                <Badge variant={scheme.plan_type === "unclassified" ? "neutral" : "positive"}>
                  {scheme.plan_type}
                </Badge>
                {needsPlanTypeOverride(scheme.plan_type) && (
                  <select
                    value={overrides[scheme.temp_id]?.planType ?? ""}
                    onChange={(event) =>
                      updateOverride(scheme.temp_id, {
                        planType: event.target.value as "" | "direct" | "regular",
                      })
                    }
                  >
                    <option value="">Select...</option>
                    <option value="direct">Direct</option>
                    <option value="regular">Regular</option>
                  </select>
                )}
              </td>
              <td>{scheme.transaction_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" disabled={!allResolved || confirming} onClick={handleConfirm}>
        {confirming ? "Confirming..." : "Confirm Import"}
      </button>
    </div>
  );
}
```

`frontend/src/features/import/ReviewTable.module.css`:
```css
.container {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--space-8);
}

.investorInfo {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-4);
  font-size: var(--type-body-size);
  margin-bottom: var(--space-6);
}

.investorInfo dt {
  color: var(--color-text-secondary);
}

.investorInfo dd {
  margin: 0;
  font-family: var(--font-body);
}

.warnings {
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-6);
  color: var(--color-warning);
  font-size: var(--type-caption-size);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--type-data-size);
  font-variant-numeric: tabular-nums;
}

.table th {
  text-align: left;
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.table td {
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-2) var(--space-3);
  vertical-align: top;
}

.suggestion {
  font-size: var(--type-caption-size);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- ReviewTable.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/ReviewTable.tsx frontend/src/features/import/ReviewTable.module.css frontend/src/features/import/ReviewTable.test.tsx
git commit -m "feat(import-frontend): ReviewTable screen with gated Confirm (S10)"
```

---

### Task 6: ImportFlow — the orchestrator

**Files:**
- Create: `frontend/src/features/import/ImportFlow.tsx`
- Create: `frontend/src/features/import/ImportFlow.test.tsx`

**Interfaces:**
- Consumes: `UploadForm`, `ParsingIndicator`, `ReviewTable`, `ImportError`,
  `ImportConfirmed` (Tasks 3-5), `parseImport`, `confirmImport`, `ApiError`
  (Task 2).
- Produces: `<ImportFlow />` — no props. Task 7 mounts this from `App.tsx`.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/features/import/ImportFlow.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImportFlow } from "./ImportFlow";
import * as api from "./api";
import { ApiError } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, parseImport: vi.fn(), confirmImport: vi.fn() };
});

function uploadAFile() {
  const file = new File(["pdf-bytes"], "cas.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText(/cas pdf/i), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText(/pdf password/i), { target: { value: "secret" } });
  fireEvent.click(screen.getByRole("button", { name: /upload/i }));
}

const EMPTY_PREVIEW = {
  session_id: "s1", filename: "cas.pdf", investor_name: "Test", investor_email: null,
  pan_masked: "A********F", schemes: [], transactions: [], transaction_count: 0,
  parse_warnings: [], cas_type: "DETAILED", file_type: "FileType.CAMS",
};

describe("ImportFlow", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("moves from upload to review on a successful parse", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);

    render(<ImportFlow />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/review cas import/i)).toBeInTheDocument());
  });

  it("moves to the error screen on a ParseError", async () => {
    vi.mocked(api.parseImport).mockRejectedValue(
      new ApiError(422, { code: "wrong_password", message: "Incorrect PDF password." }),
    );

    render(<ImportFlow />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/incorrect pdf password/i)).toBeInTheDocument());
  });

  it("shows a generic message on a network failure", async () => {
    vi.mocked(api.parseImport).mockRejectedValue(new TypeError("Failed to fetch"));

    render(<ImportFlow />);
    uploadAFile();

    await waitFor(() => expect(screen.getByText(/couldn't reach the server/i)).toBeInTheDocument());
  });

  it("moves to confirmed on a successful confirm", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 3, skipped: 1, import_id: "imp1" });

    render(<ImportFlow />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByText(/import complete/i)).toBeInTheDocument());
  });

  it("shows an inline notice instead of navigating away on a 409", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockRejectedValue(new ApiError(409, "Scheme 'X' requires an explicit AMFI code."));

    render(<ImportFlow />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/requires an explicit amfi code/i));
    expect(screen.getByText(/review cas import/i)).toBeInTheDocument();
  });

  it("resets to upload from the confirmed screen", async () => {
    vi.mocked(api.parseImport).mockResolvedValue(EMPTY_PREVIEW);
    vi.mocked(api.confirmImport).mockResolvedValue({ added: 1, skipped: 0, import_id: "imp1" });

    render(<ImportFlow />);
    uploadAFile();
    await waitFor(() => screen.getByRole("button", { name: /confirm import/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm import/i }));
    await waitFor(() => screen.getByRole("button", { name: /import another cas/i }));
    fireEvent.click(screen.getByRole("button", { name: /import another cas/i }));

    expect(screen.getByRole("button", { name: /^upload$/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- ImportFlow.test.tsx`
Expected: FAIL — `Cannot find module './ImportFlow'`

- [ ] **Step 3: Write minimal implementation**

`frontend/src/features/import/ImportFlow.tsx`:
```tsx
import { useState } from "react";
import { UploadForm } from "./UploadForm";
import { ParsingIndicator } from "./ParsingIndicator";
import { ReviewTable } from "./ReviewTable";
import { ImportError } from "./ImportError";
import { ImportConfirmed } from "./ImportConfirmed";
import { ApiError, confirmImport, parseImport } from "./api";
import type {
  ImportConfirmResponse,
  ImportPreviewResponse,
  ParseErrorPayload,
  SchemeConfirmation,
} from "./types";

type Step = "upload" | "parsing" | "review" | "error" | "confirmed";

const GENERIC_NETWORK_ERROR: ParseErrorPayload = {
  code: "network_error",
  message: "Couldn't reach the server. Check your connection and try again.",
};

function toParseErrorPayload(err: unknown): ParseErrorPayload {
  if (err instanceof ApiError) {
    return typeof err.payload === "string" ? { code: "error", message: err.payload } : err.payload;
  }
  return GENERIC_NETWORK_ERROR;
}

export function ImportFlow() {
  const [step, setStep] = useState<Step>("upload");
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [confirmResult, setConfirmResult] = useState<ImportConfirmResponse | null>(null);
  const [error, setError] = useState<ParseErrorPayload | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const reset = () => {
    setStep("upload");
    setPreview(null);
    setConfirmResult(null);
    setError(null);
    setReviewNotice(null);
    setConfirming(false);
  };

  const handleUpload = async (file: File, password: string) => {
    setStep("parsing");
    try {
      const result = await parseImport(file, password);
      setPreview(result);
      setStep("review");
    } catch (err) {
      setError(toParseErrorPayload(err));
      setStep("error");
    }
  };

  const handleConfirm = async (confirmations: SchemeConfirmation[]) => {
    if (!preview) return;
    setConfirming(true);
    setReviewNotice(null);
    try {
      const result = await confirmImport(preview.session_id, confirmations);
      setConfirmResult(result);
      setStep("confirmed");
    } catch (err) {
      if (err instanceof ApiError && (err.status === 409 || err.status === 404)) {
        setReviewNotice(
          err.status === 404
            ? "This import session has expired. Please re-upload your CAS."
            : typeof err.payload === "string"
              ? err.payload
              : err.payload.message,
        );
      } else {
        setError(toParseErrorPayload(err));
        setStep("error");
      }
    } finally {
      setConfirming(false);
    }
  };

  if (step === "upload") {
    return <UploadForm onSubmit={handleUpload} />;
  }
  if (step === "parsing") {
    return <ParsingIndicator />;
  }
  if (step === "review" && preview) {
    return (
      <>
        {reviewNotice && <p role="alert">{reviewNotice}</p>}
        <ReviewTable preview={preview} confirming={confirming} onConfirm={handleConfirm} />
      </>
    );
  }
  if (step === "confirmed" && confirmResult) {
    return <ImportConfirmed result={confirmResult} onImportAnother={reset} />;
  }
  return <ImportError error={error ?? GENERIC_NETWORK_ERROR} onRetry={reset} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- ImportFlow.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/import/ImportFlow.tsx frontend/src/features/import/ImportFlow.test.tsx
git commit -m "feat(import-frontend): ImportFlow orchestrator wiring all five screens"
```

---

### Task 7: Backend CORS, dev household_member_id seed, wire into App.tsx

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_health.py`
- Create: `backend/scripts/seed_dev_household_member.py`
- Create: `frontend/.env.example`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ImportFlow` (Task 6).
- Produces: a running backend that accepts cross-origin requests from the
  Vite dev server, a real `household_member_id` UUID for local dev, and a
  frontend that actually mounts the Import flow.

This is the task that makes the whole feature runnable end-to-end, not just
individually tested — the plan's final integration point.

- [ ] **Step 1: Write the failing test**

`backend/app/main.py` currently has no CORS middleware — a request from
the Vite dev server (`http://localhost:5173`) would be blocked by the
browser. Extend `backend/tests/test_health.py`:
```python
def test_cors_allows_frontend_dev_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_health.py -v`
Expected: FAIL — `KeyError: 'access-control-allow-origin'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analytics, auth, dashboard, imports

app = FastAPI(title="Unifolio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(imports.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

`backend/scripts/seed_dev_household_member.py` (no pytest test — a
one-time dev utility, verified by running it, per Step 4 below):
```python
"""One-time dev fixture: creates a User + HouseholdMember so the frontend
has a real household_member_id to send. No auth flow exists yet (PRD-02 is
a separate phase) to create one for real. Idempotent — safe to run more
than once, always prints the same UUID once seeded.

Run from backend/: .venv/bin/python scripts/seed_dev_household_member.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.enums import Relationship
from app.models.user import HouseholdMember, User

DEV_PHONE_NUMBER = "+910000000000"


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(phone_number=DEV_PHONE_NUMBER).first()
        if not user:
            user = User(phone_number=DEV_PHONE_NUMBER, created_at=datetime.now(timezone.utc))
            db.add(user)
            db.flush()

        member = db.query(HouseholdMember).filter_by(user_id=user.id).first()
        if not member:
            member = HouseholdMember(
                user_id=user.id,
                name="Dev User",
                relationship=Relationship.SELF,
                created_at=datetime.now(timezone.utc),
            )
            db.add(member)
            db.commit()

        print(f"household_member_id={member.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

`frontend/.env.example`:
```
# Backend base URL for local dev (uvicorn default)
VITE_API_BASE_URL=http://localhost:8000

# Run `.venv/bin/python scripts/seed_dev_household_member.py` from backend/
# and paste the printed UUID here. No auth flow exists yet to supply this
# for real (PRD-02, separate phase) — this is dev-only plumbing.
VITE_DEV_HOUSEHOLD_MEMBER_ID=
```

`frontend/src/App.tsx`:
```tsx
import { ImportFlow } from "./features/import/ImportFlow";

function App() {
  return (
    <div>
      <header>
        <h2>Unifolio</h2>
      </header>
      <ImportFlow />
    </div>
  );
}

export default App;
```

- [ ] **Step 4: Run tests and self-checks to verify everything passes**

Run: `.venv/bin/python -m pytest tests/test_health.py -v` (from `backend/`)
Expected: PASS

Run: `.venv/bin/python -m pytest -m "not postgres" -v` (from `backend/`)
Expected: PASS — full backend suite, no regressions from the CORS change.

Run: `.venv/bin/python scripts/seed_dev_household_member.py` twice (from
`backend/`, with a real `DATABASE_URL` — SQLite dev DB is fine).
Expected: both runs print the identical `household_member_id=<uuid>` line
(confirms idempotency).

Run: `npm test` (from `frontend/`)
Expected: PASS — full frontend suite, including the existing `App.test.tsx`
(`screen.getByText(/unifolio/i)` still matches via the `<h2>Unifolio</h2>`
header — confirm this rather than assuming it).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_health.py backend/scripts \
        frontend/.env.example frontend/src/App.tsx
git commit -m "feat(import-frontend): CORS for local dev, household_member_id seed, wire ImportFlow into App"
```

---

## Self-Review

**Spec coverage** — design spec section by section:
- Architecture (file structure, `ImportFlow` state shape, no router/context)
  — Tasks 1-6 build exactly this structure.
- `household_member_id` sourcing (env var, dev seed) — Task 7.
- Screens (Upload/Parsing/Review/Error/Confirmed, exact behaviors per the
  design's table) — Tasks 3, 4, 5.
- Error handling (422/409/404/network, each routed as the design specifies)
  — Task 6, directly tested.
- Styling (CSS Modules, Design Schema tokens, Badge spec) — Task 1, used
  throughout.
- Testing (Vitest + RTL per component, no E2E) — every task.

**Placeholder scan** — no TBD/"add later" in any task; every step has real,
complete code.

**Type/name consistency** — `ImportPreviewResponse`/`SchemeMatchPreview`/
`SchemeConfirmation`/`ImportConfirmResponse`/`ParseErrorPayload` (Task 2)
match field-for-field against `backend/app/services/import_/schemas.py`
(re-verified by reading that file directly, not from memory); `ApiError`'s
shape is consumed identically by Task 6's `toParseErrorPayload` and the 409/
404 branch; `Badge`'s `BadgeVariant` union (`positive`/`neutral`/`warning`)
matches Design Schema's badge spec exactly (no `negative` variant, per that
document's own note that losses live in data cells, not badges).

## Open Items Flagged, Not Resolved Here

- The design spec's own "Open Items" carry forward unchanged: AMFI-override
  UX (autocomplete/validation) beyond a plain text field, real navigation
  from Confirmed to a Dashboard, and a manual dark-mode toggle — all
  blocked on future phases (Dashboard, Settings) that don't exist yet.
- No visual/manual QA pass against the actual `Fund Signal` component or
  broader Dashboard patterns — out of scope, this plan only touches the
  Import flow's own screens, which don't use Fund Signal.
