# Unifolio Marketing Website — Creative Brief & Spec

**Status:** Approved direction, ready for handoff to Manus (manus.im).
**Build target:** Manus builds and hosts this site — it is *not* implemented in this repo.
**Audience:** Both self-directed retail MF investors and independent advisors/RIAs.
**Core differentiator this site sells:** effortless unified view (one CAS import replacing
scattered folios/apps/spreadsheets), not "free vs. paid" and not analytics depth — those
are supporting beats, not the lead.

This document is a creative brief, not a software design spec. Five inputs (founder
story, pricing model, trust-bar claim, product screenshots, GEO scope) couldn't be sourced
from the repo, so each is filled with a **creative placeholder** — marked `[PLACEHOLDER]`
inline and collected in §6. Confirm or replace every one before this goes live; don't hand
the placeholder copy to Manus as final.

---

## 1. Narrative arc

Fragmentation is the villain — not "lack of AI," not "lack of features." The investor's
actual current life: CAS statements scattered across RTAs, holdings split across broker
apps, a dying Excel sheet, and a paid tool (Mprofit) gatekeeping the one view that would
fix it. Unifolio's story, restated in some form on every page: **one import, one truth,
free.**

The hero must not open on an abstract "AI-agent" illustration (the visual cliché the
reference collection leans on). It opens on the actual mess — CAS PDFs, broker app icons,
a spreadsheet — visually resolving into the real product screenshot. That resolution *is*
the pitch; it should not be explained away in a caption.

## 2. Brand constraints (do not deviate)

- **Colors:** `#111111` (near-black), `#FCFCFC` (off-white), `#22C55E` (single green
  accent — the gauge-arc). No gradients. No blue/purple/teal, even though the visual
  references (Dribbble collection, `dribbble.com/siddharth-surve/collections/7919278-Unifolio`)
  use them — those are being borrowed for motion/polish quality only, not palette.
- **Type:** Manrope for headings/subheadings, DM Sans for body/accents/taglines/subtext.
- **Mark:** the gauge-arc in the logo is a reusable motif (see §4), not just a logotype
  detail.
- **No AI-chat framing.** Unifolio is a tracking/analytics product, not a conversational
  AI assistant — avoid chat-bubble UI, avatar illustrations, or "ask AI" framing anywhere
  on the site, even though most of the reference collection is built around that trope.

## 3. Page-by-page

### Home
Hero: scroll-triggered sequence where scattered CAS PDFs/broker icons/spreadsheet cells
converge into the real unified-dashboard screenshot, staged in a tilted 3D frame. Tagline
plays on "uni-" in Unifolio. Below the hero, in order:
1. A before/after scroll narrative (not a features grid) — literalizes the fragmentation
   story.
2. A trust bar. `[PLACEHOLDER]` copy: *"Works with your CAS from every AMC — powered by
   MFCentral"* (the repo's actual CAS ingestion is built against the MFCentral API, per
   `Docs/749204247-MFCentral-API-Integration-Document-CAS-v2-2-1-2.txt`, so this is
   grounded rather than invented — but it still needs a marketing/legal check before
   launch, and any AMC-count claim like "44+ AMCs" needs a real number substituted in).
   Don't source individual RTA logos (CAMS/KFintech) for this bar unless confirmed
   accurate — lead with the MFCentral claim instead.
3. A 3-beat feature teaser (Import / See / Understand) linking to Features.
4. A short free-vs-Mprofit teaser linking to Pricing.
5. Newsletter signup band (see below), near the footer.

Clicking the logo returns to Home from anywhere on the site — standard behavior, stated
explicitly here since it was called out as a requirement.

### Features
Structured as the product's actual flow, not an icon grid: **Import → See → Understand →
Track.** Each beat is one real screenshot or short demo clip with a literal, specific
mechanism claim ("one CAS upload parses every AMC statement automatically" — not "smart
parsing" or other vague AI-adjacent copy). No real screenshot assets exist in this repo
yet (`[PLACEHOLDER]`): until they're supplied, have Manus mock each screen's layout from
the actual PRDs rather than inventing generic dashboard art —
`Docs/PRDs/PRD-02-Signup-Onboarding.md` for Import, `Docs/PRD-03-Main-Dashboard.md` for
See, `Docs/PRD-04-MF-Analytics-Dashboard.md` for Understand. Swap in real screenshots
before launch; placeholder mockups should not ship as final. Include the proprietary scoring methodology
(`Docs/Scorer-Methodology-Unifolio.md`) as a named differentiator — competitors don't have
this, and it should be presented as a specific, explainable method, not a black box.

A subtle "For investors / For advisors" toggle at the top reframes emphasis for the dual
audience (e.g. advisors care about multi-client/household aggregation, retail investors
care about personal-portfolio clarity) without duplicating the whole page into two copies.

### Pricing
A direct, sourced comparison table against Mprofit, pulled from the existing competitor
analysis (`Docs/Competitor Analysis/`) — real, verifiable claims only, nothing fabricated.
`[PLACEHOLDER]` structure, chosen to match this repo's own "free-core" framing
(`CLAUDE.md`: "a genuinely superior, free-core alternative to Mprofit"): single-column
page, **"Free. Forever. No card required."** as the headline, with a soft-teased,
greyed-out "Pro — coming soon" row (household-level aggregation for advisors, extended
history) so the page doesn't foreclose a future paid tier. Replace with a real two-tier
comparison if a paid tier is actually confirmed and priced.

### About Us
Tells the same fragmentation story from the founders' side — why this got built, who it's
for, what was underserved between expensive paid tools and messy spreadsheets.
`[PLACEHOLDER]` narrative (replace names/years/background before use): *"Unifolio started
when `[Founder Name]`, tracking a family's mutual funds across `[N]` AMCs by hand in
`[Year]`, couldn't get a straight answer to 'are we actually doing well?' out of a
spreadsheet or a paid tool that made the same question cost a subscription. `[Co-founder
Name]`, coming from `[background — e.g. product/engineering at a fintech]`, joined to
build the version that should have existed already: free, and honest about the number
behind the number."*

### Open web app / Download mobile app
Not a standalone page — a persistent, sticky-header CTA pair present on every page. The
mobile button OS-detects the visitor's device and routes to the Play Store or App Store
accordingly; the web button opens the live app.

### Newsletter
A section/band on Home plus the footer, not a standalone page. Framed around portfolio/
market insight tied to the analytics angle ("data you won't find in a monthly Mprofit
report"), not generic "subscribe for updates" copy.

### Contact Us (signup funnel)
Functions as a funnel, not a plain contact form:
1. A qualifying step first — "Investor" vs. "Advisor."
2. Investor path routes to **Start Free** (web app signup).
3. Advisor path routes to **Book a Demo**.
4. A plain contact form remains only as the fallback, for press/partnership inquiries.

## 4. Motion & visual language

- Carry the in-app milestone pop/glow animations (already built into the product) into
  the marketing site instead of inventing new motion from scratch — this is a continuity
  move a generic AI-built site can't replicate, since it has no real product to draw from.
- The logo's gauge-arc recurs as a transition device — an arc-sweep reveal between major
  sections.
- Typographic contrast: Manrope large/bold for narrative statements, DM Sans quiet for
  supporting copy.
- Explicitly avoid: stock photography of people at laptops, gradient-blob backgrounds,
  chat-bubble UI, generic 3-icon feature grids with no connection to the actual product,
  and placeholder/fake "trusted by" logo walls.
- Keep motion light enough not to regress Core Web Vitals (LCP/CLS) — see §5.

## 5. SEO / AEO / GEO

**SEO:** keyword targets anchored to real intent — "Mprofit alternative," "free mutual
fund tracker India," "CAS import tool," "XIRR calculator," "mutual fund portfolio
analytics." Per-page metadata, `SoftwareApplication` / `FAQPage` / `Organization` schema.org
markup, sitemap.xml, OG/Twitter card images per page.

**AEO/GEO (answer-engine / generative-engine optimization — ChatGPT, Perplexity, Google
AI Overviews):** declarative, consistently-worded entity statements repeated verbatim
across Home and About (e.g. "Unifolio is a free mutual fund portfolio tracker for India")
so answer/generative engines converge on one canonical description of the product. An FAQ
section phrased as real searched questions ("what is the best free alternative to
Mprofit," "how do I import a CAS statement automatically"). An `llms.txt` file at the site
root.

`[PLACEHOLDER]` resolution: "GEO" was ambiguous (generative-engine vs. geographic
optimization). Given both readings are cheap to build and plausible for an India-only
product, this draft does **both** — the generative-engine treatment above, plus, on top
of it: `hreflang="en-IN"`, INR currency in schema.org markup, and India-specific
structured data (e.g. `addressCountry: IN` in `Organization` schema). Confirm this scope
is right before Manus builds it — drop the geographic layer if "GEO" was only ever meant
as generative-engine optimization.

## 6. Placeholder content used in this draft (confirm or replace before launch)

Five inputs couldn't be sourced from the repo. Each was given a creative placeholder
inline (marked `[PLACEHOLDER]` at each location above) so the brief is complete enough to
hand to Manus now — but none of these should reach a live site unconfirmed:

1. **Founder/team bios** (About Us, §3) — placeholder narrative with bracketed
   `[Founder Name]` / `[Year]` / `[background]` fields. Replace with the real story.
2. **Pricing model** (Pricing, §3) — placeholder assumes free-core forever with a
   greyed-out "Pro — coming soon" tease. Replace with a real two-tier table if a paid tier
   is actually planned and priced.
3. **RTA/AMC trust-bar claim** (Home, §3) — placeholder leads with "powered by MFCentral"
   (grounded in this repo's actual CAS integration), not specific RTA logos. Needs a
   marketing/legal check and a real AMC-count before launch.
4. **Product screenshots** (Features, §3) — none exist in the repo yet. Placeholder
   directs Manus to mock each screen from the cited PRDs rather than inventing generic
   dashboard art. Replace with real screenshots/recordings before launch.
5. **SEO/AEO/GEO scope** (§5) — placeholder resolves "GEO" as both generative-engine
   optimization and India geographic targeting. Confirm or narrow before Manus builds it.
