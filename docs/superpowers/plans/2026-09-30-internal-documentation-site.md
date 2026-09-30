# Internal Documentation Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Track steps using checkbox (`- [ ]`) syntax.

**Goal:** Deploy this vault as a password-gated, searchable MkDocs Material documentation site on Vercel, reachable at `internaldocumentation.unifolio.in`.

**Architecture:** MkDocs (with `docs_dir: .`) builds the vault's existing numbered folders directly into a static site; `mkdocs-awesome-pages-plugin` supplies clean top-level nav titles/ordering from one root `.pages` file; `mkdocs-gen-files` auto-generates index pages for `08-evidence/`'s raw files. Vercel hosts the static output and runs a small Edge Middleware function in front of every request to enforce one shared password.

**Tech Stack:** MkDocs, mkdocs-material, mkdocs-awesome-pages-plugin, mkdocs-gen-files, Python 3 + pytest (build/config tests), Vercel (hosting + Edge Middleware, plain JS, no framework), pytest for Python tests, Node's built-in `assert` for the middleware test.

**Spec:** `docs/superpowers/specs/2026-09-29-internal-documentation-site-design.md`

## Global Constraints

- Site generator is MkDocs + Material theme only — no Docusaurus, no other SSG.
- Hosting is Vercel free Hobby tier only — no AWS resources of any kind.
- Custom domain is `internaldocumentation.unifolio.in`, via a CNAME on the existing `unifolio.in` Route 53 zone.
- Access control is exactly one shared password via Basic Auth in a Vercel Edge Middleware function reading a `SITE_PASSWORD` env var — no per-user identity, no SSO, password never committed to source.
- `docs_dir` is the repo root (`.`) — no content is duplicated into a separate folder.
- Published output must exclude: `00-inbox/`, `09-archive/`, `.obsidian/`, `.claude/`, `.superpowers/`, `.git/`, `templates/`, `docs/`, `scripts/`, `tests/`, `CLAUDE.md`, `MAP.md`, `README.md`, `requirements.txt`, `vercel.json`, `package.json`, `middleware.js`, `middleware.test.mjs`, `site/`.
- `08-evidence/` is included but is a separate, visually secondary nav section from the primary structured-record nav.
- Search is Material's built-in client-side search only — no Algolia or other third-party indexer.
- Diagrams render via Mermaid through `pymdownx.superfences` — no separate diagram-export step.
- The standard build command is `mkdocs build --strict` — a broken internal link must fail the build, not ship silently.
- Branding uses Material's default palette until the user supplies a custom one; nothing in this plan depends on which palette is used.

## Review Focus

- A stakeholder reaches site content without ever being asked for the password (middleware not applied to some route, or auth check logic inverted) — covered in Task 8's middleware unit tests (missing header, wrong password, correct password).
- A broken internal link between any of the 150+ structured markdown files ships to the live site unnoticed because strict mode isn't actually wired in or doesn't actually fail the build — covered in Task 7's regression test against a fixture with a deliberately broken link.
- A raw/authoring-only file (`00-inbox/`, `CLAUDE.md`, `.claude/`, etc.) leaks into the published output because an exclude pattern is missing or misspelled — covered in Task 2's regression test asserting those paths are absent from a real build.
- An evidence file cited from a structured record 404s on the live site because MkDocs didn't carry it into the build output, or the evidence index page for its folder was never generated — covered in Task 6's test asserting a known real evidence PDF round-trips into the build output and its folder's generated index page exists.
- An existing Mermaid diagram renders as a literal fenced code block instead of a diagram because the superfences custom-fence config is missing or wrong — covered in Task 4's regression test asserting a mermaid-fenced block produces a `class="mermaid"` div in the built HTML.

---

### Task 1: MkDocs + Material scaffolding — prove the build pipeline works

**Files:**
- Create: `requirements.txt`
- Create: `mkdocs.yml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a working `mkdocs build` command any later task can extend; `mkdocs.yml` as the single config file every later task edits.

- [ ] **Step 1: Create `requirements.txt`**

```
mkdocs-material
```

- [ ] **Step 2: Install and check the version resolves**

Run: `pip install -r requirements.txt`
Expected: installs cleanly, `mkdocs --version` prints a `mkdocs, version 1.x` line.

- [ ] **Step 3: Create a minimal `mkdocs.yml`**

```yaml
site_name: Unifolio Internal Documentation
docs_dir: .
site_dir: site

exclude_docs: |
  .git/
  site/

theme:
  name: material

nav:
  - Home: 01-overview/executive-overview.md
```

- [ ] **Step 4: Add the build output directory to `.gitignore`**

Append to `.gitignore`:

```
site/
```

- [ ] **Step 5: Run the build and verify it succeeds**

Run: `mkdocs build`
Expected: exits 0, prints `INFO - Documentation built in` with no errors; `site/01-overview/executive-overview/index.html` exists.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt mkdocs.yml .gitignore
git commit -m "docs-site: scaffold minimal MkDocs Material build"
```

---

### Task 2: Full exclude list — keep raw/authoring files out of the published site

**Files:**
- Modify: `mkdocs.yml`
- Create: `tests/test_excluded_paths_not_published.py`

**Interfaces:**
- Consumes: `mkdocs.yml` from Task 1.
- Produces: the finalized `exclude_docs` block every later task's files (scripts/, tests/, package.json, etc.) must be added to as they're created.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_excluded_paths_not_published.py
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PATHS = [
    "00-inbox",
    "09-archive",
    ".obsidian",
    ".claude",
    ".superpowers",
    "templates",
    "docs",
    "CLAUDE.md",
    "MAP.md",
]


def test_raw_and_authoring_files_are_not_published(tmp_path):
    site_dir = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--site-dir", str(site_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    for excluded in EXCLUDED_PATHS:
        assert not (site_dir / excluded).exists(), f"{excluded} leaked into published site"
```

- [ ] **Step 2: Install pytest and run the test, verify it fails**

Run: `pip install pytest && pytest tests/test_excluded_paths_not_published.py -v`
Expected: FAIL — at least `00-inbox`, `.claude`, `CLAUDE.md`, `MAP.md` etc. exist under the built `site_dir` because `mkdocs.yml` only excludes `.git/` and `site/` so far.

- [ ] **Step 3: Expand `exclude_docs` in `mkdocs.yml`**

Replace the `exclude_docs` block with:

```yaml
exclude_docs: |
  .git/
  site/
  00-inbox/
  09-archive/
  .obsidian/
  .claude/
  .superpowers/
  templates/
  docs/
  scripts/
  tests/
  CLAUDE.md
  MAP.md
  README.md
  requirements.txt
  vercel.json
  package.json
  middleware.js
  middleware.test.mjs
```

- [ ] **Step 4: Add `pytest` to `requirements.txt`**

```
mkdocs-material
pytest
```

- [ ] **Step 5: Run the test again, verify it passes**

Run: `pytest tests/test_excluded_paths_not_published.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mkdocs.yml requirements.txt tests/test_excluded_paths_not_published.py
git commit -m "docs-site: exclude raw/authoring paths from published output"
```

---

### Task 3: Top-level nav & clean section titles

**Files:**
- Modify: `mkdocs.yml`
- Create: `.pages`
- Create: `tests/test_nav_labels.py`

**Interfaces:**
- Consumes: `mkdocs.yml` from Task 2.
- Produces: the final top-level nav order/labels (Home, Overview, Journey, Decisions, Investigations, Reference & How-tos, Architecture, Risks & Debt, Evidence) that Task 5 (landing page) and Task 6 (evidence nav) build on.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nav_labels.py
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_LABELS = [
    "Overview",
    "Journey",
    "Decisions",
    "Investigations",
    "Reference &amp; How-tos",
    "Architecture",
    "Risks &amp; Debt",
    "Evidence",
]


def test_nav_shows_clean_labels_not_raw_folder_names(tmp_path):
    site_dir = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--site-dir", str(site_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    html = (site_dir / "index.html").read_text(encoding="utf-8")
    for label in EXPECTED_LABELS:
        assert label in html, f"nav label {label!r} not found in rendered homepage"
    assert "01-overview" not in html
    assert "08-evidence" not in html
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/test_nav_labels.py -v`
Expected: FAIL — `mkdocs.yml` still has only a one-entry `nav:` from Task 1 pointing at `Home`, so none of the expected section labels exist yet.

- [ ] **Step 3: Add `mkdocs-awesome-pages-plugin` to `requirements.txt`**

```
mkdocs-material
pytest
mkdocs-awesome-pages-plugin
```

Run: `pip install -r requirements.txt`

- [ ] **Step 4: Remove the temporary `nav:` block from `mkdocs.yml` and add the plugin**

`mkdocs.yml`'s `nav:` block from Task 1 is deleted entirely (nav now comes from `.pages`). Add under a `plugins:` key:

```yaml
plugins:
  - search
  - awesome-pages
```

- [ ] **Step 5: Create the root `.pages` file**

```yaml
# .pages
nav:
  - Home: index.md
  - Overview: 01-overview
  - Journey: 02-journey
  - Decisions: 03-decisions
  - Investigations: 04-investigations
  - Reference & How-tos: 05-docs
  - Architecture: 06-architecture
  - Risks & Debt: 07-risks-and-debt.md
  - Evidence: 08-evidence
```

Note: `.pages` references `index.md`, which doesn't exist until Task 5 — `mkdocs build` will still succeed (MkDocs creates a default placeholder for a nav entry pointing at a missing file is NOT true; it will fail). To keep this task's build green, create a one-line placeholder now:

- [ ] **Step 6: Create a placeholder `index.md`** (Task 5 replaces this with real landing-page content)

```markdown
# Unifolio Internal Documentation

Landing page content coming in a later task.
```

- [ ] **Step 7: Run the build, then the test, verify it passes**

Run: `mkdocs build && pytest tests/test_nav_labels.py -v`
Expected: build exits 0; test PASSes — clean labels present, raw folder-name strings absent.

- [ ] **Step 8: Commit**

```bash
git add mkdocs.yml requirements.txt .pages index.md tests/test_nav_labels.py
git commit -m "docs-site: top-level nav via awesome-pages, clean section titles"
```

---

### Task 4: Reading experience — theme features, palette toggle, Mermaid diagrams

**Files:**
- Modify: `mkdocs.yml`
- Create: `tests/test_mermaid_rendering.py`

**Interfaces:**
- Consumes: `mkdocs.yml` from Task 3.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mermaid_rendering.py
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mermaid_fence_renders_as_mermaid_div(tmp_path):
    (tmp_path / "index.md").write_text(
        textwrap.dedent("""\
        # Fixture

        ```mermaid
        flowchart LR
            A --> B
        ```
        """)
    )
    # Reuse the real project's markdown_extensions/theme config as-is;
    # docs_dir: . resolves relative to cwd, which is set to tmp_path below.
    mkdocs_yml = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    (tmp_path / "mkdocs.yml").write_text(mkdocs_yml)

    site_dir = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--site-dir", str(site_dir)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert 'class="mermaid"' in html
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/test_mermaid_rendering.py -v`
Expected: FAIL — `class="mermaid"` not present; the fenced block currently renders as a plain code block because `pymdownx.superfences`'s mermaid custom fence isn't configured yet.

- [ ] **Step 3: Add markdown extensions and theme features to `mkdocs.yml`**

```yaml
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - toc.follow
    - content.code.copy
    - search.suggest
    - search.highlight
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.tabbed:
      alternate_style: true
  - tables
  - toc:
      permalink: true
```

- [ ] **Step 4: Run the test again, verify it passes**

Run: `pytest tests/test_mermaid_rendering.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing test suite to check nothing regressed**

Run: `pytest -v`
Expected: all tests from Tasks 2, 3, and 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add mkdocs.yml tests/test_mermaid_rendering.py
git commit -m "docs-site: Material reading features, dark/light toggle, Mermaid diagrams"
```

---

### Task 5: Landing page

**Files:**
- Modify: `index.md`

**Interfaces:**
- Consumes: content from `01-overview/executive-overview.md` (read, not duplicated verbatim — summarized with links).

- [ ] **Step 1: Read the current executive overview**

Run: `cat "01-overview/executive-overview.md"` (or open it) to pull the real current summary paragraph(s) and confirm the exact heading text to link to.

- [ ] **Step 2: Replace the placeholder `index.md` with real landing content**

Write `index.md` with: a short (2-4 sentence) summary of what Unifolio is and what this site covers, pulled from the executive overview's own wording (not invented), followed by quick links. Example shape — adapt the summary paragraph to match the real current text found in Step 1:

```markdown
# Unifolio Internal Documentation

This is the internal documentation site for Unifolio — the delivery
journey, decision records, investigations, current architecture, and
supporting evidence, built incrementally as the product is built rather
than written after the fact.

Read the [executive overview](01-overview/executive-overview.md) for the
full front-door summary, or jump straight in:

- [Current status](01-overview/current-status.md) — living snapshot
- [Journey](02-journey/00-index.md) — the delivery narrative, stage by stage
- [Decisions](03-decisions/decisions-log.md) — what was decided and why
- [Architecture](06-architecture/00-index.md) — how the system works today
- [Risks & Debt](07-risks-and-debt.md) — known open items
```

- [ ] **Step 3: Build and manually check the homepage**

Run: `mkdocs build && python3 -m http.server -d site 8000` then open `http://localhost:8000/` in a browser.
Expected: real landing content shows (not the "coming in a later task" placeholder), all five quick links are clickable and land on the correct pages. Stop the server (Ctrl+C) once confirmed.

- [ ] **Step 4: Run the full test suite, verify nothing regressed**

Run: `pytest -v`
Expected: all PASS (Task 3's `test_nav_labels.py` also confirms `index.md` builds correctly as part of its own check).

- [ ] **Step 5: Commit**

```bash
git add index.md
git commit -m "docs-site: real landing page from executive overview"
```

---

### Task 6: Evidence folder — auto-generated per-folder index pages

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/evidence_index_lib.py`
- Create: `scripts/gen_evidence_index.py`
- Create: `tests/test_evidence_index_lib.py`
- Create: `tests/test_evidence_build_integration.py`
- Modify: `mkdocs.yml`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `build_index_content(rel_dir: str, filenames: list[str]) -> str` and `iter_evidence_dirs(evidence_root: str) -> Iterator[tuple[str, str, list[str]]]` in `scripts/evidence_index_lib.py`, consumed by `scripts/gen_evidence_index.py` (the mkdocs-gen-files entry point, not imported by tests).

- [ ] **Step 1: Write the failing unit tests for the pure logic**

```python
# tests/test_evidence_index_lib.py
from scripts.evidence_index_lib import build_index_content, iter_evidence_dirs


def test_top_level_evidence_title():
    content = build_index_content(".", ["report.pdf", "notes.md"])
    assert content.startswith("# Evidence\n")
    assert "- [notes.md](notes.md)" in content
    assert "- [report.pdf](report.pdf)" in content


def test_nested_dir_title_uses_readable_path():
    content = build_index_content("documents/specs", ["design.md"])
    assert content.startswith("# documents / specs\n")


def test_files_are_alphabetically_sorted():
    content = build_index_content(".", ["zeta.png", "alpha.png"])
    lines = content.splitlines()
    assert lines.index("- [alpha.png](alpha.png)") < lines.index("- [zeta.png](zeta.png)")


def test_iter_evidence_dirs_skips_empty_dirs(tmp_path):
    root = tmp_path / "evidence"
    (root / "empty").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "file.md").write_text("hello")
    results = list(iter_evidence_dirs(str(root)))
    rel_dirs = [rel for _, rel, _ in results]
    assert "docs" in rel_dirs
    assert "empty" not in rel_dirs


def test_iter_evidence_dirs_ignores_existing_index(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir(parents=True)
    (root / "index.md").write_text("old")
    results = list(iter_evidence_dirs(str(root)))
    assert results == []
```

- [ ] **Step 2: Create empty `scripts/__init__.py`**

```python
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `pytest tests/test_evidence_index_lib.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.evidence_index_lib'`

- [ ] **Step 4: Implement `scripts/evidence_index_lib.py`**

```python
import os


def build_index_content(rel_dir, filenames):
    title = "Evidence" if rel_dir == "." else rel_dir.replace("/", " / ")
    lines = [f"# {title}", ""]
    for name in sorted(filenames):
        lines.append(f"- [{name}]({name})")
    return "\n".join(lines) + "\n"


def iter_evidence_dirs(evidence_root):
    for dirpath, dirnames, filenames in os.walk(evidence_root):
        dirnames.sort()
        real_files = [f for f in filenames if f != "index.md"]
        if not real_files:
            continue
        rel_dir = os.path.relpath(dirpath, evidence_root).replace(os.sep, "/")
        yield dirpath, rel_dir, real_files
```

- [ ] **Step 5: Run the tests again, verify they pass**

Run: `pytest tests/test_evidence_index_lib.py -v`
Expected: PASS

- [ ] **Step 6: Implement the mkdocs-gen-files entry point**

```python
# scripts/gen_evidence_index.py
import os
import mkdocs_gen_files

from scripts.evidence_index_lib import build_index_content, iter_evidence_dirs

EVIDENCE_ROOT = "08-evidence"

for dirpath, rel_dir, real_files in iter_evidence_dirs(EVIDENCE_ROOT):
    content = build_index_content(rel_dir, real_files)
    with mkdocs_gen_files.open(os.path.join(dirpath, "index.md"), "w") as f:
        f.write(content)
```

- [ ] **Step 7: Add `mkdocs-gen-files` to `requirements.txt`**

```
mkdocs-material
pytest
mkdocs-awesome-pages-plugin
mkdocs-gen-files
```

Run: `pip install -r requirements.txt`

- [ ] **Step 8: Wire the plugin into `mkdocs.yml`**

Add to the existing `plugins:` list:

```yaml
plugins:
  - search
  - awesome-pages
  - gen-files:
      scripts:
        - scripts/gen_evidence_index.py
```

- [ ] **Step 9: Write the failing integration test against a known real evidence file**

```python
# tests/test_evidence_build_integration.py
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWN_EVIDENCE_FILE = "08-evidence/documents/investigations/2026-09-23-schema-and-user-journey-review.pdf"
KNOWN_EVIDENCE_DIR_INDEX = "site/08-evidence/documents/investigations/index.html"


def test_known_evidence_file_and_generated_index_are_published(tmp_path):
    site_dir = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--site-dir", str(site_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    assert (site_dir / "08-evidence/documents/investigations" /
            "2026-09-23-schema-and-user-journey-review.pdf").exists()
    assert (site_dir / "08-evidence/documents/investigations" / "index.html").exists()
```

- [ ] **Step 10: Run it, verify it fails, then re-run after confirming the plugin actually runs**

Run: `pytest tests/test_evidence_build_integration.py -v`
Expected: passes only once Steps 6-8 above are in place — if it fails, check `mkdocs build` output directly for a `gen-files` plugin error first.

- [ ] **Step 11: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every task so far PASS.

- [ ] **Step 12: Commit**

```bash
git add scripts/ mkdocs.yml requirements.txt tests/test_evidence_index_lib.py tests/test_evidence_build_integration.py
git commit -m "docs-site: auto-generate evidence folder index pages"
```

---

### Task 7: Strict build as the safety net — prove it actually catches broken links

**Files:**
- Create: `tests/test_strict_build_catches_broken_links.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (uses isolated fixtures, not the real vault content).
- Produces: the confirmed `mkdocs build --strict` invocation that Task 9's `vercel.json` build command uses.

- [ ] **Step 1: Write the test**

```python
# tests/test_strict_build_catches_broken_links.py
import subprocess
import sys
import textwrap


def run_build(tmp_path, link_target):
    (tmp_path / "index.md").write_text(
        textwrap.dedent(f"""\
        # Home

        [a link]({link_target})
        """)
    )
    (tmp_path / "other.md").write_text("# Other\n")
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: fixture\ndocs_dir: .\nsite_dir: site\n"
    )
    return subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_strict_mode_fails_on_broken_internal_link(tmp_path):
    result = run_build(tmp_path, "does-not-exist.md")
    assert result.returncode != 0


def test_strict_mode_passes_on_valid_internal_link(tmp_path):
    result = run_build(tmp_path, "other.md")
    assert result.returncode == 0
```

- [ ] **Step 2: Run it, verify both pass immediately**

Run: `pytest tests/test_strict_build_catches_broken_links.py -v`
Expected: PASS — this confirms MkDocs' own `--strict` flag behaves as required; no application code needed for this task, only the regression test proving the safety net that Tasks 8-9 depend on actually works.

- [ ] **Step 3: Confirm the real vault currently builds clean under strict mode too**

Run: `mkdocs build --strict` (from repo root)
Expected: exits 0. If it fails, note the reported broken link(s) — fixing pre-existing broken links in vault content is out of scope for this plan and should be flagged to the user rather than silently patched.

- [ ] **Step 4: Commit**

```bash
git add tests/test_strict_build_catches_broken_links.py
git commit -m "docs-site: regression test proving --strict catches broken links"
```

---

### Task 8: Shared-password Edge Middleware

**Files:**
- Create: `middleware.js`
- Create: `middleware.test.mjs`
- Create: `package.json`

**Interfaces:**
- Produces: `middleware.js` default-exported `middleware(request)` function, matched by Vercel's platform-level Edge Middleware convention — consumed by Vercel itself at deploy time (Task 9), not imported by any other file in this repo.

- [ ] **Step 1: Write the failing test**

```javascript
// middleware.test.mjs
import assert from 'node:assert/strict';
import middleware from './middleware.js';

process.env.SITE_PASSWORD = 'correct-horse';

function makeRequest(authHeader) {
  const headers = new Headers();
  if (authHeader) headers.set('authorization', authHeader);
  return { headers };
}

const missing = middleware(makeRequest(undefined));
assert.equal(missing.status, 401);
assert.equal(missing.headers.get('WWW-Authenticate'), 'Basic realm="Internal Documentation"');

const wrong = 'Basic ' + btoa(':wrong-password');
const wrongResult = middleware(makeRequest(wrong));
assert.equal(wrongResult.status, 401);

const correct = 'Basic ' + btoa(':correct-horse');
const correctResult = middleware(makeRequest(correct));
assert.equal(correctResult, undefined);

console.log('middleware.test.mjs: all assertions passed');
```

- [ ] **Step 2: Run it, verify it fails**

Run: `node middleware.test.mjs`
Expected: FAIL — `Cannot find module './middleware.js'` (file doesn't exist yet).

- [ ] **Step 3: Implement `middleware.js`**

```javascript
export const config = {
  matcher: '/((?!favicon.ico).*)',
};

export default function middleware(request) {
  const expected = 'Basic ' + btoa(':' + process.env.SITE_PASSWORD);
  const provided = request.headers.get('authorization');

  if (provided === expected) {
    return;
  }

  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Internal Documentation"',
    },
  });
}
```

- [ ] **Step 4: Create `package.json`**

```json
{
  "name": "unifolio-internal-docs",
  "private": true,
  "type": "module"
}
```

- [ ] **Step 5: Run the test again, verify it passes**

Run: `node middleware.test.mjs`
Expected: prints `middleware.test.mjs: all assertions passed`, exits 0.

- [ ] **Step 6: Commit**

```bash
git add middleware.js middleware.test.mjs package.json
git commit -m "docs-site: shared-password Basic Auth Edge Middleware"
```

---

### Task 9: Vercel project config and deployment

**Files:**
- Create: `vercel.json`

**Interfaces:**
- Consumes: the `mkdocs build --strict` command confirmed in Task 7, the `site/` output directory from Task 1.

- [ ] **Step 1: Create `vercel.json`**

```json
{
  "buildCommand": "pip3 install -r requirements.txt && mkdocs build --strict",
  "outputDirectory": "site"
}
```

- [ ] **Step 2: Commit**

```bash
git add vercel.json
git commit -m "docs-site: Vercel build/output configuration"
```

- [ ] **Step 3: Manual — connect the repo in Vercel** (cannot be scripted from this repo; do this in the Vercel dashboard)

1. Vercel dashboard → New Project → import this GitHub repo.
2. Framework preset: "Other" (not Next.js — this confirms Vercel still runs `middleware.js` for non-framework static projects; if the dashboard doesn't expose a middleware option under "Other", note this and fall back to Vercel's documented steps for framework-agnostic Edge Middleware before continuing).
3. Build command / output directory: confirm they match `vercel.json` (Vercel should read them automatically).

- [ ] **Step 4: Manual — set the shared password**

In the Vercel project's Settings → Environment Variables, add `SITE_PASSWORD` with a real password value (not the test value `correct-horse` from Task 8's test). Apply to Production.

- [ ] **Step 5: Manual — add the custom domain**

1. Vercel project → Settings → Domains → add `internaldocumentation.unifolio.in`.
2. Vercel shows the required CNAME target — add that as a new CNAME record on the existing `unifolio.in` Route 53 hosted zone, host `internaldocumentation`.
3. Wait for DNS propagation and Vercel's automatic TLS certificate issuance to complete (Vercel's dashboard shows domain status as "Valid Configuration" when done).

- [ ] **Step 6: Trigger the first deploy**

Push this branch's commits to `main` (or the branch Vercel is configured to deploy from).
Expected: Vercel build log shows `pip3 install -r requirements.txt && mkdocs build --strict` succeeding, deploy status "Ready".

---

### Task 10: Post-deploy verification

**Files:** none — manual checklist against the live deployment.

- [ ] **Step 1: Confirm the password gate actually blocks access**

Open `https://internaldocumentation.unifolio.in/` in an incognito/private window.
Expected: the browser's native Basic Auth prompt appears before any page content is visible. Cancelling it must not reveal content.

- [ ] **Step 2: Confirm the password gate lets the right password through**

Enter the real `SITE_PASSWORD` value (any username) at the prompt.
Expected: the landing page from Task 5 loads.

- [ ] **Step 3: Confirm nav and search work**

Click through Overview → Journey → Decisions → Evidence in the sidebar; use the search box to search for a term known to appear in a structured record (e.g. a risk ID like `R-012`).
Expected: all nav sections load; search returns the matching page.

- [ ] **Step 4: Confirm a cited evidence file is reachable**

From any structured record that cites `08-evidence/...`, click through to the Evidence tab and open the known PDF from Task 6 (`08-evidence/documents/investigations/2026-09-23-schema-and-user-journey-review.pdf`).
Expected: it opens/downloads instead of 404ing.

- [ ] **Step 5: Confirm a Mermaid diagram renders**

Open a structured record known to contain a `mermaid` fenced block (e.g. `02-journey/00-index.md`, if it contains one — otherwise any page with one).
Expected: renders as a diagram, not a literal code block.

- [ ] **Step 6: Report back to the user**

Summarize pass/fail for Steps 1-5 and the live URL. Any failure here means returning to the relevant earlier task, not patching around it live.
