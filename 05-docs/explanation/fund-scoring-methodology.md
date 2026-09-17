# Why the fund score works the way it does

## What the score is

A single number per fund, computed by Unifolio from public data, saying how that fund has
performed against funds of its own kind — adjusted for how much risk it took and how much
it charges.

## Why it is modelled on Morningstar, and why it is not a copy of it

Morningstar's star rating is the most widely recognised fund-rating methodology in the
world. Its approach is public even though its exact formula is not, and the approach is
what matters:

- Rank funds **within their own category**, never across categories.
- Use a risk-adjusted return measure computed from **monthly returns**.
- **Weight downside variation more heavily than upside variation** — an application of
  expected-utility theory, not a symmetric risk measure like a plain Sharpe ratio. A fund
  that gets you the same return with fewer painful drops is genuinely better, and the
  maths should say so.
- Bucket into **percentile tiers within category**: top 10%, next 22.5%, middle 35%, next
  22.5%, bottom 10%.
- Require a **minimum return history** (three years) and a **minimum category size** (at
  least five funds) before rating anything at all.

The decisive property for Unifolio: **all of this is computable from NAV history alone.**
No portfolio holdings data is needed — which is exactly why it is buildable from public
sources.

Unifolio computes its own version rather than reproducing Morningstar's exact proprietary
formula, which is neither fully published nor free to use. The methodology is the
industry standard; the implementation is Unifolio's.

## The part that makes it Unifolio's own: cost

General-purpose star ratings do not directly incorporate what a fund charges. Unifolio
layers a **cost overlay** on top: once the risk-adjusted tier is set, a fund's TER
relative to its category average nudges the score — meaningfully below-average cost nudges
up, meaningfully above-average nudges down.

This is where the score stops being a copy of an existing agency's number and becomes a
genuine product decision. For an investor choosing between a Direct and a Regular plan of
the same fund — the single highest-leverage cost decision in Indian mutual funds — a
score that ignores cost is answering the wrong question.

The exact magnitude of the nudge is an implementation detail. The direction — reward low
cost — is unambiguous and does not need further sign-off.

## The portfolio-level number

A portfolio's score is an **AUM-weighted rollup** of its funds' scores, computed on read.
It is not stored. A stored rollup would go stale the moment a holding changed value, and
there is no per-user analytics table in the schema by design.

## Refusing to score is a feature

Three cases produce no score rather than a bad one:

- A fund with **less than three years** of history shows "insufficient history."
- A category with **fewer than five** rateable schemes shows "insufficient category
  data."
- A fund missing the inputs is **skipped by the monthly job**, which is not treated as a
  job failure.

Scoring a two-year-old fund against fifteen-year peers, or ranking a fund against two
others and calling it "top tier," would produce a number that looks authoritative and
means nothing. A financial product loses trust faster by being confidently wrong than by
saying "not enough data."

## Every score must be explainable

The scorer must be *explained*, not just displayed — a short "why this score" alongside
the number. A ranking an investor cannot interrogate is a black box asking to be trusted
on faith, which is precisely the posture the product is positioned against.

## Related

- [External data sources](../reference/external-data-sources.md) — where NAV, TER, and
  AAUM come from
- [Glossary](../../06-architecture/glossary.md) — TER, AAUM, XIRR, SEBI category
