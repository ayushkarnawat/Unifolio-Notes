# The marketing website goes to a second external agent

## For stakeholders

On 31 August a creative brief for Unifolio's public marketing website was
approved and handed to Manus, an external build-and-host service — the site is
deliberately not part of the product repository. The brief is unusually
disciplined about what it does not know: five inputs could not be sourced from
the repository at all (founder story, pricing model, a trust-bar claim,
product screenshots, and what "GEO" was meant to mean), and each is marked as
a placeholder that must be confirmed before launch rather than quietly
invented. One of those placeholders contains a factual claim about how
Unifolio imports statements that **contradicts how the product actually
works**, and it is the kind of claim that would be repeated by press and
answer engines if it shipped. That is the item needing attention.

## Technical detail

### Intended outcome

A public marketing site selling one differentiator — an effortless unified
view from a single statement import — to both self-directed investors and
independent advisors.

### What actually happened

The brief fixes the narrative (fragmentation is the villain; one import, one
truth, free) and the brand constraints hard: near-black, off-white and a
single green accent, no gradients, no blue/purple/teal, Manrope for headings
and DM Sans for body, the logo's gauge arc reused as a recurring motif and a
section-transition device. It bans AI-chat framing outright — no chat bubbles,
no avatars, no "ask AI" — on the grounds that Unifolio is a tracking and
analytics product, and notes that most of the visual reference collection it
was given is built around exactly that trope.

Page structure: Home opens on a scroll-triggered sequence in which scattered
statements, broker icons and spreadsheet cells converge into a real product
screenshot — the same "scattered becoming one clear picture" story the
in-product auth and mobile visuals tell. Features is structured as the
product's actual flow, Import → See → Understand → Track, with the proprietary
scoring methodology named as a differentiator and presented as explainable
rather than as a black box. Pricing leads with "Free. Forever. No card
required." plus a greyed-out "Pro — coming soon" row so a future paid tier is
not foreclosed. A sticky web-app / mobile-app call-to-action pair appears on
every page. Contact is built as a qualifying funnel — investors routed to sign
up, advisors routed to book a demo, with a plain form kept only as a fallback.

Search strategy covers conventional SEO plus answer-engine and
generative-engine optimisation: consistently-worded entity statements repeated
verbatim so answer engines converge on one description, an FAQ phrased as real
searched questions, and an `llms.txt` at the site root. The brief resolves an
ambiguity in its instructions by doing both readings of "GEO" — generative
engine and geographic — adding India-specific locale and currency markup, and
asks for that scope to be confirmed.

Motion reuses the in-product milestone animations rather than inventing new
ones, on the reasoning that continuity with a real product is something a
generically-built site cannot replicate.

### Deviation — decision or response taken

**A factual contradiction in the trust-bar placeholder.** The placeholder copy
is "Works with your CAS from every AMC — powered by MFCentral", justified in
the brief on the grounds that the repository's CAS ingestion is built against
the MFCentral API. That is not what this vault records.
`05-docs/explanation/why-we-parse-cas-pdfs.md` documents user-uploaded CAS PDFs
parsed with `casparser`, and this same batch's own Phase 2 research costs
MFCentral and Account Aggregator access as a future, regulator-gated phase —
consistent with the vault's existing "deferred by decision" entry for MFCentral
OTP/API import. The brief does ask for a marketing and legal check before
launch, which is the right instinct, but the justification for the claim is
itself wrong. Recorded as R-046; not resolved here.

**A second external agent.** Manus is the second non-team coding agent to
receive work, after Google Antigravity. R-029 already records that ADR-011's
orchestration workflow says nothing about external agents; this widens the gap
to a second vendor, a different repository and a public-facing surface.
Recorded as R-048.

### Result

Approved direction, handed off. Five placeholders outstanding, one of them
carrying a factual error.

### Related

- R-046 — the MFCentral trust-bar claim contradicts documented CAS ingestion
- R-047 — five unresolved placeholders in the marketing brief
- R-048 — Manus is a second external agent outside ADR-011's scope
- R-029 — external coding agents are not covered by any workflow
- `05-docs/explanation/why-we-parse-cas-pdfs.md`
- Evidence: `08-evidence/documents/specs/2026-08-31-marketing-website-design.md`
